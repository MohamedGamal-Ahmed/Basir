import base64
import json
import logging
import os
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class DeepSeekProcessor:
    """Vision Processor using DeepSeek API via OpenAI SDK.
    
    Note: Requires `openai` package installed.
    """
    
    VISION_SYSTEM_PROMPT = (
        "You are an expert Autonomous QA Testing Agent named Basir. "
        "Your task is to analyze screenshots of web pages and determine "
        "the current state and necessary actions to achieve a specific goal.\n"
        "Return your analysis in a clear, actionable format."
    )

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or {}
        
        deepseek_models = self.config.get("deepseek_models", {})
        self.flash_model = deepseek_models.get("flash", "deepseek-chat")
        self.pro_model = deepseek_models.get("pro", "deepseek-chat")
        
        self._api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self._api_key:
            raise ValueError("❌ لم يُعثر على DEEPSEEK_API_KEY!")
            
        self._client = None
        logger.info("تم تهيئة DeepSeekProcessor بنجاح.")

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url="https://api.deepseek.com"
            )
        return self._client

    def _optimize_screenshot(self, screenshot: bytes, max_width: int = 1024, quality: int = 70) -> bytes:
        import io
        from PIL import Image
        
        img = Image.open(io.BytesIO(screenshot))
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()

    async def analyze_screenshot(self, screenshot: bytes, context: str = "") -> dict:
        client = self._get_client()
        optimized = self._optimize_screenshot(screenshot)
        encoded = base64.b64encode(optimized).decode("utf-8")
        
        prompt = f"{self.VISION_SYSTEM_PROMPT}\n\nContext: {context}"
        
        try:
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
            )
            raw_response = response.choices[0].message.content
        except Exception as e:
            logger.error(f"DeepSeek Vision failed: {e}. Attempting text-only fallback...")
            response = await client.chat.completions.create(
                model=self.flash_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are Basir Autonomous QA Agent. You cannot see the page right now but must guess based on context."
                    },
                    {
                        "role": "user",
                        "content": prompt + "\n\n(Note: Screenshot is not available. Please output a valid wait or done action.)"
                    }
                ],
                max_tokens=1024,
                temperature=0.1,
            )
            raw_response = response.choices[0].message.content
            
        logger.info("⚡ تم استلام الاستجابة من DeepSeek.")
        return {"raw_response": raw_response, "source": "deepseek"}

    async def get_element_coordinates(self, screenshot: bytes, element_description: str) -> Tuple[float, float]:
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
            f"Example response: {{\"y\": 350, \"x\": 500}}\n\n"
            f"If the element is not found, respond: {{\"error\": \"not found\"}}"
        )

        try:
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
        except Exception as e:
            logger.error(f"DeepSeek Vision failed: {e}. Returning fallback target coords.")
            raw_text = '{"x": 500, "y": 500}'
            
        logger.info(f"🎯 DeepSeek response for '{element_description}': {raw_text}")
        
        norm_x, norm_y = self._parse_coordinates(raw_text, element_description)
        logger.info(f"📍 إحداثيات '{element_description}': x={norm_x}, y={norm_y} (normalized 0-1000)")
        return norm_x, norm_y

    def _parse_coordinates(self, text: str, element_description: str) -> Tuple[float, float]:
        try:
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                data = json.loads(text)
                
            if "error" in data:
                raise ValueError(f"العنصر '{element_description}' لم يُعثر عليه: {data['error']}")
                
            if "x" not in data or "y" not in data:
                raise ValueError("الإحداثيات غير مكتملة.")
                
            return float(data["x"]), float(data["y"])
        except Exception as e:
            logger.error(f"❌ فشل تحليل إحداثيات: {text}")
            raise ValueError(f"فشل تحليل الـ JSON لإحداثيات '{element_description}': {e}") from e

    async def analyze_for_recovery(self, screenshot: bytes) -> dict:
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

        try:
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
            raw_response = response.choices[0].message.content
        except Exception as e:
            raw_response = '{"page_state": "unknown", "error_cause": "vision fails", "recovery_action": "wait"}'

        logger.info("🔄 تم تحليل التعافي عبر DeepSeek.")
        return {"raw_response": raw_response, "source": "deepseek_recovery"}

    async def generate_bug_report(self, screenshot: bytes, steps: list, error_context: str) -> dict:
        client = self._get_client()
        optimized = self._optimize_screenshot(screenshot)
        encoded = base64.b64encode(optimized).decode("utf-8")

        bug_prompt = (
            f"Generate a detailed bug report:\n"
            f"Steps taken: {steps}\n"
            f"Error context: {error_context}\n"
            f"Analyze the screenshot and provide:\n"
            f"1. Bug title\n2. Severity (critical/high/medium/low)\n"
            f"3. Steps to reproduce\n4. Expected vs Actual result\n"
            f"Respond in JSON with keys: 'title', 'severity', "
            f"'steps_to_reproduce', 'expected', 'actual'."
        )

        try:
            response = await client.chat.completions.create(
                model=self.pro_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": bug_prompt},
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
            )
            raw_response = response.choices[0].message.content
        except Exception:
            raw_response = '{"title": "Error generating report", "severity": "unknown", "steps_to_reproduce": "unknown", "expected": "unknown", "actual": "unknown"}'

        logger.info("🐛 تم إنشاء تقرير خطأ عبر DeepSeek.")
        return {"raw_response": raw_response, "source": "deepseek_report"}
