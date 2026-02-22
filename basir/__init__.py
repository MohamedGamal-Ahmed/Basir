"""
Basir - Autonomous QA Visionary Agent.

A high-precision, AI-powered QA Testing Agent built for the
Gemini Live Agent Challenge (UI Navigator category).

Modules:
    agent: Main orchestrator for the QA testing workflow.
    browser_controller: Playwright-based browser interaction and control.
    vision_processor: Gemini 3.1 multimodal vision analysis (with Live Streaming).
    reporter: Bug report and test result generation.
    commands: Command Pattern for extensible test types.
"""

from basir.agent import Agent
from basir.browser_controller import BrowserController
from basir.vision_processor import VisionProcessor
from basir.reporter import Reporter

__version__ = "0.1.0"
__all__ = ["Agent", "BrowserController", "VisionProcessor", "Reporter"]
