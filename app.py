import json
import os
import time

import streamlit as st
from google import genai
from pypdf import PdfReader

import resume_check
from voice import voice_orb

# tried in this order. If one is busy or retired the next one is used.
MODELS = ["gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-flash-lite-latest",
          "gemini-3.1-flash-lite-preview", "gemini-flash-latest"]
NUM_QUESTIONS = 6

st.set_page_config(page_title="AI Interviewer", layout="wide")


def default_key():
    """The app owner's key, from an environment variable or Streamlit secrets."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        try:
            key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            key = None
    return key


def get_client(user_key=""):
    # a key typed in the app wins, otherwise use the owner's default key
    key = user_key.strip() or default_key()
    return genai.Client(api_key=key) if key else None


def explain_error(errors):
    """Turn the list of (model, error) pairs into one clear message."""
    texts = [str(e) for _, e in errors]
    if any("API key" in t or "API_KEY" in t or "PERMISSION_DENIED" in t for t in texts):
        return "The Gemini key was rejected. Check the key you entered, or clear it to use the default one."
    if any("429" in t or "RESOURCE_EXHAUSTED" in t for t in texts):
        return ("The free Gemini quota is used up for now. Wait a bit and try again, "
                "or paste your own key in the box at the top.")
    if all("404" in t or "NOT_FOUND" in t for t in texts):
        return "None of the configured Gemini models are available right now."
    return "Gemini is busy right now. Please try again in a minute."


def ask_llm(client, prompt):
    errors = []
    for model in MODELS:
        for attempt in range(2):
            try:
                reply = client.models.generate_content(model=model, contents=prompt)
                if reply.text:
                    return reply.text.strip()
                break
            except Exception as e:
                msg = str(e)
                # bad key fails on every model, so stop early
                if "API key" in msg or "API_KEY" in msg:
                    raise RuntimeError(explain_error([(model, e)]))
                # a busy model gets one more try, anything else moves to the next model
                if "503" in msg or "UNAVAILABLE" in msg:
                    errors.append((model, e))
                    time.sleep(1.5)
                    continue
                errors.append((model, e))
                break
    raise RuntimeError(explain_error(errors))


def read_resume(uploaded):
    if uploaded is None:
        return ""
    try:
        pages = PdfReader(uploaded).pages
        return "\n".join(p.extract_text() or "" for p in pages)[:4000]
    except Exception:
        return ""


def transcript_text(messages):
    lines = []
    for m in messages:
        who = "Interviewer" if m["role"] == "assistant" else "Candidate"
        lines.append(f"{who}: {m['content']}")
    return "\n".join(lines)


def interviewer_prompt(setup, messages, questions_left):
    """Builds the prompt for the interviewer's next message."""
    resume = setup["resume"] or "not provided"
    company = setup["company"] or "no specific company"
    if not messages:
        task = "Open the interview with a short greeting and your first question."
        if setup["kind"] != "Technical":
            task += " Start with 'Tell me about yourself'."
    elif questions_left == 1:
        task = "This is the last question. Ask one final question, then nothing else."
    else:
        task = (
            "Read the candidate's last answer. If it was vague or interesting, ask ONE "
            "short follow-up about it. If it was complete, move on to a new question "
            "on a different topic."
        )
    return (
        f"You are a human-sounding interviewer running a {setup['kind']} interview "
        f"for a {setup['level']} {setup['role']} role. Company style: {company} "
        "(use a general style for this kind of company, do not claim to know their "
        "real questions).\n"
        f"Candidate resume (may be empty): {resume}\n\n"
        f"Conversation so far:\n{transcript_text(messages) or '(not started)'}\n\n"
        f"{task}\n"
        "Rules: ask only one question per turn, keep it under 50 words, do not give "
        "the answer, do not score the candidate, no bullet points."
    )


def report_prompt(setup, messages):
    return (
        f"Here is a mock {setup['kind']} interview for a {setup['level']} "
        f"{setup['role']} role.\n\n{transcript_text(messages)}\n\n"
        "Evaluate the candidate honestly. Reply only with JSON in this shape:\n"
        '{"overall": 0-100, "communication": 0-10, "technical": 0-10, '
        '"clarity": 0-10, "structure": 0-10, "strengths": ["..."], '
        '"improve": ["..."], "tips": [{"question": "...", "tip": "..."}]}\n'
        "Give 2-3 strengths, 2-3 things to improve and one tip per question asked."
    )


def parse_json(text):
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except ValueError:
        return None


def reset():
    for k in ["setup", "messages", "report"]:
        st.session_state.pop(k, None)


st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&family=Inter:wght@400;500;600&display=swap');
    #MainMenu, footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
    @keyframes gradientShift { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
    @keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }
    .stApp { background: linear-gradient(-45deg, #0a0a0f, #0f0a14, #0a0f19, #140f1e); background-size: 400% 400%;
             animation: gradientShift 20s ease infinite; }
    .block-container { max-width: 1120px; padding-top: 1.2rem; }
    html, body, [class*="css"], .stMarkdown, label, p { font-family: 'Inter', sans-serif; color: #e8e8ee; }
    h1, h2, h3, h4 { font-family: 'Poppins', sans-serif !important; color: #f4f4f8; }
    .nav { display:flex; align-items:center; justify-content:space-between; padding:10px 20px; margin-bottom:12px;
           background: linear-gradient(135deg, rgba(8,8,12,.92), rgba(18,8,16,.92)); border-radius:16px;
           border-bottom:2px solid rgba(139,0,0,.35); box-shadow:0 8px 32px rgba(0,0,0,.4), 0 0 20px rgba(139,0,0,.15); }
    .logo { font-family:'Poppins'; font-weight:800; font-size:24px;
            background: linear-gradient(135deg,#FF6B6B,#DC143C); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
    .status { font-size:13px; color:#b8b8c4; display:flex; align-items:center; gap:8px; }
    .dot { width:9px; height:9px; border-radius:50%; background:#10b981; box-shadow:0 0 8px #10b981; }
    .hero { position:relative; overflow:hidden; text-align:center; padding:20px 20px; margin-bottom:14px; border-radius:24px;
            background: linear-gradient(135deg, rgba(8,8,12,.88), rgba(18,8,16,.88) 50%, rgba(10,18,28,.88));
            border:1px solid rgba(139,0,0,.3); box-shadow:0 20px 60px rgba(0,0,0,.5), 0 0 40px rgba(139,0,0,.2); }
    .hero::before { content:''; position:absolute; inset:0; width:100%;
            background: linear-gradient(90deg, transparent, rgba(139,0,0,.18), transparent); animation: shimmer 3.5s infinite; }
    .hero h1 { position:relative; font-size:2.3rem; font-weight:800; margin:0 0 6px; letter-spacing:-1px;
               background: linear-gradient(135deg,#FF6B6B,#DC143C 50%,#8B0000); -webkit-background-clip:text;
               -webkit-text-fill-color:transparent; filter: drop-shadow(0 0 18px rgba(139,0,0,.5)); }
    .hero p { position:relative; color:#c0c0c8; margin:0; }
    .stButton > button, .stDownloadButton > button { background: linear-gradient(135deg,#8B0000,#DC143C); color:#fff; border:0;
          border-radius:12px; padding:.6rem 1.6rem; font-family:'Poppins'; font-weight:600;
          box-shadow:0 6px 20px rgba(220,20,60,.25); }
    .stButton > button:hover { filter:brightness(1.15); color:#fff; border:0; }
    .stTabs [data-baseweb="tab-list"] { gap:8px; border-bottom:0; }
    .stTabs [role="tab"] { background: rgba(139,0,0,.25) !important; border-radius:999px !important; padding:8px 22px !important;
          height:auto; border:1px solid rgba(139,0,0,.45); font-family:'Poppins'; font-weight:600; }
    .stTabs [role="tab"][aria-selected="true"] { background: linear-gradient(135deg,#8B0000,#DC143C) !important; border-color:#DC143C; }
    .stTabs [role="tab"], .stTabs [role="tab"] p { color:#fff !important; }
    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display:none; }
    [data-testid="stMetric"] { background: linear-gradient(135deg, rgba(12,12,18,.9), rgba(22,12,26,.9)); border:1px solid rgba(139,0,0,.35);
          border-radius:18px; padding:14px 18px; box-shadow:0 8px 30px rgba(0,0,0,.4); }
    [data-testid="stMetricLabel"] p { color:#b0b0b8; font-weight:600; font-size:13px; }
    [data-testid="stMetricValue"] { font-family:'Poppins'; font-weight:800;
          background: linear-gradient(135deg,#FF6B6B,#DC143C); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
    [data-testid="stChatMessage"], [data-testid="stExpander"] { background: rgba(15,15,20,.85); border:1px solid rgba(139,0,0,.3); border-radius:16px; }
    [data-testid="stFileUploader"] section, .stTextInput input, .stTextArea textarea, .stSelectbox > div > div
        { background: rgba(20,16,30,.9); border-radius:12px; border-color: rgba(139,0,0,.35); }
    .stProgress > div > div > div { background: linear-gradient(90deg,#8B0000,#DC143C); }
    </style>
    <div class="nav">
      <div class="logo">AI Interviewer</div>
      <div class="status"><span class="dot"></span>Voice ready</div>
    </div>
    """,
    unsafe_allow_html=True,
)
if "setup" not in st.session_state:
    # the big banner only shows before the interview starts, so the interview fits one screen
    st.markdown(
        """
        <div class="hero">
          <h1>Interview Practice Studio</h1>
          <p>Answer out loud or in text. Get a score report when you finish.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with st.expander("Use your own Gemini key (optional)"):
    st.caption(
        "The app already has a key. If you see a quota error, paste your own free key "
        "from Google AI Studio here. It is kept only for this browser session and is "
        "never saved or logged."
    )
    user_key = st.text_input("Your Gemini API key", type="password", key="user_key")

client = get_client(user_key)
if client is None:
    st.warning("No Gemini API key available. Paste your own key above to continue.")
    st.stop()

def resume_screen():
    st.write("Check how well your resume matches a job post. This part is plain "
             "keyword matching, no AI, so you can explain exactly how the score is made.")
    up, jdcol = st.columns(2)
    with up:
        pdf = st.file_uploader("Your resume (PDF)", type="pdf", key="resume_pdf")
    with jdcol:
        jd = st.text_area("Paste the job description", height=160)
    if st.button("Check fit"):
        text = read_resume(pdf)
        if not text or not jd.strip():
            st.error("Upload a text based resume PDF and paste the job description.")
            return
        info = resume_check.parse_resume(text)
        fit = resume_check.compare(text, jd)
        st.metric("Skill match", f"{fit['score']}%")
        st.write("**Skills the job asks for that you have:** " + (", ".join(fit["matched"]) or "none"))
        st.write("**Missing from your resume:** " + (", ".join(fit["missing"]) or "nothing, good"))
        st.caption("Only add a missing skill if you really have it.")
        with st.expander("What I read from your resume"):
            st.write(f"Email: {info['email']}")
            st.write(f"Phone: {info['phone']}")
            st.write("Sections found: " + ", ".join(info["sections"]))
            st.write("Skills found: " + ", ".join(info["skills"]))
            st.write(f"Length: {info['words']} words")
        st.session_state.fit_text = (text, jd, fit)
    if "fit_text" in st.session_state and st.button("Get AI tips for this job"):
        text, jd, fit = st.session_state.fit_text
        prompt = ("Resume:\n" + text + "\n\nJob description:\n" + jd +
                  "\n\nMissing skills: " + ", ".join(fit["missing"]) +
                  "\n\nGive 4 short, honest tips to tailor this resume to the job. "
                  "Do not suggest inventing experience.")
        try:
            with st.spinner("Thinking..."):
                st.write(ask_llm(client, prompt))
        except Exception as e:
            st.error(str(e))


def interview_screen():
    # ---- setup screen ----
    if "setup" not in st.session_state:
        left, right = st.columns(2)
        with left:
            role = st.text_input("Role", "Python Developer")
            level = st.selectbox("Level", ["fresher", "junior", "mid-level"])
            kind = st.radio("Interview type", ["Mixed", "HR", "Technical"], horizontal=True)
        with right:
            company = st.text_input("Target company (optional)", placeholder="e.g. TCS, a startup")
            uploaded = st.file_uploader("Resume PDF (optional, questions will use it)", type="pdf")
        if st.button("Start interview"):
            st.session_state.setup = {
                "role": role, "level": level, "kind": kind,
                "company": company.strip(), "resume": read_resume(uploaded),
            }
            st.session_state.messages = []
            st.rerun()
        return

    setup = st.session_state.setup
    messages = st.session_state.messages
    asked = sum(1 for m in messages if m["role"] == "assistant")
    answered = sum(1 for m in messages if m["role"] == "user")

    # ---- report screen ----
    if answered >= NUM_QUESTIONS:
        if "report" not in st.session_state:
            try:
                with st.spinner("Writing your feedback report..."):
                    raw = ask_llm(client, report_prompt(setup, messages))
            except Exception as e:
                st.error(str(e))
                return
            st.session_state.report = parse_json(raw) or {"raw": raw}
        rep = st.session_state.report
        st.subheader("Interview report")
        if "overall" not in rep:
            st.write(rep.get("raw", "No report."))
        else:
            cols = st.columns(5)
            cols[0].metric("Overall score", f"{rep['overall']} / 100")
            for col, name in zip(cols[1:], ["communication", "technical", "clarity", "structure"]):
                col.metric(name.capitalize(), f"{rep.get(name, '-')}/10")
            st.write("**What went well**")
            for s in rep.get("strengths", []):
                st.write("- " + s)
            st.write("**What to work on**")
            for s in rep.get("improve", []):
                st.write("- " + s)
            with st.expander("Tips per question"):
                for t in rep.get("tips", []):
                    st.write(f"**{t.get('question', '')}**")
                    st.write(t.get("tip", ""))
        with st.expander("Full transcript"):
            st.text(transcript_text(messages))
        if st.button("New interview"):
            reset()
            st.rerun()
        return

    # ---- interview screen ----
    st.caption(f"{setup['kind']} interview, {setup['role']} ({setup['level']}), "
               f"question {min(asked, NUM_QUESTIONS)} of {NUM_QUESTIONS}")
    st.progress(answered / NUM_QUESTIONS)

    if asked == answered:
        # interviewer's turn
        try:
            with st.spinner("Interviewer is thinking..."):
                nxt = ask_llm(client, interviewer_prompt(setup, messages, NUM_QUESTIONS - answered))
        except Exception as e:
            st.error(str(e))
            return
        messages.append({"role": "assistant", "content": nxt})
        st.rerun()

    talk, history = st.columns([3, 2])
    with talk:
        voice_orb(messages[-1]["content"])
        answer = st.chat_input("Or type your answer here")
    with history:
        st.markdown("**Conversation so far**")
        with st.container(height=440):
            if len(messages) > 1:
                for m in messages[:-1]:
                    who = "Interviewer" if m["role"] == "assistant" else "You"
                    st.markdown(f"**{who}**")
                    st.write(m["content"])
                    st.divider()
            else:
                st.caption("Your earlier answers will show up here.")
    if answer:
        messages.append({"role": "user", "content": answer})
        st.rerun()


tab_interview, tab_resume = st.tabs(["Mock interview", "Resume check"])
with tab_interview:
    interview_screen()
with tab_resume:
    resume_screen()
