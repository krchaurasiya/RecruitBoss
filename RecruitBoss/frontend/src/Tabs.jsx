import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CalendarClock, CalendarPlus, Check, Copy, Mail, Sparkles } from "lucide-react";
import { api, copy, fmtDay, fmtTime, mailtoTo } from "./api";
import { RejectDialog, ScorecardDialog } from "./Dialogs";
import { Empty, Orb, Score, StageChip } from "./ui";

const validEmail = (e) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e || "");

/* =============================== Interviews =============================== */
export function Interviews({ ctx }) {
  const { role, cands, meetings, model, reload, goSchedule, notify } = ctx;
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState(null);
  const byId = useMemo(() => Object.fromEntries(cands.map((c) => [c.id, c])), [cands]);
  const ready = cands.filter((c) => c.stage === "shortlisted" && validEmail(c.email));
  const plan = role.interview_plan;

  async function makePlan() {
    setBusy(true);
    try { await api.interviewPlan(role.id, model); await reload(); notify("Interview Planning Agent wrote the interview plan"); } catch (e) { notify(e.message, true); }
    setBusy(false);
  }

  return (
    <div className="tab">
      <div className="tab-head">
        <div><h2>Interviews</h2><p className="lede">Plan the rounds, book the slots, then record feedback after each interview.</p></div>
        <button className="btn sun" disabled={!ready.length} onClick={() => goSchedule(ready.map((c) => c.id))} title={ready.length ? "" : "Shortlist candidates first"}>
          <CalendarClock size={18} />Schedule {ready.length || ""} shortlisted
        </button>
      </div>

      <section className="block">
        <div className="block-head"><h3>Interview plan</h3>
          <button className="btn ghost small" disabled={busy} onClick={makePlan}>{busy ? <><Orb busy size={12} />Planning…</> : <><Sparkles size={16} />{plan ? "Plan again" : "Plan the interviews"}</>}</button></div>
        {plan ? (
          <div className="rounds">
            {plan.map((r) => (
              <details key={r.name} className="round">
                <summary><b>{r.name}</b><span>{r.focus}</span></summary>
                <div className="round-body">
                  <ul>{r.questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
                  <div className="crit">{r.criteria.map((c) => <span key={c} className="chip mini">{c}</span>)}</div>
                </div>
              </details>
            ))}
          </div>
        ) : <p className="muted">No plan yet. The agent writes questions and scorecard criteria for each round you chose.</p>}
      </section>

      <section className="block">
        <div className="block-head"><h3>Meetings</h3>
          <a className="btn ghost small" href={`/api/calendar.ics?req_id=${role.id}`}><CalendarPlus size={16} />All as .ics</a></div>
        {meetings.length === 0 ? (
          <Empty title="No interviews booked" text="Shortlist candidates on the Shortlist tab, then schedule them here." />
        ) : (
          <ul className="meet-list">
            {meetings.map((m) => {
              const c = byId[m.candidate_id];
              const open = c && ["interviewing", "evaluated", "shortlisted"].includes(c.stage);
              return (
                <li key={m.id} className={m.status === "completed" ? "done" : ""}>
                  <div className="m-when">{fmtDay(m.start)}<b>{fmtTime(m.start)}</b></div>
                  <div className="m-who"><b>{m.candidate_name}</b><span>{m.round_name} with {m.interviewer}</span></div>
                  <span className={`stage ${m.status === "completed" ? "st-mint" : "st-blue"}`}>{m.status === "completed" ? "Feedback in" : "Scheduled"}</span>
                  <div className="slot-actions">
                    {open && <button className="btn small ghost" onClick={() => setCard({ c, m })}>{m.status === "completed" ? "Add more feedback" : "Record feedback"}</button>}
                    <a className="icon-btn" href={`/api/meetings/${m.id}.ics`} aria-label="Download calendar file" title="Download .ics"><CalendarPlus size={17} /></a>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <AnimatePresence>
        {card && <ScorecardDialog candidate={card.c} meeting={card.m} plan={plan} model={model} onClose={() => setCard(null)}
          onSubmit={async (b) => { await api.scorecard(card.c.id, b); await reload(); notify(`Evaluation Agent combined the feedback for ${card.c.name}. See Decisions.`); }} />}
      </AnimatePresence>
    </div>
  );
}

/* =============================== Decisions =============================== */
export function Decisions({ ctx }) {
  const { role, cands, reload, notify, setTab } = ctx;
  const waiting = cands.filter((c) => c.stage === "evaluated");
  const decided = cands.filter((c) => c.decision && c.stage !== "evaluated");
  const [notes, setNotes] = useState({});
  const [busy, setBusy] = useState(null);
  const [rej, setRej] = useState(null);

  async function act(c, action) {
    setBusy(c.id + action);
    try {
      await api.decide(c.id, { action, notes: notes[c.id] || "" });
      await reload();
      notify(action === "approve" ? `Offer Management Agent drafted an offer for ${c.name}` : "Decision recorded");
      if (action === "approve") setTab("offers");
    } catch (e) { notify(e.message, true); }
    setBusy(null);
  }

  return (
    <div className="tab">
      <div className="tab-head"><div><h2>Hiring decisions</h2><p className="lede">The Evaluation Agent combined each candidate's interview feedback. You make the call.</p></div></div>
      {waiting.length === 0 && <Empty title="No one is waiting for a decision" text="Record interview feedback and the evaluated candidates appear here." />}
      {waiting.map((c) => {
        const ev = c.evaluation;
        return (
          <motion.article key={c.id} className="decide" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <div className="decide-top">
              <Score n={Math.round(ev.overall * 20)} size={64} />
              <div><h3>{c.name}</h3><p className="muted">{[c.role, c.experience != null && `${c.experience} yrs`].filter(Boolean).join(" · ")} · screening score {c.final_score}</p></div>
              <span className={`stage st-${ev.recommendation === "Hire" ? "mint" : ev.recommendation === "No hire" ? "coral" : "sun"}`}>Panel leans: {ev.recommendation}</span>
            </div>
            <div className="detail-grid flat">
              <div>
                <h4>Ratings, average {ev.overall} out of 5 <span className="muted">({ev.n} scorecard{ev.n > 1 ? "s" : ""})</span></h4>
                {Object.entries(ev.per).map(([k, v]) => (
                  <div key={k} className="brow"><span>{k}</span><div className="mini-bar"><motion.span initial={{ width: 0 }} animate={{ width: `${v * 20}%` }} /></div><b>{v}</b></div>
                ))}
                <div className="crit">{Object.entries(ev.votes).map(([k, v]) => <span key={k} className="chip mini">{v} × {k}</span>)}</div>
              </div>
              <div>
                <h4>Summary {ev.ai && <span className="ai-score">written by the model</span>}</h4>
                <p>{ev.summary}</p>
                {ev.strengths?.length > 0 && <ul className="plus">{ev.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>}
                {ev.concerns?.length > 0 && <ul className="minus">{ev.concerns.map((s, i) => <li key={i}>{s}</li>)}</ul>}
              </div>
            </div>
            {c.scorecards?.some((s) => s.notes) && (
              <details className="qs"><summary>Interviewer notes</summary>
                <ul>{c.scorecards.filter((s) => s.notes).map((s, i) => <li key={i}><b>{s.interviewer}</b> ({s.recommendation}): {s.notes}</li>)}</ul></details>
            )}
            <label className="field"><span className="field-label">Note for the record (optional)</span>
              <input className="inp" value={notes[c.id] || ""} onChange={(e) => setNotes({ ...notes, [c.id]: e.target.value })} placeholder="Why this decision?" /></label>
            <div className="nav left">
              <button className="btn sun" disabled={!!busy} onClick={() => act(c, "approve")}>{busy === c.id + "approve" ? <Orb busy size={12} /> : <Check size={18} />}Approve hire</button>
              <button className="btn ghost" disabled={!!busy} onClick={() => act(c, "more")}>Ask for more interviews</button>
              <button className="btn ghost danger-o" disabled={!!busy} onClick={() => setRej(c)}>Reject</button>
            </div>
          </motion.article>
        );
      })}

      {decided.length > 0 && (
        <section className="block"><h3>Decided</h3>
          <ul className="meet-list">{decided.map((c) => (
            <li key={c.id}><div className="m-who"><b>{c.name}</b><span>{c.decision.action === "approve" ? "Approved" : c.decision.action === "more" ? "More interviews" : "Rejected"}{c.decision.notes ? `: ${c.decision.notes}` : ""}</span></div><StageChip stage={c.stage} /></li>
          ))}</ul></section>
      )}
      <AnimatePresence>
        {rej && <RejectDialog names={[rej.name]} defaultReason="Not the right fit after interviews" onClose={() => setRej(null)} onDone={reload}
          submit={(reason, feedback) => api.decide(rej.id, { action: "reject", notes: reason, feedback })} />}
      </AnimatePresence>
    </div>
  );
}

/* ================================= Offers ================================= */
const STEPS = ["Draft", "HR approval", "Approved", "Sent", "Reply"];
const STEP_AT = { draft: 0, pending_approval: 1, approved: 2, sent: 3, accepted: 4, declined: 4 };

function OfferCard({ c, cands, ctx }) {
  const { role, reload, notify, setTab } = ctx;
  const o = c.offer;
  const [f, setF] = useState({ salary: o.salary ?? "", joining_date: o.joining_date || "", extra_terms: o.extra_terms || "" });
  const [who, setWho] = useState("HR");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setF({ salary: o.salary ?? "", joining_date: o.joining_date || "", extra_terms: o.extra_terms || "" }); }, [o.salary, o.joining_date, o.extra_terms]);
  const edit = o.status === "draft";
  const body = () => ({ salary: f.salary === "" ? null : Number(f.salary), joining_date: f.joining_date || null, extra_terms: f.extra_terms });

  async function act(action, extra = {}, msg) {
    setBusy(true);
    try { await api.offer(c.id, action, extra); await reload(); if (msg) notify(msg); } catch (e) { notify(e.message, true); }
    setBusy(false);
  }
  const submitForApproval = async () => {
    setBusy(true);
    try { await api.offer(c.id, "update", body()); await api.offer(c.id, "submit"); await reload(); notify("Sent to HR for approval"); } catch (e) { notify(e.message, true); }
    setBusy(false);
  };
  const next = cands.find((x) => x.id !== c.id && ["screened", "shortlisted", "evaluated"].includes(x.stage) && validEmail(x.email));

  return (
    <article className="offer">
      <div className="offer-top"><h3>{c.name}</h3><span className="muted">{role.title}</span><StageChip stage={c.stage} /></div>
      <ol className="track">{STEPS.map((s, i) => <li key={s} className={i < STEP_AT[o.status] ? "past" : i === STEP_AT[o.status] ? "now" : ""}><b>{i < STEP_AT[o.status] ? <Check size={13} /> : i + 1}</b>{s}</li>)}</ol>
      <div className="offer-grid">
        <div className="stack">
          <div className="grid2">
            <label className="field"><span className="field-label">Yearly salary ({o.currency})</span>
              <input className="inp" type="number" min="0" step="10000" disabled={!edit} value={f.salary} onChange={(e) => setF({ ...f, salary: e.target.value })} placeholder="e.g. 1200000" /></label>
            <label className="field"><span className="field-label">Joining date</span>
              <input className="inp" type="date" disabled={!edit} value={f.joining_date} onChange={(e) => setF({ ...f, joining_date: e.target.value })} /></label>
          </div>
          <label className="field"><span className="field-label">Extra terms (optional)</span>
            <textarea className="inp" rows={3} disabled={!edit} value={f.extra_terms} onChange={(e) => setF({ ...f, extra_terms: e.target.value })} placeholder="Only terms you've actually agreed. Nothing is added for you." /></label>
          {o.comment && o.status === "draft" && <p className="notice">HR sent it back: {o.comment}</p>}

          {o.status === "draft" && (<div className="nav left">
            <button className="btn ghost" disabled={busy} onClick={() => act("update", body(), "Offer letter updated")}>Save changes</button>
            <button className="btn sun" disabled={busy || !f.salary} onClick={submitForApproval}>Send for HR approval</button>
            {!f.salary && <span className="muted">Add a yearly salary to continue.</span>}</div>)}
          {o.status === "pending_approval" && (<div className="stack">
            <div className="grid2">
              <label className="field"><span className="field-label">Approved by</span><input className="inp" value={who} onChange={(e) => setWho(e.target.value)} /></label>
              <label className="field"><span className="field-label">If sending back, what should change?</span><input className="inp" value={comment} onChange={(e) => setComment(e.target.value)} /></label>
            </div>
            <div className="nav left"><button className="btn sun" disabled={busy || !who.trim()} onClick={() => act("approve", { approver: who }, "Offer approved")}>Approve offer</button>
              <button className="btn ghost" disabled={busy} onClick={() => act("revise", { comment }, "Sent back for changes")}>Send back for changes</button></div></div>)}
          {o.status === "approved" && (<div className="nav left"><button className="btn sun" disabled={busy} onClick={() => act("send", {}, "Offer marked as sent. Open the email below.")}>Mark offer as sent</button>
            <span className="muted">Approved by {o.approved_by}. You send the email yourself.</span></div>)}
          {o.status === "sent" && (<div className="stack">
            <div className="nav left">
              {validEmail(c.email) && <a className="btn" href={mailtoTo(c.email, o.email)}><Mail size={18} />Open offer email</a>}
              <button className="btn ghost" onClick={() => copy(o.email.body)}><Copy size={18} />Copy offer text</button></div>
            <p className="field-label">When the candidate replies:</p>
            <div className="nav left"><button className="btn sun" disabled={busy} onClick={() => act("accept", {}, "Onboarding Agent created the employee record and checklist")}>Candidate accepted</button>
              <button className="btn ghost danger-o" disabled={busy} onClick={() => act("decline", {}, "Offer declined")}>Candidate declined</button></div></div>)}
          {o.status === "accepted" && <div className="notice good"><Check size={18} />Accepted. <button className="linklike" onClick={() => setTab("onboarding")}>Go to onboarding</button></div>}
          {o.status === "declined" && (
            <div className="notice">Declined. This application is closed.{next ? <> Next best: <b>{next.name}</b> ({next.final_score}). <button className="linklike" onClick={async () => { await api.shortlist(role.id, [next.id]); await reload(); notify(`${next.name} shortlisted`); setTab("shortlist"); }}>Shortlist them</button></> : " No one else is waiting."}</div>)}
        </div>
        <pre className="letter">{o.letter}</pre>
      </div>
    </article>
  );
}

export function Offers({ ctx }) {
  const { cands } = ctx;
  const list = cands.filter((c) => c.offer && c.offer.letter);
  const active = list.filter((c) => ["offer_draft", "offer_pending", "offer_approved", "offer_sent", "declined"].includes(c.stage));
  const closed = list.filter((c) => ["onboarding", "joined"].includes(c.stage));
  return (
    <div className="tab">
      <div className="tab-head"><div><h2>Offers</h2><p className="lede">Draft, get HR approval, send, and record the reply. The offer text only contains what you enter.</p></div></div>
      {active.length === 0 && closed.length === 0 && <Empty title="No offers yet" text="Approve a candidate on the Decisions tab and the Offer Management Agent drafts the offer." />}
      {active.map((c) => <OfferCard key={c.id} c={c} cands={cands} ctx={ctx} />)}
      {closed.length > 0 && <section className="block"><h3>Accepted</h3><ul className="meet-list">{closed.map((c) => <li key={c.id}><div className="m-who"><b>{c.name}</b><span>Joining {c.offer.joining_date}</span></div><StageChip stage={c.stage} /></li>)}</ul></section>}
    </div>
  );
}

/* ============================== Onboarding ============================== */
export function Onboarding({ ctx }) {
  const { cands, reload, notify } = ctx;
  const list = cands.filter((c) => c.onboarding);
  async function tick(c, t) {
    try { await api.toggleTask(c.id, t.id, !t.done); await reload(); } catch (e) { notify(e.message, true); }
  }
  return (
    <div className="tab">
      <div className="tab-head"><div><h2>Onboarding</h2><p className="lede">Everyone who accepted. Tick tasks off as they're done. When all are done, the person is marked as joined.</p></div></div>
      {list.length === 0 && <Empty title="No one is onboarding yet" text="When a candidate accepts an offer, the Onboarding Agent creates their record and checklist here." />}
      {list.map((c) => {
        const ob = c.onboarding, done = ob.checklist.filter((t) => t.done).length, pct = Math.round((done / ob.checklist.length) * 100);
        const e = ob.employee;
        return (
          <article key={c.id} className="onb">
            <div className="offer-top"><h3>{c.name}</h3><span className="muted">{e.title}</span><StageChip stage={c.stage} /></div>
            <div className="bar"><motion.span animate={{ width: `${pct}%` }} /></div>
            <p className="muted">{done} of {ob.checklist.length} tasks done</p>
            <div className="offer-grid">
              <ul className="checks">{ob.checklist.map((t) => (
                <li key={t.id}><label><input type="checkbox" checked={t.done} onChange={() => tick(c, t)} /><span>{t.label}</span></label></li>))}</ul>
              <div className="stack">
                <dl className="emp">{[["Employee ID", e.employee_id], ["Status", e.status], ["Start date", e.start_date], ["Department", e.department], ["Type", e.employment_type], ["Works", e.work_mode === "Remote" ? "Remote" : `${e.work_mode}${e.location ? `, ${e.location}` : ""}`], ["Email", e.email]].filter(([, v]) => v).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
                <div className="nav left">
                  {validEmail(c.email) && <a className="btn small" href={mailtoTo(c.email, ob.welcome)}><Mail size={16} />Welcome email</a>}
                  <button className="btn small ghost" onClick={() => copy(`${ob.welcome.subject}\n\n${ob.welcome.body}`)}><Copy size={16} />Copy</button></div>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

/* ============================== Analytics ============================== */
export function Analytics({ ctx }) {
  const { role, cands, reload, notify } = ctx;
  const [a, setA] = useState(null);
  const [ask, setAsk] = useState(false);
  const sig = cands.map((c) => c.stage).join(",") + role.status;
  useEffect(() => { api.analytics(role.id).then(setA).catch(() => {}); }, [role.id, sig]);
  if (!a) return <div className="tab"><p className="muted">Loading…</p></div>;
  const max = Math.max(1, ...a.funnel.map((f) => f.count));
  const closed = role.status === "closed";
  const fmt = (v, s = "") => (v == null ? "Not yet" : `${v}${s}`);
  return (
    <div className="tab">
      <div className="tab-head"><div><h2>Hiring analytics</h2><p className="lede">{a.filled} of {a.openings} opening{a.openings > 1 ? "s" : ""} filled{closed ? ". This role is closed." : "."}</p></div>
        {!closed && !ask && <button className="btn ghost" onClick={() => setAsk(true)}>Close this role</button>}
        {!closed && ask && <div className="nav left"><span>Close it for good?</span>
          <button className="btn sun small" onClick={async () => { try { await api.close(role.id); await reload(); notify("Closure Agent closed the role"); setAsk(false); } catch (e) { notify(e.message, true); } }}>Yes, close</button>
          <button className="btn ghost small" onClick={() => setAsk(false)}>Not yet</button></div>}
      </div>
      <section className="block">
        <h3>Funnel</h3>
        <ul className="funnel">{a.funnel.map((f, i) => (
          <li key={f.key}><span>{f.label}</span><div className="fbar"><motion.span initial={{ width: 0 }} animate={{ width: `${(f.count / max) * 100}%` }} transition={{ delay: i * 0.05 }} /></div><b>{f.count}</b></li>))}</ul>
        <p className="muted">Also: {a.rejected} rejected · {a.declined} declined the offer · {a.interviews_done} interviews with feedback.</p>
      </section>
      <dl className="facts">
        <div><dt>Time to hire</dt><dd>{fmt(a.time_to_hire_days, " days")}</dd></div>
        <div><dt>Offers accepted</dt><dd>{fmt(a.offer_acceptance, "%")}</dd></div>
        <div><dt>Average screening score</dt><dd>{fmt(a.avg_screen_score)}</dd></div>
        <div><dt>Average interview rating</dt><dd>{a.avg_interview_rating == null ? "Not yet" : `${a.avg_interview_rating} / 5`}</dd></div>
      </dl>
    </div>
  );
}
