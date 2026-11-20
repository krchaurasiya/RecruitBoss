import { Pencil } from "lucide-react";
import Results from "./Results";
import { Analytics, Decisions, Interviews, Offers, Onboarding } from "./Tabs";

export default function Workspace({ ctx }) {
  const { role, cands, meetings, tab, setTab, onEdit } = ctx;
  const n = (...st) => cands.filter((c) => st.includes(c.stage)).length;
  const tabs = [
    ["shortlist", "Shortlist", n("screened", "shortlisted")],
    ["interviews", "Interviews", meetings.filter((m) => m.status !== "completed").length],
    ["decisions", "Decisions", n("evaluated")],
    ["offers", "Offers", n("offer_draft", "offer_pending", "offer_approved", "offer_sent")],
    ["onboarding", "Onboarding", n("onboarding")],
    ["analytics", "Analytics", 0],
  ];
  return (
    <div className="workspace">
      <div className="ws-head">
        <div>
          <h1>{role.title}</h1>
          <p className="muted">{role.seniority} · {role.department} · {role.openings} opening{role.openings > 1 ? "s" : ""} · <span className={`pill-s ${role.status}`}>{role.status === "closed" ? "Closed" : role.status === "approved" ? "Approved" : "Open"}</span></p>
        </div>
        <button className="btn ghost small" onClick={onEdit}><Pencil size={15} />Edit brief</button>
      </div>
      <nav className="tabs" role="tablist" aria-label="Role workspace">
        {tabs.map(([k, label, count]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
            {label}{count > 0 && <span className="count">{count}</span>}
          </button>
        ))}
      </nav>
      {tab === "shortlist" && <Results {...ctx.results} />}
      {tab === "interviews" && <Interviews ctx={ctx} />}
      {tab === "decisions" && <Decisions ctx={ctx} />}
      {tab === "offers" && <Offers ctx={ctx} />}
      {tab === "onboarding" && <Onboarding ctx={ctx} />}
      {tab === "analytics" && <Analytics ctx={ctx} />}
    </div>
  );
}
