# 🤖 Ambient Agent - AI Email Assistant

An AI-powered email assistant that triages your Gmail inbox, drafts responses, and schedules meetings — with human approval at every step.

Built with **LangGraph**, **Groq LLaMA 3.3 70B**, and **Gmail/Calendar APIs**.

---

## ✨ Features

- 📧 **Smart Email Triage** — Classifies emails as respond, notify, or ignore
- 🤖 **AI-Drafted Replies** — Generates contextual email responses
- 📅 **Calendar Integration** — Checks availability & schedules meetings
- 👤 **Human-in-the-Loop** — Approve, edit, or reject before any action is taken
- 🧠 **Adaptive Memory** — Learns your preferences over time

---

## 🛠️ Tech Stack

- Python 3.10+
- LangGraph & LangChain
- Groq (LLaMA 3.3 70B)
- Gmail API & Google Calendar API
- Agent Inbox UI

---

## 📁 Project Structure

```
├── agent.py              # Main agent workflow
├── tools.py              # Tool definitions
├── gmail_tools.py        # Gmail API integration
├── schemas.py            # Pydantic schemas
├── prompts.py            # LLM prompts
├── prompt_templates.py   # Tool prompt templates
├── utils.py              # Utility functions
├── langgraph.json        # LangGraph config
├── requirements.txt      # Dependencies
└── .env                  # API keys (not committed)
```

---

## ⚙️ Setup

1. **Clone & install:**
```bash
git clone https://github.com/V-Amareshwar/Ambient-Agent.git
cd Ambient-Agent
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

2. **Set up Google OAuth:**
   - Enable Gmail & Calendar APIs in [Google Cloud Console](https://console.cloud.google.com/)
   - Download OAuth credentials → save as `credentials.json`

3. **Create `.env` file:**
```env
GROQ_API_KEY=your_groq_api_key
EMAIL_ADDRESS=your_email@gmail.com
```

4. **Run:**
```bash
langgraph dev
```

---

## 🔄 How It Works

```
New Email → Triage (classify) → Response Agent (draft reply)
                                       ↓
                              Human Approval (accept/edit/reject)
                                       ↓
                              Send Email / Schedule Meeting
```

| Tool | What it does | Needs Approval |
|------|-------------|:-:|
| `send_email_tool` | Sends email reply | ✅ |
| `schedule_meeting_tool` | Creates calendar event | ✅ |
| `check_calendar_tool` | Checks availability | ❌ |
| `Question` | Asks user for info | ✅ |
| `Done` | Marks task complete | ❌ |

---

## 📜 License

MIT License

---

**Built by [V-Amareshwar](https://github.com/V-Amareshwar)** | ⭐ Star if helpful!