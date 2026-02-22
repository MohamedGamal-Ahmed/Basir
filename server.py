"""FastAPI Server for Basir Web Co-Pilot.

This server exposes endpoints to start/interrupt the agent and stream
the live view to the frontend dashboard via multipart/x-mixed-replace.
"""

import os
import sys
import asyncio

# Fix NotImplementedError for Playwright subprocesses on Windows in uvicorn
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
import json
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from basir.agent import Agent
from basir.commands.autonomous_command import IntentCommand

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add FileHandler for Streamlit to tail
Path("reports/live").mkdir(parents=True, exist_ok=True)
log_file = "reports/live/agent.log"
open(log_file, 'w').close() # clear on boot
file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s"))
logging.getLogger().addHandler(file_handler)

app = FastAPI(title="Basir Web Co-Pilot API")

# Add CORS middleware for Streamlit to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
current_agent = None
global_status = {
    "state": "idle"
}

class GoalRequest(BaseModel):
    url: str
    goal: str
    max_steps: int = 15

class InterruptRequest(BaseModel):
    message: str

def get_agent_config():
    import yaml
    with open("configs/settings.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return {
        "max_retries": config.get("agent", {}).get("max_retries", 3),
        "browser": config.get("browser", {}),
        "vision": {
            "flash_model": config.get("models", {}).get("default_model", "gemini-2.5-flash"),
            "pro_model": config.get("models", {}).get("high_reasoning_model", "gemini-2.5-pro"),
        },
    }

def sync_run_agent_task(url: str, goal: str, max_steps: int):
    global current_agent, global_status
    
    import sys
    import asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
    async def _inner():
        global current_agent, global_status
        try:
            global_status["state"] = "running"
            current_agent = Agent(config=get_agent_config())
            intent_cmd = IntentCommand(goal=goal, max_steps=max_steps)
            
            await current_agent.run(target_url=url, test_command=intent_cmd)
            global_status["state"] = "completed"
        except Exception as e:
            logger.error(f"Agent task failed: {e}")
            global_status["state"] = "failed"
        finally:
            current_agent = None

    asyncio.run(_inner())

@app.post("/api/assist")
async def assist_endpoint(req: GoalRequest, background_tasks: BackgroundTasks):
    global global_status
    if global_status["state"] == "running":
        raise HTTPException(status_code=400, detail="Agent is already running a task.")
        
    background_tasks.add_task(sync_run_agent_task, req.url, req.goal, req.max_steps)
    return {"message": "Agent started.", "goal": req.goal}

@app.post("/api/interrupt")
async def interrupt_endpoint(req: InterruptRequest):
    Path("reports/live").mkdir(parents=True, exist_ok=True)
    Path("reports/live/interrupt.txt").write_text(req.message, encoding="utf-8")
    return {"message": "Interrupt instruction received."}

@app.get("/api/status")
async def status_endpoint():
    # Allow client to know if agent finished
    return global_status

async def frame_generator():
    """Generates a multipart/x-mixed-replace stream of the latest browser frame."""
    frame_path = Path("reports/live/frame.jpg")
    last_mtime = 0
    while True:
        try:
            if frame_path.exists():
                mtime = frame_path.stat().st_mtime
                if mtime != last_mtime:
                    last_mtime = mtime
                    frame_data = frame_path.read_bytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
        except Exception:
            pass
        await asyncio.sleep(0.05)  # Max ~20 FPS

@app.get("/api/stream")
async def stream_endpoint():
    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Placeholder for ultra-low latency two-way comms
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "provider": "google_ai"}
