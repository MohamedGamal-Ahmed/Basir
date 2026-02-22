"""Basir Live Dashboard - Real-time QA Agent Interface.

A Streamlit-based web dashboard for controlling and monitoring
the Basir Autonomous QA Testing Agent in real-time.

Uses subprocess to run the agent in a separate process,
avoiding Windows asyncio/Playwright conflicts.

Run:
    python -m streamlit run app.py
"""

import json
import subprocess
import sys
import os
import glob
import time
import streamlit as st
from datetime import datetime
from pathlib import Path


# ─── Page Config ──────────────────────────────────────────────
st.set_page_config(
    page_title="Basir 🔭 QA Agent Dashboard",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Custom CSS ───────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

    .stApp { font-family: 'Inter', sans-serif; }

    .basir-header {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        text-align: center;
        color: white;
    }
    .basir-header h1 { margin: 0; font-size: 2rem; letter-spacing: 1px; }
    .basir-header p { margin: 0.3rem 0 0 0; opacity: 0.7; font-size: 0.9rem; }

    .live-view-container {
        background: #0a0a0a;
        border: 2px solid #333;
        border-radius: 12px;
        padding: 8px;
        min-height: 500px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .log-entry {
        padding: 0.5rem 0.8rem;
        margin: 0.3rem 0;
        border-radius: 8px;
        font-size: 0.85rem;
        border-left: 3px solid;
    }
    .log-thought { background: rgba(99,102,241,0.1); border-color: #6366f1; color: #a5b4fc; }
    .log-action { background: rgba(16,185,129,0.1); border-color: #10b981; color: #6ee7b7; }
    .log-error { background: rgba(239,68,68,0.1); border-color: #ef4444; color: #fca5a5; }
    .log-status { background: rgba(59,130,246,0.1); border-color: #3b82f6; color: #93c5fd; }

    .status-badge {
        display: inline-block; padding: 0.3rem 0.8rem;
        border-radius: 20px; font-size: 0.8rem; font-weight: 600;
    }
    .status-running { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white; }
    .status-passed { background: linear-gradient(135deg, #10b981, #059669); color: white; }
    .status-failed { background: linear-gradient(135deg, #ef4444, #dc2626); color: white; }

    .step-counter {
        background: rgba(99,102,241,0.15);
        border: 1px solid rgba(99,102,241,0.3);
        border-radius: 8px; padding: 0.8rem;
        text-align: center; margin: 0.5rem 0;
    }

    /* Live Stream & Overlay CSS */
    .vision-container {
        position: relative;
        border-radius: 12px;
        overflow: hidden;
        border: 2px solid #333;
        background: #000;
        min-height: 400px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .vision-image {
        width: 100%;
        display: block;
    }
    .glass-overlay {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        backdrop-filter: blur(12px);
        background: rgba(17, 25, 40, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.125);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        z-index: 50;
    }
    .pulse-logo {
        font-size: 4rem;
        animation: pulse 1.5s infinite ease-in-out;
        margin-bottom: 1rem;
        text-shadow: 0 0 20px rgba(99,102,241,0.8);
    }
    @keyframes pulse {
        0% { transform: scale(0.9); opacity: 0.7; }
        50% { transform: scale(1.1); opacity: 1; }
        100% { transform: scale(0.9); opacity: 0.7; }
    }
    .thinking-text {
        color: white;
        font-size: 1.2rem;
        font-weight: 600;
        letter-spacing: 1px;
    }
</style>
""", unsafe_allow_html=True)


# ─── Session State Init ──────────────────────────────────────
if "logs" not in st.session_state:
    st.session_state.logs = []
if "screenshot_path" not in st.session_state:
    st.session_state.screenshot_path = None
if "running" not in st.session_state:
    st.session_state.running = False
if "step_count" not in st.session_state:
    st.session_state.step_count = 0
if "status" not in st.session_state:
    st.session_state.status = "idle"
if "results" not in st.session_state:
    st.session_state.results = None
if "is_thinking" not in st.session_state:
    st.session_state.is_thinking = False
if "thinking_msg" not in st.session_state:
    st.session_state.thinking_msg = "Basir is navigating the logic..."


# ─── Log Parser ───────────────────────────────────────────────
def parse_log_line(line: str) -> dict | None:
    """تحليل سطر log من مخرجات main.py وتصنيفه.

    Args:
        line: سطر من stdout/stderr.

    Returns:
        dict أو None: {"type": str, "text": str}
    """
    line = line.strip()
    if not line:
        return None

    timestamp = datetime.now().strftime("%H:%M:%S")

    # تصنيف بناءً على الأيقونات والكلمات المفتاحية
    if "💭" in line or "التفكير" in line or "thought" in line.lower():
        return {"time": timestamp, "type": "thought", "text": line}
    elif "⚡" in line or "نقر" in line or "كتابة" in line or "click" in line.lower():
        return {"time": timestamp, "type": "action", "text": line}
    elif "❌" in line or "خطأ" in line or "ERROR" in line or "فشل" in line:
        return {"time": timestamp, "type": "error", "text": line}
    elif "✅" in line or "🚀" in line or "🔭" in line or "🧠" in line:
        return {"time": timestamp, "type": "status", "text": line}
    elif "📍" in line or "🎯" in line or "CoordinateMapper" in line:
        return {"time": timestamp, "type": "action", "text": line}
    elif "🔄" in line or "ReAct" in line:
        return {"time": timestamp, "type": "thought", "text": line}
    elif "|" in line and ("INFO" in line or "WARNING" in line):
        # Standard log format: HH:MM:SS | module | LEVEL | message
        parts = line.split("|", 3)
        if len(parts) >= 4:
            msg = parts[3].strip()
            level = parts[2].strip()
            if level == "WARNING" or level == "ERROR":
                return {"time": timestamp, "type": "error", "text": msg}
            return {"time": timestamp, "type": "status", "text": msg}

    return {"time": timestamp, "type": "status", "text": line}

import threading
import queue

def _read_stdout(proc, q):
    """دالة تقرأ מخرجات الـ subprocess في Background Thread."""
    for line in proc.stdout:
        q.put(line)

def run_agent_subprocess(url: str, goal: str, mode: str, max_steps: int, live_placeholder):
    """تشغيل Agent عبر subprocess لتجاوز مشاكل asyncio/threading.

    Args:
        url: URL الهدف.
        goal: الهدف بلغة طبيعية.
        mode: "autonomous" أو "scripted".
        max_steps: الحد الأقصى للخطوات.
    """
    cmd = [
        sys.executable, "main.py",
        "--url", url,
        "--mode", mode,
        "--goal", goal,
        "--max-steps", str(max_steps),
    ]

    st.session_state.logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "type": "status",
        "text": f"🚀 Launching: {' '.join(cmd)}"
    })

    try:
        # إعداد البيئة مع UTF-8 لتجنب UnicodeEncodeError
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(Path(__file__).parent),
        )

        # قراءة المخرجات في Thread مستقل כדי לא يعرقل הـ Stream
        q = queue.Queue()
        t = threading.Thread(target=_read_stdout, args=(proc, q), daemon=True)
        t.start()
        
        # قائمة الانتظار للإطارات للـ Streaming (لكلا الفريمات وتحديثات الـ State)
        live_frame_path = Path("reports/live/frame.jpg")
        last_mtime = 0

        # الاستمرار طول ما البروسيس شغالة أو الكيو مش فاضية
        while proc.poll() is None or not q.empty():
            # تفريغ الطابور من اللوجات
            while not q.empty():
                try:
                    line = q.get_nowait()
                    if "THINKING_START" in line:
                        st.session_state.is_thinking = True
                        if "recovery" in line.lower():
                            st.session_state.thinking_msg = "Analyzing recovery options..."
                        else:
                            st.session_state.thinking_msg = "Basir is navigating the logic..."
                    elif "THINKING_END" in line:
                        st.session_state.is_thinking = False
                        
                    parsed = parse_log_line(line)
                    if parsed:
                        st.session_state.logs.append(parsed)
                        if parsed["type"] == "action":
                            st.session_state.step_count += 1
                        st.session_state.status = parsed["text"][:80]
                except queue.Empty:
                    break

            # تحديث شاشة الـ Live Stream إذا توفر إطار جديد (≈ 15 FPS)
            if live_frame_path.exists():
                try:
                    mtime = live_frame_path.stat().st_mtime
                    if mtime != last_mtime:
                        last_mtime = mtime
                        live_placeholder.image(str(live_frame_path), width="stretch")
                except Exception:
                    pass
            
            # وقت راحة لدعم ~15 FPS
            time.sleep(0.06)

        if proc.returncode == 0:
            st.session_state.status = "✅ Test completed!"
            st.session_state.results = {"status": "passed", "steps": st.session_state.step_count}
        else:
            st.session_state.status = f"❌ Process exited with code {proc.returncode}"
            st.session_state.results = {"status": "error", "error": f"Exit code: {proc.returncode}"}

    except Exception as e:
        st.session_state.logs.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": "error",
            "text": f"❌ Subprocess error: {e}"
        })
        st.session_state.status = f"❌ Error: {e}"

    st.session_state.running = False

    # البحث عن آخر screenshot في مجلد reports/screenshots
    screenshots = sorted(
        glob.glob("reports/screenshots/*.png"),
        key=os.path.getmtime, reverse=True
    )
    if screenshots:
        st.session_state.screenshot_path = screenshots[0]

    # تحديد الحالة الحقيقية من اللوغات
    for entry in reversed(st.session_state.logs):
        text = entry.get("text", "")
        if "passed" in text.lower() or "✅" in text:
            st.session_state.results = {
                "status": "passed", "steps": st.session_state.step_count
            }
            break
        elif "error" in text.lower() or "❌" in text:
            st.session_state.results = {
                "status": "error", "error": text
            }
            break


# ─── Header ────────────────────────────────────────────────────
st.markdown("""
<div class="basir-header">
    <h1>🔭 Basir Dashboard</h1>
    <p>Autonomous QA Visionary Agent — Real-time Testing Interface</p>
</div>
""", unsafe_allow_html=True)


# ─── Layout ────────────────────────────────────────────────────
col_vision, col_control = st.columns([3, 2], gap="large")


# ─── Left Column: The Vision ──────────────────────────────────
with col_vision:
    st.markdown("### 🔭 Live View")

    # طبقة الـ Thinking Overlay (CSS فقط — تظهر/تختفي بناءً على الحالة)
    if st.session_state.is_thinking:
        st.markdown(f"""
        <div style="
            background: rgba(17, 25, 40, 0.75);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.125);
            border-radius: 12px;
            padding: 2rem;
            text-align: center;
            margin-bottom: 0.5rem;
        ">
            <div style="font-size: 3rem; animation: pulse 1.5s infinite ease-in-out;">🔭</div>
            <div style="color: white; font-size: 1.1rem; font-weight: 600; letter-spacing: 1px; margin-top: 0.5rem;">
                {st.session_state.thinking_msg}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # عنصر الصورة الحية — st.image يعمل دايماً بدون مشاكل
    live_placeholder = st.empty()

    if not st.session_state.running:
        live_frame_path = Path("reports/live/frame.jpg")
        if live_frame_path.exists():
            live_placeholder.image(str(live_frame_path), width="stretch")
        elif st.session_state.screenshot_path and Path(st.session_state.screenshot_path).exists():
            live_placeholder.image(st.session_state.screenshot_path, width="stretch")
        else:
            live_placeholder.markdown("""
            <div class="vision-container">
                <div style="text-align:center; color:#555;">
                    <p style="font-size:3rem;">🔭</p>
                    <p>Waiting for Basir to open its eyes...</p>
                    <p style="font-size:0.8rem; opacity:0.5;">
                        Enter a URL and goal, then click Launch
                    </p>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # Step Counter & Status
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
        <div class="step-counter">
            <div style="font-size:2rem; font-weight:700;">{st.session_state.step_count}</div>
            <div style="font-size:0.8rem; opacity:0.6;">Steps Taken</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        status = st.session_state.status
        if "✅" in str(status):
            badge_class = "status-passed"
        elif "❌" in str(status) or "error" in str(status).lower():
            badge_class = "status-failed"
        else:
            badge_class = "status-running"

        st.markdown(f"""
        <div class="step-counter">
            <span class="status-badge {badge_class}">{status or 'Idle'}</span>
        </div>
        """, unsafe_allow_html=True)


# ─── Right Column: The Control Room ───────────────────────────
with col_control:
    st.markdown("### 🎮 Control Room")

    target_url = st.text_input(
        "🌐 Target URL",
        value="https://the-internet.herokuapp.com/login",
        placeholder="https://example.com",
    )

    test_goal = st.text_area(
        "🎯 Goal (Natural Language)",
        value="Log in with username 'tomsmith' and password 'SuperSecretPassword!' and verify we reach the secure area",
        height=80,
        placeholder="Describe what Basir should do..."
    )

    opt_col1, opt_col2 = st.columns(2)
    with opt_col1:
        test_mode = st.selectbox("⚙️ Mode", ["autonomous", "scripted"], index=0)
    with opt_col2:
        max_steps = st.slider("📊 Max Steps", 5, 30, 15)

    st.markdown("")
    if st.button(
        "🚀 Launch Basir",
        type="primary",
        width="stretch",
        disabled=st.session_state.running,
    ):
        # Reset state
        st.session_state.logs = []
        st.session_state.screenshot_path = None
        st.session_state.step_count = 0
        st.session_state.running = True
        st.session_state.status = "🚀 Launching..."
        st.session_state.results = None

        # تشغيل Agent عبر subprocess (يتجنب كل مشاكل asyncio) مع توفير live_placeholder
        run_agent_subprocess(target_url, test_goal, test_mode, max_steps, live_placeholder)
        st.rerun()

    # ─── Reasoning Log ─────────────────────────────────────
    st.markdown("### 📝 Reasoning Log")

    log_container = st.container(height=400)
    with log_container:
        if not st.session_state.logs:
            st.info("Basir's thoughts and actions will appear here...")
        else:
            for entry in reversed(st.session_state.logs[-50:]):
                log_type = entry["type"]
                t = entry["time"]
                text = entry["text"]

                icons = {"thought": "💭", "action": "⚡", "error": "❌", "status": "�"}
                classes = {"thought": "log-thought", "action": "log-action",
                           "error": "log-error", "status": "log-status"}

                icon = icons.get(log_type, "📌")
                css_class = classes.get(log_type, "log-status")

                st.markdown(
                    f'<div class="log-entry {css_class}">'
                    f'<strong>{icon} {t}</strong> — {text}'
                    f'</div>',
                    unsafe_allow_html=True
                )

    # ─── Results ───────────────────────────────────────────
    if st.session_state.results:
        st.markdown("### 📊 Results")
        results = st.session_state.results
        status = results.get("status", "unknown")

        if status == "passed":
            st.success(f"✅ Test PASSED — {results.get('steps', 0)} steps")
        elif status == "error":
            st.error(f"❌ Test ERROR — {results.get('error', 'Unknown')}")
        else:
            st.warning(f"⚠️ Test {status.upper()}")

        with st.expander("📋 Details", expanded=False):
            st.json(results)
