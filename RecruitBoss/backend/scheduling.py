"""Interview slot planner + calendar (.ics) + invite text. Pure functions, easy to test."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

FMT = "%Y-%m-%dT%H:%M"


def _t(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _at(day: datetime, hhmm: str) -> datetime:
    h, m = _t(hhmm)
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def next_slot(cursor: datetime, dur: int, busy: list[tuple[datetime, datetime]], day_start: str, day_end: str,
              lunch_start: str | None, lunch_end: str | None, buffer: int) -> datetime:
    """Earliest start >= cursor on a weekday, inside working hours, outside lunch, clear of `busy`."""
    d = timedelta(minutes=dur)
    s = cursor
    for _ in range(2000):
        if s.weekday() >= 5:  # Sat/Sun -> Monday morning
            s = _at(s + timedelta(days=7 - s.weekday()), day_start)
            continue
        ds, de = _at(s, day_start), _at(s, day_end)
        if s < ds:
            s = ds
        if lunch_start and lunch_end:
            ls, le = _at(s, lunch_start), _at(s, lunch_end)
            if s < le and s + d > ls:
                s = le
                continue
        if s + d > de:
            s = _at(s + timedelta(days=1), day_start)
            continue
        clash = next(((bs, be) for bs, be in busy if s < be + timedelta(minutes=buffer) and s + d > bs - timedelta(minutes=buffer)), None)
        if clash:
            s = clash[1] + timedelta(minutes=buffer)
            continue
        return s
    raise RuntimeError("Could not find a free slot in the next few years. Check working hours.")


def plan(candidates: list[dict], interviewers: list[str], start: str, duration: int, buffer: int,
         day_start: str, day_end: str, lunch: bool, existing: Iterable[dict]) -> list[dict]:
    """Assign each candidate (already ordered best-first) to the interviewer who is free earliest."""
    interviewers = [i.strip() for i in interviewers if i and i.strip()] or ["Hiring manager"]
    first = datetime.strptime(start, FMT)
    busy: dict[str, list[tuple[datetime, datetime]]] = {i: [] for i in interviewers}
    for m in existing:
        if m.get("interviewer") in busy:
            busy[m["interviewer"]].append((datetime.strptime(m["start"], FMT), datetime.strptime(m["end"], FMT)))
    cursors = {i: first for i in interviewers}
    ls, le = ("13:00", "14:00") if lunch else (None, None)
    out = []
    for c in candidates:
        best = None
        for i in interviewers:
            s = next_slot(cursors[i], duration, busy[i], day_start, day_end, ls, le, buffer)
            if best is None or s < best[1]:
                best = (i, s)
        who, s = best
        e = s + timedelta(minutes=duration)
        busy[who].append((s, e))
        cursors[who] = e + timedelta(minutes=buffer)
        out.append({"candidate_id": c["id"], "candidate_name": c["name"], "candidate_email": c.get("email", ""),
                    "interviewer": who, "start": s.strftime(FMT), "end": e.strftime(FMT), "duration": duration})
    return out


# ---- calendar file ------------------------------------------------------
def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b
        else:
            cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def ics(meetings: list[dict], cal_name: str = "Interviews") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//RecruitBoss//Local//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_esc(cal_name)}"]
    for m in meetings:
        s = datetime.strptime(m["start"], FMT).strftime("%Y%m%dT%H%M%S")
        e = datetime.strptime(m["end"], FMT).strftime("%Y%m%dT%H%M%S")
        desc = f"Interview with {m['candidate_name']} for {m.get('role', '')}. Interviewer: {m['interviewer']}."
        if m.get("link"):
            desc += f" Join: {m['link']}"
        if m.get("notes"):
            desc += f" Notes: {m['notes']}"
        lines += ["BEGIN:VEVENT", f"UID:recruitboss-{m['id']}@local", f"DTSTAMP:{stamp}", f"DTSTART:{s}", f"DTEND:{e}",
                  f"SUMMARY:{_esc(m.get('round_name', 'Interview'))}: {_esc(m['candidate_name'])} - {_esc(m.get('role', ''))}",
                  f"DESCRIPTION:{_esc(desc)}", f"LOCATION:{_esc(m.get('link') or m.get('mode', ''))}"]
        if m.get("candidate_email"):
            lines.append(f"ATTENDEE;CN={_esc(m['candidate_name'])}:mailto:{m['candidate_email']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


# ---- invite text --------------------------------------------------------
def invite(m: dict, company: str = "our team") -> dict:
    s = datetime.strptime(m["start"], FMT)
    when = s.strftime("%A, %d %B %Y at %I:%M %p").replace(" 0", " ")
    where = m.get("link") or m.get("mode", "")
    subject = f"Interview invitation: {m.get('role', 'the role')} ({m.get('round_name', 'Interview')})"
    body = (
        f"Hi {m['candidate_name'].split()[0]},\n\n"
        f"Thank you for applying for the {m.get('role', 'open')} role. We'd like to invite you to a "
        f"{m['duration']}-minute {m.get('round_name', 'interview').lower()} with {m['interviewer']}.\n\n"
        f"When: {when}\nHow: {m.get('mode', '')}{(' - ' + m['link']) if m.get('link') else ''}\n\n"
        f"Please reply to confirm, or suggest another time if this doesn't work.\n\nBest regards,\n{company}"
    )
    return {"subject": subject, "body": body, "where": where}
