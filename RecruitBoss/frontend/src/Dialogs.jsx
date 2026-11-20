import { useState } from "react";
import { Copy, Mail } from "lucide-react";
import { copy, mailtoTo } from "./api";
import { DEFAULT_CRITERIA, RECOMMENDATIONS, REJECT_REASONS } from "./options";
import { Dropdown, Modal, Orb } from "./ui";

/** Reject one or many people. `submit(reason, feedback)` must resolve to { emails: [...] }. */
export function RejectDialog({ names, onClose, onDone, submit, defaultReason }) {
  const [reason, setReason] = useState(defaultReason || REJECT_REASONS[0]);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [emails, setEmails] = useState(null);

  async function go() {
    setBusy(true); setErr("");
    try { const r = await submit(reason, feedback); setEmails(r.emails || []); } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  const done = () => { onDone(); onClose(); };

  return (
    <Modal title={emails ? "Rejection emails ready" : names.length === 1 ? `Reject ${names[0]}` : `Reject ${names.length} candidates`} onClose={emails ? done : onClose}>
      {!emails ? (
        <div className="stack">
          <Dropdown label="Reason (for your records)" value={reason} onChange={setReason} options={REJECT_REASONS} />
          <label className="field"><span className="field-label">Feedback to include in the email (optional)</span>
            <textarea className="inp" rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Short, kind and specific works best." /></label>
          {err && <p className="error">{err}</p>}
          <div className="nav"><button className="btn ghost" onClick={onClose}>Cancel</button>
            <button className="btn danger" disabled={busy} onClick={go}>{busy ? <><Orb busy size={12} />Drafting…</> : "Reject and draft email"}</button></div>
        </div>
      ) : (
        <div className="stack">
          <p className="muted">Marked as rejected. Nothing is sent automatically: open each email in your mail app.</p>
          <ul className="mail-list">
            {emails.map((m) => (
              <li key={m.candidate_id}>
                <div><b>{m.name}</b><span>{m.to || "No email address"}</span></div>
                <div className="slot-actions">
                  {m.to && <a className="icon-btn" href={mailtoTo(m.to, m)} aria-label={`Email ${m.name}`} title="Open in mail"><Mail size={17} /></a>}
                  <button className="icon-btn" aria-label="Copy email" title="Copy email text" onClick={() => copy(`${m.subject}\n\n${m.body}`)}><Copy size={17} /></button>
                </div>
              </li>
            ))}
          </ul>
          <div className="nav"><span /><button className="btn" onClick={done}>Done</button></div>
        </div>
      )}
    </Modal>
  );
}

/** Interview feedback form. Criteria come from the interview plan for that round. */
export function ScorecardDialog({ candidate, meeting, plan, model, onClose, onSubmit }) {
  const round = plan?.find((r) => r.name === meeting?.round_name);
  const criteria = round?.criteria?.length ? round.criteria : DEFAULT_CRITERIA;
  const [ratings, setRatings] = useState({});
  const [rec, setRec] = useState("");
  const [who, setWho] = useState(meeting?.interviewer || "");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const ready = criteria.every((c) => ratings[c]) && rec && who.trim();

  async function go() {
    setBusy(true); setErr("");
    try {
      await onSubmit({ meeting_id: meeting?.id ?? null, interviewer: who, round_name: meeting?.round_name || "", ratings, recommendation: rec, notes, model });
      onClose();
    } catch (e) { setErr(e.message); setBusy(false); }
  }

  return (
    <Modal title={`Feedback: ${candidate.name}`} onClose={busy ? () => {} : onClose} wide>
      <div className="stack">
        {round && <p className="muted"><b>{round.name}.</b> {round.focus}</p>}
        <div className="rate-grid">
          {criteria.map((c) => (
            <div key={c} className="rate-row"><span>{c}</span>
              <div className="rate" role="radiogroup" aria-label={c}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button key={n} type="button" role="radio" aria-checked={ratings[c] === n} className={ratings[c] === n ? "on" : ""} onClick={() => setRatings({ ...ratings, [c]: n })}>{n}</button>
                ))}
              </div>
            </div>
          ))}
          <p className="field-hint">1 = well below the bar, 3 = meets it, 5 = clearly exceeds it.</p>
        </div>
        <div className="grid2">
          <Dropdown label="Your recommendation" value={rec} onChange={setRec} options={RECOMMENDATIONS} placeholder="Choose" />
          <label className="field"><span className="field-label">Interviewer</span><input className="inp" value={who} onChange={(e) => setWho(e.target.value)} /></label>
        </div>
        {round?.questions?.length > 0 && <details className="qs"><summary>Questions from the plan</summary><ul>{round.questions.map((q, i) => <li key={i}>{q}</li>)}</ul></details>}
        <label className="field"><span className="field-label">Notes (what did you see or hear?)</span>
          <textarea className="inp" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Specific examples help the panel decide." /></label>
        {err && <p className="error">{err}</p>}
        <div className="nav"><button className="btn ghost" disabled={busy} onClick={onClose}>Cancel</button>
          <button className="btn sun" disabled={!ready || busy} onClick={go}>{busy ? <><Orb busy size={12} />Evaluation Agent is combining feedback…</> : "Submit feedback"}</button></div>
      </div>
    </Modal>
  );
}
