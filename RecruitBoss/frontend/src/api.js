const j = async (res) => {
  if (!res.ok) {
    let msg = res.statusText;
    try { const b = await res.json(); msg = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail); } catch { /* keep statusText */ }
    throw new Error(msg);
  }
  return res.json();
};
const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(j);

export const api = {
  health: () => fetch("/api/health").then(j),
  roles: () => fetch("/api/requisitions").then(j),
  role: (id) => fetch(`/api/requisitions/${id}`).then(j),
  createRole: (brief) => post("/api/requisitions", brief),
  reviseRole: (id, brief) => fetch(`/api/requisitions/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(brief) }).then(j),
  approve: (id) => post(`/api/requisitions/${id}/approve`, {}),
  postings: (id, model) => post(`/api/requisitions/${id}/postings`, { model }),
  interviewPlan: (id, model) => post(`/api/requisitions/${id}/interview-plan`, { model }),
  shortlist: (id, ids) => post(`/api/requisitions/${id}/shortlist`, { candidate_ids: ids }),
  reject: (id, ids, reason, feedback) => post(`/api/requisitions/${id}/reject`, { candidate_ids: ids, reason, feedback }),
  scorecard: (cid, body) => post(`/api/candidates/${cid}/scorecard`, body),
  decide: (cid, body) => post(`/api/candidates/${cid}/decision`, body),
  offer: (cid, action, body = {}) => post(`/api/candidates/${cid}/offer/${action}`, body),
  toggleTask: (cid, task_id, done) => post(`/api/candidates/${cid}/onboarding/toggle`, { task_id, done }),
  close: (id) => post(`/api/requisitions/${id}/close`, {}),
  analytics: (id) => fetch(`/api/requisitions/${id}/analytics`).then(j),
  traces: (limit = 80, after = 0) => fetch(`/api/traces?limit=${limit}&after=${after}`).then(j),
  agents: () => fetch("/api/agents").then(j),
  candidates: (id) => fetch(`/api/requisitions/${id}/candidates`).then(j),
  preview: (id, body) => post(`/api/requisitions/${id}/schedule/preview`, body),
  book: (id, body) => post(`/api/requisitions/${id}/schedule`, body),
  meetings: (reqId) => fetch(`/api/meetings${reqId ? `?req_id=${reqId}` : ""}`).then(j),
  cancel: (id) => fetch(`/api/meetings/${id}`, { method: "DELETE" }).then(j),

  // Text streams in as the model writes it.
  async streamJD(id, model, onText) {
    const res = await fetch(`/api/requisitions/${id}/jd?model=${encodeURIComponent(model || "")}`, { method: "POST" });
    if (!res.ok || !res.body) throw new Error("Couldn't start the job description.");
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let text = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      text += dec.decode(value, { stream: true });
      onText(text);
    }
    return text;
  },

  // Newline-delimited JSON events: check, plan, progress, warn, done, error.
  async screen(id, file, model, depth, onEvent) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("model", model || "");
    fd.append("depth", depth);
    const res = await fetch(`/api/requisitions/${id}/screen`, { method: "POST", body: fd });
    if (!res.ok || !res.body) await j(res);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) onEvent(JSON.parse(line));
      }
    }
  },
};

export const fmtDay = (iso) => new Date(iso).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
export const fmtTime = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
export const mailto = (m) =>
  `mailto:${m.candidate_email}?subject=${encodeURIComponent(m.invite.subject)}&body=${encodeURIComponent(m.invite.body)}`;

export const mailtoTo = (to, email) => `mailto:${to || ""}?subject=${encodeURIComponent(email.subject)}&body=${encodeURIComponent(email.body)}`;
export const copy = (t) => navigator.clipboard?.writeText(t);
