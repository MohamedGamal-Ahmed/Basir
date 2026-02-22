"""Basir Live Dashboard - Real-time QA Agent Interface.

A Streamlit-based web dashboard for controlling and monitoring
the Basir Autonomous QA Testing Agent in real-time.

This connects to a FastAPI backend at http://localhost:8000.
"""

import json
import os
import requests
import time
import streamlit as st
from datetime import datetime
from pathlib import Path


# ─── Configuration ────────────────────────────────────────────
API_URL = "http://127.0.0.1:8000/api"

st.set_page_config(
    page_title="Basir — Web Co-Pilot",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

    .stApp { font-family: 'Inter', sans-serif; }

    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
    }
    div.stButton, div.stMarkdown {margin-top: -10px;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}

    .basir-header {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        padding: 0.8rem 1.5rem;
        border-radius: 12px;
        margin-bottom: 0.5rem;
        text-align: center;
        color: white;
    }
    .basir-header h1 { margin: 0; font-size: 1.5rem; letter-spacing: 1px; }
    .basir-header p { margin: 0.2rem 0 0 0; opacity: 0.7; font-size: 0.85rem; }

    .live-view-container {
        border-radius: 12px;
        padding: 8px;
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

    .vision-container {
        position: relative;
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #333;
        background: #0f172a;
        box-shadow: 0 5px 15px rgba(0,0,0,0.5);
        margin-bottom: 0.5rem;
    }
    .browser-header {
        background: #1e293b;
        padding: 5px 15px;
        display: flex;
        align-items: center;
        border-bottom: 1px solid #333;
    }
    .browser-dot {
        width: 12px; height: 12px; border-radius: 50%; margin-right: 8px;
    }
    .dot-red { background: #ef4444; }
    .dot-yellow { background: #f59e0b; }
    .dot-green { background: #10b981; }
    
    .browser-url-bar {
        flex-grow: 1;
        background: #0f172a;
        margin: 0 15px;
        padding: 5px 15px;
        border-radius: 20px;
        font-size: 0.8rem;
        color: #94a3b8;
        font-family: monospace;
        text-align: center;
        border: 1px solid #334155;
    }

    .vision-image {
        width: 100%;
        display: block;
        height: 53vh;
        min-height: 380px;
        object-fit: contain;
    }
    .pulse-logo {
        font-size: 1.5rem;
        animation: pulse 1.5s infinite ease-in-out;
    }
    @keyframes pulse {
        0% { transform: scale(0.95); opacity: 0.8; }
        50% { transform: scale(1.05); opacity: 1; }
        100% { transform: scale(0.95); opacity: 0.8; }
    }
    .narration-panel {
        background: linear-gradient(145deg, #1e293b, #0f172a);
        border-left: 4px solid #38bdf8;
        border-radius: 8px;
        padding: 0.6rem 1rem;
        margin-bottom: 0.2rem;
        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        gap: 0.8rem;
    }
    .narration-icon { font-size: 1.5rem; }
</style>
""", unsafe_allow_html=True)


# ─── Session State Init ──────────────────────────────────────
if "logs" not in st.session_state:
    st.session_state.logs = []
if "running" not in st.session_state:
    st.session_state.running = False
if "step_count" not in st.session_state:
    st.session_state.step_count = 0
if "api_calls" not in st.session_state:
    st.session_state.api_calls = []
if "daily_count" not in st.session_state:
    st.session_state.daily_count = 0

# ─── API Clients ─────────────────────────────────────────────
def fetch_status():
    try:
        r = requests.get(f"{API_URL}/status", timeout=2)
        if r.status_code == 200:
            data = r.json()
            # If server indicates completed/failed but we still think running
            if data.get("state") in ["completed", "failed"] and st.session_state.running:
                st.session_state.running = False
            return data
    except Exception:
        pass
    return None

def fetch_logs():
    """Read agent.log and parse it for the reasoning log container"""
    log_file = Path("reports/live/agent.log")
    if not log_file.exists():
        return []

    parsed_logs = []
    lines = log_file.read_text(encoding="utf-8").strip().split('\n')
    
    for line in lines[-50:]:
        line = line.strip()
        if not line: continue
        
        parts = line.split(" | ")
        if len(parts) < 4: continue
        t = parts[0].split(" ")[1][:8]  # Extract time portion
        msg = parts[3]
        
        # Categorize
        if "💭" in msg or "التفكير" in msg or "thought" in msg.lower() or "🧠" in msg:
            log_type = "thought"
        elif "⚡" in msg or "نقر" in msg or "كتابة" in msg or "action" in msg.lower():
            log_type = "action"
        elif "❌" in msg or "خطأ" in msg or "ERROR" in msg or "فشل" in msg:
            log_type = "error"
        else:
            log_type = "status"
            
        parsed_logs.append({"time": t, "type": log_type, "text": msg[:150]})
        
    return parsed_logs

# ─── Layout ────────────────────────────────────────────────────
st.markdown("""
<div class="basir-header">
    <h1>🔭 Basir: Co-Pilot for the Web</h1>
    <p>Watch as your AI agent perfectly navigates the web on your behalf.</p>
</div>
""", unsafe_allow_html=True)

# Main Agent Status Polling
server_state = fetch_status()
if server_state and server_state.get("state") == "running":
    st.session_state.running = True

# ─── Sidebar: Control Room & Quota Monitor ─────────────────────
with st.sidebar:
    st.markdown("## 🎮 Control Room")
    
    target_url = st.text_input("🌐 Target URL", value="https://the-internet.herokuapp.com/login")
    test_goal = st.text_area("🎯 User Intent (Goal)", value="Log in with username 'tomsmith' and password 'SuperSecretPassword!' and verify we reach the secure area", height=120)
    max_steps = st.slider("📊 Max Steps", 5, 50, 15)

    if st.button("🚀 Launch Basir", type="primary", use_container_width=True, disabled=st.session_state.running):
        st.session_state.logs = []
        st.session_state.step_count = 0
        st.session_state.running = True
        
        try:
            requests.post(f"{API_URL}/assist", json={"url": target_url, "goal": test_goal, "max_steps": max_steps})
        except Exception as e:
            st.error(f"Could not connect to FastAPI server: {e}")
            st.session_state.running = False
        st.rerun()

    # Live Redirection Tools
    if st.session_state.running:
        st.markdown("### ✋ Live Redirection")
        interrupt_msg = st.text_input("💬 Tell Basir...", placeholder="e.g. Stop! Click the blue button.", key="sidebar_interrupt")
        if st.button("Send Correction ⚡", type="secondary", use_container_width=True):
            if interrupt_msg:
                requests.post(f"{API_URL}/interrupt", json={"message": interrupt_msg})
                st.success("🛑 Interrupt sent to API!")

    st.markdown("---")
    
    # Static Quota Display (Mocked for UI decoupling, backend can provide real stats)
    st.markdown("### 📊 Server Status")
    if st.session_state.running:
        st.success("🟢 FastAPI Background Worker: Running")
    else:
        st.info("😴 FastAPI Background Worker: Idle")


# ─── Narration Panel ───────────────────────────────────
narration_path = Path("reports/live/narration.txt")
current_narration = ""
if narration_path.exists():
    try:
        current_narration = narration_path.read_text(encoding="utf-8").strip()
    except Exception:
        pass

if current_narration and st.session_state.running:
    st.markdown(f"""
    <div class="narration-panel">
        <div class="narration-icon pulse-logo">🗣️</div>
        <div class="narration-text">{current_narration}</div>
    </div>
    """, unsafe_allow_html=True)


# ─── Main Content Area ────────────────────────────────────────────────
col1, col2 = st.columns([2, 1], gap="small")

with col1:
    st.markdown("""
    <div class="browser-header">
        <div class="browser-dot dot-red"></div>
        <div class="browser-dot dot-yellow"></div>
        <div class="browser-dot dot-green"></div>
        <div class="browser-url-bar">Live API Stream (multipart/x-mixed-replace)</div>
    </div>
    """, unsafe_allow_html=True)
    
    if st.session_state.running:
        # Native browser MJPEG stream tag - infinite framerate with zero Streamlit re-renders!
        st.markdown(f'<img src="{API_URL}/stream" class="vision-image">', unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="vision-image live-view-container" style="background:#0a0a0a;">
            <div style="text-align:center; color:#64748b;">
                <div style="font-size:4rem; margin-bottom:1rem;">🛰️</div>
                <h2>Live Stream Paused</h2>
                <p>Launch the agent to connect to the FastAPI stream.</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

with col2:
    st.markdown("#### 📝 Reasoning Log")
    log_container = st.container(height=400)
    with log_container:
        logs = fetch_logs()
        if not logs:
            st.info("Agent backend logs will stream here...")
        else:
            for entry in logs:
                log_type = entry.get("type", "status")
                t = entry.get("time", "00:00")
                text = entry.get("text", "")

                icons = {"thought": "💭", "action": "⚡", "error": "❌", "status": "📌"}
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

# Autorefresh to sync logs with background task
if st.session_state.running:
    time.sleep(1.0)
    st.rerun()
