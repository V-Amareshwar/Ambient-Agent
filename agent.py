import logging
from typing import Literal, Dict, Any, List
import uuid

from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, START, END
from langgraph.store.base import BaseStore
from langgraph.types import interrupt, Command
from langgraph.store.memory import InMemoryStore
from dotenv import load_dotenv
import os

# --- IMPORTS ---
from tools import get_tools, get_tools_by_name
from gmail_tools import mark_as_read
from prompt_templates import GMAIL_TOOLS_PROMPT 
from prompts import (
    triage_system_prompt, triage_user_prompt, agent_system_prompt_hitl_memory,
    default_triage_instructions, default_background, 
    default_response_preferences, default_cal_preferences, 
    MEMORY_UPDATE_INSTRUCTIONS, MEMORY_UPDATE_INSTRUCTIONS_REINFORCEMENT
)
from schemas import State, RouterSchema, StateInput, UserPreferences
from utils import parse_gmail, format_for_display, format_gmail_markdown

# --- SETUP ---
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

# Initialize Tools
tools = get_tools(["send_email_tool", "schedule_meeting_tool", "check_calendar_tool", "Question", "Done"], include_gmail=True)
tools_by_name = get_tools_by_name(tools)

# Initialize Models
llm = init_chat_model("groq:llama-3.3-70b-versatile", temperature=0.0)
llm_router = llm.with_structured_output(RouterSchema) 
llm_with_tools = llm.bind_tools(tools, tool_choice="any")

# Get User Email Default
USER_EMAIL = os.getenv("EMAIL_ADDRESS", "me")

# --- HELPERS ---
def get_memory(store: BaseStore, namespace: tuple, default_content=None):
    """Safely retrieve memory or return default."""
    try:
        user_preferences = store.get(namespace, "user_preferences")
        if user_preferences:
            return user_preferences.value
        store.put(namespace, "user_preferences", default_content)
        return default_content
    except Exception as e:
        logger.error(f"Memory Get Error: {e}")
        return default_content

def update_memory(store: BaseStore, namespace: tuple, messages: list):
    """Update user preferences in memory based on interactions."""
    try:
        user_preferences = store.get(namespace, "user_preferences")
        current_profile = user_preferences.value if user_preferences else ""
        
        llm_mem = init_chat_model("groq:llama-3.3-70b-versatile", temperature=0.0).with_structured_output(UserPreferences)
        result = llm_mem.invoke(
            [{"role": "system", "content": MEMORY_UPDATE_INSTRUCTIONS.format(current_profile=current_profile, namespace=namespace)}] + messages
        )
        store.put(namespace, "user_preferences", result.user_preferences)
    except Exception as e:
        logger.error(f"Memory Update Error: {e}")

def validate_and_fix_tool_args(tool_call, state):
    """
    The 'Mechanic' Function:
    Validates tool arguments and fills in missing required fields to prevent crashes.
    """
    # Create a copy to avoid modifying the original iterator immediately
    args = tool_call.get("args", {}).copy() if tool_call.get("args") else {}
    tool_name = tool_call.get("name")
    
    # 1. Fix send_email_tool
    if tool_name == "send_email_tool":
        # Ensure email_id exists
        if not args.get("email_id"):
            args["email_id"] = state["email_input"].get("id", "manual_test_id")
        
        # Ensure email_address exists (Sender)
        if not args.get("email_address"):
            args["email_address"] = state["email_input"].get("to", USER_EMAIL)
        
        # Ensure response_text exists
        if not args.get("response_text"):
            args["response_text"] = "Response text missing."
            
        # Ensure additional_recipients is a list
        if "additional_recipients" not in args or args["additional_recipients"] is None:
            args["additional_recipients"] = []

    # 2. Fix schedule_meeting_tool
    elif tool_name == "schedule_meeting_tool":
        if not args.get("organizer_email"):
            args["organizer_email"] = USER_EMAIL
        if "attendees" not in args or args["attendees"] is None:
            args["attendees"] = []

    # 3. General Sanitization (Fix None to empty strings/lists)
    for k, v in args.items():
        if v is None:
            if k.endswith('s') or "recipients" in k or "attendees" in k:
                args[k] = []
            else:
                args[k] = ""
    
    return args

# --- NODES ---

def triage_router(state: State, store: BaseStore) -> Command[Literal["triage_interrupt_handler", "response_agent", "__end__"]]:
    """Decides if the email needs a response, ignore, or notification."""
    email_input = state["email_input"]
    
    # Safety Defaults
    if "id" not in email_input: email_input["id"] = "manual_test_id"
    if "threadId" not in email_input: email_input["threadId"] = "manual_thread_id"
    if "to" not in email_input: email_input["to"] = "unknown@example.com"
    if "from" not in email_input and "author" not in email_input: email_input["from"] = "unknown@example.com"

    author, to, subject, email_thread, email_id = parse_gmail(email_input)
    user_prompt = triage_user_prompt.format(author=author, to=to, subject=subject, email_thread=email_thread)
    
    try:
        email_markdown = format_gmail_markdown(subject, author, to, email_thread, email_id)
    except Exception:
        email_markdown = f"Subject: {subject}\nFrom: {author}"

    triage_instructions = get_memory(store, ("email_assistant", "triage_preferences"), default_triage_instructions)
    system_prompt = triage_system_prompt.format(background=default_background, triage_instructions=triage_instructions)

    result = llm_router.invoke([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])
    classification = result.classification

    if classification == "respond":
        goto = "response_agent"
        update = {"classification_decision": classification, "messages": [{"role": "user", "content": f"Respond to the email: {email_markdown}"}]}
    elif classification == "ignore":
        goto = END
        update = {"classification_decision": classification}
    elif classification == "notify":
        goto = "triage_interrupt_handler"
        update = {"classification_decision": classification}
    else:
        goto = "response_agent" # Fallback
        update = {"classification_decision": "respond", "messages": [{"role": "user", "content": f"Respond to the email: {email_markdown}"}]}
    
    return Command(goto=goto, update=update)

def triage_interrupt_handler(state: State, store: BaseStore) -> Command[Literal["response_agent", "__end__"]]:
    """Interruption for Notify cases."""
    author, to, subject, email_thread, email_id = parse_gmail(state["email_input"])
    email_markdown = format_gmail_markdown(subject, author, to, email_thread, email_id)
    messages = [{"role": "user", "content": f"Email to notify user about: {email_markdown}"}]

    request = {
        "action_request": {"action": f"Email Assistant: {state['classification_decision']}", "args": {}},
        "config": {"allow_ignore": True, "allow_respond": True, "allow_edit": False, "allow_accept": False},
        "description": email_markdown,
    }
    
    response = interrupt([request])[0]

    if response["type"] == "response":
        messages.append({"role": "user", "content": f"User wants to reply. Feedback: {response['args']}"})
        goto = "response_agent"
        update_memory(store, ("email_assistant", "triage_preferences"), [{"role": "user", "content": "User decided to respond."}] + messages)
    elif response["type"] == "ignore":
        messages.append({"role": "user", "content": "User ignored the notification."})
        update_memory(store, ("email_assistant", "triage_preferences"), messages)
        goto = END
    else:
        goto = END

    return Command(goto=goto, update={"messages": messages})

def llm_call(state: State, store: BaseStore):
    """Main Agent Node to Generate Tool Calls."""
    cal_prefs = get_memory(store, ("email_assistant", "cal_preferences"), default_cal_preferences)
    resp_prefs = get_memory(store, ("email_assistant", "response_preferences"), default_response_preferences)
    
    return {
        "messages": [llm_with_tools.invoke(
            [{"role": "system", "content": agent_system_prompt_hitl_memory.format(
                tools_prompt=GMAIL_TOOLS_PROMPT, background=default_background,
                response_preferences=resp_prefs, cal_preferences=cal_prefs)}] + state["messages"]
        )]
    }

def interrupt_handler(state: State, store: BaseStore) -> Command[Literal["llm_call", "__end__"]]:
    """
    Handles Human-in-the-Loop for Tool Execution.
    Includes Smart Mode and Robust Sanitization.
    """
    result = []
    goto = "llm_call"
    
    last_message = state["messages"][-1]
    if not last_message.tool_calls:
        return Command(goto="llm_call", update={})

    for tool_call in last_message.tool_calls:
        tool_name = tool_call.get("name")
        # Generate ID if missing to prevent KeyError
        tool_id = tool_call.get("id", str(uuid.uuid4()))
        
        # 1. Skip Done Tool
        if tool_name == "Done":
            result.append({"role": "tool", "content": "Task Marked as Complete.", "tool_call_id": tool_id})
            continue

        # 2. Smart Mode: Auto-execute Calendar Check
        if tool_name == "check_calendar_tool":
            print(f"📅 Auto-executing {tool_name}...")
            try:
                # Use Validation Function here too
                safe_args = validate_and_fix_tool_args(tool_call, state)
                tool = tools_by_name[tool_name]
                observation = tool.invoke(safe_args)
            except Exception as e:
                observation = f"Error checking calendar: {str(e)}"
            result.append({"role": "tool", "content": observation, "tool_call_id": tool_id})
            continue

        # 3. Prepare Display Content
        try:
            email_input = state["email_input"]
            author, to, subject, email_thread, email_id = parse_gmail(email_input)
            original_email_markdown = format_gmail_markdown(subject, author, to, email_thread, email_id)
            tool_display = format_for_display(tool_call)
            description = original_email_markdown + tool_display
        except Exception as e:
            print(f"Formatting Warning: {e}")
            description = f"# Request\n\nAgent wants to use: {tool_name}\n\nArgs:\n{tool_call.get('args')}"

        # 4. Configure Buttons
        if tool_name == "Question":
            config = {"allow_ignore": True, "allow_respond": True, "allow_edit": False, "allow_accept": False}
        else:
            config = {"allow_ignore": True, "allow_respond": True, "allow_edit": True, "allow_accept": True}

        # 5. DATA SANITIZATION (The "Mechanic")
        # Fixes missing fields and None values
        safe_args = validate_and_fix_tool_args(tool_call, state)

        # Create Request for UI
        request = {
            "action_request": {"action": tool_name, "args": safe_args},
            "config": config,
            "description": description,
        }

        # 6. Trigger Interrupt (Wait for User)
        response = interrupt([request])[0]

        # 7. Process User Decision
        if response["type"] == "accept":
            print(f"✅ User Accepted tool: {tool_name}")
            
            # Simulation Check
            arg_email_id = safe_args.get("email_id", "")
            is_manual = "manual" in str(arg_email_id) or "test" in str(arg_email_id)

            if is_manual:
                print(f"✅ SIMULATION: Pretending to run {tool_name}")
                observation = f"Tool {tool_name} executed successfully (Simulated)."
            else:
                try:
                    tool = tools_by_name[tool_name]
                    # CRITICAL: Use the safe_args for execution
                    observation = tool.invoke(safe_args)
                except Exception as e:
                    logger.error(f"Tool Execution Failed: {e}")
                    observation = f"Error executing tool {tool_name}: {str(e)}"
            
            result.append({"role": "tool", "content": observation, "tool_call_id": tool_id})

        elif response["type"] == "edit":
            print(f"✏️ User Edited tool: {tool_name}")
            edited_args = response["args"]["args"]
            
            # Validate Edited Args
            # We create a fake tool_call structure to reuse the validator logic
            fake_tool_call = {"name": tool_name, "args": edited_args}
            safe_edited_args = validate_and_fix_tool_args(fake_tool_call, state)

            # Update the AI Message history
            ai_message = state["messages"][-1]
            updated_tool_calls = [tc for tc in ai_message.tool_calls if tc.get("id") != tool_id] + [
                {"type": "tool_call", "name": tool_name, "args": safe_edited_args, "id": tool_id}
            ]
            result.append(ai_message.model_copy(update={"tool_calls": updated_tool_calls}))

            # Execute with Edited Args
            arg_email_id = safe_edited_args.get("email_id", "")
            is_manual = "manual" in str(arg_email_id) or "test" in str(arg_email_id)

            if is_manual:
                observation = f"Tool {tool_name} executed successfully (Simulated)."
            else:
                try:
                    tool = tools_by_name[tool_name]
                    observation = tool.invoke(safe_edited_args)
                except Exception as e:
                    observation = f"Error executing tool {tool_name}: {str(e)}"

            result.append({"role": "tool", "content": observation, "tool_call_id": tool_id})
            
            # Update Memory
            if tool_name == "send_email_tool":
                update_memory(store, ("email_assistant", "response_preferences"), [{"role": "user", "content": "User edited response."}])

        elif response["type"] == "ignore":
            print(f"🚫 User Ignored tool: {tool_name}")
            result.append({"role": "tool", "content": "User ignored this draft.", "tool_call_id": tool_id})
            goto = END
            update_memory(store, ("email_assistant", "triage_preferences"), state["messages"] + result + [{"role": "user", "content": "User ignored the draft."}])

        elif response["type"] == "response":
            print(f"💬 User Feedback: {response['args']}")
            result.append({"role": "tool", "content": f"User feedback: {response['args']}", "tool_call_id": tool_id})
            if tool_name == "send_email_tool":
                update_memory(store, ("email_assistant", "response_preferences"), state["messages"] + result + [{"role": "user", "content": "User provided feedback."}])

    return Command(goto=goto, update={"messages": result})

def should_continue(state: State, store: BaseStore) -> Literal["interrupt_handler", "mark_as_read_node"]:
    """Route to tool handler, or end if Done tool called"""
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        for tool_call in last_message.tool_calls: 
            if tool_call["name"] == "Done": return "mark_as_read_node"
        return "interrupt_handler"
    return "interrupt_handler"

def mark_as_read_node(state: State):
    """Marks email as read after successful processing."""
    email_input = state["email_input"]
    email_id = email_input.get("id")
    if email_id and "manual" not in str(email_id) and "test" not in str(email_id):
        try: 
            mark_as_read(email_id)
            print(f"✅ Marked email {email_id} as read.")
        except Exception as e:
            print(f"⚠️ Could not mark as read: {e}")

# --- GRAPH BUILD ---
agent_builder = StateGraph(State)
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("interrupt_handler", interrupt_handler)
agent_builder.add_node("mark_as_read_node", mark_as_read_node)

agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    {
        "interrupt_handler": "interrupt_handler", 
        "mark_as_read_node": "mark_as_read_node"
    }
)
# This edge fixes the loop
agent_builder.add_edge("interrupt_handler", "llm_call")
agent_builder.add_edge("mark_as_read_node", END)

response_agent = agent_builder.compile()

# Overall Workflow
overall_workflow = (
    StateGraph(State, input=StateInput)
    .add_node(triage_router)
    .add_node(triage_interrupt_handler)
    .add_node("response_agent", response_agent)
    .add_node("mark_as_read_node", mark_as_read_node)
    .add_edge(START, "triage_router")
    .add_edge("mark_as_read_node", END)
)

memory_store = InMemoryStore()
email_assistant = overall_workflow.compile(store=memory_store)