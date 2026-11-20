"""RecruitBoss API + static React app. Run: uvicorn backend.main:app --port 8000

Every action goes through the LangGraph supervisor in agents.py."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import PlainTextResponse, Response, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import agents, db, llm, scheduling  # noqa: E402

app = FastAPI(title="RecruitBoss")
db.init()
STATIC = Path(__file__).resolve().parent / "static"


# ---- models -------------------------------------------------------------
class Brief(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    department: str = "Engineering"
    seniority: str = "Mid-level"
    employment_type: str = "Full-time"
    work_mode: str = "Hybrid"
    location: str = ""
    openings: int = 1
    min_exp: float = 0
    max_exp: float = 0
    must_skills: list[str] = []
    nice_skills: list[str] = []
    education: str = "Any"
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str = "INR"
    max_notice_days: int | None = None
    urgency: str = "Normal"
    rounds: list[str] = ["Screening call", "Technical interview", "HR round"]
    notes: str = ""


class ScheduleReq(BaseModel):
    candidate_ids: list[int]
    interviewers: list[str]
    start: str  # YYYY-MM-DDTHH:MM
    duration: int = 45
    buffer: int = 15
    day_start: str = "10:00"
    day_end: str = "18:00"
    lunch: bool = True
    mode: str = "Video call"
    link: str = ""
    round_name: str = "Screening call"
    notes: str = ""


class IdsIn(BaseModel):
    candidate_ids: list[int]


class RejectIn(BaseModel):
    candidate_ids: list[int]
    reason: str = ""
    feedback: str = ""


class ModelIn(BaseModel):
    model: str = ""


class ScorecardIn(BaseModel):
    meeting_id: int | None = None
    interviewer: str = ""
    round_name: str = ""
    ratings: dict[str, int]
    recommendation: str
    notes: str = ""
    model: str = ""


class DecisionIn(BaseModel):
    action: str
    notes: str = ""
    feedback: str = ""


class OfferIn(BaseModel):
    salary: float | None = None
    joining_date: str | None = None
    extra_terms: str | None = None
    approver: str = ""
    comment: str = ""


class ToggleIn(BaseModel):
    task_id: str
    done: bool


def run(event: str, req_id: int | None, **payload):
    """Run one event through the agent graph; agent refusals become clean 400 errors."""
    try:
        return agents.invoke(event, req_id, **payload)
    except agents.AgentError as exc:
        raise HTTPException(400, str(exc)) from exc


def need_role(rid: int) -> dict:
    r = db.get_requisition(rid)
    if not r:
        raise HTTPException(404, "Role not found")
    return r


def need_cand(cid: int) -> dict:
    c = db.get_candidate(cid)
    if not c:
        raise HTTPException(404, "Candidate not found")
    return c


# ---- health & agents ----------------------------------------------------
@app.get("/api/health")
def health():
    return llm.status()


@app.get("/api/agents")
def agent_structure():
    return agents.structure()


@app.get("/api/traces")
def traces(req_id: int | None = None, limit: int = 60, after: int = 0):
    return db.list_traces(req_id, min(limit, 200), after)


# ---- roles --------------------------------------------------------------
@app.post("/api/requisitions")
def create_requisition(b: Brief):
    data = b.model_dump()
    data["status"] = "open"
    r = db.add_requisition(data)
    db.add_trace("new", r["id"], None, "Requisition Agent", f"Role #{r['id']} created: {r['title']}")
    return r


@app.put("/api/requisitions/{rid}")
def revise_requisition(rid: int, b: Brief):
    need_role(rid)
    return run("revise_role", rid, brief=b.model_dump())["role"]


@app.get("/api/requisitions")
def requisitions():
    return db.list_requisitions()


@app.get("/api/requisitions/{rid}")
def requisition(rid: int):
    return need_role(rid)


@app.post("/api/requisitions/{rid}/approve")
def approve_role(rid: int):
    need_role(rid)
    return run("approve_role", rid)["role"]


@app.post("/api/requisitions/{rid}/jd")
def generate_jd(rid: int, model: str = ""):
    need_role(rid)

    def gen():
        for ev in agents.stream("draft_role", rid, model=model):
            if ev.get("type") == "chunk":
                yield ev["text"]

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@app.post("/api/requisitions/{rid}/postings")
def postings(rid: int, m: ModelIn):
    need_role(rid)
    return run("draft_postings", rid, model=m.model)["postings"]


@app.post("/api/requisitions/{rid}/interview-plan")
def interview_plan(rid: int, m: ModelIn):
    need_role(rid)
    return run("plan_interviews", rid, model=m.model)["interview_plan"]


@app.post("/api/requisitions/{rid}/close")
def close_role(rid: int):
    need_role(rid)
    return run("close_role", rid)


@app.get("/api/requisitions/{rid}/analytics")
def role_analytics(rid: int):
    need_role(rid)
    return agents.analytics(rid)


# ---- screening ----------------------------------------------------------
@app.post("/api/requisitions/{rid}/screen")
async def screen(rid: int, file: UploadFile = File(...), model: str = Form(""), depth: str = Form("balanced")):
    need_role(rid)
    data = await file.read()
    st = llm.status()
    model = model or st["default"]
    if st["online"] and model not in st["models"]:
        model = st["default"]

    def gen():
        try:
            for ev in agents.stream("screen", rid, filename=file.filename or "upload.zip", data=data, model=model,
                                    depth=depth, online=st["online"]):
                yield json.dumps(ev) + "\n"
        except Exception as exc:  # noqa: BLE001
            yield json.dumps({"type": "error", "message": f"Screening failed: {str(exc)[:200]}"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/requisitions/{rid}/candidates")
def candidates(rid: int):
    return db.list_candidates(rid)


@app.get("/api/candidates/{cid}")
def candidate(cid: int):
    return need_cand(cid)


@app.post("/api/requisitions/{rid}/shortlist")
def shortlist(rid: int, b: IdsIn):
    need_role(rid)
    return run("shortlist", rid, candidate_ids=b.candidate_ids)


@app.post("/api/requisitions/{rid}/reject")
def reject(rid: int, b: RejectIn):
    need_role(rid)
    return run("reject", rid, **b.model_dump())


# ---- meetings -----------------------------------------------------------
@app.post("/api/requisitions/{rid}/schedule/preview")
def schedule_preview(rid: int, s: ScheduleReq):
    r = need_role(rid)
    try:
        return agents.plan_slots(r, s.model_dump())
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, f"Couldn't plan slots: {exc}") from exc


@app.post("/api/requisitions/{rid}/schedule")
def schedule(rid: int, s: ScheduleReq):
    need_role(rid)
    return run("schedule", rid, **s.model_dump())["meetings"]


@app.get("/api/meetings")
def meetings(req_id: int | None = None):
    out = db.list_meetings(req_id)
    for m in out:
        m["invite"] = scheduling.invite(m)
    return out


@app.delete("/api/meetings/{mid}")
def cancel_meeting(mid: int):
    db.delete_meeting(mid)
    return {"ok": True}


@app.get("/api/meetings/{mid}.ics")
def meeting_ics(mid: int):
    m = db.get_meeting(mid)
    if not m:
        raise HTTPException(404, "Meeting not found")
    return Response(scheduling.ics([m]), media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="interview-{mid}.ics"'})


@app.get("/api/calendar.ics")
def all_ics(req_id: int | None = None):
    return Response(scheduling.ics(db.list_meetings(req_id)), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="interviews.ics"'})


# ---- interview feedback, decision, offer, onboarding --------------------
@app.post("/api/candidates/{cid}/scorecard")
def scorecard(cid: int, b: ScorecardIn):
    c = need_cand(cid)
    return run("submit_scorecard", c["req_id"], candidate_id=cid, **b.model_dump())["candidate"]


@app.post("/api/candidates/{cid}/decision")
def decision(cid: int, b: DecisionIn):
    c = need_cand(cid)
    return run("decide", c["req_id"], candidate_id=cid, **b.model_dump())


@app.post("/api/candidates/{cid}/offer/{action}")
def offer(cid: int, action: str, b: OfferIn):
    c = need_cand(cid)
    ev = {"update": "update_offer", "submit": "submit_offer", "approve": "approve_offer", "revise": "revise_offer",
          "send": "send_offer", "accept": "candidate_response", "decline": "candidate_response"}.get(action)
    if not ev:
        raise HTTPException(404, "Unknown offer action")
    extra = {"accepted": action == "accept"} if ev == "candidate_response" else {}
    return run(ev, c["req_id"], candidate_id=cid, **b.model_dump(), **extra)


@app.post("/api/candidates/{cid}/onboarding/toggle")
def toggle_task(cid: int, b: ToggleIn):
    c = need_cand(cid)
    return run("toggle_task", c["req_id"], candidate_id=cid, **b.model_dump())["candidate"]


# ---- front end ----------------------------------------------------------
if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
else:
    @app.get("/")
    def no_ui():
        return PlainTextResponse("Backend is running, but the React build is missing. "
                                 "Run `npm install && npm run build` inside the frontend folder.")
