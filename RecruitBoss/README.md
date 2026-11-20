# RecruitBoss

A local AI hiring desk. It runs on your PC with your own Ollama model. Nothing is sent to the cloud.

**Project page:** https://krchaurasiya.github.io/RecruitBoss/

The whole hiring process, from the job brief to a new joiner's checklist, is run by a **LangGraph multi-agent system**.

## The flow

| Step | What you do | Agent that works |
|---|---|---|
| 1. Hiring request | "Recruit people": answer dropdown questions | Requisition Agent |
| 2. Job requirements | Read the drafted job description, edit the brief any time, approve | Requisition Agent |
| 3. Sourcing | Draft posts for LinkedIn, careers page, job portal, referrals | Sourcing Agent |
| 4. Screening | Upload a zip of CSVs (resumes as .pdf, .docx, .txt work too). The data is checked, scored and ranked | Sourcing, Resume Intelligence, Matching |
| 5. Shortlisting | Tick the people you want, or reject with feedback (an email is drafted) | Shortlisting, Communication |
| 6. Interview planning | Rounds, questions and scorecard criteria are written for the role | Interview Planning Agent |
| 7. Scheduling | Free slots per interviewer, no double-booking, `.ics` files and invite text | Scheduling Agent |
| 8. Interview evaluation | Interviewers record scorecards. A final evaluation is produced | Evaluation Agent |
| 9. Hiring decision | You choose: approve, more interviews, or reject | Hiring Decision Gate |
| 10. Offer management | Offer draft, HR approval (or send back), mark as sent | Offer Management Agent |
| 11. Candidate response | Accepted: onboarding starts. Declined: next-best candidate is suggested | Offer Management, Onboarding |
| 12. Onboarding and close | Employee record, welcome email, checklist, analytics, close the role | Onboarding, Closure |

Click **Agents** (top right) to watch the supervisor hand work to each agent live.

## Run it in VS Code (Windows)

1. Install **Python 3.10+** (python.org, tick "Add to PATH") and make sure **Ollama** is running (`ollama list`).
2. Unzip, then in VS Code: **File → Open Folder…** and pick `RecruitBoss`.
3. Open **Terminal → New Terminal** (PowerShell) and run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

4. Open **http://127.0.0.1:8000**.

If PowerShell blocks the activate script, run `Set-ExecutionPolicy -Scope Process Bypass`, then activate again.
Shortcut: double-click `START_WINDOWS.bat`. Press **F5** in VS Code to debug (pick the `.venv` interpreter).

## The LangGraph multi-agent design (`backend/agents.py`)

```
START → Supervisor ⇄ [ Requisition | Sourcing | Resume Intelligence | Matching | Shortlisting | Interview Planning |
                       Scheduling | Evaluation | Hiring Decision Gate | Offer Management | Communication |
                       Onboarding | Closure ]  → END
```

- Every button click becomes an **event** (`screen`, `submit_scorecard`, `approve_offer`, ...).
- The **Supervisor** node turns the event into a plan, sends work to one agent at a time, and gets control back after each one.
  Agents can ask for **follow-ups**: approving a hire makes the Decision Gate add the Offer Management Agent;
  an accepted offer adds the Onboarding Agent; a rejection adds the Communication Agent.
- A run stops at the next **human gate**: JD approval, shortlist, interview feedback, hiring decision, offer approval, candidate reply.
- State is stored in SQLite (`recruitboss.db`), so every run is short and the app survives restarts.
- Agents that use the model fall back to templates or rules if Ollama is off, so the flow never blocks.
- `docs/agent_graph.mmd` is the graph exported by LangGraph (paste it into any Mermaid viewer). `GET /api/agents` returns it too.

## Choose the model

The model dropdown (top right, and on the upload screen) lists every model from `ollama list`.
Default is `qwen2.5:7b-instruct`; change `OLLAMA_MODEL` in `.env` to use another one.
On a laptop without a strong GPU use **Balanced** (the AI reads the top 10) or **Quick** (rules only).

## CSV and resume files

Zip any number of `.csv` files, plus optional resumes (`.pdf`, `.docx`, `.txt`). Column names match flexibly
(`Full Name`, `Candidate`, `Name`). A name column plus a skills or resume column is the minimum.
Scanned PDFs (images) can't be read. A second upload **adds** to the role, and anyone with a matching email is skipped.
Try `sample_data/sample_candidates.zip` first.

## How candidates are scored

- **Rules (100 points):** skills 55, experience 20, education 10, location 10, notice 5. The breakdown is shown for everyone.
- **AI reading:** your model reads the profile and writes a score, summary, strengths, gaps and what to ask. Final = 60% rules + 40% AI.
- **Interview evaluation:** the average of scorecard ratings decides the panel's lean (Hire, Hold, No hire). The model only writes the summary.
- Scores support decisions. People decide. The model is told not to consider protected traits.

## What it does not do

It is local on purpose, so it does **not** connect to: LinkedIn or job portals (it drafts the posts, you publish them),
Google Calendar or Outlook (it makes `.ics` files), email or SMS (it opens your mail app with the text filled in),
HRIS systems like Workday or BambooHR (it keeps a local employee record), vector databases or embeddings
(matching uses rules plus the LLM), or candidate availability and reminder messages.
Offer letters are templates filled with what you type: the model never invents pay or terms.

## Editing the front end (optional, Node 18+)

```powershell
cd frontend
npm install
npm run dev      # live reload on http://localhost:5173 (backend must be running on :8000)
npm run build    # writes the production files into backend/static
```

## Tests

```powershell
pip install pytest httpx reportlab
python -m pytest -q tests
```
`tests/mock_ollama.py` is a fake Ollama used to test the model paths without a GPU.
