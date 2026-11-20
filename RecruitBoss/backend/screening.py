"""Reads a zip of candidate CSVs, checks the data, scores every candidate against the brief.

Two layers, on purpose:
  1. Transparent rules (skills, experience, education, location, notice) -> always works, always explainable.
  2. The local Ollama model reads each profile and writes a short assessment -> adds judgement and wording.
The final score blends both. If Ollama is off, the rules score is used on its own and the UI says so.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from . import llm

MAX_ZIP_BYTES = 40 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_CANDIDATES = 500

# ---- column detection ---------------------------------------------------
ALIASES = {
    "name": ["name", "full name", "candidate", "candidate name", "applicant", "applicant name"],
    "email": ["email", "e mail", "email id", "email address", "mail"],
    "phone": ["phone", "mobile", "contact", "phone number", "mobile number"],
    "skills": ["skills", "skill set", "skillset", "key skills", "technologies", "tech stack", "primary skills"],
    "experience": ["experience", "years of experience", "yoe", "exp", "total experience", "experience years",
                   "experience yrs", "years experience", "total exp"],
    "education": ["education", "qualification", "degree", "highest education", "highest qualification"],
    "role": ["current role", "role", "title", "designation", "current title", "position", "job title"],
    "company": ["company", "current company", "employer", "organization", "organisation"],
    "location": ["location", "city", "current location", "current city", "place"],
    "notice": ["notice", "notice period", "notice days", "notice period days", "availability"],
    "salary": ["expected ctc", "expected salary", "ectc", "expected", "salary expectation", "expected compensation"],
    "resume": ["resume", "resume text", "summary", "profile", "about", "bio", "profile summary", "experience summary",
               "cv", "description"],
}


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (h or "").lower())).strip()


def map_columns(headers: list[str]) -> tuple[dict, list[str]]:
    normed = {h: _norm_header(h) for h in headers}
    mapping: dict[str, str] = {}
    used = set()
    for field, names in ALIASES.items():
        for h, n in normed.items():
            if h in used:
                continue
            if n in names:
                mapping[field] = h
                used.add(h)
                break
    unmapped = [h for h in headers if h not in used and h]
    return mapping, unmapped


# ---- value parsing ------------------------------------------------------
SYNONYMS = {
    "javascript": ["javascript", "js", "ecmascript"],
    "typescript": ["typescript", "ts"],
    "react": ["react", "reactjs", "react.js"],
    "nodejs": ["nodejs", "node.js", "node"],
    "python": ["python", "py"],
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning", "dl"],
    "postgresql": ["postgresql", "postgres"],
    "kubernetes": ["kubernetes", "k8s"],
    "scikit-learn": ["scikit-learn", "scikit learn", "sklearn"],
    "tensorflow": ["tensorflow", "tf"],
    "natural language processing": ["natural language processing", "nlp"],
    "large language models": ["large language models", "llm", "llms"],
    "amazon web services": ["amazon web services", "aws"],
    "google cloud": ["google cloud", "gcp"],
    "ci/cd": ["ci/cd", "cicd", "ci cd"],
    "c++": ["c++", "cpp"],
    "c#": ["c#", "csharp"],
    "sql": ["sql"],
    "mongodb": ["mongodb", "mongo"],
    "power bi": ["power bi", "powerbi"],
    "excel": ["excel", "ms excel"],
}
_VARIANT_TO_CANON = {v: c for c, vs in SYNONYMS.items() for v in vs}


def canon_skill(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip().lower())
    return _VARIANT_TO_CANON.get(s, s)


def variants(skill: str) -> list[str]:
    c = canon_skill(skill)
    return SYNONYMS.get(c, [c])


def _has_term(text: str, term: str) -> bool:
    if not term:
        return False
    return re.search(r"(?<![a-z0-9+#])" + re.escape(term) + r"(?![a-z0-9+#])", text) is not None


def split_skills(s: str) -> list[str]:
    parts = re.split(r"[,;|/\n]+", s or "")
    out, seen = [], set()
    for p in parts:
        p = p.strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def parse_years(s: str) -> float | None:
    if s is None:
        return None
    s = str(s).strip().lower()
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    v = float(m.group(0))
    if "month" in s or re.search(r"\bmo\b", s):
        v = v / 12
    return round(v, 1)


def parse_notice_days(s: str) -> int | None:
    if not s:
        return None
    t = str(s).strip().lower()
    if re.search(r"immediate|now|none|zero|ready", t):
        return 0
    m = re.search(r"\d+(?:\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0))
    if "month" in t:
        v *= 30
    elif "week" in t:
        v *= 7
    return int(v)


EDU_LEVELS = {0: "Any", 1: "Diploma", 2: "Bachelor's", 3: "Master's", 4: "PhD"}
EDU_FROM_LABEL = {"Any": 0, "Diploma": 1, "Bachelor's": 2, "Master's": 3, "PhD": 4}
_EDU_PATTERNS = [
    (4, r"\b(ph\.?d|doctorate|doctoral)\b"),
    (3, r"\b(master|m\.?tech|m\.?sc|m\.?s|mba|m\.?e|mca|m\.?a|m\.?com|pgdm|post ?graduate)\b"),
    (2, r"\b(bachelor|b\.?tech|b\.?sc|b\.?e|bca|b\.?a|b\.?com|bba|graduate|undergraduate|b\.?s)\b"),
    (1, r"\b(diploma|polytechnic|associate)\b"),
]


def parse_edu(s: str) -> int | None:
    t = (s or "").lower()
    if not t.strip():
        return None
    for lvl, pat in _EDU_PATTERNS:
        if re.search(pat, t):
            return lvl
    return None


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---- reading the zip ----------------------------------------------------
def _decode(b: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:  # noqa: BLE001
            continue
    return b.decode("utf-8", errors="replace")


DOC_EXT = (".pdf", ".docx", ".txt", ".md")
MAX_UNZIPPED = 200 * 1024 * 1024


def extract_text(name: str, data: bytes) -> str:
    """Pull plain text out of a resume file. Raises ValueError if it can't be read."""
    low = name.lower()
    try:
        if low.endswith(".pdf"):
            from pypdf import PdfReader
            r = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in r.pages[:12]).strip()
        if low.endswith(".docx"):
            from docx import Document
            d = Document(io.BytesIO(data))
            parts = [p.text for p in d.paragraphs]
            for t in d.tables:
                for row in t.rows:
                    parts.append(" ".join(c.text for c in row.cells))
            return "\n".join(parts).strip()
        return _decode(data).strip()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"couldn't read {name}: {str(exc)[:80]}") from exc


def read_inputs(filename: str, data: bytes) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[str]]:
    """Return ([(csv_name, text)], [(resume_name, text)], warnings). Accepts a .zip or one .csv / resume file."""
    warnings: list[str] = []
    files: list[tuple[str, str]] = []
    docs: list[tuple[str, str]] = []
    if len(data) > MAX_ZIP_BYTES:
        raise ValueError("That file is larger than 40 MB. Split the candidates into smaller zips.")
    low = filename.lower()
    if low.endswith(".csv"):
        return [(filename, _decode(data))], docs, warnings
    if low.endswith(DOC_EXT):
        try:
            return files, [(filename, extract_text(filename, data))], warnings
        except ValueError as exc:
            raise ValueError(str(exc).capitalize()) from exc
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("That isn't a valid .zip file. Upload a zip that contains .csv files.") from exc
    total = 0
    for info in z.infolist():
        name = info.filename
        if info.is_dir() or name.startswith("__MACOSX") or name.split("/")[-1].startswith("."):
            continue
        ext = "." + name.lower().rsplit(".", 1)[-1] if "." in name else ""
        if ext != ".csv" and ext not in DOC_EXT:
            warnings.append(f"Skipped {name} (not a CSV or resume file).")
            continue
        total += info.file_size
        if info.file_size > MAX_FILE_BYTES or total > MAX_UNZIPPED:
            warnings.append(f"Skipped {name} (too large).")
            continue
        raw = z.read(info)
        if ext == ".csv":
            files.append((name, _decode(raw)))
        else:
            try:
                txt = extract_text(name, raw)
                if len(txt) < 40:
                    warnings.append(f"{name} has almost no readable text (scanned image?). Skipped.")
                else:
                    docs.append((name, txt))
            except ValueError as exc:
                warnings.append(f"Skipped: {exc}.")
    if not files and not docs:
        raise ValueError("No .csv or resume files (.pdf, .docx, .txt) found inside the zip.")
    return files, docs, warnings


def parse_rows(text: str) -> tuple[list[str], list[dict]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except Exception:  # noqa: BLE001
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [h.strip() for h in (reader.fieldnames or []) if h is not None]
    rows = []
    for r in reader:
        clean = {(k or "").strip(): (v or "").strip() if isinstance(v, str) else "" for k, v in r.items() if k is not None}
        if any(clean.values()):
            rows.append(clean)
    return headers, rows


# ---- data check ---------------------------------------------------------
def build_candidates(files: list[tuple[str, str]], warnings: list[str], docs: list[tuple[str, str]] | None = None, req: dict | None = None) -> tuple[list[dict], dict]:
    report = {"files": [], "total_rows": 0, "usable": 0, "duplicates_removed": 0, "issues": []}
    issues: dict[str, dict] = {}

    def issue(key: str, severity: str, msg: str, who: str = ""):
        it = issues.setdefault(key, {"severity": severity, "message": msg, "count": 0, "examples": []})
        it["count"] += 1
        if who and len(it["examples"]) < 4:
            it["examples"].append(who)

    for w in warnings:
        issue("warn:" + w, "info", w)

    cands: list[dict] = []
    seen_emails: dict[str, str] = {}
    for fname, text in files:
        headers, rows = parse_rows(text)
        mapping, unmapped = map_columns(headers)
        finfo = {"name": fname, "rows": len(rows), "mapped": mapping, "unmapped": unmapped}
        report["files"].append(finfo)
        report["total_rows"] += len(rows)
        if "name" not in mapping or not ({"skills", "resume", "role"} & set(mapping)):
            finfo["skipped"] = True
            issue("nofile:" + fname, "error",
                  f"{fname}: couldn't find a name column and a skills/resume column, so the file was skipped.")
            continue
        for i, r in enumerate(rows, start=2):  # row 1 is the header
            g = lambda f: r.get(mapping[f], "") if f in mapping else ""  # noqa: E731
            name = g("name")
            label = name or f"{fname} row {i}"
            if not name:
                issue("noname", "error", "Rows with no name were dropped.", f"{fname} row {i}")
                continue
            email = g("email").strip()
            if not email:
                issue("noemail", "warn", "No email — can be screened but can't be invited.", label)
            elif not EMAIL_RE.match(email):
                issue("bademail", "warn", "Email looks invalid — fix it before sending invites.", f"{name} ({email})")
            else:
                key = email.lower()
                if key in seen_emails:
                    report["duplicates_removed"] += 1
                    issue("dup", "info", "Duplicate emails merged (first row kept).", f"{name} = {seen_emails[key]}")
                    continue
                seen_emails[key] = name
            skills = split_skills(g("skills"))
            resume = g("resume")
            if not skills and not resume:
                issue("noskills", "warn", "No skills and no resume text — scores will be low.", label)
            exp_raw = g("experience")
            exp = parse_years(exp_raw)
            if exp_raw and exp is None:
                issue("badexp", "warn", "Experience isn't a number, treated as unknown.", f"{name} ({exp_raw})")
            if not exp_raw:
                issue("noexp", "info", "Experience missing for some rows.", label)
            edu_raw = g("education")
            cands.append({
                "name": name, "email": email, "phone": g("phone"), "role": g("role"), "company": g("company"),
                "location": g("location"), "skills": skills, "experience": exp, "education": edu_raw,
                "edu_level": parse_edu(edu_raw), "notice_days": parse_notice_days(g("notice")),
                "notice_raw": g("notice"), "expected_salary": g("salary"), "resume": resume,
                "source_file": fname, "row": i,
                "extra": {k: v for k, v in r.items() if k in unmapped and v},
            })
            if len(cands) >= MAX_CANDIDATES:
                issue("cap", "warn", f"Stopped at {MAX_CANDIDATES} candidates.")
                break
    for dname, text in docs or []:
        c = doc_candidate(dname, text, req or {})
        report["files"].append({"name": dname, "rows": 1, "mapped": {"resume": "whole file"}, "unmapped": [], "document": True})
        report["total_rows"] += 1
        if not c["email"]:
            issue("noemail", "warn", "No email — can be screened but can't be invited.", c["name"])
        else:
            key = c["email"].lower()
            if key in seen_emails:
                report["duplicates_removed"] += 1
                issue("dup", "info", "Duplicate emails merged (first row kept).", f"{c['name']} = {seen_emails[key]}")
                continue
            seen_emails[key] = c["name"]
        issue("docs", "info", "Resume files were read as text. Details are best-effort — verify them.", c["name"])
        cands.append(c)
    order = {"error": 0, "warn": 1, "info": 2}
    report["issues"] = sorted(issues.values(), key=lambda x: order[x["severity"]])
    report["usable"] = len(cands)
    return cands, report


# ---- resume files -------------------------------------------------------
_PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){9,11}\d(?!\d)")
_EMAIL_FIND = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_YEARS = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years|yrs)", re.I)
VOCAB = sorted({v for vs in SYNONYMS.values() for v in vs if len(v) > 2} | {
    "java", "docker", "git", "linux", "pandas", "numpy", "pytorch", "fastapi", "django", "flask", "html", "css",
    "tableau", "statistics", "figma", "selenium", "terraform", "redis", "spark", "hadoop", "airflow", "communication"})


def doc_candidate(fname: str, text: str, req: dict) -> dict:
    """Best-effort candidate from a resume's raw text. The AI can improve it later; this never needs Ollama."""
    stem = re.sub(r"[_\-.]+", " ", fname.rsplit("/", 1)[-1].rsplit(".", 1)[0]).strip()
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    name = first if 2 <= len(first.split()) <= 4 and len(first) < 40 and "@" not in first and not re.search(r"\d", first) else stem.title()
    m = _EMAIL_FIND.search(text)
    ph = _PHONE.search(text)
    low = text.lower()
    wanted = list(req.get("must_skills", [])) + list(req.get("nice_skills", []))
    found = []
    for sk in wanted + VOCAB:
        if any(_has_term(low, v) for v in variants(sk)) and canon_skill(sk) not in {canon_skill(x) for x in found}:
            found.append(sk)
    yrs = [float(x) for x in _YEARS.findall(text)]
    edu = next((l.strip() for l in text.splitlines() if parse_edu(l) and len(l) < 120), "")
    return {
        "name": name, "email": m.group(0) if m else "", "phone": ph.group(0).strip() if ph else "", "role": "", "company": "",
        "location": "", "skills": found[:25], "experience": max(yrs) if yrs else None, "education": edu,
        "edu_level": parse_edu(edu), "notice_days": None, "notice_raw": "", "expected_salary": "",
        "resume": text[:6000], "source_file": fname, "row": 0, "extra": {}, "from_document": True,
    }


EXTRACT_SYSTEM = (
    "You extract facts from ONE resume. Use only what is written; never guess and never use protected traits. "
    'Reply with one JSON object: {"name": "", "email": "", "current_role": "", "location": "", '
    '"experience_years": <number or null>, "education": "", "skills": ["max 15 short items"]}'
)


def llm_extract(c: dict, model: str) -> bool:
    """Fill gaps in a document candidate using the local model. Returns True if it helped."""
    out = llm.chat_json(model, EXTRACT_SYSTEM, "RESUME:\n" + c["resume"][:3500])
    if not out:
        return False
    if out.get("current_role") and not c["role"]:
        c["role"] = str(out["current_role"])[:80]
    if out.get("location") and not c["location"]:
        c["location"] = str(out["location"])[:60]
    if out.get("experience_years") not in (None, "") and c["experience"] is None:
        c["experience"] = parse_years(str(out["experience_years"]))
    if out.get("education") and not c["education"]:
        c["education"] = str(out["education"])[:80]
        c["edu_level"] = parse_edu(c["education"])
    if out.get("email") and not c["email"] and EMAIL_RE.match(str(out["email"])):
        c["email"] = str(out["email"])
    if isinstance(out.get("skills"), list):
        have = {canon_skill(x) for x in c["skills"]}
        for sk in out["skills"][:15]:
            if sk and canon_skill(str(sk)) not in have:
                c["skills"].append(str(sk)[:40])
    return True


# ---- rules scoring ------------------------------------------------------
W = {"skills": 55, "experience": 20, "education": 10, "location": 10, "notice": 5}


_GOA = {"goa", "panaji", "panjim", "margao", "madgaon", "mapusa", "vasco", "ponda", "porvorim", "calangute"}


def _same_place(want: str, have: str) -> bool:
    if want in have or have in want:
        return True
    tokens = lambda t: {x for x in re.split(r"[^a-z]+", t) if x}  # noqa: E731
    return bool(tokens(want) & _GOA and tokens(have) & _GOA)


def rule_score(c: dict, req: dict) -> dict:
    must = req.get("must_skills") or []
    nice = req.get("nice_skills") or []
    hay = " ".join([" ".join(c["skills"]), c.get("resume", ""), c.get("role", "")]).lower()
    listed = {canon_skill(s) for s in c["skills"]}

    def hit(skill: str) -> float:
        c0 = canon_skill(skill)
        if c0 in listed or any(v in listed for v in variants(skill)):
            return 1.0
        if any(_has_term(hay, v) for v in variants(skill)):
            return 0.7  # mentioned in the resume text but not listed as a skill
        return 0.0

    must_hits = {s: hit(s) for s in must}
    nice_hits = {s: hit(s) for s in nice}
    must_cov = sum(must_hits.values()) / len(must) if must else None
    nice_cov = sum(nice_hits.values()) / len(nice) if nice else None
    if must_cov is not None and nice_cov is not None:
        sk = 0.8 * must_cov + 0.2 * nice_cov
    elif must_cov is not None:
        sk = must_cov
    elif nice_cov is not None:
        sk = nice_cov
    else:
        sk = 0.5

    flags: list[str] = []
    mn, mx = float(req.get("min_exp") or 0), float(req.get("max_exp") or 0)
    exp = c["experience"]
    if exp is None:
        ex = 0.4
        flags.append("Experience unknown")
    elif exp >= mn:
        ex = 1.0
        if mx and exp > mx * 1.5:
            ex = 0.85
            flags.append("May be over-qualified")
    else:
        ex = max(0.0, exp / mn) if mn else 1.0

    need = EDU_FROM_LABEL.get(req.get("education", "Any"), 0)
    lvl = c["edu_level"]
    if need == 0:
        ed = 1.0
    elif lvl is None:
        ed = 0.5
        flags.append("Education unclear")
    elif lvl >= need:
        ed = 1.0
    elif lvl == need - 1:
        ed = 0.5
    else:
        ed = 0.0

    wm = req.get("work_mode", "Hybrid")
    city = (req.get("location") or "").lower().strip()
    loc = (c.get("location") or "").lower()
    if wm == "Remote" or not city:
        lo = 1.0
    elif not loc:
        lo = 0.5
        flags.append("Location unknown")
    elif _same_place(city, loc):
        lo = 1.0
    elif "relocat" in hay or "relocat" in " ".join(c.get("extra", {}).values()).lower():
        lo = 0.8
    else:
        lo = 0.2
        flags.append(f"Based outside {req.get('location')}")

    max_notice = req.get("max_notice_days")
    nd = c["notice_days"]
    if max_notice is None or max_notice == "":
        no = 1.0
    elif nd is None:
        no = 0.6
    elif nd <= int(max_notice):
        no = 1.0
    else:
        no = max(0.0, 1 - (nd - int(max_notice)) / 60)
        flags.append(f"{nd}-day notice")

    parts = {"skills": sk, "experience": ex, "education": ed, "location": lo, "notice": no}
    pts = {k: round(parts[k] * W[k], 1) for k in W}
    return {
        "rule_score": round(sum(pts.values())),
        "breakdown": pts,
        "matched_must": [s for s, v in must_hits.items() if v > 0],
        "missing_must": [s for s, v in must_hits.items() if v == 0],
        "matched_nice": [s for s, v in nice_hits.items() if v > 0],
        "flags": flags,
    }


def verdict(score: int) -> str:
    return "Strong fit" if score >= 75 else "Possible fit" if score >= 55 else "Weak fit"


# ---- AI review ----------------------------------------------------------
SYSTEM = (
    "You are a careful recruiting assistant. You assess ONE candidate against ONE job brief using only the "
    "text provided. Never infer or consider age, gender, religion, ethnicity, marital status, health, or any "
    "other protected trait. Do not invent facts. If something is not in the profile, say it is not shown. "
    "Reply with a single JSON object and nothing else, in this shape: "
    '{"fit_score": <integer 0-100>, "summary": "<max 25 words>", "strengths": ["<max 3 short items>"], '
    '"gaps": ["<max 3 short items>"], "interview_focus": ["<max 2 questions to probe>"]}'
)


def brief_text(req: dict) -> str:
    return (
        f"Role: {req.get('title')} ({req.get('seniority')}, {req.get('department')})\n"
        f"Must-have skills: {', '.join(req.get('must_skills', [])) or 'none listed'}\n"
        f"Nice-to-have skills: {', '.join(req.get('nice_skills', [])) or 'none listed'}\n"
        f"Experience wanted: {req.get('min_exp', 0)}-{req.get('max_exp', 0)} years\n"
        f"Education wanted: {req.get('education', 'Any')}\n"
        f"Location: {req.get('location')} ({req.get('work_mode')})"
    )


def profile_text(c: dict) -> str:
    return (
        f"Name: {c['name']}\nCurrent role: {c.get('role') or 'n/a'} at {c.get('company') or 'n/a'}\n"
        f"Experience: {c['experience'] if c['experience'] is not None else 'not stated'} years\n"
        f"Education: {c.get('education') or 'not stated'}\nLocation: {c.get('location') or 'not stated'}\n"
        f"Notice: {c.get('notice_raw') or 'not stated'}\nSkills: {', '.join(c['skills']) or 'not stated'}\n"
        f"Resume summary: {(c.get('resume') or 'not provided')[:1200]}"
    )


def ai_review(c: dict, req: dict, model: str) -> dict | None:
    out = llm.chat_json(model, SYSTEM, f"JOB BRIEF\n{brief_text(req)}\n\nCANDIDATE\n{profile_text(c)}")
    if not out:
        return None
    try:
        score = int(float(out.get("fit_score")))
    except Exception:  # noqa: BLE001
        return None
    lst = lambda k, n: [str(x)[:140] for x in (out.get(k) or []) if x][:n] if isinstance(out.get(k), list) else []  # noqa: E731
    return {
        "fit_score": max(0, min(100, score)),
        "summary": str(out.get("summary", ""))[:300],
        "strengths": lst("strengths", 3),
        "gaps": lst("gaps", 3),
        "interview_focus": lst("interview_focus", 2),
    }
