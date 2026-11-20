import { motion } from "framer-motion";

const TITLES = { schedule: "Which role are we scheduling?", screen: "Which role are we screening for?", workspace: "Which role are we working on?" };

export default function Pipeline({ roles, intent, onPick }) {
  return (
    <div className="pipeline">
      <h2>{TITLES[intent] || "All roles"}</h2>
      {roles.length === 0 && <p className="lede">No roles yet. Start by recruiting for one.</p>}
      <ul className="roles">
        {roles.map((r, i) => {
          const st = r.stages || {};
          const n = (...k) => k.reduce((a, x) => a + (st[x] || 0), 0);
          const off = (intent === "schedule" || intent === "workspace") && !r.candidate_count;
          const bits = [r.candidate_count && `${r.candidate_count} screened`, n("interviewing", "evaluated") && `${n("interviewing", "evaluated")} interviewing`,
            n("offer_draft", "offer_pending", "offer_approved", "offer_sent") && `${n("offer_draft", "offer_pending", "offer_approved", "offer_sent")} with offers`,
            n("onboarding", "joined") && `${n("onboarding", "joined")} hired`].filter(Boolean);
          return (
            <motion.li key={r.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
              <button className="role" disabled={off} onClick={() => onPick(r)}>
                <span className="role-title">{r.title}<em>{r.seniority} · {r.department} · {r.status === "closed" ? "Closed" : `${r.openings} opening${r.openings > 1 ? "s" : ""}`}</em></span>
                <span className="role-meta">{bits.join(" · ") || "No candidates yet"}</span>
                <span className="role-go">{off ? "Screen candidates first" : r.candidate_count ? (intent === "schedule" ? "Schedule" : "Open") : "Upload candidates"}</span>
              </button>
            </motion.li>
          );
        })}
      </ul>
    </div>
  );
}
