import base64
import json
import logging
import os
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class GroqProcessor:
    """Vision Processor using Groq API for ultra-fast inference.
    
    Uses llama-3.2-90b-vision-preview for blazing fast visual analysis.
    """
    
    VISION_SYSTEM_PROMPT = (
        "You are an expert Autonomous QA Testing Agent named Basir. "
        "Your task is to analyze screenshots of web pages and determine "
        "the current state and necessary actions to achieve a specific goal.\n"
        "Return your analysis in a clear, actionable format."
    )

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or {}
        
        # تحميل اسم الموديل من config
        groq_models = self.config.get("groq_models", {})
        self.flash_model = groq_models.get("flash", "meta-llama/llama-4-scout-17b-16e-instruct")
        self.pro_model = groq_models.get("pro", "meta-llama/llama-4-scout-17b-16e-instruct")
        
        # استخراج API Key
        self._api_key = os.getenv("GROQ_API_KEY")
        if not self._api_key:
            raise ValueError("❌ لم يُعثر على GROQ_API_KEY!")
            
        self._client = None
        logger.info("تم تهيئة GroqProcessor بنجاح (LPU Speed).")

    def _get_client(self):
        if self._client is None:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self._api_key)
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
            response_format={"type": "json_object"},
        )
        
        logger.info("⚡ تم تحليل لقطة الشاشة عبر Groq بسرعة البرق.")
        return {"raw_response": response.choices[0].message.content, "source": "groq"}

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
            max_tokens=64,
            temperature=0.0,
        )
        
        raw_text = response.choices[0].message.content.strip()
        logger.info(f"🎯 Groq response for '{element_description}': {raw_text}")
        
        norm_x, norm_y = self._parse_coordinates(raw_text, element_description)
        logger.info(f"📍 إحداثيات '{element_description}': x={norm_x}, y={norm_y} (normalized 0-1000)")
        return norm_x, norm_y

    def _parse_coordinates(self, text: str, element_description: str) -> Tuple[float, float]:
        try:
            # استخراج كود JSON من الرد باستخدام Regex (لأن LLMs قد تضيف نصوص حول كود JSON)
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
            else:
                data = json.loads(text)
                
            if "error" in data:
                raise ValueError(f"العنصر '{element_description}' لم يُعثر عليه: {data['error']}")
                
            if "x" not in data or "y" not in data:
                raise ValueError("الإحداثيات غير مكتملة في استجابة Groq.")
                
            y = float(data["y"])
            x = float(data["x"])
            return x, y
        except json.JSONDecodeError as e:
            logger.error(f"❌ فشل تحليل إحداثيات Groq: {text}")
            raise ValueError(f"فشل تحليل الـ JSON لإحداثيات '{element_description}': {e}") from e

    async def analyze_for_recovery(self, screenshot: bytes) -> dict:
        """تحليل شاشة لأغراض التعافي الذاتي باستخدام نموذج Groq Pro.

        Args:
            screenshot: بيانات لقطة الشاشة بصيغة PNG.

        Returns:
            dict: اقتراح التعافي:
                - raw_response: التحليل الخام.
                - source: "pro_recovery".
        """
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

        logger.info("🔄 تم تحليل التعافي عبر Groq.")
        return {"raw_response": response.choices[0].message.content, "source": "pro_recovery"}
