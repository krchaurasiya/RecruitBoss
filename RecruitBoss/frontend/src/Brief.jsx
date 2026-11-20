import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Copy, Megaphone, Sparkles } from "lucide-react";
import { api } from "./api";
import * as O from "./options";
import { ChipPicker, Dropdown, Orb } from "./ui";

const STEPS = ["The role", "Terms", "Requirements", "Hiring process"];

const init = {
  titleChoice: "", titleCustom: "", department: "Engineering", seniority: "Mid-level", openings: 1,
  employment_type: "Full-time", work_mode: "Hybrid", locChoice: "Panaji", locCustom: "", salary: "none", notice: "",
  urgency: O.URGENCY[1], exp: "1-3", education: "Bachelor's", must: [], nice: [],
  rounds: ["Screening call", "Technical interview", "HR round"], notes: "",
};

function fromRole(r) {
  const known = (list, v) => (list.includes(v) ? v : "Other…");
  const exp = O.EXPERIENCE.find((e) => e.min === r.min_exp && e.max === r.max_exp);
  const sal = O.SALARY.find((x) => x.min === r.salary_min && x.max === r.salary_max);
  return {
    ...init, titleChoice: known(O.TITLES, r.title), titleCustom: O.TITLES.includes(r.title) ? "" : r.title, department: r.department,
    seniority: r.seniority, openings: r.openings, employment_type: r.employment_type, work_mode: r.work_mode,
    locChoice: r.location ? known(O.LOCATIONS, r.location) : "Panaji", locCustom: O.LOCATIONS.includes(r.location) ? "" : r.location || "",
    salary: sal ? sal.value : "none", notice: r.max_notice_days ?? "", urgency: r.urgency || init.urgency, exp: exp ? exp.value : "1-3",
    education: r.education, must: r.must_skills || [], nice: r.nice_skills || [], rounds: r.rounds || init.rounds, notes: r.notes || "",
  };
}

export default function Brief({ model, online, existing, onCreated, onDone }) {
  const [step, setStep] = useState(0);
  const [f, setF] = useState(existing ? fromRole(existing) : init);
  const [phase, setPhase] = useState("form"); // form | drafting
  const [jd, setJd] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [role, setRole] = useState(existing || null);
  const [posts, setPosts] = useState(existing?.postings || null);
  const [postBusy, setPostBusy] = useState(false);
  const set = (k) => (v) => setF((o) => ({ ...o, [k]: v }));

  const title = f.titleChoice === "Other…" ? f.titleCustom : f.titleChoice;
  const location = f.locChoice === "Other…" ? f.locCustom : f.locChoice;
  const exp = O.EXPERIENCE.find((e) => e.value === f.exp);
  const sal = O.SALARY.find((s) => s.value === f.salary);
  const sugg = useMemo(() => O.skillSuggestions(title), [title]);

  const ok = [
    title.trim().length >= 2,
    work_ok(f, location),
    f.must.length > 0,
    f.rounds.length > 0,
  ];

  function work_ok(x, loc) { return x.work_mode === "Remote" || loc.trim().length > 0; }

  const brief = () => ({
    title: title.trim(), department: f.department, seniority: f.seniority, employment_type: f.employment_type,
    work_mode: f.work_mode, location: location.trim(), openings: f.openings, min_exp: exp.min, max_exp: exp.max,
    must_skills: f.must, nice_skills: f.nice, education: f.education,
    salary_min: sal.min ?? null, salary_max: sal.max ?? null, currency: "INR",
    max_notice_days: f.notice === "" ? null : Number(f.notice), urgency: f.urgency, rounds: f.rounds, notes: f.notes,
  });

  async function create() {
    setBusy(true); setErr(""); setPhase("drafting"); setJd("");
    try {
      const r = role ? await api.reviseRole(role.id, brief()) : await api.createRole(brief());
      setRole(r); setPosts(null); onCreated(r);
      await api.streamJD(r.id, model, setJd);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }

  async function makePosts() {
    setPostBusy(true);
    try { setPosts(await api.postings(role.id, model)); } catch (e) { setErr(e.message); }
    setPostBusy(false);
  }
  async function approve() {
    setBusy(true);
    try { const r = await api.approve(role.id); onDone({ ...role, ...r }); } catch (e) { setErr(e.message); setBusy(false); }
  }

  const toggleRound = (r) => set("rounds")(f.rounds.includes(r) ? f.rounds.filter((x) => x !== r) : [...f.rounds, r]);

  return (
    <div className="brief">
      <div className="brief-main">
        <AnimatePresence mode="wait">
          {phase === "form" ? (
            <motion.div key={step} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.2 }}>
              <p className="step-count">Question {step + 1} of {STEPS.length}</p>
              {existing?.screened && step === 0 && <p className="notice">Candidates already scored keep their scores. New uploads use the updated brief.</p>}
              <h2>{["Who are we hiring?", "What are the terms?", "What must they bring?", "How should we hire?"][step]}</h2>

              {step === 0 && (
                <div className="grid2">
                  <Dropdown label="Job title" value={f.titleChoice} onChange={set("titleChoice")} options={O.TITLES} placeholder="Pick a title" />
                  {f.titleChoice === "Other…" && (
                    <label className="field"><span className="field-label">Your title</span>
                      <input className="inp" value={f.titleCustom} onChange={(e) => set("titleCustom")(e.target.value)} placeholder="e.g. Prompt Engineer" autoFocus /></label>
                  )}
                  <Dropdown label="Department" value={f.department} onChange={set("department")} options={O.DEPARTMENTS} />
                  <Dropdown label="Seniority" value={f.seniority} onChange={set("seniority")} options={O.SENIORITY} />
                  <Dropdown label="How many people?" value={f.openings} onChange={set("openings")} options={O.OPENINGS} />
                </div>
              )}

              {step === 1 && (
                <div className="grid2">
                  <Dropdown label="Employment type" value={f.employment_type} onChange={set("employment_type")} options={O.EMPLOYMENT} />
                  <Dropdown label="Where do they work?" value={f.work_mode} onChange={set("work_mode")} options={O.WORK_MODES} />
                  {f.work_mode !== "Remote" && <Dropdown label="Office city" value={f.locChoice} onChange={set("locChoice")} options={O.LOCATIONS} />}
                  {f.work_mode !== "Remote" && f.locChoice === "Other…" && (
                    <label className="field"><span className="field-label">City</span>
                      <input className="inp" value={f.locCustom} onChange={(e) => set("locCustom")(e.target.value)} placeholder="City name" autoFocus /></label>
                  )}
                  <Dropdown label="Pay band" value={f.salary} onChange={set("salary")} options={O.SALARY} />
                  <Dropdown label="Longest notice period you'll accept" value={f.notice} onChange={set("notice")} options={O.NOTICE} />
                  <Dropdown label="How soon do you need them?" value={f.urgency} onChange={set("urgency")} options={O.URGENCY} />
                </div>
              )}

              {step === 2 && (
                <div className="stack">
                  <div className="grid2">
                    <Dropdown label="Experience" value={f.exp} onChange={set("exp")} options={O.EXPERIENCE} />
                    <Dropdown label="Education" value={f.education} onChange={set("education")} options={O.EDUCATION} />
                  </div>
                  <ChipPicker label="Must-have skills" values={f.must} onChange={set("must")} suggestions={sugg} placeholder="Type a skill and press Enter"
                    hint="Candidates missing these lose the most points." />
                  <ChipPicker label="Nice-to-have skills" values={f.nice} onChange={set("nice")} suggestions={sugg.filter((s) => !f.must.includes(s))} placeholder="Optional" tone="sun" />
                </div>
              )}

              {step === 3 && (
                <div className="stack">
                  <div className="field">
                    <span className="field-label">Interview rounds</span>
                    <div className="suggest big">
                      {O.ROUNDS.map((r) => (
                        <button key={r} type="button" className={`chip ${f.rounds.includes(r) ? "on" : ""}`} aria-pressed={f.rounds.includes(r)} onClick={() => toggleRound(r)}>{r}</button>
                      ))}
                    </div>
                  </div>
                  <label className="field"><span className="field-label">Anything else I should know?</span>
                    <textarea className="inp" rows={4} value={f.notes} onChange={(e) => set("notes")(e.target.value)} placeholder="Team size, tools, what great looks like…" /></label>
                </div>
              )}

              <div className="nav">
                <button className="btn ghost" onClick={() => setStep(step - 1)} disabled={step === 0}><ArrowLeft size={18} />Back</button>
                {step < STEPS.length - 1 ? (
                  <button className="btn" disabled={!ok[step]} onClick={() => setStep(step + 1)}>Next<ArrowRight size={18} /></button>
                ) : (
                  <button className="btn sun" disabled={!ok.every(Boolean) || busy} onClick={create}><Sparkles size={18} />{role ? "Update role and redraft job description" : "Create role and draft job description"}</button>
                )}
              </div>
            </motion.div>
          ) : (
            <motion.div key="jd" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <p className="step-count">{role ? `Role #${role.id} saved. Read the draft, then approve it.` : "Saving role…"}</p>
              <h2>{busy ? "Drafting your job description" : "Job description ready"}</h2>
              <div className="jd-status"><Orb busy={busy} /><span>{busy ? (online ? `Writing with ${model || "your local model"}` : "Ollama is offline, so I'm using a standard template") : "Edit it anywhere you like before you post it."}</span></div>
              {err && <p className="error">{err}</p>}
              <pre className="jd" aria-live="polite">{jd || " "}{busy && <i className="caret dark" />}</pre>
              {!busy && jd && (
                <section className="block">
                  <div className="block-head"><h3>Job posts for each channel</h3>
                    {!posts && <button className="btn ghost small" disabled={postBusy} onClick={makePosts}>{postBusy ? <><Orb busy size={12} />Writing…</> : <><Megaphone size={16} />Draft posts</>}</button>}</div>
                  {posts ? <div className="posts">{posts.map((p) => (
                    <div key={p.key} className="post"><div className="block-head"><b>{p.channel}</b><button className="icon-btn" aria-label={`Copy ${p.channel}`} onClick={() => navigator.clipboard?.writeText(p.text)}><Copy size={16} /></button></div><p>{p.text}</p></div>))}</div>
                    : <p className="muted">The Sourcing Agent can write a LinkedIn post, careers page text, a portal listing and a referral message. You post them yourself.</p>}
                </section>
              )}
              <div className="nav">
                <button className="btn ghost" onClick={() => { setPhase("form"); setStep(3); }} disabled={busy}><ArrowLeft size={18} />Change the brief</button>
                <button className="btn ghost" onClick={() => navigator.clipboard?.writeText(jd)} disabled={busy || !jd}><Copy size={18} />Copy text</button>
                <button className="btn sun" disabled={busy || !role || !jd} onClick={approve}>{existing?.screened ? "Approve and go back" : "Approve and upload candidates"}<ArrowRight size={18} /></button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <aside className="live-brief" aria-label="Brief so far">
        <h3>{title || "Untitled role"}</h3>
        <p className="lb-sub">{f.seniority} · {f.department}</p>
        <dl>
          <Row k="Openings" v={f.openings} />
          <Row k="Type" v={f.employment_type} />
          <Row k="Works" v={f.work_mode === "Remote" ? "Remote" : `${f.work_mode}${location ? `, ${location}` : ""}`} />
          <Row k="Experience" v={exp.label} />
          <Row k="Education" v={O.EDUCATION.find((e) => e.value === f.education).label} />
          <Row k="Pay" v={sal.value === "none" ? "" : sal.label} />
          <Row k="Notice" v={f.notice === "" ? "" : O.NOTICE.find((n) => n.value === Number(f.notice))?.label} />
        </dl>
        {f.must.length > 0 && <div className="lb-chips">{f.must.map((s) => <span key={s} className="chip on mini">{s}</span>)}</div>}
        {f.nice.length > 0 && <div className="lb-chips">{f.nice.map((s) => <span key={s} className="chip sunny mini">{s}</span>)}</div>}
      </aside>
    </div>
  );
}

function Row({ k, v }) {
  if (v === "" || v == null) return null;
  return <div className="lb-row"><dt>{k}</dt><dd>{v}</dd></div>;
}
