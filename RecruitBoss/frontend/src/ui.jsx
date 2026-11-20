import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown, Plus, X } from "lucide-react";
import { STAGES } from "./options";

const norm = (o) => (typeof o === "object" ? o : { value: o, label: String(o) });

/** Custom dropdown: click or keyboard (arrows, Enter, Esc). */
export function Dropdown({ label, value, onChange, options, placeholder = "Choose…", hint }) {
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const root = useRef(null);
  const opts = useMemo(() => options.map(norm), [options]);
  const cur = opts.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const away = (e) => root.current && !root.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  const pick = (o) => { onChange(o.value); setOpen(false); };
  const key = (e) => {
    if (!open && ["ArrowDown", "Enter", " "].includes(e.key)) { e.preventDefault(); setHi(Math.max(0, opts.findIndex((o) => o.value === value))); setOpen(true); return; }
    if (!open) return;
    if (e.key === "Escape") setOpen(false);
    else if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(opts.length - 1, h + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); pick(opts[hi]); }
  };

  return (
    <div className="field" ref={root}>
      {label && <span className="field-label">{label}</span>}
      <button type="button" className={`dd ${open ? "open" : ""}`} onClick={() => { setHi(Math.max(0, opts.findIndex((o) => o.value === value))); setOpen(!open); }}
        onKeyDown={key} aria-haspopup="listbox" aria-expanded={open}>
        <span className={cur ? "" : "ph"}>{cur ? cur.label : placeholder}</span>
        <ChevronDown size={18} className="chev" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.ul role="listbox" className="dd-list" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.14 }}>
            {opts.map((o, i) => (
              <li key={String(o.value)} role="option" aria-selected={o.value === value} className={`${i === hi ? "hi" : ""} ${o.value === value ? "sel" : ""}`}
                onMouseEnter={() => setHi(i)} onMouseDown={(e) => { e.preventDefault(); pick(o); }}>
                <span>{o.label}</span>{o.value === value && <Check size={16} />}
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
      {hint && <span className="field-hint">{hint}</span>}
    </div>
  );
}

/** Type something, press Enter, it becomes a chip. Suggestions are one click. */
export function ChipPicker({ label, values, onChange, suggestions = [], placeholder, hint, tone = "blue" }) {
  const [text, setText] = useState("");
  const has = (s) => values.some((v) => v.toLowerCase() === s.toLowerCase());
  const add = (s) => { s = s.trim(); if (s && !has(s)) onChange([...values, s]); setText(""); };
  const rest = suggestions.filter((s) => !has(s));
  return (
    <div className="field">
      {label && <span className="field-label">{label}</span>}
      <div className={`chips-box tone-${tone}`}>
        <AnimatePresence initial={false}>
          {values.map((v) => (
            <motion.span key={v} layout initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.6, opacity: 0 }} className="chip on">
              {v}<button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(values.filter((x) => x !== v))}><X size={13} /></button>
            </motion.span>
          ))}
        </AnimatePresence>
        <input value={text} placeholder={values.length ? "" : placeholder} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(text); } else if (e.key === "Backspace" && !text && values.length) onChange(values.slice(0, -1)); }} />
      </div>
      {rest.length > 0 && (
        <div className="suggest">
          {rest.slice(0, 12).map((s) => (<button type="button" key={s} className="chip" onClick={() => add(s)}><Plus size={13} />{s}</button>))}
        </div>
      )}
      {hint && <span className="field-hint">{hint}</span>}
    </div>
  );
}

export function Toggle({ label, on, onChange }) {
  return (
    <button type="button" className={`toggle ${on ? "on" : ""}`} role="switch" aria-checked={on} onClick={() => onChange(!on)}>
      <span className="knob" /><span>{label}</span>
    </button>
  );
}

export function Orb({ busy, size = 14 }) {
  return <span className={`orb ${busy ? "busy" : ""}`} style={{ width: size, height: size }} />;
}

export function Score({ n, size = 52 }) {
  const tone = n >= 75 ? "mint" : n >= 55 ? "sun" : "coral";
  const r = size / 2 - 4, c = 2 * Math.PI * r;
  return (
    <span className={`score tone-${tone}`} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} className="track" />
        <motion.circle cx={size / 2} cy={size / 2} r={r} className="arc" strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - n / 100) }} transition={{ duration: 0.8, ease: "easeOut" }} />
      </svg>
      <b>{n}</b>
    </span>
  );
}

export function StageChip({ stage }) {
  const [label, tone] = STAGES[stage || "screened"] || [stage, "plain"];
  return <span className={`stage st-${tone}`}>{label}</span>;
}

export function Modal({ title, onClose, children, wide }) {
  useEffect(() => {
    const k = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", k);
    return () => document.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <motion.div className="modal-back" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <motion.div role="dialog" aria-modal="true" aria-label={title} className={`modal ${wide ? "wide" : ""}`} initial={{ y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 24, opacity: 0 }}>
        <div className="modal-head"><h3>{title}</h3><button className="icon-btn" aria-label="Close" onClick={onClose}><X size={18} /></button></div>
        {children}
      </motion.div>
    </motion.div>
  );
}

export function Empty({ title, text, children }) {
  return <div className="empty-state"><h3>{title}</h3><p>{text}</p>{children}</div>;
}
