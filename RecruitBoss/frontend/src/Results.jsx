import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CalendarClock, ChevronDown, Search, UserPlus, UserX } from "lucide-react";
import { api } from "./api";
import { RejectDialog } from "./Dialogs";
import { CheckReport } from "./Screen";
import { Score, StageChip } from "./ui";

const OPEN = ["screened", "shortlisted", "interviewing", "evaluated"];

const BANDS = [["all", "Everyone"], ["strong", "Strong fit"], ["possible", "Possible fit"], ["weak", "Weak fit"]];
const band = (n) => (n >= 75 ? "strong" : n >= 55 ? "possible" : "weak");
const LABELS = { skills: "Skills", experience: "Experience", education: "Education", location: "Location", notice: "Notice" };
const MAXP = { skills: 55, experience: 20, education: 10, location: 10, notice: 5 };

export default function Results({ role, cands, report, aiUsed, selected, setSelected, cutoff, setCutoff, onSchedule, onMore, reload, notify }) {
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);
  const [showCheck, setShowCheck] = useState(false);
  const [rej, setRej] = useState(null); // { ids, names }

  const counts = useMemo(() => {
    const c = { strong: 0, possible: 0, weak: 0 };
    cands.forEach((x) => c[band(x.final_score)]++);
    return c;
  }, [cands]);
  const shown = cands.filter((c) => (filter === "all" || band(c.final_score) === filter) && (!q || `${c.name} ${c.role} ${c.skills.join(" ")}`.toLowerCase().includes(q.toLowerCase())));

  const invitable = (c) => OPEN.includes(c.stage || "screened") && !!c.email && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c.email);
  const below = cands.filter((c) => ["screened", "shortlisted"].includes(c.stage || "screened") && c.final_score < cutoff);
  const applyCutoff = (v) => { setCutoff(v); setSelected(new Set(cands.filter((c) => c.final_score >= v && invitable(c)).map((c) => c.id))); };
  const toggle = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  return (
    <div className="results">
      <div className="results-head">
        <div>
          <h2>{cands.length} candidates for {role.title}</h2>
          <p className="lede">{aiUsed ? "Scores blend the rules (60%) with the AI's reading (40%)." : "Scores come from the rules only. The AI wasn't used for this batch."}</p>
        </div>
        <div className="nav left" style={{ margin: 0 }}>
          <button className="btn ghost small" onClick={onMore}><UserPlus size={16} />Add more candidates</button>
          {report && <button className="btn ghost small" onClick={() => setShowCheck(!showCheck)}>{showCheck ? "Hide" : "Show"} data check</button>}
        </div>
      </div>
      <AnimatePresence>{showCheck && report && <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: "hidden" }}><CheckReport report={report} /></motion.div>}</AnimatePresence>

      <div className="split" role="img" aria-label={`${counts.strong} strong, ${counts.possible} possible, ${counts.weak} weak`}>
        <motion.span className="s-strong" animate={{ flexGrow: counts.strong }} /><motion.span className="s-possible" animate={{ flexGrow: counts.possible }} /><motion.span className="s-weak" animate={{ flexGrow: counts.weak }} />
      </div>
      <div className="split-legend"><span className="d-strong">{counts.strong} strong</span><span className="d-possible">{counts.possible} possible</span><span className="d-weak">{counts.weak} weak</span></div>

      <div className="toolbar">
        <div className="pills">{BANDS.map(([k, l]) => <button key={k} className={`pill ${filter === k ? "on" : ""}`} onClick={() => setFilter(k)}>{l}</button>)}</div>
        <label className="search"><Search size={16} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, role, skill" /></label>
        <label className="cut">Shortlist everyone scoring <b>{cutoff}</b>+
          <input type="range" min={30} max={95} step={5} value={cutoff} onChange={(e) => applyCutoff(Number(e.target.value))} /></label>
      </div>

      <ol className="cand-list">
        {shown.map((c) => (
          <li key={c.id} className={`cand ${selected.has(c.id) ? "picked" : ""} ${["rejected", "declined"].includes(c.stage) ? "gone" : ""}`}>
            <div className="cand-row">
              <input type="checkbox" aria-label={`Select ${c.name}`} checked={selected.has(c.id)} disabled={!invitable(c)} onChange={() => toggle(c.id)} title={invitable(c) ? "" : "No valid email, can't be invited"} />
              <Score n={c.final_score} />
              <button className="cand-main" onClick={() => setOpen(open === c.id ? null : c.id)} aria-expanded={open === c.id}>
                <span className="cand-name">{c.name}<em className={`v-${band(c.final_score)}`}>{c.verdict}</em><StageChip stage={c.stage} /></span>
                <span className="cand-sub">{[c.role, c.experience != null && `${c.experience} yrs`, c.location].filter(Boolean).join(" · ")}</span>
                <span className="cand-tags">
                  {c.matched_must.slice(0, 5).map((s) => <span key={s} className="chip on mini">{s}</span>)}
                  {c.missing_must.slice(0, 3).map((s) => <span key={s} className="chip miss mini">no {s}</span>)}
                </span>
              </button>
              <ChevronDown className={`caret-i ${open === c.id ? "up" : ""}`} size={20} />
            </div>
            <AnimatePresence initial={false}>
              {open === c.id && (
                <motion.div className="cand-detail" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: "hidden" }}>
                  <div className="detail-grid">
                    <div>
                      <h4>Why this score</h4>
                      {Object.entries(c.breakdown).map(([k, v]) => (
                        <div key={k} className="brow"><span>{LABELS[k]}</span><div className="mini-bar"><motion.span initial={{ width: 0 }} animate={{ width: `${(v / MAXP[k]) * 100}%` }} /></div><b>{v}/{MAXP[k]}</b></div>
                      ))}
                      {c.flags.length > 0 && <p className="flags">{c.flags.join(" · ")}</p>}
                    </div>
                    <div>
                      {c.ai ? (
                        <>
                          <h4>What the AI saw <span className="ai-score">AI score {c.ai.fit_score}</span></h4>
                          <p>{c.ai.summary}</p>
                          {c.ai.strengths.length > 0 && <ul className="plus">{c.ai.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>}
                          {c.ai.gaps.length > 0 && <ul className="minus">{c.ai.gaps.map((s, i) => <li key={i}>{s}</li>)}</ul>}
                          {c.ai.interview_focus.length > 0 && <p className="focus"><b>Ask them:</b> {c.ai.interview_focus.join(" ")}</p>}
                        </>
                      ) : (<><h4>AI reading</h4><p className="muted">Not read by the AI. Rules score only.</p></>)}
                      <p className="contact">{c.email || "No email"}{c.phone && ` · ${c.phone}`}{c.notice_raw && ` · Notice: ${c.notice_raw}`}</p>
                      {c.timeline?.length > 0 && <details className="qs"><summary>History</summary><ul>{[...c.timeline].reverse().map((t, i) => <li key={i}><span className="muted">{t.ts}</span> {t.text}</li>)}</ul></details>}
                      {["screened", "shortlisted"].includes(c.stage || "screened") && <button className="btn small ghost danger-o" onClick={() => setRej({ ids: [c.id], names: [c.name] })}><UserX size={15} />Reject…</button>}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </li>
        ))}
        {shown.length === 0 && <li className="empty">No one matches that filter.</li>}
      </ol>

      <div className="action-bar">
        <span><b>{selected.size}</b> selected</span>
        {below.length > 0 && <button className="btn ghost-d" onClick={() => setRej({ ids: below.map((c) => c.id), names: below.map((c) => c.name) })}><UserX size={16} />Reject {below.length} below {cutoff}</button>}
        <button className="btn sun" disabled={selected.size === 0} onClick={() => onSchedule([...selected])}><CalendarClock size={18} />Schedule meetings</button>
      </div>
      <AnimatePresence>
        {rej && <RejectDialog names={rej.names} onClose={() => setRej(null)} onDone={() => { setSelected((s) => new Set([...s].filter((id) => !rej.ids.includes(id)))); reload(); }}
          submit={(reason, feedback) => api.reject(role.id, rej.ids, reason, feedback)} />}
      </AnimatePresence>
    </div>
  );
}
