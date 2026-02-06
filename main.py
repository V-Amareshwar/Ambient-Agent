"""
Main Runner for Official Agent v1
Fetches emails and wakes up the agent.
"""

import asyncio
from dotenv import load_dotenv
from agent import email_assistant
from gmail_tools import fetch_emails_tool

# Load env vars
load_dotenv()

async def main():
    print("🚀 Starting Official Agent v1...")
    
    # 1. Fetch Emails
    print("👀 Checking Inbox...")
    emails_text = fetch_emails_tool.invoke({"email_address": "me", "minutes_since": 60})
    
    if "No new emails found" in emails_text:
        print("💤 No new emails.")
        return

    # 2. Process each email found (You would parse the text here in a real app)
    # For now, we simulate passing the raw text to let the agent parse/triage
    # Note: In the real repo, run_ingest.py parses the JSON. 
    # Here is a simulated single run for demonstration:
    
    print(f"📧 Emails Found: {emails_text[:100]}...")
    
    # Mock input for the graph based on what fetch_emails returns
    # In a real loop, you'd iterate over the JSON from fetch_group_emails
    
    print("⚠️ To fully process, please use 'langgraph dev' which handles the async loop better.")

if __name__ == "__main__":
    asyncio.run(main())