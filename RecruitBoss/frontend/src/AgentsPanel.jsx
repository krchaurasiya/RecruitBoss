import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { X } from "lucide-react";
import { api } from "./api";

const SHORT = { requisition: "Requisition", sourcing: "Sourcing", resume_intel: "Resume", matching: "Matching", shortlisting: "Shortlist",
  interview_planning: "Interviews", scheduling: "Scheduling", evaluation: "Evaluation", decision: "Decision", offer_management: "Offer",
  communication: "Comms", onboarding: "Onboarding", closure: "Closure" };

function Hub({ agents, lit }) {
  const R = 128, cx = 170, cy = 160;
  const nodes = agents.map((a, i) => {
    const ang = (-90 + (360 / agents.length) * i) * (Math.PI / 180);
    return { ...a, x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang) };
  });
  return (
    <svg viewBox="0 0 340 320" className="hub" role="img" aria-label="Supervisor connected to thirteen agents">
      {nodes.map((n) => <line key={n.id} x1={cx} y1={cy} x2={n.x} y2={n.y} className={lit.has(n.name) ? "on" : ""} />)}
      <circle cx={cx} cy={cy} r="30" className="sup" />
      <text x={cx} y={cy + 4} textAnchor="middle" className="sup-t">Supervisor</text>
      {nodes.map((n) => (
        <g key={n.id} className={`node ${lit.has(n.name) ? "on" : ""}`}>
          <circle cx={n.x} cy={n.y} r="9" />
          <text x={n.x} y={n.y + (n.y > cy ? 24 : -15)} textAnchor="middle">{SHORT[n.id]}</text>
        </g>
      ))}
    </svg>
  );
}

export default function AgentsPanel({ onClose, roleId }) {
  const [graph, setGraph] = useState(null);
  const [traces, setTraces] = useState([]);
  const [only, setOnly] = useState(false);
  useEffect(() => { api.agents().then(setGraph).catch(() => {}); }, []);
  useEffect(() => {
    const load = () => api.traces(120).then(setTraces).catch(() => {});
    load(); const t = setInterval(load, 2500); return () => clearInterval(t);
  }, []);
  useEffect(() => { const k = (e) => e.key === "Escape" && onClose(); document.addEventListener("keydown", k); return () => document.removeEventListener("keydown", k); }, [onClose]);

  const shown = useMemo(() => traces.filter((t) => !only || t.req_id === roleId), [traces, only, roleId]);
  const lit = useMemo(() => {
    const last = shown[0]?.run;
    return new Set(shown.filter((t) => t.run === last).map((t) => t.agent));
  }, [shown]);
  const runs = useMemo(() => {
    const out = [];
    for (const t of shown) { const g = out[out.length - 1]; if (g && g.run === t.run) g.items.push(t); else out.push({ run: t.run, items: [t] }); }
    return out;
  }, [shown]);

  return (
    <motion.aside className="agents" initial={{ x: 440 }} animate={{ x: 0 }} exit={{ x: 440 }} transition={{ type: "tween", duration: 0.22 }} aria-label="Agent activity">
      <div className="agents-head"><div><h3>Agent activity</h3><p className="muted">A LangGraph supervisor sends each action to the right specialist.</p></div>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button></div>
      {graph && <Hub agents={graph.agents} lit={lit} />}
      <label className="only"><input type="checkbox" checked={only} onChange={(e) => setOnly(e.target.checked)} disabled={!roleId} /> Only this role</label>
      <div className="runs">
        {runs.length === 0 && <p className="muted">Nothing has run yet. Create a role and the agents will show up here.</p>}
        {runs.map((g) => (
          <ol key={g.run + g.items[0].id} className="run">
            {[...g.items].reverse().map((t) => (
              <li key={t.id} className={t.agent === "Supervisor" ? "sup" : ""}>
                <time>{new Date(t.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
                <b>{t.agent}</b><span>{t.text}</span>
              </li>
            ))}
          </ol>
        ))}
      </div>
    </motion.aside>
  );
}
