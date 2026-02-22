"""Ollama Vision Processor — 100% Local AI via OpenAI-compatible API.

Uses llama3.2-vision running on Ollama at http://localhost:11434/v1.
No API keys, no quotas, no rate limits.
"""

import base64
import json
import logging
import os
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class OllamaProcessor:
    """Vision Processor using local Ollama server via OpenAI SDK."""

    VISION_SYSTEM_PROMPT = (
        "You are an expert Autonomous QA Testing Agent named Basir. "
        "Your task is to analyze screenshots of web pages and determine "
        "the current state and necessary actions to achieve a specific goal.\n"
        "Return your analysis in a clear, actionable format."
    )

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or {}

        ollama_models = self.config.get("ollama_models", {})
        self.flash_model = ollama_models.get("flash", "llama3.2-vision")
        self.pro_model = ollama_models.get("pro", "llama3.2-vision")

        self._base_url = self.config.get("ollama_base_url", "http://localhost:11434/v1")
        self._client = None
        print(f"\n🦙 OllamaProcessor initialized | model={self.flash_model} | url={self._base_url}")
        logger.info(
            f"تم تهيئة OllamaProcessor بنجاح | model={self.flash_model} | url={self._base_url}"
        )

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            import httpx
            self._client = AsyncOpenAI(
                base_url=self._base_url,
                api_key="ollama",
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
        return self._client

    def _optimize_screenshot(
        self, screenshot: bytes, max_width: int = 800, quality: int = 60
    ) -> bytes:
        import io
        from PIL import Image

        img = Image.open(io.BytesIO(screenshot))
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # Convert to grayscale to massively reduce payload size
        img = img.convert("L")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()

    async def check_connectivity(self) -> bool:
        """Test if Ollama is reachable before making LLM calls."""
        import urllib.request
        import json as _json
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read().decode())
                models = data.get("models", [])
                names = [m.get("name", "") for m in models]
                print(f"✅ Ollama is running! Available models: {names}")
                logger.info(f"Ollama connected. Models: {names}")
                if not any(self.flash_model in n for n in names):
                    print(f"⚠️ WARNING: Model '{self.flash_model}' not found! Run: ollama pull {self.flash_model}")
                    logger.warning(f"Model '{self.flash_model}' not found in Ollama.")
                return True
        except Exception as e:
            print(f"❌ Cannot connect to Ollama at localhost:11434: {e}")
            print(f"   → Make sure Ollama is running: 'ollama serve'")
            logger.error(f"Ollama unreachable: {e}")
            return False
    async def analyze_screenshot(self, screenshot: bytes, context: str = "") -> dict:
        """Analyze a screenshot using llama3.2-vision via Ollama."""
        print(f"\n🔍 [Ollama] Sending screenshot for analysis ({len(screenshot)} bytes)...")
        print(f"   Model: {self.flash_model} | Context length: {len(context)} chars")
        logger.info(f"Sending screenshot to Ollama ({len(screenshot)} bytes)")
        
        client = self._get_client()
        optimized = self._optimize_screenshot(screenshot)
        encoded = base64.b64encode(optimized).decode("utf-8")
        print(f"   Optimized: {len(optimized)} bytes → base64: {len(encoded)} chars")

        prompt = f"{self.VISION_SYSTEM_PROMPT}\n\nContext: {context}"

        import time as _time
        start = _time.time()
        print(f"   ⏳ Waiting for Ollama response...")
        
        response = await client.chat.completions.create(
            model=self.flash_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=1024,
            temperature=0.1,
            extra_body={"options": {"num_ctx": 8192}},
        )

        elapsed = _time.time() - start
        content = response.choices[0].message.content
        print(f"   ✅ Ollama responded in {elapsed:.1f}s ({len(content)} chars)")
        logger.info(f"⚡ تم تحليل لقطة الشاشة عبر Ollama في {elapsed:.1f} ثانية.")
        return {
            "raw_response": content,
            "source": "ollama",
        }

    async def get_element_coordinates(
        self, screenshot: bytes, element_description: str
    ) -> Tuple[float, float]:
        """Find element coordinates using vision model."""
        client = self._get_client()
        optimized = self._optimize_screenshot(screenshot)
        encoded = base64.b64encode(optimized).decode("utf-8")

        coord_prompt = (
            f"Look at this webpage screenshot. "
            f"Find the element: '{element_description}'.\n\n"
            f"Return ONLY the center coordinates of this element "
            f"as a JSON object with 'y' and 'x' keys, "
            f"where both values are integers in the range 0-1000.\n"
            f"0,0 is the top-left corner. 1000,1000 is the bottom-right.\n\n"
            f'Example response: {{"y": 350, "x": 500}}\n\n'
            f'If the element is not found, respond: {{"error": "not found"}}'
        )

        response = await client.chat.completions.create(
            model=self.flash_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": coord_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=256,
            temperature=0.0,
        )

        raw_text = response.choices[0].message.content.strip()
        logger.info(f"🎯 Ollama response for '{element_description}': {raw_text}")

        norm_x, norm_y = self._parse_coordinates(raw_text, element_description)
        logger.info(
            f"📍 إحداثيات '{element_description}': x={norm_x}, y={norm_y}"
        )
        return norm_x, norm_y

    async def analyze_for_recovery(self, screenshot: bytes) -> dict:
        """Analyze screen for self-healing recovery."""
        client = self._get_client()
        optimized = self._optimize_screenshot(screenshot)
        encoded = base64.b64encode(optimized).decode("utf-8")

        recovery_prompt = (
            "An error occurred while testing this page. Analyze the current screen:\n"
            "1. What is the current state of the page?\n"
            "2. What is the likely cause of the error?\n"
            "3. What is the next recovery step?\n"
            "Respond in JSON with keys: 'page_state', 'error_cause', 'recovery_action'."
        )

        response = await client.chat.completions.create(
            model=self.pro_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": recovery_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=512,
            temperature=0.1,
        )

        logger.info("🔄 تم تحليل التعافي عبر Ollama.")
        return {
            "raw_response": response.choices[0].message.content,
            "source": "ollama_recovery",
        }

    def _parse_coordinates(
        self, text: str, element_description: str
    ) -> Tuple[float, float]:
        try:
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                data = json.loads(text)

            if "error" in data:
                raise ValueError(
                    f"العنصر '{element_description}' لم يُعثر عليه: {data['error']}"
                )

            if "x" not in data or "y" not in data:
                raise ValueError("الإحداثيات غير مكتملة.")

            return float(data["x"]), float(data["y"])
        except json.JSONDecodeError as e:
            logger.error(f"❌ فشل تحليل إحداثيات Ollama: {text}")
            raise ValueError(
                f"فشل تحليل JSON لإحداثيات '{element_description}': {e}"
            ) from e
