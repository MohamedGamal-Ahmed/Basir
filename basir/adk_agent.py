"""ADK Agent Module - Wraps Basir for Google ADK Integration.

This module defines the BasirAgent class, which extends the Google ADK Agent.
It exposes Basir's capabilities (Vision, ARIA, Stealth Browser) as ADK tools
to enable intent-based navigation and human-in-the-loop interaction.
"""

import logging
from typing import Any, Dict, Optional, List
from google.adk.agents.llm_agent import LlmAgent as GoogleADKAgent
from google.adk.tools.function_tool import FunctionTool as Tool

from basir.agent import Agent as BasirCoreAgent
from basir.commands.autonomous_command import IntentCommand

logger = logging.getLogger(__name__)

class BasirAgent(GoogleADKAgent):
    """Google ADK wrapper for the Basir Web Co-Pilot.

    Exposes the core IntentCommand loop as the primary `assist_user` tool,
    allowing the ADK orchestration layer to handle high-level intent routing
    while Basir handles the gritty DOM/Vision navigation.
    """

    def __init__(self, core_agent: BasirCoreAgent):
        """Initialize the ADK Agent wrapper.

        Args:
            core_agent: The underlying Basir Agent (browser/vision orchestrator).
        """
        self.core_agent = core_agent
        self.current_task_results = None
        
        # Define the tools available to this ADK Agent
        tools = self._setup_tools()
        
        # Initialize ADK Agent with a navigator persona
        super().__init__(
            name="Basir_Web_CoPilot",
            description="An AI agent that navigates the web on behalf of the user.",
            instructions=(
                "You are Basir, a Web Co-Pilot. Your primary goal is to help users "
                "accomplish tasks on the web (e.g., booking flights, finding products). "
                "Use the 'assist_user' tool to execute the user's goal. "
                "Always narrate your steps and ask for clarification if ambiguous."
            ),
            tools=tools,
        )
        logger.info("🤖 Basir ADK Agent initialized.")

    def _setup_tools(self) -> List[Tool]:
        """Configure the ADK tools exposed by this agent."""
        return [
            Tool(
                name="assist_user",
                description="Executes a high-level user goal on the current webpage.",
                func=self.assist_user,
            ),
            Tool(
                name="navigate",
                description="Navigates the browser to a specific URL.",
                func=self.navigate,
            ),
            Tool(
                name="explain_to_user",
                description="Provides a natural language explanation of the current screen to the user.",
                func=self.explain_to_user,
            ),
            Tool(
                name="ask_user",
                description="Pauses execution to ask the user a question for clarification.",
                func=self.ask_user,
            ),
            Tool(
                name="screenshot",
                description="Captures and returns the current page state.",
                func=self.screenshot,
            ),
            Tool(
                name="click",
                description="Clicks at normalized coordinates (0-1000).",
                func=self.click,
            ),
            Tool(
                name="type_text",
                description="Types text into the currently focused element.",
                func=self.type_text,
            ),
            Tool(
                name="scroll",
                description="Scrolls the page.",
                func=self.scroll,
            ),
            Tool(
                name="aria_snapshot",
                description="Gets the ARIA accessibility tree of the page.",
                func=self.aria_snapshot,
            ),
        ]

    async def assist_user(self, goal: str) -> str:
        """Core tool: Attempts to fulfill the user's intent using the ReAct loop."""
        logger.info(f"🎯 ADK Tool Call: assist_user(goal='{goal}')")
        
        try:
            # Create an IntentCommand for this specific goal
            intent_cmd = IntentCommand(goal=goal, max_steps=self.core_agent.max_retries * 5)
            
            # Execute the goal via the core agent (starts the Observe-Think-Act loop)
            # Assuming the browser is already on the target page or will navigate internally
            url = self.core_agent.browser._page.url if self.core_agent.browser._page else "about:blank"
            self.current_task_results = await self.core_agent.run(target_url=url, test_command=intent_cmd)
            
            status = self.current_task_results.get("status", "unknown")
            return f"Task finished with status: {status}"
        except Exception as e:
            logger.error(f"❌ Error in assist_user: {e}")
            return f"Error: {e}"

    async def navigate(self, url: str) -> str:
        """Tool: Navigates the browser."""
        logger.info(f"🌐 ADK Tool Call: navigate(url='{url}')")
        try:
            if not self.core_agent.browser._browser:
                await self.core_agent.browser.launch()
            await self.core_agent.browser.navigate(url)
            return f"Successfully navigated to {url}"
        except Exception as e:
            return f"Navigation failed: {e}"

    async def explain_to_user(self, text: str) -> str:
        """Tool: Emits narration for the user (dashboard/voice)."""
        logger.info(f"🗣️ ADK Tool Call: explain_to_user(text='{text}')")
        # In a real app, this might push to a WebSocket, TTS engine, or Streamlit state
        print(f"\n🗣️ [Basir]: {text}\n")
        return "Narration delivered."

    async def ask_user(self, question: str) -> str:
        """Tool: Asks the user a question and waits for a response (Human-in-the-loop)."""
        logger.info(f"❓ ADK Tool Call: ask_user(text='{question}')")
        # In the Streamlit app, we will intercept this and pause execution
        print(f"\n❓ [Basir asks]: {question}\n")
        return "Wait for user input..."

    async def screenshot(self) -> str:
        """Tool: Take a screenshot."""
        logger.info("📸 ADK Tool Call: screenshot()")
        try:
            shot = await self.core_agent.browser.take_screenshot()
            return f"Screenshot taken, bytes length: {len(shot)}"
        except Exception as e:
            return f"Error: {e}"

    async def click(self, x: int, y: int) -> str:
        """Tool: Click at normalized coords."""
        logger.info(f"🖱️ ADK Tool Call: click(x={x}, y={y})")
        try:
            await self.core_agent.browser.click_at_normalized(x, y)
            return f"Clicked at ({x}, {y})"
        except Exception as e:
            return f"Error: {e}"

    async def type_text(self, text: str) -> str:
        """Tool: Type text."""
        logger.info(f"⌨️ ADK Tool Call: type_text(text='{text}')")
        try:
            await self.core_agent.browser.type_text(text)
            return f"Typed text"
        except Exception as e:
            return f"Error: {e}"

    async def scroll(self, direction: str) -> str:
        """Tool: Scroll page."""
        logger.info(f"📜 ADK Tool Call: scroll(direction='{direction}')")
        try:
            await self.core_agent.browser.scroll(direction)
            return f"Scrolled {direction}"
        except Exception as e:
            return f"Error: {e}"

    async def aria_snapshot(self) -> str:
        """Tool: Get ARIA snapshot."""
        logger.info("🌳 ADK Tool Call: aria_snapshot()")
        try:
            tree = await self.core_agent.browser.get_aria_snapshot()
            return tree
        except Exception as e:
            return f"Error: {e}"

