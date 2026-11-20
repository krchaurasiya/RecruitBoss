import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, CalendarCheck, CalendarPlus, Copy, Mail, Trash2 } from "lucide-react";
import { api, fmtDay, fmtTime, mailto } from "./api";
import * as O from "./options";
import { ChipPicker, Dropdown, Toggle } from "./ui";

const TONES = ["#2431E8", "#E0A800", "#17A673", "#D6423A", "#7A3FD1"];
const pad = (n) => String(n).padStart(2, "0");
function nextWorkday() {
  const d = new Date(); d.setDate(d.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
const groupByDay = (ms) => ms.reduce((a, m) => { const k = m.start.slice(0, 10); (a[k] ||= []).push(m); return a; }, {});

export default function Schedule({ role, cands, selected, booked, setBooked, onBack, onInterviews }) {
  const ids = useMemo(() => cands.filter((c) => selected.has(c.id)).map((c) => c.id), [cands, selected]);
  const [f, setF] = useState({
    interviewers: ["Hiring manager"], date: nextWorkday(), time: "10:00", duration: 45, buffer: 15,
    day_start: "10:00", day_end: "18:00", lunch: true, mode: "Video call", link: "", round_name: role.rounds?.[0] || "Screening call", notes: "",
  });
  const [preview, setPreview] = useState([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (v) => setF((o) => ({ ...o, [k]: v }));
  const body = () => ({
    candidate_ids: ids, interviewers: f.interviewers, start: `${f.date}T${f.time}`, duration: f.duration, buffer: f.buffer,
    day_start: f.day_start, day_end: f.day_end, lunch: f.lunch, mode: f.mode, link: f.link, round_name: f.round_name, notes: f.notes,
  });

  useEffect(() => {
    if (booked || !ids.length || !f.interviewers.length) { setPreview([]); return; }
    const t = setTimeout(() => api.preview(role.id, body()).then((p) => { setPreview(p); setErr(""); }).catch((e) => { setPreview([]); setErr(e.message); }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(f), ids.join(","), booked]);

  async function book() {
    setBusy(true); setErr("");
    try { setBooked(await api.book(role.id, body())); } catch (e) { setErr(e.message); }
    setBusy(false);
  }
  async function cancel(m) { await api.cancel(m.id); setBooked((booked || []).filter((x) => x.id !== m.id)); }
  const colorOf = (who, list) => TONES[[...new Set(list.map((m) => m.interviewer))].indexOf(who) % TONES.length];
  const list = booked || preview;
  const days = groupByDay(list);

  return (
    <div className="schedule">
      <div className="sched-form">
        <button className="btn ghost small" onClick={onBack}><ArrowLeft size={16} />Back</button>
        <h2>{booked ? "Interviews booked" : "Set up the interviews"}</h2>
        {!booked && (
          <div className="stack">
            <ChipPicker label="Who is interviewing?" values={f.interviewers} onChange={set("interviewers")} suggestions={O.INTERVIEWERS} placeholder="Add a name"
              hint="With more than one person, I split candidates so nobody is double-booked." />
            <div className="grid2">
              <label className="field"><span className="field-label">First day</span><input className="inp" type="date" value={f.date} onChange={(e) => set("date")(e.target.value)} /></label>
              <Dropdown label="Start time" value={f.time} onChange={set("time")} options={["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]} />
              <Dropdown label="Length" value={f.duration} onChange={set("duration")} options={O.DURATIONS} />
              <Dropdown label="Gap" value={f.buffer} onChange={set("buffer")} options={O.BUFFERS} />
              <Dropdown label="Day starts" value={f.day_start} onChange={set("day_start")} options={O.HOURS} />
              <Dropdown label="Day ends" value={f.day_end} onChange={set("day_end")} options={O.HOURS_END} />
              <Dropdown label="Round" value={f.round_name} onChange={set("round_name")} options={role.rounds?.length ? role.rounds : O.ROUNDS} />
              <Dropdown label="Format" value={f.mode} onChange={set("mode")} options={O.MODES} />
            </div>
            <label className="field"><span className="field-label">Meeting link or address (optional)</span>
              <input className="inp" value={f.link} onChange={(e) => set("link")(e.target.value)} placeholder="Paste your Meet, Teams or Zoom link" /></label>
            <Toggle label="Keep 13:00 to 14:00 free for lunch" on={f.lunch} onChange={set("lunch")} />
            {err && <p className="error">{err}</p>}
            <button className="btn sun wide" disabled={!list.length || busy} onClick={book}><CalendarCheck size={18} />Book {ids.length} interview{ids.length > 1 ? "s" : ""}</button>
          </div>
        )}
        {booked && (
          <div className="stack">
            <p className="lede">Nothing leaves this computer on its own. Use each row to email the candidate, or download the calendar file and open it in Google Calendar or Outlook.</p>
            <div className="nav left">
              <a className="btn" href={`/api/calendar.ics?req_id=${role.id}`}><CalendarPlus size={18} />Download all as .ics</a>
              <button className="btn ghost" onClick={onInterviews}>Go to interviews</button>
            </div>
          </div>
        )}
      </div>

      <div className="timeline" aria-live="polite">
        <h3>{booked ? `${booked.length} on the calendar` : preview.length ? "Preview" : "Pick candidates to preview slots"}</h3>
        {Object.entries(days).map(([day, ms]) => (
          <div key={day} className="day">
            <div className="day-label">{fmtDay(day)}</div>
            <AnimatePresence initial={false}>
              {ms.map((m, i) => (
                <motion.div key={m.id ?? m.candidate_id} className="slot" layout initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, height: 0 }} transition={{ delay: i * 0.04 }}
                  style={{ borderLeftColor: colorOf(m.interviewer, list) }}>
                  <div className="slot-time">{fmtTime(m.start)}<small>{m.duration} min</small></div>
                  <div className="slot-main"><b>{m.candidate_name}</b><span>with {m.interviewer}</span></div>
                  {booked && (
                    <div className="slot-actions">
                      {m.candidate_email && <a className="icon-btn" href={mailto(m)} title="Email invite" aria-label={`Email invite to ${m.candidate_name}`}><Mail size={17} /></a>}
                      <button className="icon-btn" title="Copy invite text" aria-label="Copy invite text" onClick={() => navigator.clipboard?.writeText(`${m.invite.subject}\n\n${m.invite.body}`)}><Copy size={17} /></button>
                      <a className="icon-btn" href={`/api/meetings/${m.id}.ics`} title="Download .ics" aria-label="Download calendar file"><CalendarPlus size={17} /></a>
                      <button className="icon-btn danger" title="Cancel" aria-label={`Cancel interview with ${m.candidate_name}`} onClick={() => cancel(m)}><Trash2 size={17} /></button>
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        ))}
      </div>
    </div>
  );
}
