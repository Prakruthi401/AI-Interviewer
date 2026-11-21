"""Plain keyword based resume tools. No AI here, so every number can be explained."""
import re

# skills we look for. Add more here if you need them.
SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "sql", "mysql", "postgresql",
    "mongodb", "html", "css", "react", "node", "flask", "fastapi", "django", "streamlit",
    "pandas", "numpy", "scikit-learn", "tensorflow", "keras", "pytorch", "opencv",
    "machine learning", "deep learning", "nlp", "llm", "generative ai", "prompt engineering",
    "rag", "langchain", "openai", "gemini", "data analysis", "data visualization",
    "power bi", "tableau", "excel", "statistics", "git", "github", "docker", "aws",
    "azure", "linux", "rest api", "api", "unit testing", "agile", "communication",
    "problem solving", "teamwork",
]

SECTIONS = ["education", "experience", "projects", "skills", "certifications", "summary"]


def find_skills(text):
    text = text.lower()
    found = []
    for skill in SKILLS:
        # word boundaries so "java" does not match "javascript"
        if re.search(r"(?<![a-z+])" + re.escape(skill) + r"(?![a-z+])", text):
            found.append(skill)
    return found


def parse_resume(text):
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    phone = re.search(r"(\+?\d[\d\s-]{8,13}\d)", text)
    lower = text.lower()
    return {
        "email": email.group(0) if email else "not found",
        "phone": phone.group(0).strip() if phone else "not found",
        "sections": [s for s in SECTIONS if s in lower],
        "skills": find_skills(text),
        "words": len(text.split()),
    }


def compare(resume_text, jd_text):
    wanted = find_skills(jd_text)
    have = set(find_skills(resume_text))
    matched = [s for s in wanted if s in have]
    missing = [s for s in wanted if s not in have]
    score = round(100 * len(matched) / len(wanted)) if wanted else 0
    return {"score": score, "matched": matched, "missing": missing, "wanted": wanted}
