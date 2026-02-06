"""
Gmail tools implementation module. 
This module formats the Gmail API functions into LangChain tools.
"""

import os
import sys
import base64
import email.utils
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Iterator
from pathlib import Path
from pydantic import Field, BaseModel
from langchain_core.tools import tool

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define paths for credentials and tokens
_ROOT = Path(__file__).parent.absolute()
_SECRETS_DIR = _ROOT

# We need to try importing the Gmail API libraries
# If they're not available, we'll use a mock implementation
try:
    import logging
    from googleapiclient.discovery import build
    from email.mime.text import MIMEText
    from datetime import timedelta
    from dateutil.parser import parse as parse_time
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Email content extraction function
    def extract_message_part(payload):
        """Extract content from a message part."""
        if payload.get("body", {}).get("data"):
            # Handle base64 encoded content
            data = payload["body"]["data"]
            decoded = base64.urlsafe_b64decode(data).decode("utf-8")
            return decoded
            
        # Handle multipart messages
        if payload.get("parts"):
            text_parts = []
            for part in payload["parts"]:
                # Recursively process parts
                content = extract_message_part(part)
                if content:
                    text_parts.append(content)
            return "\n".join(text_parts)
            
        return ""
    
    # Function to get credentials from token.json or environment variables
    def get_credentials(gmail_token=None, gmail_secret=None):
        token_path = _SECRETS_DIR / "token.json"
        token_data = None
        
        # Try to get token data from various sources
        if gmail_token:
            try:
                token_data = json.loads(gmail_token) if isinstance(gmail_token, str) else gmail_token
            except Exception as e:
                logger.warning(f"Could not parse provided gmail_token: {str(e)}")
                
        if token_data is None:
            env_token = os.getenv("GMAIL_TOKEN")
            if env_token:
                try:
                    token_data = json.loads(env_token)
                except Exception as e:
                    logger.warning(f"Could not parse GMAIL_TOKEN environment variable: {str(e)}")
        
        if token_data is None:
            if os.path.exists(token_path):
                try:
                    with open(token_path, "r") as f:
                        token_data = json.load(f)
                except Exception as e:
                    logger.warning(f"Could not load token from {token_path}: {str(e)}")
        
        if token_data is None:
            logger.error("Could not find valid token data in any location")
            return None
        
        try:
            from google.oauth2.credentials import Credentials
            
            # Create credentials object
            credentials = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/gmail.modify"])
            )
            return credentials
        except Exception as e:
            logger.error(f"Error creating credentials object: {str(e)}")
            return None
    
    GMAIL_API_AVAILABLE = True
    
except ImportError:
    GMAIL_API_AVAILABLE = False
    logger = logging.getLogger(__name__)

# Helper function
def fetch_group_emails(
    email_address: str,
    minutes_since: int = 30,
    gmail_token: Optional[str] = None,
    gmail_secret: Optional[str] = None,
    include_read: bool = False,
    skip_filters: bool = False,
) -> Iterator[Dict[str, Any]]:
    
    if not GMAIL_API_AVAILABLE:
        return

    try:
        creds = get_credentials(gmail_token, gmail_secret)
        if not creds:
            return
            
        service = build("gmail", "v1", credentials=creds)
        
        after = int((datetime.now() - timedelta(minutes=minutes_since)).timestamp())
        query = f"(to:{email_address} OR from:{email_address}) after:{after}"
        
        if not include_read:
            query += " is:unread"
            
        messages = []
        nextPageToken = None
        
        while True:
            results = service.users().messages().list(userId="me", q=query, pageToken=nextPageToken, maxResults=1).execute()
            if "messages" in results:
                messages.extend(results["messages"])
            nextPageToken = results.get("nextPageToken")
            if not nextPageToken:
                break

        for message in messages:
            try:
                msg = service.users().messages().get(userId="me", id=message["id"]).execute()
                payload = msg["payload"]
                headers = payload.get("headers", [])
                
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                from_email = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
                to_email = next((h["value"] for h in headers if h["name"] == "To"), "Unknown")
                date = next((h["value"] for h in headers if h["name"] == "Date"), "Unknown")
                
                body = extract_message_part(payload)
                
                yield {
                    "from_email": from_email,
                    "to_email": to_email,
                    "subject": subject,
                    "page_content": body,
                    "id": message["id"],
                    "thread_id": msg["threadId"],
                    "send_time": date,
                }
                    
            except Exception as e:
                logger.warning(f"Failed to process message {message['id']}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error accessing Gmail API: {str(e)}")

class FetchEmailsInput(BaseModel):
    email_address: str = Field(description="Email address to fetch emails for")
    minutes_since: int = Field(default=30, description="Only retrieve emails newer than this many minutes")

@tool(args_schema=FetchEmailsInput)
def fetch_emails_tool(email_address: str, minutes_since: int = 30) -> str:
    """Fetches recent emails from Gmail for the specified email address."""
    emails = list(fetch_group_emails(email_address, minutes_since))
    
    if not emails:
        return "No new emails found."
    
    result = f"Found {len(emails)} new emails:\n\n"
    for i, email in enumerate(emails, 1):
        result += f"{i}. From: {email['from_email']}\n"
        result += f"   To: {email['to_email']}\n"
        result += f"   Subject: {email['subject']}\n"
        result += f"   ID: {email['id']}\n"
        result += f"   Content: {email['page_content'][:200]}...\n\n"
    return result

class SendEmailInput(BaseModel):
    email_id: str = Field(description="Gmail message ID to reply to.")
    response_text: str = Field(description="Content of the reply")
    email_address: str = Field(description="Current user's email address")
    additional_recipients: Optional[List[str]] = Field(default=None, description="Optional additional recipients")

@tool(args_schema=SendEmailInput)
def send_email_tool(email_id: str, response_text: str, email_address: str, additional_recipients: Optional[List[str]] = None) -> str:
    """Send a reply to an existing email thread or create a new email in Gmail."""
    try:
        creds = get_credentials()
        service = build("gmail", "v1", credentials=creds)
        
        # Try to get thread ID if replying
        thread_id = None
        subject = "Response"
        original_from = "recipient@example.com"

        try:
            message = service.users().messages().get(userId="me", id=email_id).execute()
            thread_id = message["threadId"]
            headers = message["payload"]["headers"]
            subject = next(h["value"] for h in headers if h["name"] == "Subject")
            if not subject.startswith("Re:"): subject = f"Re: {subject}"
            original_from = next(h["value"] for h in headers if h["name"] == "From")
        except:
            pass

        msg = MIMEText(response_text)
        msg["to"] = original_from
        msg["from"] = email_address
        msg["subject"] = subject
        
        if additional_recipients:
            msg["cc"] = ", ".join(additional_recipients)
            
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        body = {"raw": raw}
        if thread_id: body["threadId"] = thread_id
            
        sent = service.users().messages().send(userId="me", body=body).execute()
        return f"Email reply sent successfully to message ID: {sent['id']}"
    except Exception as e:
        return f"Failed to send email: {str(e)}"

class CheckCalendarInput(BaseModel):
    dates: List[str] = Field(description="List of dates to check in DD-MM-YYYY format")

@tool(args_schema=CheckCalendarInput)
def check_calendar_tool(dates: List[str]) -> str:
    """Check Google Calendar for events on specified dates."""
    try:
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        result = "Calendar events:\n\n"
        
        for date_str in dates:
            day, month, year = date_str.split("-")
            start_time = f"{year}-{month}-{day}T00:00:00Z"
            end_time = f"{year}-{month}-{day}T23:59:59Z"
            
            events_result = service.events().list(calendarId="primary", timeMin=start_time, timeMax=end_time, singleEvents=True, orderBy="startTime").execute()
            events = events_result.get("items", [])
            
            result += f"Events for {date_str}:\n"
            if not events:
                result += "  No events found. Available all day.\n"
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                summary = event.get("summary", "No Title")
                result += f"  - {start}: {summary}\n"
        return result
    except Exception as e:
        return f"Failed to check calendar: {str(e)}"

class ScheduleMeetingInput(BaseModel):
    attendees: List[str] = Field(description="Email addresses of meeting attendees")
    title: str = Field(description="Meeting title")
    start_time: str = Field(description="Start time ISO format")
    end_time: str = Field(description="End time ISO format")
    organizer_email: str = Field(description="Organizer email")
    timezone: str = Field(default="America/Los_Angeles")

@tool(args_schema=ScheduleMeetingInput)
def schedule_meeting_tool(attendees: List[str], title: str, start_time: str, end_time: str, organizer_email: str, timezone: str = "America/Los_Angeles") -> str:
    """Schedule a meeting with Google Calendar and send invites."""
    try:
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        
        event = {
            "summary": title,
            "start": {"dateTime": start_time, "timeZone": timezone},
            "end": {"dateTime": end_time, "timeZone": timezone},
            "attendees": [{"email": email} for email in attendees],
            "organizer": {"email": organizer_email},
        }
        
        event = service.events().insert(calendarId="primary", body=event).execute()
        return f"Meeting '{title}' scheduled successfully: {event.get('htmlLink')}"
    except Exception as e:
        return f"Error scheduling meeting: {str(e)}"

def mark_as_read(message_id):
    """Marks a message as read in Gmail."""
    try:
        creds = get_credentials()
        service = build("gmail", "v1", credentials=creds)
        service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()
    except Exception as e:
        print(f"Failed to mark as read: {e}")