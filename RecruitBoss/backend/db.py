"""Tiny SQLite store. Everything is kept as JSON blobs so the schema never gets in the way."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).resolve().parent.parent / "recruitboss.db"))
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS requisitions(
                id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, data TEXT);
            CREATE TABLE IF NOT EXISTS candidates(
                id INTEGER PRIMARY KEY AUTOINCREMENT, req_id INTEGER, data TEXT);
            CREATE TABLE IF NOT EXISTS meetings(
                id INTEGER PRIMARY KEY AUTOINCREMENT, req_id INTEGER, data TEXT);
            CREATE TABLE IF NOT EXISTS traces(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, run TEXT, req_id INTEGER, cand_id INTEGER,
                agent TEXT, text TEXT);
            """
        )


def _load(row) -> dict:
    d = json.loads(row["data"])
    d["id"] = row["id"]
    if "req_id" in row.keys():
        d["req_id"] = row["req_id"]
    return d


# ---- requisitions -------------------------------------------------------
def add_requisition(data: dict) -> dict:
    with _lock, _conn() as c:
        cur = c.execute("INSERT INTO requisitions(created,data) VALUES(?,?)", (time.time(), json.dumps(data)))
        data["id"] = cur.lastrowid
        data["created"] = time.time()
        c.execute("UPDATE requisitions SET data=? WHERE id=?", (json.dumps(data), cur.lastrowid))
    return data


def update_requisition(rid: int, patch: dict) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM requisitions WHERE id=?", (rid,)).fetchone()
        if not row:
            return None
        d = _load(row)
        d.update(patch)
        c.execute("UPDATE requisitions SET data=? WHERE id=?", (json.dumps(d), rid))
        return d


def get_requisition(rid: int) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM requisitions WHERE id=?", (rid,)).fetchone()
        return _load(row) if row else None


def list_requisitions() -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute("SELECT * FROM requisitions ORDER BY id DESC").fetchall()
        out = []
        for r in rows:
            d = _load(r)
            d["candidate_count"] = c.execute("SELECT COUNT(*) FROM candidates WHERE req_id=?", (r["id"],)).fetchone()[0]
            d["meeting_count"] = c.execute("SELECT COUNT(*) FROM meetings WHERE req_id=?", (r["id"],)).fetchone()[0]
            stages: dict = {}
            for (blob,) in c.execute("SELECT data FROM candidates WHERE req_id=?", (r["id"],)).fetchall():
                st = json.loads(blob).get("stage", "screened")
                stages[st] = stages.get(st, 0) + 1
            d["stages"] = stages
            out.append(d)
        return out


# ---- candidates ---------------------------------------------------------
def replace_candidates(rid: int, cands: list[dict]) -> list[dict]:
    with _lock, _conn() as c:
        c.execute("DELETE FROM candidates WHERE req_id=?", (rid,))
        c.execute("DELETE FROM meetings WHERE req_id=?", (rid,))  # old meetings point at old candidates
        out = []
        for cand in cands:
            cur = c.execute("INSERT INTO candidates(req_id,data) VALUES(?,?)", (rid, json.dumps(cand)))
            cand = dict(cand)
            cand["id"] = cur.lastrowid
            c.execute("UPDATE candidates SET data=? WHERE id=?", (json.dumps(cand), cur.lastrowid))
            out.append(cand)
        return out


def add_candidates(rid: int, cands: list[dict]) -> list[dict]:
    """Append a new batch without touching anyone already in the role."""
    with _lock, _conn() as c:
        out = []
        for cand in cands:
            cur = c.execute("INSERT INTO candidates(req_id,data) VALUES(?,?)", (rid, json.dumps(cand)))
            cand = dict(cand)
            cand["id"] = cur.lastrowid
            c.execute("UPDATE candidates SET data=? WHERE id=?", (json.dumps(cand), cur.lastrowid))
            out.append(cand)
        return out


def list_candidates(rid: int) -> list[dict]:
    with _lock, _conn() as c:
        rows = c.execute("SELECT * FROM candidates WHERE req_id=?", (rid,)).fetchall()
        out = [_load(r) for r in rows]
    out.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    return out


def get_candidate(cid: int) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
        return _load(row) if row else None


def update_candidate(cid: int, fn) -> dict | None:
    """Load a candidate, let `fn` change the dict in place, save it. Returns the saved dict."""
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
        if not row:
            return None
        d = _load(row)
        fn(d)
        c.execute("UPDATE candidates SET data=? WHERE id=?", (json.dumps(d), cid))
        return d


def get_candidates(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    with _lock, _conn() as c:
        q = ",".join("?" * len(ids))
        rows = c.execute(f"SELECT * FROM candidates WHERE id IN ({q})", ids).fetchall()
        return [_load(r) for r in rows]


# ---- meetings -----------------------------------------------------------
def add_meeting(rid: int, data: dict) -> dict:
    with _lock, _conn() as c:
        cur = c.execute("INSERT INTO meetings(req_id,data) VALUES(?,?)", (rid, json.dumps(data)))
        data = dict(data)
        data["id"] = cur.lastrowid
        data["req_id"] = rid
        c.execute("UPDATE meetings SET data=? WHERE id=?", (json.dumps(data), cur.lastrowid))
        return data


def list_meetings(rid: int | None = None) -> list[dict]:
    with _lock, _conn() as c:
        if rid is None:
            rows = c.execute("SELECT * FROM meetings").fetchall()
        else:
            rows = c.execute("SELECT * FROM meetings WHERE req_id=?", (rid,)).fetchall()
        out = [_load(r) for r in rows]
    out.sort(key=lambda m: m.get("start", ""))
    return out


def get_meeting(mid: int) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM meetings WHERE id=?", (mid,)).fetchone()
        return _load(row) if row else None


def delete_meeting(mid: int) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM meetings WHERE id=?", (mid,))


def update_meeting(mid: int, patch: dict) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM meetings WHERE id=?", (mid,)).fetchone()
        if not row:
            return None
        d = _load(row)
        d.update(patch)
        c.execute("UPDATE meetings SET data=? WHERE id=?", (json.dumps(d), mid))
        return d


# ---- agent activity trace ----------------------------------------------
def add_trace(run: str, req_id: int | None, cand_id: int | None, agent: str, text: str) -> None:
    with _lock, _conn() as c:
        c.execute("INSERT INTO traces(ts,run,req_id,cand_id,agent,text) VALUES(?,?,?,?,?,?)",
                  (time.time(), run, req_id, cand_id, agent, text))


def list_traces(req_id: int | None = None, limit: int = 60, after: int = 0) -> list[dict]:
    with _lock, _conn() as c:
        q, args = "SELECT * FROM traces WHERE id>?", [after]
        if req_id is not None:
            q += " AND req_id=?"
            args.append(req_id)
        rows = c.execute(q + " ORDER BY id DESC LIMIT ?", args + [limit]).fetchall()
        return [dict(r) for r in rows]
