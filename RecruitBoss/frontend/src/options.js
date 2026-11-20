// Every dropdown the boss sees lives here. Edit freely.
export const TITLES = [
  "Data Scientist", "ML Engineer", "AI Engineer", "Data Analyst", "Frontend Developer", "Backend Developer",
  "Full-stack Developer", "DevOps Engineer", "QA Engineer", "Product Manager", "UI/UX Designer", "Business Analyst",
  "HR Executive", "Sales Executive", "Marketing Executive", "Other…",
];
export const DEPARTMENTS = ["Engineering", "Data & AI", "Product", "Design", "Sales", "Marketing", "HR", "Operations", "Finance"];
export const SENIORITY = ["Intern", "Junior", "Mid-level", "Senior", "Lead", "Manager"];
export const OPENINGS = Array.from({ length: 10 }, (_, i) => ({ value: i + 1, label: i === 0 ? "1 opening" : `${i + 1} openings` }));
export const EMPLOYMENT = ["Full-time", "Part-time", "Contract", "Internship"];
export const WORK_MODES = ["On-site", "Hybrid", "Remote"];
export const LOCATIONS = ["Panaji", "Margao", "Mumbai", "Pune", "Bengaluru", "Hyderabad", "Chennai", "Delhi NCR", "Other…"];
export const SALARY = [
  { value: "none", label: "Not decided yet" },
  { value: "3-6", label: "3 to 6 lakh per year", min: 300000, max: 600000 },
  { value: "6-10", label: "6 to 10 lakh per year", min: 600000, max: 1000000 },
  { value: "10-15", label: "10 to 15 lakh per year", min: 1000000, max: 1500000 },
  { value: "15-25", label: "15 to 25 lakh per year", min: 1500000, max: 2500000 },
  { value: "25-40", label: "25 to 40 lakh per year", min: 2500000, max: 4000000 },
  { value: "40+", label: "40 lakh and above", min: 4000000, max: null },
];
export const NOTICE = [
  { value: "", label: "Doesn't matter" },
  { value: 0, label: "Can join immediately" },
  { value: 15, label: "Up to 15 days" },
  { value: 30, label: "Up to 30 days" },
  { value: 60, label: "Up to 60 days" },
  { value: 90, label: "Up to 90 days" },
];
export const URGENCY = ["Low (within 3 months)", "Normal (within 6 weeks)", "Urgent (within 2 weeks)"];
export const EXPERIENCE = [
  { value: "0-1", label: "Fresher (0 to 1 year)", min: 0, max: 1 },
  { value: "1-3", label: "1 to 3 years", min: 1, max: 3 },
  { value: "3-5", label: "3 to 5 years", min: 3, max: 5 },
  { value: "5-8", label: "5 to 8 years", min: 5, max: 8 },
  { value: "8-12", label: "8 to 12 years", min: 8, max: 12 },
  { value: "12-20", label: "12 years and above", min: 12, max: 20 },
];
export const EDUCATION = [
  { value: "Any", label: "Any qualification" },
  { value: "Diploma", label: "Diploma or higher" },
  { value: "Bachelor's", label: "Bachelor's or higher" },
  { value: "Master's", label: "Master's or higher" },
  { value: "PhD", label: "PhD" },
];
export const ROUNDS = ["Screening call", "Technical interview", "Assignment review", "Manager round", "HR round", "Culture fit"];
export const INTERVIEWERS = ["Hiring manager", "Tech lead", "HR partner", "Founder"];
export const DURATIONS = [30, 45, 60, 90].map((m) => ({ value: m, label: `${m} minutes` }));
export const BUFFERS = [0, 10, 15, 30].map((m) => ({ value: m, label: m ? `${m} min break between` : "No break between" }));
export const MODES = ["Video call", "Phone call", "On-site"];
export const HOURS = ["08:00", "09:00", "10:00", "11:00"].map((v) => ({ value: v, label: v }));
export const HOURS_END = ["16:00", "17:00", "18:00", "19:00"].map((v) => ({ value: v, label: v }));
export const DEPTH = [
  { value: "fast", label: "Quick: rules only", hint: "Seconds. No AI reading." },
  { value: "balanced", label: "Balanced: AI reads the top 10", hint: "A few minutes on a laptop." },
  { value: "deep", label: "Deep: AI reads everyone", hint: "Slowest. Best for small batches." },
];

const SKILLS = [
  [/data scien|ml |machine|ai eng/i, ["Python", "SQL", "Machine Learning", "Pandas", "scikit-learn", "Statistics", "NLP", "TensorFlow", "PyTorch", "Deep Learning", "LLM"]],
  [/analyst/i, ["SQL", "Excel", "Power BI", "Tableau", "Python", "Statistics", "Data Visualization"]],
  [/front/i, ["JavaScript", "React", "TypeScript", "HTML", "CSS", "Git", "Node.js", "Next.js"]],
  [/back/i, ["Python", "FastAPI", "Node.js", "PostgreSQL", "SQL", "Docker", "Redis", "AWS", "REST APIs", "Git"]],
  [/full/i, ["JavaScript", "React", "Node.js", "Python", "SQL", "Docker", "Git", "TypeScript"]],
  [/devops/i, ["Docker", "Kubernetes", "AWS", "CI/CD", "Linux", "Terraform", "Git"]],
  [/qa|test/i, ["Selenium", "Test Automation", "Python", "SQL", "API Testing", "Git"]],
  [/design|ux/i, ["Figma", "User Research", "Prototyping", "Design Systems"]],
  [/product/i, ["Roadmapping", "User Research", "SQL", "Stakeholder Management", "Analytics"]],
  [/hr/i, ["Recruitment", "Onboarding", "Employee Relations", "Excel"]],
  [/sales|marketing/i, ["Communication", "CRM", "Negotiation", "Lead Generation", "Excel"]],
];
const GENERIC = ["Communication", "Excel", "SQL", "Python", "Git", "Problem Solving", "Teamwork"];
export function skillSuggestions(title) {
  for (const [re, list] of SKILLS) if (re.test(title || "")) return list;
  return GENERIC;
}

export const REJECT_REASONS = ["Skills don't match the role", "Not enough experience", "Position filled", "Notice period too long", "Not the right fit after interviews", "Other"];
export const RECOMMENDATIONS = ["Strong hire", "Hire", "Hold", "No hire"];
export const DEFAULT_CRITERIA = ["Role knowledge", "Problem solving", "Communication", "Culture fit"];
export const STAGES = {
  screened: ["Screened", "plain"], shortlisted: ["Shortlisted", "blue"], interviewing: ["Interview booked", "blue"],
  evaluated: ["Evaluated", "sun"], offer_draft: ["Offer draft", "sun"], offer_pending: ["With HR", "sun"], offer_approved: ["Offer approved", "mint"],
  offer_sent: ["Offer sent", "mint"], onboarding: ["Onboarding", "mint"], joined: ["Joined", "mint"], rejected: ["Rejected", "coral"], declined: ["Declined offer", "coral"],
};
