"""Builds sample_data/sample_candidates.zip : synthetic people only, with a few deliberately messy rows."""
import csv, io, random, zipfile
from pathlib import Path

random.seed(7)
first = ["Aarav","Diya","Rohan","Meera","Kabir","Ishita","Arjun","Sana","Vikram","Neha","Dev","Anaya","Rahul","Tara","Nikhil",
         "Priya","Siddharth","Kavya","Aditya","Riya","Manav","Zoya","Karan","Pooja","Yash","Lakshmi","Omkar","Nisha","Varun","Anika"]
last = ["Naik","Desai","Kamat","Fernandes","Shetty","Gaonkar","Pai","Dessai","Rao","Menon","Kulkarni","Sharma","Iyer","Bhat","D'Souza"]
cities = ["Panaji","Margao","Mumbai","Pune","Bengaluru","Hyderabad","Panaji","Goa","Panaji"]
profiles = {
 "Data Scientist": (["Python","SQL","Machine Learning","Pandas","scikit-learn","Statistics","NLP","TensorFlow","Power BI"], "M.Sc Data Science"),
 "ML Engineer": (["Python","PyTorch","TensorFlow","Docker","AWS","Machine Learning","LLM","Kubernetes","FastAPI"], "B.Tech Computer Science"),
 "Frontend Developer": (["JavaScript","React","TypeScript","CSS","HTML","Node.js","Git"], "B.Sc Computer Science"),
 "Backend Developer": (["Python","FastAPI","PostgreSQL","Docker","Redis","SQL","AWS","Git"], "B.E. Information Technology"),
 "Data Analyst": (["SQL","Excel","Power BI","Python","Tableau","Statistics"], "B.Com"),
}
edu_alt = ["MBA","B.Tech","M.Tech","Diploma in IT","B.Sc","PhD Computer Science","BCA"]
companies = ["Beachline Tech","Mandovi Analytics","Zuari Systems","Konkan Labs","Calangute Digital","Western Ghats AI","Sahyadri Soft"]

def person(i):
    role = random.choice(list(profiles))
    pool, edu = profiles[role]
    sk = random.sample(pool, k=random.randint(3, min(7, len(pool))))
    exp = round(random.choice([0.5,1,1.5,2,3,3.5,4,5,6,7,8,10]) + 0, 1)
    nm = f"{random.choice(first)} {random.choice(last)}"
    return {
        "Full Name": nm, "Email": f"{nm.lower().replace(' ','.').replace(chr(39),'')}{i}@example.com",
        "Phone": f"98{random.randint(10000000,99999999)}", "Current Role": role, "Company": random.choice(companies),
        "Location": random.choice(cities), "Years of Experience": exp,
        "Education": random.choice([edu, edu, random.choice(edu_alt)]),
        "Notice Period": random.choice(["Immediate","15 days","30 days","60 days","90 days","2 months"]),
        "Skills": ", ".join(sk),
        "Resume Summary": f"{role} with {exp} years of experience. Worked on projects using {', '.join(sk[:3])}. "
                          f"Currently at a product company in {random.choice(cities)}.",
    }

rows = [person(i) for i in range(1, 37)]
a, b = rows[:20], rows[20:]
# deliberate mess
b.append(dict(b[0]))                                          # duplicate email
b.append({**person(99), "Email": "not-an-email"})              # bad email
b.append({**person(98), "Email": ""})                          # missing email
b.append({**person(97), "Full Name": ""})                      # missing name
b.append({**person(96), "Years of Experience": "a lot"})       # bad experience
b.append({**person(95), "Skills": "", "Resume Summary": ""})   # nothing to judge
hdr = list(rows[0].keys())

def to_csv(rs, headers):
    s = io.StringIO(); w = csv.DictWriter(s, fieldnames=headers); w.writeheader(); w.writerows(rs); return s.getvalue()

# second file uses different header names on purpose, to prove column matching works
alt = {"Full Name":"Candidate","Email":"E-mail","Years of Experience":"Experience (yrs)","Current Role":"Designation","Skills":"Key Skills","Resume Summary":"Profile"}
b2 = [{alt.get(k,k): v for k, v in r.items()} for r in b]
out = Path(__file__).parent / "sample_candidates.zip"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("batch_1_campus_referrals.csv", to_csv(a, hdr))
    z.writestr("batch_2_job_portal.csv", to_csv(b2, list(b2[0].keys())))
print("wrote", out, len(a), len(b2))
