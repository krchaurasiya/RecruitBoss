"""The LangGraph multi-agent system.

One Supervisor, thirteen specialist nodes. Every action in the app (a button click) becomes an *event*.
The Supervisor turns the event into a plan (a queue of agents), sends work to one agent at a time, and
takes the agent back in between so it can add follow-up agents (for example: Hiring Decision Gate ->
Offer Management Agent). When the queue is empty the run stops at the next human gate.

State lives in SQLite, not in the graph, so a run is short and the app survives restarts.
Humans decide at: JD approval, shortlist, interview feedback, hiring decision, offer approval, candidate reply.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Annotated, Iterator, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from . import db, llm, scheduling
from . import screening as S

# --------------------------------------------------------------------------------------
# Agent roster (also shown in the UI)
# --------------------------------------------------------------------------------------
AGENTS: dict[str, tuple[str, str]] = {
    "requisition": ("Requisition Agent", "Understands the role. Drafts, revises and records approval of the job description."),
    "sourcing": ("Sourcing Agent", "Reads uploaded CSVs and resumes, checks the data, drafts job posts for each channel."),
    "resume_intel": ("Resume Intelligence Agent", "Extracts details from resume files and scores every profile with transparent rules."),
    "matching": ("Matching Agent", "Has your local model read and rank the top profiles against the brief."),
    "shortlisting": ("Shortlisting Agent", "Records who the boss shortlisted."),
    "interview_planning": ("Interview Planning Agent", "Writes interview rounds, questions and scorecard criteria."),
    "scheduling": ("Scheduling Agent", "Finds free slots per interviewer, books them, drafts invitations."),
    "evaluation": ("Evaluation Agent", "Combines scorecards and feedback into a final candidate evaluation."),
    "decision": ("Hiring Decision Gate", "Records the panel's decision: hire, more interviews, or reject."),
    "offer_management": ("Offer Management Agent", "Drafts the offer, runs HR approval, sends it, records the candidate's reply."),
    "communication": ("Communication Agent", "Drafts respectful rejection emails with feedback."),
    "onboarding": ("Onboarding Agent", "Creates the employee record, welcome email and onboarding checklist."),
    "closure": ("Closure Agent", "Closes the requisition and produces hiring analytics."),
}

PLANS: dict[str, list[str]] = {
    "draft_role": ["requisition"], "revise_role": ["requisition"], "approve_role": ["requisition"],
    "draft_postings": ["sourcing"],
    "screen": ["sourcing", "resume_intel", "matching"],
    "shortlist": ["shortlisting"],
    "reject": ["communication"],
    "plan_interviews": ["interview_planning"],
    "schedule": ["scheduling"],
    "submit_scorecard": ["evaluation"],
    "decide": ["decision"],
    "draft_offer": ["offer_management"], "update_offer": ["offer_management"], "submit_offer": ["offer_management"],
    "approve_offer": ["offer_management"], "revise_offer": ["offer_management"], "send_offer": ["offer_management"],
    "candidate_response": ["offer_management"],
    "start_onboarding": ["onboarding"], "toggle_task": ["onboarding"],
    "close_role": ["closure"],
}

REC_OPTIONS = ["Strong hire", "Hire", "Hold", "No hire"]
DEFAULT_CRITERIA = ["Role knowledge", "Problem solving", "Communication", "Culture fit"]


class AgentError(Exception):
    pass


def _merge(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


class State(TypedDict, total=False):
    event: str
    run: str
    req_id: int | None
    payload: dict
    queue: list[str]
    followups: list[str]
    route: str
    error: str
    result: Annotated[dict, _merge]


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def _now() -> str:
    return time.strftime("%d %b %Y, %H:%M")


def _note(c: dict, text: str) -> None:
    c.setdefault("timeline", []).append({"ts": _now(), "text": text})


def _reach(c: dict, *milestones: str) -> None:
    r = c.setdefault("reached", [])
    for m in milestones:
        if m not in r:
            r.append(m)


def _log(state: State, agent: str, text: str, cand_id: int | None = None) -> None:
    db.add_trace(state.get("run", ""), state.get("req_id"), cand_id, agent, text)


def _fail(state: State, agent: str, msg: str) -> dict:
    _log(state, agent, f"Stopped: {msg}")
    return {"error": msg, "queue": [], "followups": []}


def _writer():
    try:
        return get_stream_writer()
    except Exception:  # noqa: BLE001  (not streaming)
        return lambda _x: None


def _cand(state: State, cid) -> dict | None:
    try:
        return db.get_candidate(int(cid))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------------------
# Supervisor
# --------------------------------------------------------------------------------------
def supervisor(state: State) -> dict:
    if state.get("error"):
        return {"route": "END"}
    if "queue" not in state:
        plan = list(PLANS.get(state["event"], []))
        if not plan:
            return {"error": f"Unknown action: {state['event']}", "route": "END"}
        names = " → ".join(AGENTS[a][0] for a in plan)
        db.add_trace(state.get("run", ""), state.get("req_id"), None, "Supervisor", f"{state['event']}: planned {names}")
    else:
        plan = list(state.get("queue") or [])
    extra = list(state.get("followups") or [])
    if extra:
        db.add_trace(state.get("run", ""), state.get("req_id"), None, "Supervisor",
                     "Added follow-up: " + " → ".join(AGENTS[a][0] for a in extra))
    queue = extra + plan
    if not queue:
        return {"route": "END", "queue": [], "followups": []}
    return {"route": queue[0], "queue": queue[1:], "followups": []}


# --------------------------------------------------------------------------------------
# 1. Requisition Agent
# --------------------------------------------------------------------------------------
def template_jd(r: dict) -> str:
    must = "\n".join(f"- {s}" for s in r.get("must_skills", [])) or "- To be confirmed"
    nice = "\n".join(f"- {s}" for s in r.get("nice_skills", [])) or "- None listed"
    return (
        f"{r['title']} ({r['seniority']}, {r['employment_type']})\n"
        f"{r['department']} | {r.get('location') or 'Location flexible'} | {r['work_mode']}\n\n"
        f"About the role\nWe are hiring {r['openings']} {r['title']} to join the {r['department']} team. "
        f"You will own your work end to end and collaborate closely with the wider team.\n\n"
        f"What you bring\n- {r['min_exp']}-{r['max_exp']} years of relevant experience\n- Education: {r['education']}\n{must}\n\n"
        f"Nice to have\n{nice}\n\nHow we hire\n" + "\n".join(f"- {x}" for x in r.get("rounds", []))
    )


JD_SYSTEM = ("You write clear, honest, inclusive job descriptions in plain text (no markdown symbols like ** or #). "
             "Use short section titles on their own line: About the role, What you'll do, What you bring, Nice to have, "
             "How we hire. Keep it under 300 words. Do not invent salary, perks or company facts that are not given.")


def requisition_agent(state: State) -> dict:
    ev, rid, p = state["event"], state["req_id"], state.get("payload", {})
    name = AGENTS["requisition"][0]
    if ev == "approve_role":
        r = db.update_requisition(rid, {"status": "approved", "approved_at": time.time()})
        _log(state, name, "Boss approved the requirements")
        return {"result": {"role": r}}
    if ev == "revise_role":
        r = db.update_requisition(rid, {**p["brief"], "status": "open"})
        _log(state, name, "Brief updated in place (same role, new details)")
        return {"result": {"role": r}}
    # draft_role: stream the text so the UI types it out live
    r = db.get_requisition(rid)
    model = p.get("model") or llm.DEFAULT_MODEL
    user = (f"Write a job description.\n{S.brief_text(r)}\nOpenings: {r['openings']}\n"
            f"Employment type: {r['employment_type']}\nHiring rounds: {', '.join(r.get('rounds', []))}\n"
            f"Extra notes from the hiring manager: {r.get('notes') or 'none'}")
    w, text, used_ai = _writer(), "", True
    try:
        for piece in llm.chat_stream(model, JD_SYSTEM, user):
            text += piece
            w({"type": "chunk", "text": piece})
    except Exception:  # noqa: BLE001
        pass
    if not text.strip():
        used_ai, text = False, template_jd(r)
        w({"type": "chunk", "text": text})
    db.update_requisition(rid, {"jd": text})
    _log(state, name, f"Drafted the job description with {model}" if used_ai else "Ollama unavailable: used the standard template")
    return {"result": {"jd": text, "ai": used_ai}}


# --------------------------------------------------------------------------------------
# 2. Sourcing Agent  (job posts + reading uploads)
# --------------------------------------------------------------------------------------
CHANNELS = [("linkedin", "LinkedIn post"), ("careers", "Careers page"), ("portal", "Job portal listing"), ("referral", "Referral message")]
POST_SYSTEM = ("You write short job posts for different channels from one job brief. Be factual: do not invent salary, perks "
               "or company facts. Plain text only. Reply with one JSON object with exactly these keys: linkedin (engaging, "
               "under 120 words), careers (structured, under 160 words), portal (keyword-rich, under 120 words), "
               "referral (a friendly message an employee could forward, under 70 words).")


def template_postings(r: dict) -> dict:
    must = ", ".join(r.get("must_skills", [])[:6]) or "see the full description"
    where = r["work_mode"] if r["work_mode"] == "Remote" else f"{r['work_mode']}, {r.get('location') or 'location flexible'}"
    head = f"{r['title']} ({r['seniority']}) · {r['department']} · {where}"
    return {
        "linkedin": f"We're hiring: {head}\n\nYou'll bring {must} and {r['min_exp']}-{r['max_exp']} years of experience.\nInterested? Send your CV or message me.",
        "careers": f"{head}\n\nRole type: {r['employment_type']}\nOpenings: {r['openings']}\nMust have: {must}\nExperience: {r['min_exp']}-{r['max_exp']} years\nHiring steps: {' → '.join(r.get('rounds', []))}",
        "portal": f"{r['title']} | {r['seniority']} | {r['employment_type']} | {where}\nSkills: {must}\nExperience: {r['min_exp']}-{r['max_exp']} years\nEducation: {r['education']}",
        "referral": f"Hi! We're hiring a {r['title']} ({where}). Skills: {must}. Know someone good? Ask them to send a CV and mention your name.",
    }


def sourcing_agent(state: State) -> dict:
    ev, rid, p = state["event"], state["req_id"], state.get("payload", {})
    name = AGENTS["sourcing"][0]
    r = db.get_requisition(rid)
    if ev == "draft_postings":
        model = p.get("model") or llm.DEFAULT_MODEL
        out = llm.chat_json(model, POST_SYSTEM, f"JOB BRIEF\n{S.brief_text(r)}\nOpenings: {r['openings']}\nType: {r['employment_type']}", timeout=120)
        fb, used_ai = template_postings(r), False
        posts = {}
        for key, _ in CHANNELS:
            v = out.get(key) if out else None
            if isinstance(v, str) and len(v.strip()) > 20:
                posts[key], used_ai = v.strip(), True
            else:
                posts[key] = fb[key]
        listing = [{"key": k, "channel": label, "text": posts[k]} for k, label in CHANNELS]
        db.update_requisition(rid, {"postings": listing})
        _log(state, name, f"Drafted {len(listing)} channel posts" + (f" with {model}" if used_ai else " from the template"))
        return {"result": {"postings": listing}}

    # screen: read the upload
    w = _writer()
    try:
        files, docs, warnings = S.read_inputs(p["filename"], p.pop("data"))
    except ValueError as exc:
        w({"type": "error", "message": str(exc)})
        return _fail(state, name, str(exc))
    cands, report = S.build_candidates(files, warnings, docs, r)
    if not cands:
        w({"type": "check", "report": report})
        msg = "No usable candidates were found. Check the data report above."
        w({"type": "error", "message": msg})
        return _fail(state, name, msg)
    # a second upload adds to the role: skip people who are already in it
    key = lambda c: (c.get("email") or "").lower() or f"{c['name'].lower()}|{c.get('source_file', '')}"  # noqa: E731
    have = {key(c) for c in db.list_candidates(rid)}
    fresh = [c for c in cands if key(c) not in have]
    skipped = len(cands) - len(fresh)
    if skipped:
        report["issues"].append({"severity": "info", "message": "Already in this role from an earlier upload, so skipped.", "count": skipped, "examples": []})
        report["duplicates_removed"] += skipped
        report["usable"] = len(fresh)
    if not fresh:
        msg = "Everyone in this file is already in this role."
        w({"type": "check", "report": report})
        w({"type": "error", "message": msg})
        return _fail(state, name, msg)
    cands = fresh
    w({"type": "check", "report": report})
    p["cands"], p["req"] = cands, r
    _log(state, name, f"Read {len(files)} CSV file(s) and {len(docs)} resume file(s): {len(cands)} new candidates"
                      + (f", {skipped} already in the role" if skipped else ""))
    return {"payload": p}


# --------------------------------------------------------------------------------------
# 3. Resume Intelligence Agent
# --------------------------------------------------------------------------------------
def resume_intel_agent(state: State) -> dict:
    p, name, w = state["payload"], AGENTS["resume_intel"][0], _writer()
    req, cands, depth, model = p["req"], p["cands"], p["depth"], p["model"]
    use_ai = bool(p["online"]) and depth in ("balanced", "deep")
    extracted = 0
    for c in cands:
        c["stage"] = "screened"
        if c.get("from_document") and use_ai and extracted < 60 and S.llm_extract(c, model):
            extracted += 1
        c.update(S.rule_score(c, req))
        c["final_score"], c["ai"] = c["rule_score"], None
        c["verdict"] = S.verdict(c["final_score"])
    ranked = sorted(cands, key=lambda x: x["rule_score"], reverse=True)
    limit = {"balanced": 10, "deep": 60}.get(depth, 0) if use_ai else 0
    p["targets"], p["use_ai"] = ranked[:limit], use_ai
    w({"type": "plan", "total": len(cands), "ai_total": len(p["targets"]), "ai": use_ai, "model": model if use_ai else None})
    _log(state, name, f"Scored {len(cands)} profiles on rules" + (f"; read {extracted} resume file(s) with the model" if extracted else ""))
    return {"payload": p}


# --------------------------------------------------------------------------------------
# 4. Matching Agent
# --------------------------------------------------------------------------------------
def matching_agent(state: State) -> dict:
    p, name, w = state["payload"], AGENTS["matching"][0], _writer()
    rid, req, cands, targets, model = state["req_id"], p["req"], p["cands"], p["targets"], p["model"]
    ai_failed = 0
    for n, c in enumerate(targets, start=1):
        w({"type": "progress", "done": n - 1, "total": len(targets), "name": c["name"]})
        res = S.ai_review(c, req, model)
        if res:
            c["ai"] = res
            c["final_score"] = round(0.6 * c["rule_score"] + 0.4 * res["fit_score"])
            c["verdict"] = S.verdict(c["final_score"])
        else:
            ai_failed += 1
        w({"type": "progress", "done": n, "total": len(targets), "name": c["name"]})
        if ai_failed >= 3 and n == ai_failed:
            w({"type": "warn", "message": "The model isn't returning usable answers, so the rest are scored by rules only."})
            break
    ranked = sorted(cands, key=lambda x: x["final_score"], reverse=True)
    for c in ranked:
        _note(c, f"Screened: {c['final_score']} ({c['verdict']}) from {c['source_file']}")
    db.add_candidates(rid, ranked)
    saved = db.list_candidates(rid)
    ai_used = bool(p["use_ai"]) and ai_failed < len(targets)
    db.update_requisition(rid, {"screened": True, "model": model if ai_used else None})
    w({"type": "done", "candidates": saved, "ai_failed": ai_failed, "ai_used": ai_used})
    _log(state, name, f"Ranked {len(ranked)} new candidates ({len(saved)} in the role)" + (f"; model read {len(targets) - ai_failed} of {len(targets)}" if p["use_ai"] else " (rules only)"))
    return {"result": {"screened": len(saved)}}


# --------------------------------------------------------------------------------------
# 5. Shortlisting Agent
# --------------------------------------------------------------------------------------
def shortlisting_agent(state: State) -> dict:
    ids = state["payload"].get("candidate_ids", [])
    n = 0
    for cid in ids:
        def f(c):
            nonlocal n
            if c.get("stage") in ("screened", "shortlisted"):
                c["stage"] = "shortlisted"
                _reach(c, "shortlisted")
                if not any("Shortlisted" in t["text"] for t in c.get("timeline", [])):
                    _note(c, "Shortlisted by the boss")
                n += 1
        db.update_candidate(int(cid), f)
    _log(state, AGENTS["shortlisting"][0], f"Recorded {n} shortlisted candidate(s)")
    return {"result": {"shortlisted": n}}


# --------------------------------------------------------------------------------------
# 6. Communication Agent  (rejections)
# --------------------------------------------------------------------------------------
def rejection_email(c: dict, role: str, feedback: str) -> dict:
    first = (c.get("name") or "there").split()[0]
    body = (f"Hi {first},\n\nThank you for your interest in the {role} role and for the time you put into applying. "
            f"After careful review, we won't be taking your application forward at this stage.\n\n"
            + (f"Feedback: {feedback.strip()}\n\n" if feedback.strip() else "")
            + "We'll keep your details in mind for future openings. We wish you every success.\n\nBest regards,\nThe hiring team")
    return {"subject": f"Your application for {role}", "body": body}


def communication_agent(state: State) -> dict:
    p, name = state["payload"], AGENTS["communication"][0]
    role = db.get_requisition(state["req_id"])["title"]
    emails = []
    for cid in p.get("candidate_ids", []):
        c = _cand(state, cid)
        if not c:
            continue
        if c.get("stage") in ("offer_sent", "onboarding", "joined"):
            return _fail(state, name, f"{c['name']} already has an offer in progress, so I won't draft a rejection.")
        em = rejection_email(c, role, p.get("feedback", ""))

        def f(x, em=em):
            x["stage"] = "rejected"
            x["rejected"] = {"reason": p.get("reason", ""), "feedback": p.get("feedback", ""), "email": em, "ts": _now()}
            _note(x, f"Rejected ({p.get('reason') or 'no reason given'}). Email drafted.")
        db.update_candidate(c["id"], f)
        emails.append({"candidate_id": c["id"], "name": c["name"], "to": c.get("email", ""), **em})
    _log(state, name, f"Drafted {len(emails)} rejection email(s) with feedback")
    return {"result": {"emails": emails}}


# --------------------------------------------------------------------------------------
# 7. Interview Planning Agent
# --------------------------------------------------------------------------------------
PLAN_SYSTEM = ("You design structured interviews. For each interview round given, return focus, 3 to 5 specific interview "
               "questions, and 3 to 4 scorecard criteria (2 to 3 words each). Questions must be job-related and must not "
               "ask about age, family, religion, health or other personal matters. Reply with one JSON object: "
               '{"rounds": [{"name": "<round name exactly as given>", "focus": "<one sentence>", '
               '"questions": ["..."], "criteria": ["..."]}]}')


def template_round(name: str, r: dict) -> dict:
    low, skills = name.lower(), r.get("must_skills", [])[:3]
    if "screen" in low:
        return {"name": name, "focus": "Check basic fit, motivation and availability.", "criteria": ["Communication", "Role interest", "Basic fit"],
                "questions": ["Tell me about your current role and what you own.", f"Why are you interested in the {r['title']} role?",
                              "What are you looking for in your next job?", "When could you start if selected?"]}
    if "tech" in low or "assign" in low:
        qs = [f"Walk me through a project where you used {s}." for s in skills] or ["Walk me through your most relevant project."]
        return {"name": name, "focus": "Test depth in the must-have skills.", "criteria": ["Technical depth", "Problem solving", "Communication"],
                "questions": qs + ["Describe a hard problem you solved and how you checked it worked."]}
    if "manager" in low:
        return {"name": name, "focus": "Judge ownership, prioritising and working style.", "criteria": ["Ownership", "Prioritisation", "Collaboration"],
                "questions": ["Tell me about a time priorities changed quickly. What did you do?", "How do you handle disagreement on your team?",
                              "What would you want to achieve in your first 90 days?"]}
    if "hr" in low:
        return {"name": name, "focus": "Confirm expectations, notice period and fit with how the team works.", "criteria": ["Expectations alignment", "Communication", "Culture fit"],
                "questions": ["What are your expectations around role and growth?", "What does a good team environment look like to you?",
                              "Is there anything about the role you'd like to clarify?"]}
    return {"name": name, "focus": "Understand how the person works with others.", "criteria": ["Collaboration", "Values", "Communication"],
            "questions": ["Describe a team you enjoyed working in and why.", "Tell me about feedback you received and what you did with it."]}


def interview_planning_agent(state: State) -> dict:
    p, name, rid = state.get("payload", {}), AGENTS["interview_planning"][0], state["req_id"]
    r = db.get_requisition(rid)
    model = p.get("model") or llm.DEFAULT_MODEL
    rounds = r.get("rounds") or ["Screening call", "Technical interview", "HR round"]
    out = llm.chat_json(model, PLAN_SYSTEM, f"JOB BRIEF\n{S.brief_text(r)}\nRounds: {json.dumps(rounds)}", timeout=150)
    by_name = {}
    if out and isinstance(out.get("rounds"), list):
        for x in out["rounds"]:
            if isinstance(x, dict) and isinstance(x.get("questions"), list) and x["questions"]:
                by_name[str(x.get("name", "")).strip().lower()] = x
    plan, ai_rounds = [], 0
    for rn in rounds:
        x = by_name.get(rn.lower())
        if x:
            ai_rounds += 1
            crit = [str(c)[:30] for c in (x.get("criteria") or []) if c][:4] or DEFAULT_CRITERIA[:3]
            plan.append({"name": rn, "focus": str(x.get("focus", ""))[:200], "questions": [str(q)[:220] for q in x["questions"]][:5], "criteria": crit})
        else:
            plan.append(template_round(rn, r))
    db.update_requisition(rid, {"interview_plan": plan})
    _log(state, name, f"Planned {len(plan)} round(s)" + (f"; model wrote {ai_rounds}" if ai_rounds else " from templates"))
    return {"result": {"interview_plan": plan}}


# --------------------------------------------------------------------------------------
# 8. Scheduling Agent
# --------------------------------------------------------------------------------------
SCHEDULABLE = ("screened", "shortlisted", "interviewing", "evaluated")


def plan_slots(req: dict, s: dict) -> list[dict]:
    order = {cid: i for i, cid in enumerate(s["candidate_ids"])}
    cands = sorted(db.get_candidates(s["candidate_ids"]), key=lambda c: order[c["id"]])
    if not cands:
        raise ValueError("Pick at least one candidate.")
    for c in cands:
        if c.get("stage", "screened") not in SCHEDULABLE:
            raise ValueError(f"{c['name']} is already '{c.get('stage')}', so can't be scheduled for an interview.")
    slots = scheduling.plan(cands, s["interviewers"], s["start"], s["duration"], s["buffer"], s["day_start"], s["day_end"],
                            s["lunch"], db.list_meetings())
    for m in slots:
        m.update({"role": req["title"], "mode": s["mode"], "link": s["link"], "round_name": s["round_name"], "notes": s["notes"]})
    return slots


def scheduling_agent(state: State) -> dict:
    s, rid, name = state["payload"], state["req_id"], AGENTS["scheduling"][0]
    req = db.get_requisition(rid)
    try:
        slots = plan_slots(req, s)
    except (ValueError, RuntimeError) as exc:
        return _fail(state, name, f"Couldn't plan slots: {exc}")
    saved = []
    for m in slots:
        m = db.add_meeting(rid, {**m, "status": "scheduled"})
        m["invite"] = scheduling.invite(m)
        saved.append(m)

        def f(c, m=m):
            c["stage"] = "interviewing"
            _reach(c, "shortlisted", "interviewing")
            _note(c, f"{m['round_name']} booked with {m['interviewer']} on {m['start'].replace('T', ' ')}")
        db.update_candidate(m["candidate_id"], f)
    _log(state, name, f"Booked {len(saved)} interview(s) across {len({m['interviewer'] for m in saved})} interviewer(s)")
    return {"result": {"meetings": saved}}


# --------------------------------------------------------------------------------------
# 9. Evaluation Agent
# --------------------------------------------------------------------------------------
EVAL_SYSTEM = ("You summarise interview evidence for a hiring panel. Use ONLY the scorecards given. Do not consider or mention "
               "age, gender, religion, ethnicity, health, family or any protected trait. Do not invent facts. Reply with one JSON "
               'object: {"summary": "<max 40 words>", "strengths": ["max 3 short items"], "concerns": ["max 3 short items"]}')


def aggregate(cards: list[dict]) -> dict:
    per: dict[str, list[int]] = {}
    votes: dict[str, int] = {}
    for sc in cards:
        for k, v in sc["ratings"].items():
            per.setdefault(k, []).append(int(v))
        votes[sc["recommendation"]] = votes.get(sc["recommendation"], 0) + 1
    per_avg = {k: round(sum(v) / len(v), 2) for k, v in per.items()}
    allr = [x for v in per.values() for x in v]
    overall = round(sum(allr) / len(allr), 2) if allr else 0
    no, yes = votes.get("No hire", 0), votes.get("Strong hire", 0) + votes.get("Hire", 0)
    rec = "Hire" if overall >= 3.8 and no == 0 else "No hire" if overall < 2.8 or no > yes else "Hold"
    return {"overall": overall, "per": per_avg, "votes": votes, "recommendation": rec, "n": len(cards)}


def evaluation_agent(state: State) -> dict:
    p, name = state["payload"], AGENTS["evaluation"][0]
    c = _cand(state, p.get("candidate_id"))
    if not c:
        return _fail(state, name, "Candidate not found.")
    if c.get("stage") not in ("interviewing", "evaluated", "shortlisted", "screened"):
        return _fail(state, name, f"{c['name']} is '{c.get('stage')}', so feedback can't be added.")
    ratings = p.get("ratings") or {}
    if not ratings or any(not isinstance(v, int) or not 1 <= v <= 5 for v in ratings.values()):
        return _fail(state, name, "Rate every criterion from 1 to 5.")
    if p.get("recommendation") not in REC_OPTIONS:
        return _fail(state, name, "Choose a recommendation.")
    card = {"interviewer": (p.get("interviewer") or "Interviewer").strip()[:60], "round_name": p.get("round_name", ""), "ratings": ratings,
            "recommendation": p["recommendation"], "notes": (p.get("notes") or "").strip()[:1500], "ts": _now(), "meeting_id": p.get("meeting_id")}
    cards = list(c.get("scorecards", [])) + [card]
    agg = aggregate(cards)

    req = db.get_requisition(state["req_id"])
    model = p.get("model") or llm.DEFAULT_MODEL
    evidence = "\n".join(f"- {x['interviewer']} ({x['round_name'] or 'interview'}): ratings {json.dumps(x['ratings'])}; "
                         f"recommends {x['recommendation']}; notes: {x['notes'] or 'none'}" for x in cards)
    out = llm.chat_json(model, EVAL_SYSTEM, f"JOB BRIEF\n{S.brief_text(req)}\n\nCANDIDATE: {c['name']}\nSCORECARDS\n{evidence}", timeout=120)
    ordered = sorted(agg["per"].items(), key=lambda kv: kv[1], reverse=True)
    if out and out.get("summary"):
        lst = lambda k: [str(x)[:120] for x in (out.get(k) or []) if x][:3] if isinstance(out.get(k), list) else []  # noqa: E731
        agg.update({"summary": str(out["summary"])[:320], "strengths": lst("strengths"), "concerns": lst("concerns"), "ai": True})
    else:
        agg.update({"summary": f"{len(cards)} scorecard(s), average {agg['overall']} out of 5. Panel recommends: {agg['recommendation']}.",
                    "strengths": [f"{k} ({v})" for k, v in ordered[:2] if v >= 3.5], "concerns": [f"{k} ({v})" for k, v in ordered[::-1][:2] if v < 3],
                    "ai": False})

    def f(x):
        x.setdefault("scorecards", []).append(card)
        x["evaluation"] = agg
        x["stage"] = "evaluated"
        _reach(x, "shortlisted", "interviewed")
        _note(x, f"Feedback from {card['interviewer']}: {card['recommendation']} (average {agg['overall']}/5)")
    db.update_candidate(c["id"], f)
    if p.get("meeting_id"):
        db.update_meeting(int(p["meeting_id"]), {"status": "completed"})
    _log(state, name, f"Evaluated {c['name']}: {agg['overall']}/5 → {agg['recommendation']}" + (" (model wrote the summary)" if agg["ai"] else ""), c["id"])
    return {"result": {"candidate": db.get_candidate(c["id"])}}


# --------------------------------------------------------------------------------------
# 10. Hiring Decision Gate (human)
# --------------------------------------------------------------------------------------
def decision_agent(state: State) -> dict:
    p, name = state["payload"], AGENTS["decision"][0]
    c = _cand(state, p.get("candidate_id"))
    action = p.get("action")
    if not c:
        return _fail(state, name, "Candidate not found.")
    if c.get("stage") != "evaluated":
        return _fail(state, name, f"{c['name']} needs interview feedback before a decision (stage: {c.get('stage')}).")
    if action not in ("approve", "more", "reject"):
        return _fail(state, name, "Choose approve, more interviews, or reject.")
    notes = (p.get("notes") or "").strip()

    def f(x):
        x["decision"] = {"action": action, "notes": notes, "ts": _now()}
        if action == "more":
            x["stage"] = "shortlisted"
            x["needs_more"] = True
        _note(x, {"approve": "Panel approved hiring", "more": "Panel asked for more interviews", "reject": "Panel decided not to hire"}[action] + (f": {notes}" if notes else ""))
    db.update_candidate(c["id"], f)
    _log(state, name, f"{c['name']}: {action}", c["id"])
    if action == "approve":
        return {"event": "draft_offer", "followups": ["offer_management"], "payload": {**p, "candidate_id": c["id"]}}
    if action == "reject":
        return {"event": "reject", "followups": ["communication"],
                "payload": {"candidate_ids": [c["id"]], "reason": "After interviews", "feedback": p.get("feedback") or notes}}
    return {"result": {"candidate": db.get_candidate(c["id"])}}


# --------------------------------------------------------------------------------------
# 11. Offer Management Agent
# --------------------------------------------------------------------------------------
def _money(v) -> str:
    return f"{float(v):,.0f}"


def offer_letter(c: dict, role: dict, o: dict) -> str:
    first = c["name"].split()[0]
    where = "" if role["work_mode"] == "Remote" else f" based in {role.get('location') or 'our office'}"
    try:
        from datetime import datetime
        jd = datetime.strptime(o["joining_date"], "%Y-%m-%d").strftime("%d %B %Y").lstrip("0")
    except Exception:  # noqa: BLE001
        jd = o.get("joining_date") or "to be agreed"
    sal = f"{o.get('currency', 'INR')} {_money(o['salary'])} per year" if o.get("salary") else "to be confirmed"
    return (f"Dear {first},\n\nWe are pleased to offer you the position of {role['title']} ({role['seniority']}) in our "
            f"{role['department']} team, as a {role['employment_type'].lower()} {role['work_mode'].lower()} role{where}.\n\n"
            f"Compensation: {sal}\nProposed joining date: {jd}\n"
            + (f"\n{o['extra_terms'].strip()}\n" if o.get("extra_terms", "").strip() else "")
            + "\nPlease reply to this email to accept, or let us know if you'd like to talk anything through.\n\nBest regards,\nThe hiring team")


def _next_best(rid: int, skip: int) -> dict | None:
    for c in db.list_candidates(rid):
        if c["id"] != skip and c.get("stage") in ("screened", "shortlisted", "evaluated") and c.get("email"):
            return {"id": c["id"], "name": c["name"], "score": c["final_score"], "stage": c.get("stage")}
    return None


def offer_management_agent(state: State) -> dict:
    ev, p, name, rid = state["event"], state["payload"], AGENTS["offer_management"][0], state["req_id"]
    c = _cand(state, p.get("candidate_id"))
    if not c:
        return _fail(state, name, "Candidate not found.")
    role = db.get_requisition(rid)
    o = dict(c.get("offer") or {})
    status = o.get("status")

    def need(*ok):
        return None if status in ok else f"That isn't possible while the offer is '{status or 'not started'}'."

    err, followups, new_event = None, [], None
    if ev == "draft_offer":
        if c.get("stage") != "evaluated":
            return _fail(state, name, f"{c['name']} must be approved after interviews first.")
        mid = None
        if role.get("salary_min") and role.get("salary_max"):
            mid = round((role["salary_min"] + role["salary_max"]) / 2, -4)
        elif role.get("salary_min"):
            mid = role["salary_min"]
        o = {"salary": mid, "currency": role.get("currency", "INR"),
             "joining_date": time.strftime("%Y-%m-%d", time.localtime(time.time() + 30 * 86400)), "extra_terms": "", "status": "draft"}
        stage, msg = "offer_draft", "Drafted the offer" + (" (salary set to the middle of the pay band)" if mid else " (add a salary)")
    elif ev == "update_offer":
        err = need("draft")
        for k in ("salary", "joining_date", "extra_terms"):
            if k in p and p[k] is not None:
                o[k] = p[k]
        if o.get("salary") not in (None, "") and float(o["salary"]) < 0:
            err = "Salary can't be negative."
        stage, msg = "offer_draft", "Updated the offer details"
    elif ev == "submit_offer":
        err = need("draft")
        if not err and (not o.get("salary") or float(o["salary"]) <= 0 or not o.get("joining_date")):
            err = "Add a salary and a joining date before sending for approval."
        o["status"], stage, msg = "pending_approval", "offer_pending", "Sent the offer to HR for approval"
    elif ev == "approve_offer":
        err = need("pending_approval")
        o.update({"status": "approved", "approved_by": (p.get("approver") or "HR").strip()[:60], "comment": p.get("comment", "")})
        stage, msg = "offer_approved", f"Offer approved by {o['approved_by']}"
    elif ev == "revise_offer":
        err = need("pending_approval")
        o.update({"status": "draft", "comment": (p.get("comment") or "").strip()})
        stage, msg = "offer_draft", "HR sent the offer back for changes" + (f": {o['comment']}" if o["comment"] else "")
    elif ev == "send_offer":
        err = need("approved")
        o.update({"status": "sent", "sent_at": _now()})
        stage, msg = "offer_sent", "Offer sent to the candidate"
        _reach(c, "offered")
    elif ev == "candidate_response":
        err = need("sent")
        if p.get("accepted"):
            o.update({"status": "accepted", "accepted_ts": time.time()})
            stage, msg, new_event, followups = "offer_accepted", "Candidate accepted the offer", "start_onboarding", ["onboarding"]
        else:
            o.update({"status": "declined"})
            stage, msg = "declined", "Candidate declined the offer"
    else:
        err = "Unknown offer action."
    if err:
        return _fail(state, name, err)
    if ev in ("draft_offer", "update_offer", "revise_offer"):
        o["letter"] = offer_letter(c, role, o)
    if ev == "send_offer":
        o["email"] = {"subject": f"Offer of employment: {role['title']}", "body": o["letter"]}

    def f(x):
        x["offer"] = o
        x["stage"] = stage
        if ev == "send_offer":
            _reach(x, "offered")
        if ev == "candidate_response" and p.get("accepted"):
            _reach(x, "offered", "accepted")
        _note(x, msg)
    db.update_candidate(c["id"], f)
    _log(state, name, f"{c['name']}: {msg}", c["id"])
    out: dict = {"result": {"candidate": db.get_candidate(c["id"])}}
    if ev == "candidate_response" and not p.get("accepted"):
        out["result"]["next_best"] = _next_best(rid, c["id"])
    if followups:
        out.update({"followups": followups, "event": new_event})
    return out


# --------------------------------------------------------------------------------------
# 12. Onboarding Agent
# --------------------------------------------------------------------------------------
CHECKLIST = [("welcome", "Send the welcome email"), ("docs", "Collect joining documents"), ("account", "Create work email and accounts"),
             ("equipment", "Arrange laptop and equipment"), ("buddy", "Assign a buddy and manager"), ("orientation", "Schedule orientation"),
             ("payroll", "Add to payroll"), ("week1", "Share the first-week plan")]


def welcome_email(c: dict, role: dict, o: dict) -> dict:
    first = c["name"].split()[0]
    return {"subject": f"Welcome to the team, {first}!",
            "body": (f"Hi {first},\n\nWe're delighted that you're joining us as {role['title']} on {o.get('joining_date', 'your start date')}.\n\n"
                     "Before your first day we'll share your first-week plan, and we'll ask you for the documents we need to set you up. "
                     "If you have any questions in the meantime, just reply to this email.\n\nSee you soon,\nThe hiring team")}


def onboarding_agent(state: State) -> dict:
    ev, p, name, rid = state["event"], state["payload"], AGENTS["onboarding"][0], state["req_id"]
    c = _cand(state, p.get("candidate_id"))
    if not c:
        return _fail(state, name, "Candidate not found.")
    role = db.get_requisition(rid)
    if ev == "start_onboarding":
        o = c.get("offer") or {}
        emp = {"employee_id": f"EMP-{rid:03d}-{c['id']:03d}", "name": c["name"], "email": c.get("email", ""), "phone": c.get("phone", ""),
               "title": role["title"], "department": role["department"], "employment_type": role["employment_type"],
               "work_mode": role["work_mode"], "location": role.get("location", ""), "start_date": o.get("joining_date", ""),
               "salary": o.get("salary"), "currency": o.get("currency", "INR"), "status": "Pre-joining"}
        ob = {"checklist": [{"id": i, "label": l, "done": False} for i, l in CHECKLIST], "employee": emp, "welcome": welcome_email(c, role, o)}

        def f(x):
            x["onboarding"], x["stage"] = ob, "onboarding"
            _note(x, "Onboarding started. Employee record and checklist created.")
        db.update_candidate(c["id"], f)
        _log(state, name, f"Created employee record {emp['employee_id']}, welcome email and {len(CHECKLIST)}-step checklist", c["id"])
        return {"result": {"candidate": db.get_candidate(c["id"])}}

    # toggle_task
    ob = c.get("onboarding")
    if not ob:
        return _fail(state, name, "Onboarding hasn't started for this candidate.")
    for t in ob["checklist"]:
        if t["id"] == p.get("task_id"):
            t["done"] = bool(p.get("done"))
    all_done = all(t["done"] for t in ob["checklist"])

    def f(x):
        x["onboarding"] = ob
        was = x.get("stage")
        x["stage"] = "joined" if all_done else "onboarding"
        ob["employee"]["status"] = "Active" if all_done else "Pre-joining"
        if all_done and was != "joined":
            _reach(x, "joined")
            _note(x, "Onboarding complete. Employee is active.")
    db.update_candidate(c["id"], f)
    done = sum(t["done"] for t in ob["checklist"])
    _log(state, name, f"{c['name']}: {done}/{len(ob['checklist'])} onboarding tasks done", c["id"])
    return {"result": {"candidate": db.get_candidate(c["id"])}}


# --------------------------------------------------------------------------------------
# 13. Closure Agent + analytics
# --------------------------------------------------------------------------------------
FUNNEL = [("screened", "Screened"), ("shortlisted", "Shortlisted"), ("interviewed", "Interviewed"),
          ("offered", "Offered"), ("accepted", "Accepted"), ("joined", "Joined")]


def analytics(rid: int) -> dict:
    role = db.get_requisition(rid)
    cands = db.list_candidates(rid)
    reached = lambda m: sum(1 for c in cands if m in c.get("reached", []))  # noqa: E731
    funnel = [{"key": k, "label": label, "count": len(cands) if k == "screened" else reached(k)} for k, label in FUNNEL]
    accepted = [c for c in cands if (c.get("offer") or {}).get("status") == "accepted"]
    offered = reached("offered")
    ttd = [(c["offer"]["accepted_ts"] - role["created"]) / 86400 for c in accepted if c["offer"].get("accepted_ts")]
    evals = [c["evaluation"]["overall"] for c in cands if c.get("evaluation")]
    return {
        "funnel": funnel, "openings": role.get("openings", 1), "filled": len(accepted),
        "time_to_hire_days": round(sum(ttd) / len(ttd), 1) if ttd else None,
        "offer_acceptance": round(100 * len(accepted) / offered) if offered else None,
        "avg_screen_score": round(sum(c["final_score"] for c in cands) / len(cands)) if cands else None,
        "avg_interview_rating": round(sum(evals) / len(evals), 2) if evals else None,
        "rejected": sum(1 for c in cands if c.get("stage") == "rejected"),
        "declined": sum(1 for c in cands if c.get("stage") == "declined"),
        "interviews_done": sum(1 for m in db.list_meetings(rid) if m.get("status") == "completed"),
        "status": role.get("status", "open"),
    }


def closure_agent(state: State) -> dict:
    rid = state["req_id"]
    role = db.update_requisition(rid, {"status": "closed", "closed_at": time.time()})
    a = analytics(rid)
    _log(state, AGENTS["closure"][0], f"Closed '{role['title']}': {a['filled']} of {a['openings']} opening(s) filled")
    return {"result": {"role": role, "analytics": a}}


# --------------------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------------------
NODES = {
    "requisition": requisition_agent, "sourcing": sourcing_agent, "resume_intel": resume_intel_agent, "matching": matching_agent,
    "shortlisting": shortlisting_agent, "interview_planning": interview_planning_agent, "scheduling": scheduling_agent,
    "evaluation": evaluation_agent, "decision": decision_agent, "offer_management": offer_management_agent,
    "communication": communication_agent, "onboarding": onboarding_agent, "closure": closure_agent,
}


def build_graph():
    g = StateGraph(State)
    g.add_node("supervisor", supervisor)
    for n, fn in NODES.items():
        g.add_node(n, fn)
    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", lambda s: s.get("route", "END"), {**{n: n for n in NODES}, "END": END})
    for n in NODES:
        g.add_edge(n, "supervisor")
    return g.compile()


graph = build_graph()


def _init(event: str, req_id: int | None, payload: dict) -> State:
    return {"event": event, "run": uuid.uuid4().hex[:8], "req_id": req_id, "payload": payload, "result": {}}


def invoke(event: str, req_id: int | None = None, **payload) -> dict:
    """Run one event to completion and return what the agents produced. Raises AgentError on a refusal."""
    st = graph.invoke(_init(event, req_id, payload))
    if st.get("error"):
        raise AgentError(st["error"])
    return st.get("result", {})


def stream(event: str, req_id: int | None = None, **payload) -> Iterator[dict]:
    """Run one event and yield the live events agents emit (progress, text chunks, ...)."""
    yield from graph.stream(_init(event, req_id, payload), stream_mode="custom")


def structure() -> dict:
    """Graph layout for the UI and docs."""
    return {
        "agents": [{"id": k, "name": v[0], "does": v[1]} for k, v in AGENTS.items()],
        "plans": PLANS,
        "mermaid": graph.get_graph().draw_mermaid(),
    }
