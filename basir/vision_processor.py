"""Vision Processor module - Gemini 3.1 multimodal vision analysis.

This module provides the VisionProcessor class for analyzing screenshots
using Gemini 3.1 Flash (real-time/streaming) and Gemini 3.1 Pro
(deep reasoning and bug report synthesis).

Authentication Flow:
    ┌─────────────────────────────────────────────────────────┐
    │  1. VisionProcessor.__init__() يستقبل مسار ملف JSON    │
    │     الخاص بـ Service Account.                          │
    │                                                         │
    │  2. _authenticate() يقرأ الملف ويحوّله إلى              │
    │     google.oauth2.service_account.Credentials.           │
    │                                                         │
    │  3. يُنشئ google.genai.Client باستخدام الـ Credentials  │
    │     مع تحديد project_id و location.                     │
    │                                                         │
    │  4. الـ Client جاهز لاستدعاء Gemini Flash / Pro APIs.   │
    └─────────────────────────────────────────────────────────┘

Supports Live Streaming for low-latency, real-time UI monitoring
instead of single-image batch processing.

Typical usage example:

    processor = VisionProcessor(config={
        "project_id": "my-project",
        "service_account_key": "configs/service-account.json"
    })
    analysis = await processor.analyze_screenshot(screenshot_bytes, context="Login page")

    # أو استخدام الـ Live Session
    session = await processor.start_live_session()
    await session.send_frame(screenshot_bytes)
    result = await session.receive_analysis()
    await session.close()
"""

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class LiveSession:
    """جلسة بث مباشر مع Gemini Flash Live API.

    تسمح بإرسال إطارات (frames/screenshots) متتالية والحصول
    على تحليل فوري بزمن انتقال منخفض (Low Latency) عبر اتصال
    مستمر بدلاً من إرسال طلبات منفصلة لكل صورة.

    هذا هو جوهر "Gemini Live" — الوكيل يراقب الشاشة وهي
    بتتحرك ويتفاعل معها في الوقت الحقيقي.

    Attributes:
        _session: كائن الجلسة من Google GenAI Live API.
        _is_active: حالة الجلسة (نشطة أم لا).
    """

    def __init__(self, session) -> None:
        """تهيئة جلسة البث المباشر.

        Args:
            session: كائن الجلسة من Google GenAI SDK
                     (الناتج من client.aio.live.connect).
        """
        self._session = session
        self._is_active = True

    async def send_frame(self, frame_data: bytes) -> None:
        """إرسال إطار (screenshot) إلى Gemini للتحليل الفوري.

        Args:
            frame_data: بيانات الصورة بصيغة PNG.

        Raises:
            RuntimeError: إذا كانت الجلسة غير نشطة.
        """
        if not self._is_active:
            raise RuntimeError("الجلسة غير نشطة. قم بإنشاء جلسة جديدة.")

        encoded = base64.b64encode(frame_data).decode("utf-8")
        await self._session.send(
            input={"mime_type": "image/png", "data": encoded},
            end_of_turn=True
        )
        logger.debug("تم إرسال إطار للتحليل الفوري.")

    async def receive_analysis(self) -> dict:
        """استقبال نتيجة التحليل من Gemini.

        Returns:
            dict: نتيجة التحليل تشمل:
                - raw_response: النص الخام من Gemini.
                - source: مصدر التحليل ("flash_live").
        """
        response_text = ""
        async for chunk in self._session.receive():
            if hasattr(chunk, "text"):
                response_text += chunk.text

        logger.debug(f"تحليل فوري: {response_text[:100]}...")
        return {"raw_response": response_text, "source": "flash_live"}

    async def close(self) -> None:
        """إغلاق جلسة البث المباشر وتحرير الموارد."""
        self._is_active = False
        await self._session.close()
        logger.info("تم إغلاق جلسة البث المباشر.")


class VisionProcessor:
    """معالج الرؤية البصرية باستخدام Gemini + Google AI Studio.

    يوفر ثلاث واجهات:
    1. تحليل ثابت (Static): إرسال صورة واحدة → تحليل (Flash).
    2. بث مباشر (Live Streaming): اتصال مستمر → تحليل فوري (Flash Live API).
    3. تحليل عميق (Deep Analysis): Gemini Pro → تقارير الأخطاء المفصّلة.

    Authentication:
        يستخدم Google AI Studio API Key (مجاني).
        تسلسل البحث عن المفتاح:
        1. متغير البيئة GOOGLE_API_KEY
        2. config["api_key"]
        3. ملف .env (عبر python-dotenv)

    Attributes:
        config: إعدادات المعالج.
        flash_model: اسم نموذج Gemini Flash.
        pro_model: اسم نموذج Gemini Pro.
        _client: عميل Google GenAI.
        _api_key: مفتاح API.
    """

    DEFAULT_FLASH_MODEL = "gemini-2.0-flash"
    DEFAULT_PRO_MODEL = "gemini-2.0-flash"

    # الـ System Prompt الرئيسي لتوجيه Gemini أثناء التحليل
    VISION_SYSTEM_PROMPT = (
        "You are a visual QA testing agent. When receiving a webpage screenshot:\n"
        "1. Identify ALL visible interactive elements (buttons, input fields, links).\n"
        "2. Provide coordinates of each element as (x, y) in range 0-1000.\n"
        "3. Suggest the next action based on the given context.\n"
        "4. Report any visual issues or obvious bugs.\n"
        "Respond in JSON format ONLY with keys: "
        "'elements', 'suggested_action', 'issues'."
    )

    def __init__(self, config: Optional[dict] = None) -> None:
        """تهيئة معالج الرؤية مع Google AI Studio API Key.

        تسلسل البحث عن المفتاح:
        1. متغير البيئة GOOGLE_API_KEY
        2. config["api_key"]
        3. ملف .env (عبر python-dotenv)

        Args:
            config: إعدادات اختيارية تشمل:
                - api_key: مفتاح Google AI Studio.
                - flash_model: اسم نموذج Flash.
                - pro_model: اسم نموذج Pro.

        Raises:
            ValueError: إذا لم يُعثر على API Key.
        """
        self.config = config or {}
        self.flash_model = self.config.get("flash_model", self.DEFAULT_FLASH_MODEL)
        self.pro_model = self.config.get("pro_model", self.DEFAULT_PRO_MODEL)

        self._api_key = None
        self._client = None

        # البحث عن API Key
        self._resolve_api_key()

        logger.info(
            f"✅ تم تهيئة VisionProcessor بنجاح | "
            f"Flash={self.flash_model} | Pro={self.pro_model}"
        )

    def _resolve_api_key(self):
        """البحث عن API Key من مصادر متعددة.

        تسلسل البحث:
        1. متغير البيئة GOOGLE_API_KEY
        2. config["api_key"]
        3. ملف .env (عبر python-dotenv)

        Raises:
            ValueError: إذا لم يُعثر على المفتاح.
        """
        # 1. متغير البيئة
        self._api_key = os.environ.get("GOOGLE_API_KEY")
        if self._api_key:
            logger.info("🔑 API Key من متغير البيئة GOOGLE_API_KEY")
            return

        # 2. من الإعدادات
        self._api_key = self.config.get("api_key")
        if self._api_key:
            logger.info("🔑 API Key من الإعدادات (config)")
            return

        # 3. من ملف .env
        try:
            from dotenv import load_dotenv
            load_dotenv()
            self._api_key = os.environ.get("GOOGLE_API_KEY")
            if self._api_key:
                logger.info("🔑 API Key من ملف .env")
                return
        except ImportError:
            logger.warning("⚠️ python-dotenv غير مثبّت — تخطّي .env")

        raise ValueError(
            "❌ لم يُعثر على API Key!\n"
            "الحلول:\n"
            "1. أنشئ ملف .env مع GOOGLE_API_KEY=your_key\n"
            "2. أو عيّن متغير البيئة GOOGLE_API_KEY\n"
            "3. أو أضف api_key في config\n"
            "احصل على مفتاح مجاني من: https://aistudio.google.com/apikey"
        )

    def _get_client(self):
        """إنشاء أو إرجاع عميل Google GenAI (Lazy Initialization).

        يستخدم API Key للمصادقة مع Google AI Studio.

        Returns:
            google.genai.Client: عميل GenAI جاهز.
        """
        if self._client is None:
            from google import genai

            self._client = genai.Client(
                api_key=self._api_key,
            )

        return self._client

    def _optimize_screenshot(self, screenshot: bytes, max_width: int = 1024, quality: int = 70) -> bytes:
        """تحسين لقطة الشاشة لتقليل حجم الـ Payload المرسل لـ Gemini.

        يقلل الدقة إلى max_width بكسل مع الحفاظ على النسبة،
        ويحول الصورة لـ JPEG بجودة محددة.
        
        هذا يقلل الحجم من ~2MB (PNG) لحوالي ~100KB (JPEG)
        مما يسرع وقت الرفع ويقلل أخطاء 503.

        Args:
            screenshot: بيانات الصورة الأصلية (PNG bytes).
            max_width: الحد الأقصى للعرض بالبكسل.
            quality: جودة JPEG (0-100).

        Returns:
            bytes: الصورة المحسنة بصيغة JPEG.
        """
        import io
        from PIL import Image
        
        img = Image.open(io.BytesIO(screenshot))
        
        # تقليل الدقة مع الحفاظ على النسبة
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # تحويل لـ RGB (JPEG لا يدعم الشفافية)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # حفظ كـ JPEG مضغوط
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        
        optimized = buffer.getvalue()
        logger.debug(
            f"📦 Screenshot optimized: {len(screenshot)//1024}KB → {len(optimized)//1024}KB "
            f"({img.width}x{img.height})"
        )
        return optimized

    async def analyze_screenshot(
        self, screenshot: bytes, context: str = ""
    ) -> dict:
        """تحليل لقطة شاشة واحدة باستخدام Gemini Flash.

        يُرسل الصورة مع System Prompt وسياق إضافي، ويستقبل
        تحليلاً يتضمن العناصر المكتشفة والإجراء المقترح.

        Args:
            screenshot: بيانات الصورة بصيغة PNG (bytes).
            context: سياق إضافي يوجه Gemini
                     (مثال: "صفحة تسجيل الدخول، ابحث عن زر Submit").

        Returns:
            dict: نتيجة التحليل:
                - raw_response: النص الخام من Gemini.
                - source: "flash_static".
        """
        client = self._get_client()
        
        # تحسين الصورة قبل الإرسال (تقليل الحجم بنسبة 80%)
        optimized = self._optimize_screenshot(screenshot)
        encoded = base64.b64encode(optimized).decode("utf-8")

        prompt = f"{self.VISION_SYSTEM_PROMPT}\n\nContext: {context}"

        from google.genai import types
        
        # إعداد الـ GenerateContentConfig مع ThinkingConfig
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level="HIGH",
            )
        )

        response = await client.aio.models.generate_content(
            model=self.flash_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=optimized, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt)
                    ]
                )
            ],
            config=config
        )

        logger.info("📸 تم تحليل لقطة الشاشة عبر Gemini (Thinking Enabled).")
        return {"raw_response": response.text, "source": "gemini_3_flash"}

    async def get_element_coordinates(
        self, screenshot: bytes, element_description: str
    ) -> Tuple[float, float]:
        """الحصول على إحداثيات عنصر محدد في لقطة الشاشة عبر Gemini Flash.

        يُرسل لقطة الشاشة مع وصف العنصر المطلوب، ويطلب من
        Gemini إرجاع الإحداثيات المعيارية [y, x] في نطاق 0-1000.

        هذه الدالة هي الجسر بين "الرؤية" (VisionProcessor)
        و"التنفيذ" (BrowserController.click_at_normalized).

        Args:
            screenshot: بيانات لقطة الشاشة بصيغة PNG.
            element_description: وصف نصي للعنصر المطلوب
                (مثال: "Username input field", "Login button").

        Returns:
            Tuple[float, float]: (norm_x, norm_y) إحداثيات العنصر
                في نطاق 0-1000، جاهزة للاستخدام مع CoordinateMapper.

        Raises:
            ValueError: إذا لم يتمكن Gemini من تحديد موقع العنصر.

        Example:
            >>> x, y = await processor.get_element_coordinates(
            ...     screenshot, "Username input field"
            ... )
            >>> await browser.click_at_normalized(x, y)
        """
        client = self._get_client()
        
        # تحسين الصورة قبل الإرسال
        optimized = self._optimize_screenshot(screenshot)
        encoded = base64.b64encode(optimized).decode("utf-8")

        # Prompt مُحسّن لاستخراج إحداثيات دقيقة
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

        from google.genai import types
        
        # إعداد الـ GenerateContentConfig مع ThinkingConfig
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level="HIGH",
            )
        )

        response = await client.aio.models.generate_content(
            model=self.flash_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=optimized, mime_type="image/jpeg"),
                        types.Part.from_text(text=coord_prompt)
                    ]
                )
            ],
            config=config
        )

        raw_text = response.text.strip()
        logger.info(f"🎯 Gemini response for '{element_description}': {raw_text}")

        # استخراج الإحداثيات من الرد
        norm_x, norm_y = self._parse_coordinates(raw_text, element_description)

        logger.info(
            f"📍 إحداثيات '{element_description}': "
            f"x={norm_x}, y={norm_y} (normalized 0-1000)"
        )
        return norm_x, norm_y

    def _parse_coordinates(
        self, response_text: str, element_description: str
    ) -> Tuple[float, float]:
        """استخراج الإحداثيات من نص رد Gemini.

        يحاول الاستخراج بعدة طرق:
        1. JSON مباشر.
        2. JSON مضمّن في نص.
        3. أرقام من نمط [y, x] عبر regex.

        Args:
            response_text: النص الخام من Gemini.
            element_description: وصف العنصر (للرسائل الخطأ).

        Returns:
            Tuple[float, float]: (x, y) الإحداثيات المعيارية.

        Raises:
            ValueError: إذا فشل الاستخراج.
        """
        # محاولة 1: JSON مباشر
        try:
            # إزالة markdown code fences إن وجدت
            clean = response_text.strip()
            if clean.startswith("```"):
                clean = re.sub(r"```\w*\n?", "", clean).strip()

            data = json.loads(clean)

            if "error" in data:
                raise ValueError(
                    f"Gemini لم يجد العنصر '{element_description}': {data['error']}"
                )

            y = float(data.get("y", 0))
            x = float(data.get("x", 0))
            return x, y
        except (json.JSONDecodeError, TypeError):
            pass

        # محاولة 2: استخراج JSON مضمّن في نص
        json_match = re.search(r'\{[^}]*"y"\s*:\s*(\d+)[^}]*"x"\s*:\s*(\d+)[^}]*\}', response_text)
        if json_match:
            y = float(json_match.group(1))
            x = float(json_match.group(2))
            return x, y

        # محاولة 2b: ترتيب x قبل y
        json_match2 = re.search(r'\{[^}]*"x"\s*:\s*(\d+)[^}]*"y"\s*:\s*(\d+)[^}]*\}', response_text)
        if json_match2:
            x = float(json_match2.group(1))
            y = float(json_match2.group(2))
            return x, y

        # محاولة 3: أي أرقام في نمط [num, num]
        nums = re.findall(r'\d+', response_text)
        if len(nums) >= 2:
            y = float(nums[0])
            x = float(nums[1])
            logger.warning(
                f"⚠️ استخراج إحداثيات بـ regex fallback: x={x}, y={y}"
            )
            return x, y

        raise ValueError(
            f"❌ فشل استخراج إحداثيات '{element_description}' "
            f"من رد Gemini: {response_text[:200]}"
        )

    async def start_live_session(self) -> LiveSession:
        """بدء جلسة بث مباشر مع Gemini Flash Live API.

        يفتح اتصال WebSocket مستمر مع Gemini Flash لتحليل
        الشاشة بزمن انتقال منخفض — هذا هو جوهر "Gemini Live".

        بدلاً من إرسال طلب لكل صورة، الوكيل يفتح "قناة"
        ويبث الإطارات المتتالية ويستقبل التحليل فورياً.

        Returns:
            LiveSession: كائن الجلسة لإرسال الإطارات واستقبال التحليل.
        """
        client = self._get_client()
        from google.genai import types

        live_config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            system_instruction=types.Content(
                parts=[types.Part(text=self.VISION_SYSTEM_PROMPT)]
            )
        )

        session = await client.aio.live.connect(
            model=self.flash_model,
            config=live_config
        )

        logger.info("🔴 تم بدء جلسة البث المباشر (Live Session) مع Gemini.")
        return LiveSession(session)

    async def analyze_for_recovery(self, screenshot: bytes) -> dict:
        """تحليل شاشة لأغراض التعافي الذاتي باستخدام Gemini Pro.

        يستخدم النموذج الأقوى (Pro) لفهم حالة الصفحة بعد
        حدوث خطأ واقتراح خطوة تعافي ذكية.

        Args:
            screenshot: بيانات لقطة الشاشة بصيغة PNG.

        Returns:
            dict: اقتراح التعافي:
                - raw_response: تحليل Pro الخام.
                - source: "pro_recovery".
        """
        client = self._get_client()
        encoded = base64.b64encode(screenshot).decode("utf-8")

        recovery_prompt = (
            "An error occurred while testing this page. Analyze the current screen:\n"
            "1. What is the current state of the page?\n"
            "2. What is the likely cause of the error?\n"
            "3. What is the next recovery step?\n"
            "Respond in JSON with keys: 'page_state', 'error_cause', 'recovery_action'."
        )

        response = await client.aio.models.generate_content(
            model=self.pro_model,
            contents=[
                {"inline_data": {"mime_type": "image/png", "data": encoded}},
                recovery_prompt
            ]
        )

        logger.info("🔄 تم تحليل التعافي عبر Gemini Pro.")
        return {"raw_response": response.text, "source": "pro_recovery"}

    async def generate_bug_report(
        self, screenshot: bytes, steps: list, error_context: str
    ) -> dict:
        """إنشاء تقرير خطأ مفصّل باستخدام Gemini Pro.

        يجمع لقطة الشاشة مع خطوات إعادة الإنتاج والسياق
        لإنشاء تقرير خطأ شامل وقابل للتنفيذ.

        Args:
            screenshot: لقطة شاشة الخطأ بصيغة PNG.
            steps: قائمة الخطوات التي أدت إلى الخطأ.
            error_context: وصف سياق الخطأ.

        Returns:
            dict: تقرير الخطأ:
                - raw_response: التقرير المفصّل من Pro.
                - source: "pro_bug_report".
        """
        client = self._get_client()
        encoded = base64.b64encode(screenshot).decode("utf-8")

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

        response = await client.aio.models.generate_content(
            model=self.pro_model,
            contents=[
                {"inline_data": {"mime_type": "image/png", "data": encoded}},
                bug_prompt
            ]
        )

        logger.info("🐛 تم إنشاء تقرير خطأ عبر Gemini Pro.")
        return {"raw_response": response.text, "source": "pro_bug_report"}
