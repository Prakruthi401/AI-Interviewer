"""The talking orb. It runs in the browser, Streamlit only passes it the question text.

Real parts: speech comes from the browser's speechSynthesis, the mic uses the browser's
speech recognition (Chrome/Edge/Android Chrome). The orb pulses on each spoken word.
When the browser has no speech support the orb stays still and you type instead.
"""
import json

import streamlit as st
import streamlit.components.v1 as components

PAGE = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700&family=Inter:wght@400;600&display=swap');
  body { margin:0; font-family:'Inter',sans-serif; color:#f1f1f5; background:transparent; }
  .wrap { display:flex; flex-direction:column; align-items:center; padding:6px 0 0; }
  .stage { position:relative; width:150px; height:150px; display:flex; align-items:center; justify-content:center; }
  .orb { width:104px; height:104px; border-radius:50%;
         background:radial-gradient(circle at 32% 28%, #ff9a9a, #DC143C 58%, #7a0019);
         box-shadow:0 10px 40px rgba(220,20,60,.45); transition:transform .12s ease-out; z-index:2; }
  .ring { position:absolute; width:104px; height:104px; border-radius:50%;
          border:2px solid #DC143C; opacity:0; z-index:1; }
  .idle .orb { animation:breathe 3.6s ease-in-out infinite; }
  .speaking .ring, .listening .ring { animation:ripple 1.8s ease-out infinite; }
  .speaking .ring:nth-child(2), .listening .ring:nth-child(2) { animation-delay:.6s; }
  .speaking .ring:nth-child(3), .listening .ring:nth-child(3) { animation-delay:1.2s; }
  .listening .orb { background:radial-gradient(circle at 32% 28%, #a7f3d0, #10b981 58%, #065f46);
                    box-shadow:0 10px 30px rgba(16,185,129,.4); animation:breathe 1.2s ease-in-out infinite; }
  .listening .ring { border-color:#10b981; }
  @keyframes breathe { 0%,100% { transform:scale(1);} 50% { transform:scale(1.06);} }
  @keyframes ripple { 0% { transform:scale(1); opacity:.55;} 100% { transform:scale(1.9); opacity:0;} }
  .status { margin-top:6px; font-weight:600; font-size:14px; color:#b8b8c4; min-height:20px; }
  .q { margin:10px 8px 4px; text-align:center; font-family:'Poppins',sans-serif; font-size:18px;
       font-weight:600; line-height:1.35; max-width:620px; }
  .btns { display:flex; gap:10px; margin-top:12px; }
  button { font-family:'Poppins',sans-serif; font-size:14px; font-weight:600; border-radius:12px;
           padding:10px 20px; cursor:pointer; border:1px solid rgba(139,0,0,.5); background:rgba(139,0,0,.25); color:#fff; }
  button.main { background:linear-gradient(135deg,#8B0000,#DC143C); border-color:#DC143C; }
  button:disabled { opacity:.5; cursor:default; }
</style>
<div class="wrap">
  <div class="stage idle" id="stage">
    <div class="ring"></div><div class="ring"></div><div class="ring"></div>
    <div class="orb" id="orb"></div>
  </div>
  <div class="status" id="status"></div>
  <div class="q" id="q"></div>
  <div class="btns">
    <button id="replay">Replay question</button>
    <button id="mic" class="main">Tap to answer by voice</button>
  </div>
</div>
<script>
const QUESTION = __QUESTION__;
const store = window.parent.sessionStorage;
const stage = document.getElementById('stage'), orb = document.getElementById('orb');
const statusEl = document.getElementById('status'), micBtn = document.getElementById('mic');
document.getElementById('q').textContent = QUESTION;

function setState(s, text) { stage.className = 'stage ' + s; statusEl.textContent = text || ''; }
setState('idle', 'Your turn when you are ready');

// ---- interviewer speaks ----
const synth = window.speechSynthesis;
function speak() {
  if (!synth) { setState('idle', 'Voice not supported in this browser, type your answer'); return; }
  synth.cancel();
  const u = new SpeechSynthesisUtterance(QUESTION);
  u.rate = 0.98;
  const voices = synth.getVoices();
  const en = voices.find(v => /en-(IN|GB|US)/.test(v.lang)) ;
  if (en) u.voice = en;
  u.onstart = () => setState('speaking', 'Interviewer is speaking...');
  // every spoken word gives the orb a small bump, so it reacts to the real speech
  u.onboundary = () => {
    orb.style.transform = 'scale(1.18)';
    setTimeout(() => orb.style.transform = 'scale(1)', 110);
  };
  u.onend = u.onerror = () => setState('idle', 'Your turn when you are ready');
  synth.speak(u);
}
document.getElementById('replay').onclick = speak;

// speak automatically once per new question
if (store.getItem('lastSpoken') !== QUESTION) {
  store.setItem('lastSpoken', QUESTION);
  setTimeout(speak, 400);
}

// ---- candidate speaks ----
const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
function sendToChat(text) {
  const doc = window.parent.document;
  const box = doc.querySelector('textarea[data-testid="stChatInputTextArea"]');
  if (!box) return;
  const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLTextAreaElement.prototype, 'value').set;
  setter.call(box, text);
  box.dispatchEvent(new Event('input', { bubbles: true }));
  setTimeout(() => {
    const send = doc.querySelector('[data-testid="stChatInputSubmitButton"]');
    if (send) send.click();
  }, 250);
}
if (!Rec) {
  micBtn.disabled = true; micBtn.textContent = 'Voice answer not supported here';
} else {
  const rec = new Rec();
  rec.lang = 'en-IN'; rec.interimResults = true; rec.continuous = false;
  let finalText = '';
  micBtn.onclick = () => {
    if (synth) synth.cancel();
    finalText = '';
    try { rec.start(); } catch (e) {}
  };
  rec.onstart = () => setState('listening', 'Listening... speak your answer');
  rec.onresult = (e) => {
    let t = '';
    for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
    finalText = t;
    statusEl.textContent = t;
  };
  rec.onend = () => {
    setState('idle', finalText ? 'Sending your answer...' : 'Did not catch that, try again');
    if (finalText.trim()) sendToChat(finalText.trim());
  };
  rec.onerror = () => setState('idle', 'Mic problem, check permission or type your answer');
}
</script>
"""


def voice_orb(question):
    # the question comes from the model, so make sure it can never close the script tag
    safe = json.dumps(question).replace("</", "<\\/")
    html = PAGE.replace("__QUESTION__", safe)
    if hasattr(st, "iframe"):
        st.iframe(html, height=430)
    else:
        components.html(html, height=430)
