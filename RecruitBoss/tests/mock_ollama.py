"""Pretends to be Ollama on :11434 so the app can be tested without a GPU. Not used when you run the app for real."""
import json, re, time
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
app = FastAPI()
@app.get("/api/tags")
def tags(): return {"models": [{"name": "qwen2.5:7b-instruct"}, {"name": "qwen2.5:7b"}]}
@app.post("/api/chat")
async def chat(req: Request):
    b = await req.json(); system = b["messages"][0]["content"]; user = b["messages"][-1]["content"]
    if b.get("stream"):
        def gen():
            for w in "About the role\nWe are hiring a great person.\n\nWhat you bring\n- Python and SQL\n".split(" "):
                time.sleep(0.03); yield json.dumps({"message": {"content": w + " "}, "done": False}) + "\n"
            yield json.dumps({"message": {"content": ""}, "done": True}) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson")
    time.sleep(0.15)
    if "short job posts" in system:
        out = {k: f"{k.title()} post: we are hiring a data scientist who knows Python and SQL. Apply today." for k in ["linkedin", "careers", "portal", "referral"]}
    elif "design structured interviews" in system:
        names = json.loads(user.split("Rounds: ")[1].splitlines()[0])
        out = {"rounds": [{"name": n, "focus": f"Probe {n}.", "questions": ["Q1 about work?", "Q2 about tools?", "Q3 about teams?"], "criteria": ["Depth", "Clarity", "Judgement"]} for n in names]}
    elif "summarise interview evidence" in system:
        out = {"summary": "Strong technical answers with clear communication.", "strengths": ["Depth in Python"], "concerns": ["Limited cloud exposure"]}
    elif "extract facts from ONE resume" in system:
        out = {"name": "", "email": "", "current_role": "Data Scientist", "location": "Panaji", "experience_years": 4, "education": "", "skills": ["Pandas"]}
    else:
        n = len(re.findall(r"python", user.lower()))
        out = {"fit_score": 40 + 12 * min(n, 4), "summary": "Relevant background for the role.", "strengths": ["Python experience"], "gaps": ["Cloud not shown"], "interview_focus": ["Ask about a recent project."]}
    return {"message": {"content": json.dumps(out)}, "done": True}
