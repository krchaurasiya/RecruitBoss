"""Whole hiring lifecycle through the LangGraph agents, with Ollama switched off (rules + templates only)."""
import io, json, os, sys, tempfile, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "life.db")
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"

import pytest
from fastapi.testclient import TestClient
from backend.main import app

SAMPLE = ROOT / "sample_data" / "sample_candidates.zip"
BRIEF = {"title": "Data Scientist", "seniority": "Mid-level", "department": "Data", "must_skills": ["Python", "SQL"],
         "nice_skills": ["NLP"], "min_exp": 2, "max_exp": 6, "education": "Bachelor's", "location": "Panaji", "work_mode": "Hybrid",
         "salary_min": 1000000, "salary_max": 1500000, "rounds": ["Screening call", "Technical interview"]}
c = TestClient(app)


def screen(rid, name="s.zip", data=None):
    data = data or SAMPLE.read_bytes()
    r = c.post(f"/api/requisitions/{rid}/screen", files={"file": (name, data)}, data={"depth": "fast"})
    return [json.loads(l) for l in r.text.splitlines()]


@pytest.fixture(scope="module")
def world():
    role = c.post("/api/requisitions", json=BRIEF).json()
    cands = screen(role["id"])[-1]["candidates"]
    ok = [x for x in cands if x["email"] and "@" in x["email"] and "." in x["email"].split("@")[-1] and x["email"] != "not-an-email"]
    return {"rid": role["id"], "cands": cands, "ok": ok}


def test_graph_structure_and_supervisor_trace(world):
    g = c.get("/api/agents").json()
    assert len(g["agents"]) == 13 and "supervisor" in g["mermaid"] and "offer_management" in g["mermaid"]
    tr = c.get("/api/traces", params={"req_id": world["rid"]}).json()
    names = {t["agent"] for t in tr}
    assert {"Supervisor", "Sourcing Agent", "Resume Intelligence Agent", "Matching Agent"} <= names
    sup = [t for t in tr if t["agent"] == "Supervisor"]
    assert any("Sourcing Agent → Resume Intelligence Agent → Matching Agent" in t["text"] for t in sup)


def test_revise_role_in_place_and_jd_and_postings(world):
    rid = world["rid"]
    before = len(c.get("/api/requisitions").json())
    r = c.put(f"/api/requisitions/{rid}", json={**BRIEF, "openings": 3}).json()
    assert r["id"] == rid and r["openings"] == 3 and len(c.get("/api/requisitions").json()) == before   # revised, not duplicated
    text = c.post(f"/api/requisitions/{rid}/jd").text            # no Ollama -> template
    assert "Data Scientist" in text and c.get(f"/api/requisitions/{rid}").json()["jd"] == text
    posts = c.post(f"/api/requisitions/{rid}/postings", json={}).json()
    assert [p["key"] for p in posts] == ["linkedin", "careers", "portal", "referral"] and all(len(p["text"]) > 20 for p in posts)
    assert c.post(f"/api/requisitions/{rid}/approve").json()["status"] == "approved"
    plan = c.post(f"/api/requisitions/{rid}/interview-plan", json={}).json()
    assert [r["name"] for r in plan] == BRIEF["rounds"] and all(r["questions"] and r["criteria"] for r in plan)


def test_full_lifecycle(world):
    rid, ok = world["rid"], world["ok"]
    a, b, d = ok[0], ok[1], ok[2]
    # shortlist + schedule
    assert c.post(f"/api/requisitions/{rid}/shortlist", json={"candidate_ids": [a["id"], b["id"], d["id"]]}).json()["shortlisted"] == 3
    body = {"candidate_ids": [a["id"], b["id"]], "interviewers": ["Asha"], "start": "2026-11-23T10:00"}
    ms = c.post(f"/api/requisitions/{rid}/schedule", json=body).json()
    assert len(ms) == 2 and c.get(f"/api/candidates/{a['id']}").json()["stage"] == "interviewing"
    # decision / offer too early are refused with a clear message
    r = c.post(f"/api/candidates/{a['id']}/decision", json={"action": "approve"})
    assert r.status_code == 400 and "feedback" in r.json()["detail"]
    r = c.post(f"/api/candidates/{a['id']}/offer/send", json={})
    assert r.status_code == 400
    # bad rating refused
    bad = c.post(f"/api/candidates/{a['id']}/scorecard", json={"ratings": {"Skill": 9}, "recommendation": "Hire"})
    assert bad.status_code == 400 and "1 to 5" in bad.json()["detail"]
    # good feedback -> evaluated
    sc = {"meeting_id": ms[0]["id"], "interviewer": "Asha", "round_name": "Screening call",
          "ratings": {"Technical depth": 5, "Communication": 4, "Problem solving": 4}, "recommendation": "Strong hire", "notes": "Sharp."}
    ev = c.post(f"/api/candidates/{a['id']}/scorecard", json=sc).json()
    assert ev["stage"] == "evaluated" and ev["evaluation"]["recommendation"] == "Hire" and ev["evaluation"]["overall"] == 4.33
    assert [m for m in c.get("/api/meetings", params={"req_id": rid}).json() if m["id"] == ms[0]["id"]][0]["status"] == "completed"
    # second candidate: weak feedback -> reject with email
    ev2 = c.post(f"/api/candidates/{b['id']}/scorecard", json={"ratings": {"Technical depth": 2, "Communication": 2}, "recommendation": "No hire"}).json()
    assert ev2["evaluation"]["recommendation"] == "No hire"
    rej = c.post(f"/api/candidates/{b['id']}/decision", json={"action": "reject", "feedback": "We need deeper SQL."}).json()
    assert rej["emails"][0]["subject"].startswith("Your application") and "deeper SQL" in rej["emails"][0]["body"]
    assert c.get(f"/api/candidates/{b['id']}").json()["stage"] == "rejected"
    # approve a -> offer drafted automatically by the Offer Management Agent (salary = pay band middle)
    off = c.post(f"/api/candidates/{a['id']}/decision", json={"action": "approve", "notes": "Great"}).json()["candidate"]
    assert off["stage"] == "offer_draft" and off["offer"]["salary"] == 1250000 and "Dear" in off["offer"]["letter"]
    upd = c.post(f"/api/candidates/{a['id']}/offer/update", json={"salary": 1300000, "joining_date": "2026-12-15", "extra_terms": "Probation as per policy."}).json()["candidate"]
    assert "13,00,000" not in upd["offer"]["letter"] and "1,300,000" in upd["offer"]["letter"] and "15 December 2026" in upd["offer"]["letter"]
    assert c.post(f"/api/candidates/{a['id']}/offer/send", json={}).status_code == 400          # not approved yet
    assert c.post(f"/api/candidates/{a['id']}/offer/submit", json={}).json()["candidate"]["stage"] == "offer_pending"
    assert c.post(f"/api/candidates/{a['id']}/offer/update", json={"salary": 1}).status_code == 400   # locked while pending
    back = c.post(f"/api/candidates/{a['id']}/offer/revise", json={"comment": "Too high"}).json()["candidate"]
    assert back["stage"] == "offer_draft" and back["offer"]["comment"] == "Too high"
    c.post(f"/api/candidates/{a['id']}/offer/submit", json={})
    ap = c.post(f"/api/candidates/{a['id']}/offer/approve", json={"approver": "Meera (HR)"}).json()["candidate"]
    assert ap["stage"] == "offer_approved" and ap["offer"]["approved_by"] == "Meera (HR)"
    sent = c.post(f"/api/candidates/{a['id']}/offer/send", json={}).json()["candidate"]
    assert sent["stage"] == "offer_sent" and sent["offer"]["email"]["subject"].startswith("Offer of employment")
    assert c.post(f"/api/requisitions/{rid}/reject", json={"candidate_ids": [a["id"]]}).status_code == 400   # can't reject after offer
    # accept -> onboarding agent chained automatically
    acc = c.post(f"/api/candidates/{a['id']}/offer/accept", json={}).json()["candidate"]
    ob = acc["onboarding"]
    assert acc["stage"] == "onboarding" and ob["employee"]["employee_id"].startswith("EMP-") and len(ob["checklist"]) == 8 and "Welcome" in ob["welcome"]["subject"]
    for t in ob["checklist"]:
        last = c.post(f"/api/candidates/{a['id']}/onboarding/toggle", json={"task_id": t["id"], "done": True}).json()
    assert last["stage"] == "joined" and last["onboarding"]["employee"]["status"] == "Active"
    undo = c.post(f"/api/candidates/{a['id']}/onboarding/toggle", json={"task_id": "docs", "done": False}).json()
    assert undo["stage"] == "onboarding"
    c.post(f"/api/candidates/{a['id']}/onboarding/toggle", json={"task_id": "docs", "done": True})
    # third candidate: more interviews loop, then offer declined -> next best suggested
    c.post(f"/api/candidates/{d['id']}/scorecard", json={"ratings": {"Technical depth": 3}, "recommendation": "Hold"})
    more = c.post(f"/api/candidates/{d['id']}/decision", json={"action": "more", "notes": "Need a technical round"}).json()["candidate"]
    assert more["stage"] == "shortlisted" and more["needs_more"]
    # analytics
    an = c.get(f"/api/requisitions/{rid}/analytics").json()
    f = {x["key"]: x["count"] for x in an["funnel"]}
    assert f["interviewed"] == 3 and f["offered"] == 1 and f["accepted"] == 1 and f["joined"] == 1
    assert an["offer_acceptance"] == 100 and an["filled"] == 1 and an["rejected"] == 1 and an["time_to_hire_days"] is not None and an["interviews_done"] == 1
    closed = c.post(f"/api/requisitions/{rid}/close").json()
    assert closed["role"]["status"] == "closed" and closed["analytics"]["filled"] == 1
    # every step left an agent trace
    agents_seen = {t["agent"] for t in c.get("/api/traces", params={"req_id": rid, "limit": 200}).json()}
    for n in ["Evaluation Agent", "Hiring Decision Gate", "Offer Management Agent", "Communication Agent", "Onboarding Agent",
              "Closure Agent", "Scheduling Agent", "Shortlisting Agent", "Interview Planning Agent", "Requisition Agent", "Sourcing Agent"]:
        assert n in agents_seen, n


def test_decline_suggests_next_best():
    role = c.post("/api/requisitions", json=BRIEF).json()
    cands = [x for x in screen(role["id"])[-1]["candidates"] if x["email"] and x["email"] != "not-an-email"]
    top = cands[0]
    c.post(f"/api/candidates/{top['id']}/scorecard", json={"ratings": {"A": 5}, "recommendation": "Hire"})
    c.post(f"/api/candidates/{top['id']}/decision", json={"action": "approve"})
    c.post(f"/api/candidates/{top['id']}/offer/update", json={"salary": 900000})
    for a in ("submit", "approve", "send"):
        c.post(f"/api/candidates/{top['id']}/offer/{a}", json={})
    d = c.post(f"/api/candidates/{top['id']}/offer/decline", json={}).json()
    assert d["candidate"]["stage"] == "declined" and d["next_best"]["id"] == cands[1]["id"]


def test_resume_files_in_zip():
    from docx import Document
    from reportlab.pdfgen import canvas
    role = c.post("/api/requisitions", json=BRIEF).json()
    d = Document(); d.add_paragraph("Rhea Kamat"); d.add_paragraph("rhea.kamat@example.com | 9876543210")
    d.add_paragraph("Data scientist with 4 years of experience in Python, SQL and NLP. B.Tech in Computer Science. Based in Panaji.")
    buf = io.BytesIO(); d.save(buf)
    pdf = io.BytesIO(); cv = canvas.Canvas(pdf)
    for i, line in enumerate(["Tarun Naik", "tarun.naik@example.com", "6 years experience building Python and SQL pipelines for analytics teams.", "M.Sc Statistics"]):
        cv.drawString(72, 760 - 18 * i, line)
    cv.save()
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("rhea_kamat.docx", buf.getvalue()); zf.writestr("tarun.pdf", pdf.getvalue())
        zf.writestr("note.txt", "Sam Fernandes\nsam@example.com\n2 years of Excel and SQL work. Bachelor of Commerce.\n" + "x" * 10)
        zf.writestr("photo.png", b"\x89PNG")
    evs = screen(role["id"], "resumes.zip", z.getvalue())
    cands = {x["name"]: x for x in evs[-1]["candidates"]}
    assert {"Rhea Kamat", "Tarun Naik", "Sam Fernandes"} <= set(cands)
    r = cands["Rhea Kamat"]
    assert r["email"] == "rhea.kamat@example.com" and r["experience"] == 4 and "Python" in r["skills"] and r["missing_must"] == []
    assert cands["Tarun Naik"]["experience"] == 6 and cands["Tarun Naik"]["edu_level"] == 3
    msgs = " ".join(i["message"] for i in evs[0]["report"]["issues"])
    assert "photo.png" in msgs and "Resume files were read as text" in msgs


def test_second_upload_adds_without_disturbing_pipeline():
    role = c.post("/api/requisitions", json=BRIEF).json()
    first = screen(role["id"])[-1]["candidates"]
    top = [x for x in first if x["email"] and x["email"] != "not-an-email"][0]
    c.post(f"/api/requisitions/{role['id']}/shortlist", json={"candidate_ids": [top["id"]]})
    again = screen(role["id"])                                    # same file: nobody new
    assert again[-1]["type"] == "error" and "already in this role" in again[-1]["message"]
    csv = "Name,Email,Skills,Experience\nNew Person,new.person@example.com,\"Python, SQL\",4\n" + f"{top['name']},{top['email']},Python,3\n"
    evs = screen(role["id"], "more.csv", csv.encode())
    done = evs[-1]
    assert done["type"] == "done" and len(done["candidates"]) == len(first) + 1
    assert [x for x in done["candidates"] if x["id"] == top["id"]][0]["stage"] == "shortlisted"   # untouched
