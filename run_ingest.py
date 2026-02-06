"""
Email Ingestion Script for LangGraph Email Assistant
Fetches emails from Gmail and sends them to the agent for processing.
"""

import uuid
import requests
import os
from dotenv import load_dotenv
from gmail_tools import fetch_group_emails

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:2024")
ASSISTANT_ID = "agent"  # Must match the key in langgraph.json
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "me")  # Your email address
MINUTES_SINCE = int(os.getenv("MINUTES_SINCE", "60"))  # How far back to check
# ---------------------

def ingest_emails():
    """
    Fetch unread emails and send them to the agent for processing.
    """
    print("=" * 60)
    print("🔄 Email Ingestion Script Starting...")
    print(f"📧 Checking emails for: {EMAIL_ADDRESS}")
    print(f"⏰ Looking back: {MINUTES_SINCE} minutes")
    print("=" * 60)
    
    # Fetch emails (returns a generator)
    email_generator = fetch_group_emails(
        email_address=EMAIL_ADDRESS, 
        minutes_since=MINUTES_SINCE, 
        include_read=False  # Only unread emails
    )
    
    # Process emails one at a time
    processed_count = 0
    skipped_count = 0
    
    for email in email_generator:
        # Skip spam/delivery notifications
        spam_keywords = ["Delivery Status", "Failure", "Undelivered", "Mail Delivery"]
        if any(keyword in email.get('subject', '') for keyword in spam_keywords):
            print(f"⚠️  Skipping Spam: {email['subject']}")
            skipped_count += 1
            continue
        
        print(f"\n{'='*60}")
        print(f"📧 Processing Email #{processed_count + 1}")
        print(f"   Subject: {email['subject']}")
        print(f"   From: {email['from_email']}")
        print(f"   ID: {email['id']}")
        print(f"{'='*60}")
        
        # Send to agent
        success = send_to_agent(email)
        
        if success:
            processed_count += 1
        else:
            skipped_count += 1
        
        # Optional: Process only one email at a time
        # Uncomment the next line to process just the first email
        # break
    
    # Summary
    print(f"\n{'='*60}")
    print(f"✅ Processing Complete!")
    print(f"   Processed: {processed_count} emails")
    print(f"   Skipped: {skipped_count} emails")
    print(f"{'='*60}")
    
    if processed_count == 0 and skipped_count == 0:
        print("📭 No new unread emails found.")

def send_to_agent(email):
    """
    Send a single email to the agent for processing.
    
    Args:
        email: Dictionary containing email data
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # 1. Generate a unique thread ID
        thread_id = str(uuid.uuid4())
        
        # 2. Create the thread FIRST (this is required by LangGraph)
        print(f"   🔨 Creating Thread: {thread_id}...")
        thread_response = requests.post(
            f"{AGENT_URL}/threads", 
            json={"thread_id": thread_id, "metadata": {}},
            timeout=10
        )
        
        if thread_response.status_code not in [200, 201]:
            print(f"   ❌ Failed to create thread. Status: {thread_response.status_code}")
            print(f"   Response: {thread_response.text}")
            return False

        # 3. Prepare the payload for the agent
        payload = {
            "assistant_id": ASSISTANT_ID,
            "input": {
                "email_input": {
                    "id": email["id"],
                    "thread_id": email["thread_id"],  # Gmail thread ID
                    "from": email["from_email"],
                    "to": email["to_email"],
                    "subject": email["subject"],
                    "body": email["page_content"],
                    "send_time": email.get("send_time", "")
                }
            },
            "config": {
                "configurable": {
                    "thread_id": thread_id  # LangGraph thread ID
                }
            },
            "stream_mode": "events"  # Optional: get streaming updates
        }

        # 4. Send to the agent
        print(f"   🚀 Sending to Agent...")
        url = f"{AGENT_URL}/threads/{thread_id}/runs"
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code in [200, 201]:
            print(f"   ✅ SUCCESS! Email sent to Agent.")
            print(f"   👉 Thread ID: {thread_id}")
            print(f"   👉 View in Agent Inbox: http://localhost:2024")
            return True
        else:
            print(f"   ❌ Failed to run agent. Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Connection Error: Cannot connect to {AGENT_URL}")
        print(f"   👉 Is 'langgraph dev' running?")
        print(f"   👉 Try: langgraph dev")
        return False
    except requests.exceptions.Timeout:
        print(f"   ❌ Timeout Error: Request took too long")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected Error: {e}")
        return False

def test_connection():
    """Test if the LangGraph server is running."""
    try:
        response = requests.get(f"{AGENT_URL}/ok", timeout=5)
        if response.status_code == 200:
            print(f"✅ LangGraph server is running at {AGENT_URL}")
            return True
        else:
            print(f"⚠️  LangGraph server responded with status: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to LangGraph server at {AGENT_URL}")
        print(f"👉 Start the server with: langgraph dev")
        return False
    except Exception as e:
        print(f"❌ Error testing connection: {e}")
        return False

if __name__ == "__main__":
    # First, test if the server is running
    print("\n🔍 Testing LangGraph Server Connection...")
    if not test_connection():
        print("\n⚠️  Please start the LangGraph server first:")
        print("   $ langgraph dev")
        exit(1)
    
    print()
    
    # Run the email ingestion
    ingest_emails()