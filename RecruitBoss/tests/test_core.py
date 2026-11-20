import os, sys, json, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "t.db")
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"   # nothing listens here -> rules-only path

from datetime import datetime
from fastapi.testclient import TestClient
from backend import screening as S, scheduling as P
from backend.main import app

REQ = {"title": "Data Scientist", "seniority": "Mid-level", "department": "Data", "must_skills": ["Python", "SQL", "ML"],
       "nice_skills": ["NLP"], "min_exp": 2, "max_exp": 6, "education": "Bachelor's", "location": "Panaji",
       "work_mode": "Hybrid", "max_notice_days": 30}
SAMPLE = ROOT / "sample_data" / "sample_candidates.zip"


def test_column_mapping_and_parsers():
    m, un = S.map_columns(["Candidate", "E-mail", "Experience (yrs)", "Key Skills", "Weird"])
    assert m["name"] == "Candidate" and m["email"] == "E-mail" and m["experience"] == "Experience (yrs)"
    assert m["skills"] == "Key Skills" and un == ["Weird"]
    assert S.parse_years("5 yrs") == 5 and S.parse_years("6 months") == 0.5 and S.parse_years("a lot") is None
    assert S.parse_notice_days("2 months") == 60 and S.parse_notice_days("Immediate") == 0
    assert S.parse_edu("M.Sc Data Science") == 3 and S.parse_edu("B.Tech") == 2 and S.parse_edu("PhD") == 4


def test_synonyms_score_higher_than_missing():
    base = dict(name="A", email="a@x.com", skills=["python", "sql", "machine learning"], experience=3, education="B.Tech",
                edu_level=2, location="Panaji", notice_days=15, notice_raw="15", resume="", role="", extra={})
    good = S.rule_score(base, REQ)
    assert good["missing_must"] == [] and good["rule_score"] >= 85
    bad = S.rule_score({**base, "skills": ["photoshop"], "experience": 0.5, "location": "Delhi", "notice_days": 90}, REQ)
    assert bad["rule_score"] < 35 and "Python" in bad["missing_must"]


def test_zip_check_report_catches_mess():
    files, docs, w = S.read_inputs("s.zip", SAMPLE.read_bytes())
    cands, rep = S.build_candidates(files, w, docs, REQ)
    msgs = " ".join(i["message"] for i in rep["issues"])
    assert rep["total_rows"] == 42 and rep["duplicates_removed"] == 1
    assert "no name" in msgs and "invalid" in msgs and "can't be invited" in msgs
    assert all(f["mapped"].get("name") for f in rep["files"])  # both header styles recognised


def test_bad_zip_is_a_clean_error():
    c = TestClient(app)
    r = c.post("/api/requisitions", json=REQ).json()
    resp = c.post(f"/api/requisitions/{r['id']}/screen", files={"file": ("x.zip", b"not a zip")}, data={"depth": "fast"})
    evs = [json.loads(l) for l in resp.text.splitlines()]
    assert evs[-1]["type"] == "error" and "valid .zip" in evs[-1]["message"]


def test_scheduler_rules():
    cands = [{"id": i, "name": f"C{i}", "email": ""} for i in range(1, 9)]
    # Friday 2026-11-20 16:00 start -> must roll to Monday, never touch lunch or weekend
    slots = P.plan(cands, ["Asha", "Ravi"], "2026-11-20T16:00", 45, 15, "10:00", "18:00", True, [])
    for s in slots:
        a, b = datetime.strptime(s["start"], P.FMT), datetime.strptime(s["end"], P.FMT)
        assert a.weekday() < 5 and 10 <= a.hour and (b.hour, b.minute) <= (18, 0)
        assert not (a.hour * 60 + a.minute < 14 * 60 and b.hour * 60 + b.minute > 13 * 60)
    # one interviewer never double booked
    for who in ("Asha", "Ravi"):
        mine = sorted((s["start"], s["end"]) for s in slots if s["interviewer"] == who)
        assert all(mine[i][1] <= mine[i + 1][0] for i in range(len(mine) - 1))
    assert {s["interviewer"] for s in slots} == {"Asha", "Ravi"}
    # existing booking is respected
    ex = [{"interviewer": "Asha", "start": "2026-11-23T10:00", "end": "2026-11-23T11:00"}]
    one = P.plan(cands[:1], ["Asha"], "2026-11-23T10:00", 45, 15, "10:00", "18:00", True, ex)[0]
    assert one["start"] >= "2026-11-23T11:15"


def test_ics_is_valid_shape():
    m = {"id": 1, "candidate_name": "A, B", "candidate_email": "a@x.com", "interviewer": "Asha", "role": "DS",
         "start": "2026-11-23T10:00", "end": "2026-11-23T10:45", "link": "https://meet.example/x", "round_name": "Screening"}
    t = P.ics([m])
    assert t.startswith("BEGIN:VCALENDAR") and "DTSTART:20261123T100000" in t and "A\\, B" in t and t.endswith("\r\n")


def test_api_end_to_end_without_ollama():
    c = TestClient(app)
    assert c.get("/api/health").json()["online"] is False
    r = c.post("/api/requisitions", json=REQ).json()
    with SAMPLE.open("rb") as f:
        resp = c.post(f"/api/requisitions/{r['id']}/screen", files={"file": ("s.zip", f)}, data={"depth": "balanced"})
    evs = [json.loads(l) for l in resp.text.splitlines()]
    assert [e["type"] for e in evs][0] == "check" and evs[-1]["type"] == "done" and evs[-1]["ai_used"] is False
    cands = evs[-1]["candidates"]
    assert len(cands) == 36 + 5 - 1 - 1 - 0 or len(cands) > 30
    scores = [x["final_score"] for x in cands]
    assert scores == sorted(scores, reverse=True) and all("id" in x for x in cands)
    ids = [x["id"] for x in cands if x["email"]][:5]
    body = {"candidate_ids": ids, "interviewers": ["Asha"], "start": "2026-11-23T10:00"}
    prev = c.post(f"/api/requisitions/{r['id']}/schedule/preview", json=body).json()
    assert len(prev) == 5 and c.get("/api/meetings").json() == []     # preview saves nothing
    made = c.post(f"/api/requisitions/{r['id']}/schedule", json=body).json()
    assert len(made) == 5 and made[0]["invite"]["subject"]
    assert c.get(f"/api/meetings/{made[0]['id']}.ics").text.startswith("BEGIN:VCALENDAR")
    assert len(c.get("/api/calendar.ics").text.split("BEGIN:VEVENT")) == 6
    again = c.post(f"/api/requisitions/{r['id']}/schedule", json=body).json()   # conflicts avoided
    assert min(m["start"] for m in again) > max(m["start"] for m in made) or all(a["start"] != b["start"] for a in again for b in made)
    c.delete(f"/api/meetings/{made[0]['id']}")
    assert len(c.get("/api/meetings").json()) == 9
