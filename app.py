"""
Streamlit dashboard for AJ — the Purvi Technologies multi-agent assistant.

Run with:
    python -m streamlit run app.py
"""

from __future__ import annotations

import hmac
import json

import openai

import config
import documents
import exports
import memory_store
from agents import SPECIALISTS
from agents.planning_agent import clear_done, get_todos, set_done
from orchestrator import coordinate

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="AJ · Purvi Technologies", page_icon="✨", layout="wide")


def _html(markup: str) -> str:
    """Collapse multi-line HTML to one line so st.markdown renders it as HTML."""
    return " ".join(line.strip() for line in markup.splitlines() if line.strip())


def browser_speak(text: str, hint: str = "", rate: float = 0.95, pitch: float = 1.2, lang: str = "en-US") -> None:
    """Speak text via the browser's Web Speech API.

    `hint` — substring of a preferred voice name (e.g. "aria", "zira"). If empty or
    not found, falls back to the best available female English voice.
    """
    payload = json.dumps(text)
    hint_j = json.dumps(hint)
    components.html(
        f"""
        <script>
        (function() {{
            const synth = window.speechSynthesis;
            const text = {payload};
            const hint = {hint_j};
            const prefer = [/aria/i, /jenny/i, /zira/i, /hazel/i, /michelle/i, /female/i,
                            /samantha/i, /susan/i, /eva/i, /libby/i, /sonia/i,
                            /google uk english female/i, /google us english/i];
            function pick(voices) {{
                // Only consider voices in the target language (e.g. English) so we never
                // fall back to a Russian/other system voice that mangles the accent.
                const fam = '{lang}'.slice(0, 2).toLowerCase();
                const inLang = voices.filter(v => (v.lang || '').toLowerCase().slice(0, 2) === fam);
                const pool = inLang.length ? inLang : voices;
                if (hint) {{
                    const h = hint.toLowerCase();
                    const m = pool.find(v => v.name.toLowerCase().includes(h));
                    if (m) return m;
                }}
                for (const re of prefer) {{ const m = pool.find(v => re.test(v.name)); if (m) return m; }}
                return pool.find(v => /en[-_]us/i.test(v.lang)) || pool.find(v => /en[-_]gb/i.test(v.lang)) || pool[0];
            }}
            function speak() {{
                const voices = synth.getVoices();
                if (!voices.length) return false;
                const v = pick(voices);
                const u = new SpeechSynthesisUtterance(text);
                if (v) u.voice = v;
                u.lang = (v && v.lang) || '{lang}' || 'en-US';
                u.rate = {float(rate)}; u.pitch = {float(pitch)};
                synth.cancel(); synth.speak(u);
                return true;
            }}
            try {{ if (!speak()) {{ synth.onvoiceschanged = function() {{ speak(); synth.onvoiceschanged = null; }}; }} }}
            catch (e) {{ console.error('TTS error', e); }}
        }})();
        </script>
        """,
        height=0,
    )


def voice_widget(silence_ms: int = 900, lang: str = "en-US") -> None:
    """Hands-free voice input.

    One tap starts the browser's speech recognizer. It auto-stops after `silence_ms`
    of no speech, then drops the transcript into the chat box and submits it — so the
    full agent flow runs without a second click. Falls back to leaving the text in the
    box (press Enter) if auto-submit can't find the button.
    """
    components.html(
        f"""
        <style>
        #mic {{ width: 100%; padding: 10px; border: none; border-radius: 12px; cursor: pointer;
            font-family: Inter, sans-serif; font-weight: 700; font-size: 15px; color: #fff;
            background: linear-gradient(90deg,#7c5cff,#3ec6ff); transition: filter .15s; }}
        #mic:hover {{ filter: brightness(1.1); }}
        #mic.live {{ background: linear-gradient(90deg,#ff5c8a,#ff9a5c); }}
        #vstat {{ font-family: Inter, sans-serif; color: #9aa0ac; font-size: 13px; margin-top: 6px; min-height: 18px; }}
        </style>
        <button id="mic">🎤 Tap &amp; speak</button>
        <div id="vstat"></div>
        <script>
        (function() {{
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            const btn = document.getElementById('mic');
            const stat = document.getElementById('vstat');
            if (!SR) {{ stat.textContent = 'Voice needs Chrome or Edge.'; btn.disabled = true; return; }}
            const pdoc = window.parent.document;

            function submitText(text) {{
                const ta = pdoc.querySelector('textarea[data-testid="stChatInputTextArea"]')
                         || pdoc.querySelector('[data-testid="stChatInput"] textarea')
                         || pdoc.querySelector('textarea');
                if (!ta) {{ stat.textContent = 'Could not find the chat box.'; return; }}
                const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLTextAreaElement.prototype, 'value').set;
                setter.call(ta, text);
                ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                setTimeout(function() {{
                    const sb = pdoc.querySelector('button[data-testid="stChatInputSubmitButton"]');
                    if (sb) {{ sb.click(); }}
                    else {{ ta.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', keyCode: 13, which: 13, bubbles: true }})); }}
                }}, 60);
            }}

            let rec = null, finalText = '', timer = null;
            btn.addEventListener('click', function() {{
                if (rec) {{ rec.stop(); return; }}
                rec = new SR(); rec.lang = '{lang}'; rec.interimResults = true; rec.continuous = true;
                finalText = '';
                rec.onstart = function() {{ btn.classList.add('live'); btn.textContent = '⏹ Listening… (tap to stop)'; stat.textContent = ''; }};
                rec.onresult = function(e) {{
                    let interim = '';
                    for (let i = e.resultIndex; i < e.results.length; i++) {{
                        if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
                        else interim += e.results[i][0].transcript;
                    }}
                    stat.textContent = (finalText + ' ' + interim).trim();
                    if (timer) clearTimeout(timer);
                    timer = setTimeout(function() {{ if (rec) rec.stop(); }}, {silence_ms});
                }};
                rec.onerror = function(e) {{ stat.textContent = 'Mic: ' + e.error; }};
                rec.onend = function() {{
                    if (timer) clearTimeout(timer);
                    const t = (finalText || stat.textContent || '').trim();
                    rec = null; btn.classList.remove('live'); btn.textContent = '🎤 Tap &amp; speak';
                    if (t) submitText(t);
                }};
                rec.start();
            }});
        }})();
        </script>
        """,
        height=85,
    )


def conversation_widget(
    speak_text: str = "", silence_ms: int = 900, lang: str = "en-US",
    hint: str = "", rate: float = 0.95, pitch: float = 1.2,
) -> None:
    """Hands-free CONVERSATION loop — talk to AJ like a person.

    First activation needs ONE tap on the big mic button — that tap is what makes the
    browser show its "Allow microphone?" prompt (browsers refuse to start the mic
    without a user gesture). After you allow it once, it stays hands-free: AJ speaks
    each reply, then re-opens the mic by itself until you turn the mode off.

    The speech recognizer is created from the TOP-LEVEL window so it inherits the page's
    microphone permission (Streamlit's embedded component frames don't get mic rights).
    """
    payload = json.dumps(speak_text)
    hint_j = json.dumps(hint)
    components.html(
        f"""
        <style>
        #cw {{ font-family: Inter, sans-serif; }}
        #cwstat {{ display:flex; align-items:center; gap:10px; padding:11px 14px; border-radius:12px;
            background:#15171f; border:1px solid #262a36; color:#e6e8ee; font-weight:600; font-size:14px; }}
        #cwdot {{ width:12px; height:12px; border-radius:50%; background:#3ec6ff; flex:none; }}
        #cwdot.listen {{ background:#36e07f; animation:cwp 1.2s infinite; }}
        #cwdot.speak {{ background:#ff9a5c; animation:cwp 1.2s infinite; }}
        #cwtext {{ color:#cfd3dc; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
        @keyframes cwp {{ 0%{{box-shadow:0 0 0 0 rgba(54,224,127,.5);}} 70%{{box-shadow:0 0 0 9px rgba(54,224,127,0);}} 100%{{box-shadow:0 0 0 0 rgba(54,224,127,0);}} }}
        #cwgo {{ display:none; margin-top:10px; width:100%; padding:13px; border:none; border-radius:12px; cursor:pointer;
            font-family:Inter,sans-serif; font-weight:700; font-size:15px; color:#fff; background:linear-gradient(90deg,#36e07f,#3ec6ff); }}
        #cwgo:hover {{ filter:brightness(1.08); }}
        </style>
        <div id="cw">
          <div id="cwstat"><span id="cwdot"></span><span id="cwtext">Starting conversation…</span></div>
          <button id="cwgo">🎤 Tap to start talking</button>
        </div>
        <script>
        (function() {{
            // Build the recognizer from the TOP-LEVEL window so it has mic permission.
            const W = window.parent || window;
            const SR = W.SpeechRecognition || W.webkitSpeechRecognition
                     || window.SpeechRecognition || window.webkitSpeechRecognition;
            const synth = window.speechSynthesis;
            const dot = document.getElementById('cwdot');
            const txt = document.getElementById('cwtext');
            const go  = document.getElementById('cwgo');
            const pdoc = window.parent.document;
            const speakText = {payload};
            const hint = {hint_j};
            if (!SR) {{ setState('', 'Voice needs Chrome or Edge.'); return; }}

            function setState(cls, label) {{ dot.className = cls; txt.textContent = label; }}
            function showBtn(label) {{ go.textContent = '🎤 ' + label; go.style.display = 'block'; }}
            function hideBtn() {{ go.style.display = 'none'; }}

            function submitText(text) {{
                const ta = pdoc.querySelector('textarea[data-testid="stChatInputTextArea"]')
                         || pdoc.querySelector('[data-testid="stChatInput"] textarea')
                         || pdoc.querySelector('textarea');
                if (!ta) return;
                const setter = Object.getOwnPropertyDescriptor(window.parent.HTMLTextAreaElement.prototype, 'value').set;
                setter.call(ta, text);
                ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                setTimeout(function() {{
                    const sb = pdoc.querySelector('button[data-testid="stChatInputSubmitButton"]');
                    if (sb) {{ sb.click(); }}
                    else {{ ta.dispatchEvent(new KeyboardEvent('keydown', {{ key:'Enter', keyCode:13, which:13, bubbles:true }})); }}
                }}, 60);
            }}

            let rec = null, finalText = '', timer = null;
            function startListening() {{
                if (rec) return;                       // already listening
                try {{
                    rec = new SR(); rec.lang = '{lang}'; rec.interimResults = true; rec.continuous = true;
                    finalText = '';
                    rec.onstart = function() {{ W.__ajMicOk = true; hideBtn(); setState('listen', '🎧 Listening… just talk'); }};
                    rec.onresult = function(e) {{
                        let interim = '';
                        for (let i=e.resultIndex; i<e.results.length; i++) {{
                            if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
                            else interim += e.results[i][0].transcript;
                        }}
                        setState('listen', (finalText + ' ' + interim).trim() || '🎧 Listening… just talk');
                        if (timer) clearTimeout(timer);
                        timer = setTimeout(function() {{ if (rec) rec.stop(); }}, {silence_ms});
                    }};
                    rec.onerror = function(e) {{
                        if (e.error === 'no-speech' || e.error === 'aborted') return;
                        rec = null;
                        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {{
                            setState('', 'Mic blocked. Click the 🔒/camera icon in the address bar → Allow, then tap below.');
                        }} else {{ setState('', 'Mic error: ' + e.error + '. Tap to retry.'); }}
                        showBtn('Tap to talk');
                    }};
                    rec.onend = function() {{
                        if (timer) clearTimeout(timer);
                        const t = (finalText || '').trim();
                        rec = null;
                        if (t) {{ setState('', '💬 You: ' + t); submitText(t); }}
                        else {{ setState('', "Didn't catch that — tap to talk."); showBtn('Tap to talk'); }}
                    }};
                    rec.start();
                }} catch (err) {{ rec = null; setState('', 'Tap the button to start talking.'); showBtn('Start talking'); }}
            }}

            go.addEventListener('click', function() {{ try {{ synth.cancel(); }} catch(e) {{}} startListening(); }});

            const prefer = [/aria/i,/jenny/i,/zira/i,/hazel/i,/michelle/i,/female/i,/samantha/i,/google us english/i,/google uk english female/i];
            function pickVoice(vs) {{
                // Restrict to the target language family so the accent never drifts to a
                // non-English system voice (e.g. Russian) on the user's machine.
                const fam = '{lang}'.slice(0, 2).toLowerCase();
                const inLang = vs.filter(v => (v.lang || '').toLowerCase().slice(0, 2) === fam);
                const pool = inLang.length ? inLang : vs;
                if (hint) {{ const m = pool.find(v=>v.name.toLowerCase().includes(hint.toLowerCase())); if (m) return m; }}
                for (const re of prefer) {{ const m = pool.find(v=>re.test(v.name)); if (m) return m; }}
                return pool.find(v=>/en[-_]us/i.test(v.lang)) || pool.find(v=>/en[-_]gb/i.test(v.lang)) || pool[0];
            }}
            function speakThenListen() {{
                if (speakText) {{
                    setState('speak', '🗣️ AJ is speaking…');
                    function doSpeak() {{
                        const vs = synth.getVoices(); if (!vs.length) return false;
                        const u = new SpeechSynthesisUtterance(speakText);
                        const v = pickVoice(vs); if (v) u.voice = v;
                        u.lang = (v && v.lang) || '{lang}' || 'en-US'; u.rate = {float(rate)}; u.pitch = {float(pitch)};
                        u.onend = function() {{ startListening(); }};   // permission already granted mid-chat
                        u.onerror = function() {{ startListening(); }};
                        synth.cancel(); synth.speak(u);
                        return true;
                    }}
                    if (!doSpeak()) {{
                        synth.onvoiceschanged = function() {{ doSpeak(); synth.onvoiceschanged = null; }};
                        setTimeout(function() {{ if (!rec) startListening(); }}, 4000);
                    }}
                    return;
                }}
                // No reply to speak — this is the start (or an idle rerun).
                if (W.__ajMicOk) {{ startListening(); }}      // already allowed → just listen
                else {{ setState('', 'Tap below, then start talking — your browser will ask to use the mic.'); showBtn('Start talking'); }}
            }}

            setTimeout(speakThenListen, 350);  // let the parent DOM settle after rerun
        }})();
        </script>
        """,
        height=140,
    )


VOICE_OPTIONS = {
    "Auto — best female": "",
    "Aria — natural, soft (Edge)": "aria",
    "Jenny — natural, warm (Edge)": "jenny",
    "Zira — clear (Windows)": "zira",
    "Hazel — UK female (Windows)": "hazel",
    "Google US English Female": "google us english female",
    "Google UK English Female": "google uk english female",
    "Samantha": "samantha",
}


def require_login() -> None:
    """Gate the app behind a password if AJ_PASSWORD is configured."""
    if not config.APP_PASSWORD:
        return  # no password set — app is open
    if st.session_state.get("authed"):
        return

    st.markdown(
        _html(
            f'<div style="display:flex;align-items:center;gap:1rem;justify-content:center;margin:3.5rem 0 .5rem">'
            f'{LOGO_SVG}<span class="hero-title" style="font-size:2.8rem">AJ</span></div>'
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center;color:#9aa0ac;margin-bottom:1.2rem'>🔒 Enter your password to unlock AJ</p>",
        unsafe_allow_html=True,
    )
    mid = st.columns([1, 2, 1])[1]
    with mid:
        with st.form("login_form"):
            pw = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Password")
            submitted = st.form_submit_button("Unlock AJ", use_container_width=True)
        if submitted:
            if hmac.compare_digest(pw, config.APP_PASSWORD):
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()


# --- Agent presentation metadata ------------------------------------------ #
AGENT_META = {
    "email_agent": {"icon": "📧", "label": "Email Agent", "color": "#ff7a5c"},
    "research_agent": {"icon": "🔎", "label": "Research Agent", "color": "#3ec6ff"},
    "planning_agent": {"icon": "🗓️", "label": "Planning Agent", "color": "#5ddf9c"},
    "content_agent": {"icon": "✍️", "label": "Content Agent", "color": "#c08bff"},
    "finance_agent": {"icon": "💰", "label": "Finance Agent", "color": "#ffd166"},
    "strategy_agent": {"icon": "🎯", "label": "Strategy Agent", "color": "#ff6f91"},
    "social_agent": {"icon": "🐦", "label": "Social Agent", "color": "#4dd0e1"},
    "coding_agent": {"icon": "💻", "label": "Coding Agent", "color": "#9b8bff"},
}

# Spoken/written briefing AJ gives on login and from the "Daily briefing" button.
BRIEFING_PROMPT = (
    "Greet me warmly by name if you know it. Then give me a short, friendly briefing for today: "
    "summarize my pending to-dos and what's on my plate, and suggest my top 3 priorities. "
    "Keep it to about 4–6 short lines. If I have no tasks saved yet, welcome me and suggest a "
    "couple of ways to get started."
)

QUICK_STARTS = [
    {"icon": "🗓️", "label": "Plan my day", "prompt": "What should I focus on today? Give me a prioritized plan."},
    {"icon": "🎯", "label": "Strategy check", "prompt": "What's the riskiest assumption in my business right now, and how do I test it?"},
    {"icon": "🐦", "label": "Week of posts", "prompt": "Give me a week of LinkedIn post ideas for Purvi Technologies."},
    {"icon": "💰", "label": "Pricing help", "prompt": "Help me think through pricing tiers for an AI assistant product."},
]

LOGO_SVG = """
<svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="ajGrad" x1="4" y1="4" x2="60" y2="60" gradientUnits="userSpaceOnUse">
      <stop stop-color="#7c5cff"/><stop offset="0.35" stop-color="#3ec6ff"/>
      <stop offset="0.65" stop-color="#5ddf9c"/><stop offset="0.85" stop-color="#ffca28"/>
      <stop offset="1" stop-color="#ff5c8a"/>
    </linearGradient>
  </defs>
  <rect x="3" y="3" width="58" height="58" rx="17" fill="#12141c" stroke="url(#ajGrad)" stroke-width="2.8"/>
  <text x="32" y="42" font-family="Inter, Segoe UI, sans-serif" font-size="27" font-weight="800"
        fill="url(#ajGrad)" text-anchor="middle">AJ</text>
</svg>
"""

# --- Styling --------------------------------------------------------------- #
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
    html, body, [class*="css"], .stMarkdown, .stChatInput textarea { font-family: 'Inter', sans-serif; }
    #MainMenu, footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 1.6rem; max-width: 920px; }
    .stApp { background:
        radial-gradient(1100px 480px at 12% -8%, rgba(124,92,255,.16), transparent 60%),
        radial-gradient(900px 420px at 92% -2%, rgba(62,198,255,.13), transparent 60%),
        radial-gradient(900px 500px at 60% 108%, rgba(255,92,138,.10), transparent 60%),
        #0e1117; }
    .hero { position: relative; margin-bottom: 1.2rem; }
    .brand { display: flex; align-items: center; gap: 1rem; }
    .brand svg { filter: drop-shadow(0 6px 22px rgba(124,92,255,.55)); animation: float 5s ease-in-out infinite; }
    @keyframes float { 0%,100%{ transform: translateY(0);} 50%{ transform: translateY(-5px);} }
    .hero-title { font-size: 3.5rem; font-weight: 900; line-height: 1; margin: 0; letter-spacing: -1.5px;
        background: linear-gradient(95deg,#7c5cff,#3ec6ff,#5ddf9c,#ffca28,#ff5c8a,#7c5cff); background-size: 250% auto;
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: shimmer 5s linear infinite; }
    @keyframes shimmer { to { background-position: 250% center; } }
    .hero-sub { color: #aab0bd; font-size: 1.02rem; margin: .3rem 0 0; }
    .hero-sub b { background: linear-gradient(90deg,#c9bcff,#9fe3ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 700; }
    .pill { display: inline-block; padding: .26rem .8rem; border-radius: 999px;
        background: linear-gradient(90deg, rgba(124,92,255,.22), rgba(62,198,255,.18));
        border: 1px solid rgba(124,92,255,.45); color: #d8ccff; font-size: .78rem; font-weight: 600;
        margin-top: .85rem; box-shadow: 0 0 22px -6px rgba(124,92,255,.7); }
    .agent-card { display: flex; align-items: center; gap: .7rem;
        background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 22%, #161a24), #161a24);
        border: 1px solid color-mix(in srgb, var(--accent) 35%, #262b38); border-left: 3px solid var(--accent);
        border-radius: 13px; padding: .55rem .75rem; margin-bottom: .5rem; box-shadow: 0 6px 18px -12px var(--accent);
        transition: transform .14s ease; }
    .agent-card:hover { transform: translateX(3px); }
    .agent-ico { font-size: 1.05rem; width: 32px; height: 32px; flex: none; border-radius: 10px;
        display: flex; align-items: center; justify-content: center;
        background: color-mix(in srgb, var(--accent) 28%, #0e1117); border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent); }
    .agent-nm { font-weight: 700; font-size: .88rem; color: #f1f3f8; }
    .agent-dc { font-size: .72rem; color: #99a0ad; line-height: 1.2; }
    .side-h { font-size: .8rem; font-weight: 800; letter-spacing: .07em; text-transform: uppercase; margin: .2rem 0 .6rem;
        background: linear-gradient(90deg,#9b8bff,#62c6ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .side-foot { margin-top: 1.2rem; padding-top: .8rem; border-top: 1px solid #232838; color: #757b8a; font-size: .76rem; }
    .side-foot b { color: #b9bdca; }
    .qs-title { color: #aab0bd; font-size: .9rem; margin: .4rem 0 .6rem; font-weight: 600; }
    div[data-testid="column"] .stButton button { width: 100%; text-align: left; border-radius: 13px; padding: .7rem .9rem;
        font-weight: 600; background: #161a24; border: 1px solid #2a3040; color: #e6e8ef; transition: transform .12s ease, border-color .12s ease; }
    div[data-testid="column"] .stButton button:hover { transform: translateY(-2px); border-color: #7c5cff; color: #fff; }
    [data-testid="stChatMessage"] { border-radius: 15px; padding: .3rem .5rem; margin-bottom: .55rem; background: #141822; border: 1px solid #232838; }
    section[data-testid="stSidebar"] .stButton button { border-radius: 11px; border: 1px solid #2c3242;
        background: linear-gradient(90deg, rgba(124,92,255,.18), rgba(62,198,255,.14)); color: #e3e6ef; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Password gate (if AJ_PASSWORD is set) -------------------------------- #
require_login()

# --- Hero header ----------------------------------------------------------- #
st.markdown(
    _html(
        f"""
        <div class="hero">
            <div class="brand">
                {LOGO_SVG}
                <div>
                    <p class="hero-title">AJ</p>
                    <p class="hero-sub">Your AI assistant · by <b>Purvi Technologies</b></p>
                </div>
            </div>
            <span class="pill">⚡ {config.PROVIDER.title()} · {config.MODEL}{(" ↪ failover: " + ", ".join(config.CHAIN_NAMES[1:])) if len(config.CHAIN_NAMES) > 1 else ""}</span>
        </div>
        """
    ),
    unsafe_allow_html=True,
)

# --- Sidebar --------------------------------------------------------------- #
LANGUAGES = {
    "🇺🇸 English (US)": ("en-US", "en"),
    "🇮🇳 Hindi":      ("hi-IN", "hi"),
    "🇪🇸 Spanish":    ("es-ES", "es"),
    "🇫🇷 French":     ("fr-FR", "fr"),
    "🇩🇪 German":     ("de-DE", "de"),
    "🇸🇦 Arabic":     ("ar-SA", "ar"),
    "🇯🇵 Japanese":   ("ja-JP", "ja"),
    "🇨🇳 Chinese":    ("zh-CN", "zh"),
    "🇵🇹 Portuguese": ("pt-BR", "pt"),
    "🇷🇺 Russian":    ("ru-RU", "ru"),
}

with st.sidebar:
    if config.APP_PASSWORD and st.session_state.get("authed"):
        if st.button("🔒 Lock AJ", use_container_width=True):
            st.session_state["authed"] = False
            st.rerun()

    # --- Language selector -------------------------------------------------- #
    st.markdown('<div class="side-h">🌐 Language</div>', unsafe_allow_html=True)
    lang_label = st.selectbox(
        "AJ replies in",
        list(LANGUAGES),
        index=0,
        label_visibility="collapsed",
    )
    lang_voice_code, lang_short = LANGUAGES[lang_label]

    st.markdown('<div class="side-h" style="margin-top:1rem">AJ\'s Team</div>', unsafe_allow_html=True)
    for name, spec in SPECIALISTS.items():
        meta = AGENT_META.get(name, {"icon": "•", "label": name, "color": "#7c5cff"})
        desc = spec.description.split(".")[0] + "."
        st.markdown(
            _html(
                f"""
                <div class="agent-card" style="--accent:{meta['color']}">
                    <div class="agent-ico">{meta['icon']}</div>
                    <div>
                        <div class="agent-nm">{meta['label']}</div>
                        <div class="agent-dc">{desc}</div>
                    </div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    st.markdown('<div class="side-h" style="margin-top:1rem">🎙️ Voice</div>', unsafe_allow_html=True)
    conv_mode = st.checkbox(
        "🗣️ Conversation mode (hands-free)", value=False,
        help="Talk to AJ like a person — it listens, replies aloud, then listens again. "
             "No clicking. Turn off to stop. Needs Chrome or Edge + mic permission.",
    )
    speak_replies = st.checkbox("🔊 Speak replies aloud", value=True, disabled=conv_mode)
    voice_label = st.selectbox("AJ's voice", list(VOICE_OPTIONS), index=1)
    voice_hint = VOICE_OPTIONS[voice_label]
    voice_pitch = st.slider("Softness (pitch)", 0.8, 1.8, 1.25, 0.05)
    voice_rate = st.slider("Speed", 0.6, 1.3, 0.92, 0.02)
    if st.button("🔊 Test voice", use_container_width=True):
        browser_speak(
            "Hi, I'm AJ from Purvi Technologies. How can I help you today?",
            voice_hint, voice_rate, voice_pitch, lang=lang_voice_code,
        )
    voice_silence = st.slider("Auto-stop after silence (sec)", 0.4, 2.5, 0.8, 0.1)

    auto_brief = st.checkbox(
        "🌅 Greet me on login", value=True,
        help="When you log in, AJ automatically greets you and summarizes today's pending tasks.",
    )
    if st.button("🌅 Daily briefing now", use_container_width=True):
        st.session_state["pending"] = BRIEFING_PROMPT
        st.rerun()

    # Interactive to-do board
    st.markdown('<div class="side-h" style="margin-top:1rem">📋 To-do Board</div>', unsafe_allow_html=True)
    todos = get_todos()
    if not todos:
        st.caption("No tasks yet. Ask AJ to plan something.")
    for i, t in enumerate(todos):
        checked = st.checkbox(t["text"], value=t.get("done", False), key=f"todo_{i}")
        if checked != t.get("done", False):
            set_done(i, checked)
            st.rerun()
    if todos and any(t.get("done") for t in todos):
        if st.button("🧹 Clear completed", use_container_width=True):
            clear_done()
            st.rerun()

    # Memory panel
    st.markdown('<div class="side-h" style="margin-top:1rem">🧠 What AJ Remembers</div>', unsafe_allow_html=True)
    facts = memory_store.recall()
    if facts:
        for f in facts:
            st.caption(f"• {f}")
        if st.button("Forget everything", use_container_width=True):
            memory_store.clear()
            st.rerun()
    else:
        st.caption("Nothing yet — tell AJ about you or your company.")

    st.markdown(
        '<div class="side-foot">© <b>Purvi Technologies</b><br>AJ — your multi-agent assistant</div>',
        unsafe_allow_html=True,
    )

# --- Chat history ---------------------------------------------------------- #
if "history" not in st.session_state:
    st.session_state.history = []

for turn in st.session_state.history:
    avatar = "🧑‍💻" if turn["role"] == "user" else "✨"
    with st.chat_message(turn["role"], avatar=avatar):
        st.markdown(turn["content"])

# --- Determine the prompt (quick-start, voice, or text) -------------------- #
prompt = st.session_state.pop("pending", None)

# Auto-greeting: the first time after login, AJ proactively briefs you on today's
# tasks — no clicking. `silent` makes it render as AJ's opener (no fake user message).
silent = False
if auto_brief and not st.session_state.get("greeted") and not st.session_state.history and prompt is None:
    st.session_state["greeted"] = True
    prompt = BRIEFING_PROMPT
    silent = True

if not st.session_state.history and prompt is None:
    st.markdown('<div class="qs-title">✨ Try one of these to get started:</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, qs in enumerate(QUICK_STARTS):
        if cols[i % 2].button(f"{qs['icon']}  {qs['label']}", key=f"qs_{i}"):
            st.session_state["pending"] = qs["prompt"]
            st.rerun()

uploaded = st.file_uploader(
    "📎 Attach a document or image (PDF, txt, csv, png, jpg) — applies to your next message",
    type=["pdf", "txt", "md", "csv", "json", "png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)

# Hands-free voice: tap once, speak, auto-stops on silence and submits.
# In conversation mode the continuous loop (rendered at the bottom) takes over instead.
if not conv_mode:
    voice_widget(int(voice_silence * 1000), lang=lang_voice_code)
else:
    st.info(
        "🗣️ **Conversation mode is on.** Scroll down and tap the green **🎤 Start talking** "
        "button once — your browser (Edge/Chrome) will ask to use the microphone, so click "
        "**Allow**. After that it's hands-free: just talk, and AJ replies aloud and listens again. "
        "Uncheck the toggle in the sidebar to stop.",
        icon="🎤",
    )

typed = st.chat_input("Ask AJ anything — type, or tap 🎤 above to speak…")
if typed:
    prompt = typed

# --- Run the coordinator --------------------------------------------------- #
if prompt:
    # Process any attached files into doc context + image parts.
    doc_context, attachments = "", []
    for f in uploaded or []:
        data = f.getvalue()
        if documents.is_image(f.name):
            attachments.append(documents.image_part(f.name, data))
        else:
            text, err = documents.extract_text(f.name, data)
            if err:
                st.warning(f"📎 {f.name}: {err}")
            else:
                doc_context += f"[{f.name}]\n{text}\n\n"

    if not silent:
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(prompt)
            if uploaded:
                st.caption("📎 " + ", ".join(f.name for f in uploaded))

    with st.chat_message("assistant", avatar="✨"):
        status = st.status(
            "AJ is preparing your briefing…" if silent else "AJ is coordinating specialists…",
            expanded=True,
        )

        def on_event(msg: str) -> None:
            status.write(msg)

        ok = True
        try:
            answer = coordinate(
                prompt,
                history=list(st.session_state.history),
                on_event=on_event,
                doc_context=doc_context,
                attachments=attachments or None,
                language=lang_short,
            )
        except openai.RateLimitError:
            ok = False
            others = ", ".join(config.CHAIN_NAMES[1:]) or "none configured"
            answer = (
                "⚠️ **All AI providers are rate-limited right now.** AJ tried every backup "
                f"({others}) and they're all out of free quota for the moment.\n\n"
                "Wait ~30 seconds and try again. To add more headroom, add a **Groq** key "
                "(free at console.groq.com) — ask me to set it up."
            )
        except openai.APIStatusError as exc:
            ok = False
            answer = f"⚠️ The AI service returned an error ({exc.status_code}). Please try again in a moment."
        except Exception as exc:  # network, etc.
            ok = False
            answer = f"⚠️ Something went wrong: {exc}"

        status.update(
            label="Done" if ok else "Rate limited",
            state="complete" if ok else "error",
            expanded=False,
        )
        st.markdown(answer)

        if ok and conv_mode:
            # Hand the reply to the conversation loop (it speaks, then re-opens the mic).
            st.session_state["conv_speak"] = answer
        elif ok and speak_replies:
            browser_speak(answer, voice_hint, voice_rate, voice_pitch, lang=lang_voice_code)

    if not silent:
        st.session_state.history.append({"role": "user", "content": prompt})
    st.session_state.history.append({"role": "assistant", "content": answer})

# --- Conversation mode: continuous speak→listen loop (no clicking) ---------- #
if conv_mode:
    conversation_widget(
        speak_text=st.session_state.pop("conv_speak", ""),
        silence_ms=int(voice_silence * 1000),
        lang=lang_voice_code,
        hint=voice_hint,
        rate=voice_rate,
        pitch=voice_pitch,
    )

# --- Export last reply ----------------------------------------------------- #
if st.session_state.history and st.session_state.history[-1]["role"] == "assistant":
    last = st.session_state.history[-1]["content"]
    with st.expander("⬇️ Export last reply"):
        c1, c2 = st.columns(2)
        c1.download_button("Markdown (.md)", last, file_name="aj_reply.md", use_container_width=True)
        pdf, err = exports.to_pdf(last)
        if pdf:
            c2.download_button("PDF (.pdf)", pdf, file_name="aj_reply.pdf", mime="application/pdf", use_container_width=True)
        elif err:
            c2.caption(err)
