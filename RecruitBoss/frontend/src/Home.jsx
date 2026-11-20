import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";

const LINE1 = "Hello, boss.";
const LINE2 = "What would you like to do today?";

export default function Home({ roles, onGo }) {
  const [n, setN] = useState(0);
  const total = LINE1.length + LINE2.length;
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { setN(total); return; }
    const t = setInterval(() => setN((x) => (x >= total ? (clearInterval(t), x) : x + 1)), 48);
    return () => clearInterval(t);
  }, [total]);

  const l1 = LINE1.slice(0, n);
  const l2 = LINE2.slice(0, Math.max(0, n - LINE1.length));
  const done = n >= total;
  const screened = roles.filter((r) => r.candidate_count > 0);

  const actions = [
    { id: "recruit", title: "Recruit people", text: "Tell me about the role. I'll draft the job description.", go: () => onGo("brief") },
    { id: "screen", title: "Screen candidates", text: roles.length ? "Upload a zip of CSVs. I'll check the data and rank everyone." : "Create a role first, then upload your CSVs.", go: () => onGo(roles.length ? "pipeline:screen" : "brief"), dim: !roles.length },
    { id: "schedule", title: "Schedule interviews", text: screened.length ? "Book the best-fit people into free slots." : "Available once candidates are screened.", go: () => onGo("pipeline:schedule"), dim: !screened.length },
    { id: "hire", title: "Interview, offer, onboard", text: screened.length ? "Record feedback, decide, send offers, welcome new people." : "Available once candidates are screened.", go: () => onGo("pipeline:workspace"), dim: !screened.length },
    { id: "roles", title: "See all roles", text: roles.length ? `${roles.length} role${roles.length > 1 ? "s" : ""} in progress.` : "Nothing here yet.", go: () => onGo("pipeline"), dim: !roles.length },
  ];

  return (
    <section className="home">
      <div className="home-inner">
        <h1 className="greeting" aria-label={`${LINE1} ${LINE2}`}>
          <span className="g1">{l1}{!done && n <= LINE1.length && <i className="caret" />}</span>
          <span className="g2">{l2}{(done || n > LINE1.length) && <i className={`caret ${done ? "idle" : ""}`} />}</span>
        </h1>
        <motion.ul className="actions" initial="hide" animate={done ? "show" : "hide"} variants={{ show: { transition: { staggerChildren: 0.08 } } }}>
          {actions.map((a) => (
            <motion.li key={a.id} variants={{ hide: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0 } }}>
              <button className={`action ${a.dim ? "dim" : ""}`} onClick={a.go} disabled={!done}>
                <span className="a-title">{a.title}</span>
                <span className="a-text">{a.text}</span>
                <ArrowUpRight className="a-arrow" size={30} />
              </button>
            </motion.li>
          ))}
        </motion.ul>
      </div>
    </section>
  );
}
