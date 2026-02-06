from typing import Dict, List, Optional
from langchain_core.tools import BaseTool, tool
from gmail_tools import (
    fetch_emails_tool,
    send_email_tool,
    check_calendar_tool,
    schedule_meeting_tool
)

# --- Define Missing Simple Tools ---

@tool
def Done() -> str:
    """
    Use this tool when you have completed the task (e.g., sent the email).
    It signals that no further actions are needed.
    """
    return "Task Marked as Complete."

@tool
def Question(question: str) -> str:
    """
    Use this tool to ask the user a clarifying question if you are missing information.
    """
    return f"Asking User: {question}"

# --- Tool Loader Functions ---

def get_tools(tool_names: Optional[List[str]] = None, include_gmail: bool = True) -> List[BaseTool]:
    """Get specified tools."""
    
    # Map of all available tools
    all_tools = {
        "fetch_emails_tool": fetch_emails_tool,
        "send_email_tool": send_email_tool,
        "check_calendar_tool": check_calendar_tool,
        "schedule_meeting_tool": schedule_meeting_tool,
        "Done": Done,
        "Question": Question
    }
    
    if tool_names is None:
        return list(all_tools.values())
    
    # Return only the requested tools
    return [all_tools[name] for name in tool_names if name in all_tools]

def get_tools_by_name(tools: Optional[List[BaseTool]] = None) -> Dict[str, BaseTool]:
    """Get a dictionary of tools mapped by name."""
    if tools is None:
        tools = get_tools()
    
    return {tool.name: tool for tool in tools}