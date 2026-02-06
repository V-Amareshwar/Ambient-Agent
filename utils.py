from typing import List, Any
import json
import html2text

def format_email_markdown(subject, author, to, email_thread, email_id=None):
    """Format email details into a nicely formatted markdown string for display"""
    id_section = f"\n**ID**: {email_id}" if email_id else ""
    
    return f"""
**Subject**: {subject}
**From**: {author}
**To**: {to}{id_section}

{email_thread}

---
"""

def format_gmail_markdown(subject, author, to, email_thread, email_id=None):
    """Format Gmail email details into a nicely formatted markdown string for display."""
    id_section = f"\n**ID**: {email_id}" if email_id else ""
    
    # Check if email_thread is HTML content and convert to text if needed
    if email_thread and (email_thread.strip().startswith("<!DOCTYPE") or 
                          email_thread.strip().startswith("<html") or
                          "<body" in email_thread):
        try:
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0 
            email_thread = h.handle(email_thread)
        except Exception:
            pass # Fallback to raw text if conversion fails
    
    return f"""
**Subject**: {subject}
**From**: {author}
**To**: {to}{id_section}

{email_thread}

---
"""

def format_for_display(tool_call):
    """Format content for display in Agent Inbox"""
    display = ""
    
    # --- FIX: Updated to match 'send_email_tool' from tools.py ---
    if tool_call["name"] == "send_email_tool" or tool_call["name"] == "write_email":
        args = tool_call["args"]
        if "args" in args: args = args["args"]
            
        # Handle different parameter names (content vs body vs response_text)
        body_text = args.get("response_text") or args.get("body") or args.get("content") or ""
        
        display += f"""# Email Draft

**To**: {args.get("email_address") or args.get("to")}
**Subject**: {args.get("subject", "Re: Previous Email")}

{body_text}
"""
    # --- FIX: Updated to match 'schedule_meeting_tool' ---
    elif tool_call["name"] == "schedule_meeting_tool" or tool_call["name"] == "schedule_meeting":
        args = tool_call["args"]
        display += f"""# Calendar Invite

**Meeting**: {args.get("subject") or args.get("title")}
**Time**: {args.get("start_time") or "TBD"}
**Attendees**: {args.get("attendees", [])}
"""
    elif tool_call["name"] == "Question":
        # Question args might be a string or a dict
        q_text = tool_call["args"]
        if isinstance(q_text, dict):
            q_text = q_text.get("question") or q_text.get("content")
            
        display += f"""# Question for User

{q_text}
"""
    else:
        # Generic format
        display += f"""# Tool Call: {tool_call["name"]}

Arguments:"""
        if isinstance(tool_call["args"], dict):
            display += f"\n{json.dumps(tool_call['args'], indent=2)}\n"
        else:
            display += f"\n{tool_call['args']}\n"
    return display

def parse_gmail(email_input: dict) -> tuple:
    """Parse an email input dictionary for Gmail."""
    # Robust parsing handling missing keys
    author = email_input.get("from") or email_input.get("author", "Unknown")
    to = email_input.get("to", "Unknown")
    subject = email_input.get("subject", "No Subject")
    body = email_input.get("body") or email_input.get("email_thread") or ""
    id_val = email_input.get("id", "no_id")
    
    return (author, to, subject, body, id_val)