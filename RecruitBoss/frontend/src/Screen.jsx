import { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, FileArchive, Info, UploadCloud, XCircle } from "lucide-react";
import { api } from "./api";
import { DEPTH } from "./options";
import { Dropdown, Orb } from "./ui";

const SEV = { error: XCircle, warn: AlertTriangle, info: Info };

export function CheckReport({ report }) {
  if (!report) return null;
  return (
    <div className="check">
      <div className="check-head">
        <CheckCircle2 size={22} />
        <div>
          <b>{report.usable} usable candidates</b> from {report.total_rows} rows in {report.files.length} file{report.files.length > 1 ? "s" : ""}
          {report.duplicates_removed > 0 && <>, {report.duplicates_removed} duplicate removed</>}
        </div>
      </div>
      <ul className="files">
        {report.files.map((f) => (
          <li key={f.name} className={f.skipped ? "skipped" : ""}>
            <FileArchive size={16} /><span className="fname">{f.name}</span><span>{f.rows} rows</span>
            <span className="cols">{Object.entries(f.mapped).map(([k, v]) => `${v} → ${k}`).join(" · ")}</span>
          </li>
        ))}
      </ul>
      {report.issues.length > 0 && (
        <ul className="issues">
          {report.issues.map((i, k) => {
            const Icon = SEV[i.severity];
            return (
              <motion.li key={k} className={`sev-${i.severity}`} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: k * 0.06 }}>
                <Icon size={18} />
                <div><b>{i.count > 1 ? `${i.count} rows: ` : ""}</b>{i.message}{i.examples.length > 0 && <span className="ex"> {i.examples.join(", ")}{i.count > i.examples.length ? "…" : ""}</span>}</div>
              </motion.li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function Screen({ role, existingCount = 0, model, setModel, health, depth, setDepth, onDone }) {
  const [file, setFile] = useState(null);
  const [drag, setDrag] = useState(false);
  const [state, setState] = useState("idle"); // idle | running | error
  const [report, setReport] = useState(null);
  const [plan, setPlan] = useState(null);
  const [prog, setProg] = useState({ done: 0, total: 0, name: "" });
  const [warn, setWarn] = useState("");
  const [err, setErr] = useState("");
  const input = useRef(null);

  const take = (fl) => {
    const x = fl?.[0];
    if (!x) return;
    if (!/\.(zip|csv|pdf|docx|txt)$/i.test(x.name)) { setErr("Upload a .zip of CSV or resume files, or a single .csv."); return; }
    setErr(""); setFile(x);
  };

  async function run() {
    setState("running"); setErr(""); setReport(null); setPlan(null); setWarn(""); setProg({ done: 0, total: 0, name: "" });
    let finished = null;
    try {
      await api.screen(role.id, file, model, depth, (ev) => {
        if (ev.type === "check") setReport(ev.report);
        else if (ev.type === "plan") setPlan(ev);
        else if (ev.type === "progress") setProg({ done: ev.done, total: ev.total, name: ev.name });
        else if (ev.type === "warn") setWarn(ev.message);
        else if (ev.type === "error") throw new Error(ev.message);
        else if (ev.type === "done") finished = ev;
      });
      if (!finished) throw new Error("The screening stopped early. Check that the backend is still running.");
      onDone(finished, report);
    } catch (e) { setErr(e.message); setState("error"); }
  }

  const running = state === "running";
  const pct = prog.total ? Math.round((prog.done / prog.total) * 100) : 0;
  const aiOn = health?.online;

  return (
    <div className="screen">
      <h2>Upload your candidates</h2>
      <p className="lede">Zip your CSV files (resumes as .pdf, .docx or .txt work too) and drop them here. I'll read every file and rank people for <b>{role.title}</b>.{existingCount > 0 && <> {existingCount} people are already in this role. New uploads are added, and anyone with a matching email is skipped.</>}</p>

      {!running && (
        <>
          <div className={`drop ${drag ? "drag" : ""} ${file ? "has" : ""}`} role="button" tabIndex={0}
            onClick={() => input.current?.click()} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); take(e.dataTransfer.files); }}>
            <input ref={input} type="file" accept=".zip,.csv,.pdf,.docx,.txt" hidden onChange={(e) => take(e.target.files)} />
            <motion.div animate={drag ? { scale: 1.15, y: -4 } : { scale: 1, y: 0 }}>{file ? <FileArchive size={40} /> : <UploadCloud size={40} />}</motion.div>
            {file ? (<><b>{file.name}</b><span>{(file.size / 1024).toFixed(0)} KB. Click to choose a different file.</span></>)
              : (<><b>Drop your .zip here</b><span>or click to browse. A single .csv or resume works too.</span></>)}
          </div>
          <p className="field-hint">No file yet? <a href="/sample_candidates.zip" download>Download a sample zip</a> of made-up candidates with a few deliberate mistakes.</p>

          <div className="grid2 opts">
            <Dropdown label="How closely should the AI read?" value={depth} onChange={setDepth} options={DEPTH.map((d) => ({ value: d.value, label: d.label }))}
              hint={DEPTH.find((d) => d.value === depth).hint} />
            {aiOn && depth !== "fast" && (
              <Dropdown label="Model" value={model} onChange={setModel} options={health.models.map((m) => ({ value: m, label: m }))} hint="Installed on this computer." />
            )}
          </div>
          {!aiOn && <p className="notice"><Info size={18} />Ollama isn't running, so candidates will be ranked by rules only. Start Ollama and refresh for AI reading.</p>}
          {err && <p className="error">{err}</p>}
          <div className="nav"><button className="btn sun" disabled={!file} onClick={run}>Check and rank candidates</button></div>
        </>
      )}

      {running && (
        <div className="working">
          <div className="working-head"><Orb busy size={18} /><b>{!report ? "Checking your files…" : plan?.ai_total ? `${plan.model} is reading profiles` : "Ranking candidates…"}</b></div>
          <AnimatePresence>{report && <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}><CheckReport report={report} /></motion.div>}</AnimatePresence>
          {plan?.ai_total > 0 && (
            <div className="bar-wrap" aria-live="polite">
              <div className="bar"><motion.span animate={{ width: `${pct}%` }} transition={{ duration: 0.4 }} /></div>
              <p>{prog.done} of {prog.total} read{prog.name && prog.done < prog.total ? `. Now: ${prog.name}` : ""}</p>
            </div>
          )}
          {warn && <p className="notice"><AlertTriangle size={18} />{warn}</p>}
        </div>
      )}
      {state === "error" && !running && report && <CheckReport report={report} />}
    </div>
  );
}
