import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { Home as HomeIcon, Network } from "lucide-react";
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/instrument-sans";
import "./styles.css";
import { api } from "./api";
import AgentsPanel from "./AgentsPanel";
import Brief from "./Brief";
import HomeView from "./Home";
import Pipeline from "./Pipeline";
import Schedule from "./Schedule";
import Screen from "./Screen";
import Workspace from "./Workspace";
import { Orb } from "./ui";

const FLOW = [["brief", "Brief"], ["upload", "Candidates"]];
const OPEN = ["screened", "shortlisted", "interviewing", "evaluated"];
const okEmail = (e) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e || "");

export default function App() {
  const [view, setView] = useState("home");
  const [tab, setTab] = useState("shortlist");
  const [intent, setIntent] = useState("");
  const [roles, setRoles] = useState([]);
  const [role, setRole] = useState(null);
  const [editing, setEditing] = useState(null);
  const [cands, setCands] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [report, setReport] = useState(null);
  const [aiUsed, setAiUsed] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [cutoff, setCutoff] = useState(70);
  const [booked, setBooked] = useState(null);
  const [health, setHealth] = useState(null);
  const [model, setModel] = useState("");
  const [depth, setDepth] = useState("balanced");
  const [loadErr, setLoadErr] = useState("");
  const [toast, setToast] = useState(null);
  const [agentsOpen, setAgentsOpen] = useState(false);
  const [latest, setLatest] = useState(0);
  const seen = useRef(0);
  const roleId = useRef(null);
  roleId.current = role?.id ?? null;

  const refreshRoles = useCallback(() => api.roles().then(setRoles).catch(() => setLoadErr("Can't reach the backend. Is it running?")), []);
  useEffect(() => { refreshRoles(); }, [refreshRoles]);
  useEffect(() => {
    const tick = () => api.health().then((h) => { setHealth(h); setModel((m) => m || h.default); setLoadErr(""); }).catch(() => setHealth({ online: false, models: [] }));
    tick(); const t = setInterval(tick, 10000); return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const t = setInterval(() => api.traces(1).then((x) => x[0] && setLatest(x[0].id)).catch(() => {}), 4000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => { if (agentsOpen) seen.current = latest; }, [agentsOpen, latest]);
  useEffect(() => { window.scrollTo(0, 0); }, [view, booked ? "booked" : "open"]);

  const notify = useCallback((text, bad = false) => {
    setToast({ text, bad, k: Date.now() });
    api.traces(1).then((x) => x[0] && setLatest(x[0].id)).catch(() => {});
    setTimeout(() => setToast((t) => (t && Date.now() - t.k >= 4500 ? null : t)), 4600);
  }, []);

  const reload = useCallback(async () => {
    const id = roleId.current;
    if (!id) return;
    const [r, cs, ms, rs] = await Promise.all([api.role(id), api.candidates(id), api.meetings(id), api.roles()]);
    setRole((o) => ({ ...(o || {}), ...r }));
    setCands(cs); setMeetings(ms); setRoles(rs);
  }, []);

  const preselect = (list, cut) => new Set(list.filter((c) => OPEN.includes(c.stage || "screened") && c.final_score >= cut && okEmail(c.email)).map((c) => c.id));

  async function openRole(r, wanted) {
    const full = await api.role(r.id);
    const merged = { ...r, ...full };
    setRole(merged); roleId.current = merged.id; setBooked(null); setReport(null);
    if (!r.candidate_count) { setCands([]); setMeetings([]); setView(wanted === "schedule" || wanted === "workspace" ? "upload" : "upload"); return; }
    const [cs, ms] = await Promise.all([api.candidates(r.id), api.meetings(r.id)]);
    setCands(cs); setMeetings(ms); setAiUsed(!!full.model);
    if (wanted === "schedule") {
      const sl = cs.filter((c) => c.stage === "shortlisted" && okEmail(c.email));
      setSelected(sl.length ? new Set(sl.map((c) => c.id)) : preselect(cs, cutoff));
      setView("schedule");
    } else {
      setSelected(preselect(cs, cutoff));
      setTab(wanted === "workspace" ? "interviews" : "shortlist");
      setView("workspace");
    }
  }

  function go(target) {
    if (target === "brief") { setEditing(null); setView("brief"); return; }
    if (target.startsWith("pipeline")) { setIntent(target.split(":")[1] || ""); refreshRoles(); setView("pipeline"); return; }
    setView(target);
  }

  const goSchedule = (ids) => { setSelected(new Set(ids)); setBooked(null); setView("schedule"); };
  const inFlow = FLOW.findIndex(([k]) => k === view);
  const online = !!health?.online;

  const ctx = role && {
    role, cands, meetings, model, reload, notify, tab, setTab, goSchedule,
    onEdit: () => { setEditing(role); setView("brief"); },
    results: {
      role, cands, report, aiUsed, selected, setSelected, cutoff, setCutoff, reload, notify, onMore: () => setView("upload"),
      onSchedule: async (ids) => { try { await api.shortlist(role.id, ids); await reload(); setBooked(null); setView("schedule"); } catch (e) { notify(e.message, true); } },
    },
  };

  return (
    <MotionConfig reducedMotion="user">
      <div className={`app view-${view}`}>
        <header className="top">
          <button className="brand" onClick={() => { refreshRoles(); setView("home"); }} aria-label="Back to start"><span className="logo" />RecruitBoss</button>
          {inFlow >= 0 ? (
            <nav className="steps" aria-label="Progress">
              {FLOW.map(([k, label], i) => (<span key={k} className={`step ${i === inFlow ? "now" : i < inFlow ? "past" : ""}`}><b>{i + 1}</b>{label}</span>))}
            </nav>
          ) : <span />}
          <div className="top-right">
            <button className="agents-btn" onClick={() => setAgentsOpen(!agentsOpen)} aria-pressed={agentsOpen} title="See which agents did what">
              <Network size={16} />Agents{latest > seen.current && !agentsOpen && <i className="dot" />}
            </button>
            <div className={`status ${online ? "ok" : "off"}`} title={online ? "Ollama is running on this computer" : health?.error || "Ollama isn't reachable"}>
              <Orb busy={false} size={10} />{online ? (model || health.default) : "Ollama offline: rules only"}
            </div>
          </div>
        </header>

        {loadErr && <div className="banner">{loadErr}</div>}

        <main>
          <AnimatePresence mode="wait">
            <motion.div key={view} className="view" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
              {view === "home" && <HomeView roles={roles} onGo={go} />}
              {view === "brief" && (
                <Brief key={editing?.id || "new"} model={model} online={online} existing={editing} onCreated={() => refreshRoles()}
                  onDone={async (r) => {
                    if (r.screened) { setRole(r); roleId.current = r.id; await reload(); setTab("shortlist"); setView("workspace"); }
                    else { setRole({ ...r, candidate_count: 0 }); setCands([]); setMeetings([]); setView("upload"); }
                  }} />
              )}
              {view === "pipeline" && <Pipeline roles={roles} intent={intent} onPick={(r) => openRole(r, intent)} />}
              {view === "upload" && role && (
                <Screen role={role} existingCount={cands.length} model={model} setModel={setModel} health={health} depth={depth} setDepth={setDepth}
                  onDone={(ev, rep) => { setCands(ev.candidates); setReport(rep); setAiUsed(ev.ai_used); setSelected(preselect(ev.candidates, cutoff)); setBooked(null); setTab("shortlist"); reload(); setView("workspace"); }} />
              )}
              {view === "workspace" && ctx && <Workspace ctx={ctx} />}
              {view === "schedule" && role && (
                <Schedule role={role} cands={cands} selected={selected} booked={booked} setBooked={(b) => { setBooked(b); reload(); }}
                  onBack={() => { setTab("shortlist"); setView("workspace"); }} onInterviews={() => { setTab("interviews"); setView("workspace"); }} />
              )}
            </motion.div>
          </AnimatePresence>
        </main>

        {view !== "home" && <button className="home-fab" onClick={() => { refreshRoles(); setView("home"); }} aria-label="Home"><HomeIcon size={20} /></button>}
        <AnimatePresence>{agentsOpen && <AgentsPanel roleId={role?.id} onClose={() => setAgentsOpen(false)} />}</AnimatePresence>
        <AnimatePresence>
          {toast && <motion.div key={toast.k} className={`toast ${toast.bad ? "bad" : ""}`} role="status" initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 30, opacity: 0 }}>{toast.text}</motion.div>}
        </AnimatePresence>
      </div>
    </MotionConfig>
  );
}
