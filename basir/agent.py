"""Agent module - The main orchestrator for the Basir QA Testing Agent.

This module contains the Agent class which coordinates all components
(BrowserController, VisionProcessor, Reporter) using Google ADK.
It implements Self-Healing logic and supports two modes:

1. Scripted Testing: Execute predefined test commands (LoginTestCommand).
2. Autonomous Testing: Achieve natural language goals via ReAct pattern.

Typical usage example:

    agent = Agent(config=config)

    # Mode 1: Scripted
    await agent.run(target_url="https://example.com", test_command=LoginTestCommand())

    # Mode 2: Autonomous (ReAct)
    await agent.plan_and_execute(
        target_url="https://example.com",
        goal="Find the login page and sign in with test credentials"
    )
"""

import logging
from pathlib import Path
from typing import Optional

from basir.browser_controller import BrowserController
from basir.vision_processor import VisionProcessor
from basir.groq_processor import GroqProcessor
from basir.deepseek_processor import DeepSeekProcessor
from basir.ollama_processor import OllamaProcessor
from basir.reporter import Reporter

logger = logging.getLogger(__name__)


class Agent:
    """المنسق الرئيسي لوكيل ضمان الجودة (Orchestrator).

    يربط بين جميع المكونات ويدير حلقة التنفيذ الأساسية:
    التقاط الشاشة -> التحليل البصري -> اتخاذ الإجراء -> التحقق -> التكرار.
    يتضمن منطق التعافي الذاتي (Self-Healing) للتعامل مع الأخطاء.

    Attributes:
        browser: مثيل BrowserController للتحكم في المتصفح.
        vision: مثيل VisionProcessor للتحليل البصري.
        reporter: مثيل Reporter لإنشاء التقارير.
        max_retries: الحد الأقصى لمحاولات التعافي الذاتي.
        config: إعدادات الوكيل.
    """

    DEFAULT_MAX_RETRIES = 3

    def __init__(self, config: Optional[dict] = None) -> None:
        """تهيئة الوكيل بجميع مكوناته.

        Args:
            config: قاموس إعدادات اختياري يحتوي على مفاتيح API
                    وإعدادات المتصفح وغيرها.
        """
        self.config = config or {}
        self.max_retries = self.config.get("max_retries", self.DEFAULT_MAX_RETRIES)

        self.browser = BrowserController(config=self.config.get("browser", {}))
        
        provider = self.config.get("api", {}).get("provider", "google_ai")
        if provider == "groq":
            self.vision = GroqProcessor(config=self.config)
            self.is_fast_api = True
            logger.info("تم اختيار Groq كـ AI Provider.")
        elif provider == "deepseek":
            self.vision = DeepSeekProcessor(config=self.config)
            self.is_fast_api = True
            logger.info("تم اختيار DeepSeek كـ AI Provider.")
        elif provider == "ollama":
            self.vision = OllamaProcessor(config=self.config)
            self.is_fast_api = True
            logger.info("تم اختيار Ollama (محلي) كـ AI Provider.")
        else:
            self.vision = VisionProcessor(config=self.config.get("vision", {}))
            self.is_fast_api = False
            logger.info("تم اختيار Google AI كـ AI Provider.")
            
        self.reporter = Reporter(config=self.config.get("reporter", {}))
        
        # حالة ذكاء الاصطناعي لإظهار الـ Overlay
        self.is_thinking = False

        logger.info("تم تهيئة الوكيل Basir بنجاح.")

    async def run(self, target_url: str, test_command) -> dict:
        """تشغيل حلقة الاختبار الرئيسية على URL محدد.

        Args:
            target_url: عنوان URL المراد اختباره.
            test_command: مثيل BaseTestCommand يحدد نوع الاختبار.

        Returns:
            dict: نتائج الاختبار النهائية مع حالة النجاح/الفشل.

        Raises:
            RuntimeError: إذا فشلت جميع محاولات التعافي الذاتي.
        """
        logger.info(f"بدء الاختبار على: {target_url}")
        results = {"url": target_url, "status": "pending", "steps": [], "bugs": []}

        # إعداد مجلد حفظ لقطات الشاشة
        screenshots_dir = Path("reports/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        def _stream_callback(frame_bytes: bytes):
            import io, os
            from PIL import Image, ImageDraw
            try:
                img = Image.open(io.BytesIO(frame_bytes))
                # تقليل الدقة إلى 720p 
                img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
                
                os.makedirs("reports/live", exist_ok=True)
                temp_path = "reports/live/frame_tmp.jpg"
                final_path = "reports/live/frame.jpg"
                img.save(temp_path, "JPEG", quality=50)
                os.replace(temp_path, final_path)
            except Exception:
                pass

        try:
            await self.browser.launch()
            print("\n✅ Browser launched (Stealth Mode)")
            await self.browser.start_streaming(_stream_callback)
            print(f"🌐 Navigating to: {target_url}")
            await self.browser.navigate(target_url)
            print("✅ Page loaded successfully")

            # حفظ أول لقطة بعد التحميل
            screenshot = await self.browser.take_screenshot()
            self._save_screenshot(screenshot, screenshots_dir, "00_initial")
            logger.info("📸 لقطة أولية محفوظة")

            # تنفيذ أمر الاختبار
            results = await self._execute_with_healing(test_command, results,
                                                       screenshots_dir)

        except Exception as e:
            logger.error(f"❌ خطأ حرج أثناء التنفيذ: {e}")
            results["status"] = "error"
            results["error"] = str(e)
            # محاولة حفظ لقطة الخطأ
            try:
                err_shot = await self.browser.take_screenshot()
                self._save_screenshot(err_shot, screenshots_dir, "error")
            except Exception:
                pass
        finally:
            await self.browser.stop_streaming()
            try:
                await self.browser.close()
            except Exception:
                pass

        # إنشاء التقرير النهائي
        report = self.reporter.generate(results)
        logger.info(f"تم إنشاء التقرير: {report}")

        return results

    def _save_screenshot(self, data: bytes, dir_path: Path, name: str):
        """حفظ لقطة شاشة لملف PNG.

        Args:
            data: بيانات الصورة.
            dir_path: مجلد الحفظ.
            name: اسم الملف (بدون امتداد).
        """
        filepath = dir_path / f"{name}.png"
        with open(filepath, "wb") as f:
            f.write(data)
        logger.info(f"📸 Screenshot → {filepath}")

    async def _execute_with_healing(self, test_command, results: dict,
                                     screenshots_dir: Path = None) -> dict:
        """تنفيذ أمر الاختبار مع منطق التعافي الذاتي.

        إذا فشل الإجراء (مثلاً: العنصر اختفى، الصفحة علقت)،
        يقوم بإعادة تقييم الشاشة واتخاذ قرار جديد.

        Args:
            test_command: أمر الاختبار المراد تنفيذه.
            results: قاموس النتائج لتحديثه أثناء التنفيذ.
            screenshots_dir: مجلد حفظ لقطات الشاشة (اختياري).

        Returns:
            dict: النتائج المحدّثة.

        Raises:
            RuntimeError: إذا استنفد الوكيل جميع محاولات التعافي.
        """
        retries = 0
        step_num = 0

        while retries < self.max_retries:
            try:
                # التقاط الشاشة الحالية
                screenshot = await self.browser.take_screenshot()

                # استخراج ARIA tree للصفحة (نص خفيف على التوكنات)
                print("🌳 Getting ARIA snapshot...")
                aria_tree = await self.browser.get_aria_snapshot()
                print(f"   ARIA: {len(aria_tree)} chars")

                # تخزين ARIA tree في test_command عشان _think يستخدمه
                # بدل ما نعمل analyze_screenshot مرتين!
                self.is_thinking = True
                logger.info("🧠 THINKING_START: Analyzing screen and navigating logic...")
                test_command._aria_context = aria_tree if aria_tree and aria_tree != "(ARIA snapshot unavailable)" else ""
                analysis = {}  # execute_step هتعمل التحليل بنفسها في _think

                # تنفيذ الإجراء المقترح
                action_result = await test_command.execute_step(
                    agent=self,
                    analysis=analysis
                )
                self.is_thinking = False
                logger.info("✅ THINKING_END: Analysis complete")

                # انتظار استقرار الشاشة للصورة القادمة
                import asyncio
                delay = 0.5 if getattr(self, "is_fast_api", False) else 2.0
                await asyncio.sleep(delay)

                results["steps"].append(action_result)
                step_num += 1

                # حفظ لقطة بعد كل خطوة
                if screenshots_dir:
                    post_shot = await self.browser.take_screenshot()
                    self._save_screenshot(
                        post_shot, screenshots_dir, f"{step_num:02d}_step"
                    )

                if test_command.is_complete():
                    results["status"] = "passed"
                    logger.info("✅ تم إكمال الاختبار بنجاح.")
                    return results

            except Exception as step_error:
                retries += 1
                error_msg = str(step_error)
                logger.warning(
                    f"⚠️ خطأ في الخطوة (محاولة {retries}/{self.max_retries}): "
                    f"{error_msg}"
                )

                # انتظار إضافي عند 429 (rate limit)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    import asyncio
                    logger.info("⏳ انتظار 10 ثوانٍ بسبب rate limit...")
                    await asyncio.sleep(10)

                # محاولة التعافي: إعادة تقييم الشاشة
                await self._attempt_recovery()

        raise RuntimeError(
            f"فشل التعافي الذاتي بعد {self.max_retries} محاولات."
        )

    async def run_with_callback(
        self, target_url: str, test_command, callback=None
    ) -> dict:
        """تشغيل الاختبار مع بث تحديثات حية عبر callback.

        مصمم لواجهة Streamlit Dashboard — يُرسل لقطات الشاشة
        والأحداث (التفكير، الإجراء، النتيجة) بعد كل مرحلة
        من حلقة ReAct.

        callback يُستدعى بقاموس:
            {"type": "screenshot", "data": bytes}
            {"type": "thought", "data": str}
            {"type": "action", "data": str}
            {"type": "step_result", "data": dict}
            {"type": "status", "data": str}
            {"type": "error", "data": str}

        Args:
            target_url: عنوان URL المراد اختباره.
            test_command: أمر الاختبار.
            callback: دالة تُستدعى مع كل تحديث.
                      Signature: callback(event: dict) -> None

        Returns:
            dict: نتائج الاختبار النهائية.
        """
        def _emit(event_type: str, data):
            if callback:
                callback({"type": event_type, "data": data})

        logger.info(f"🖥️ بدء الاختبار مع بث مباشر على: {target_url}")
        results = {"url": target_url, "status": "pending", "steps": [], "bugs": []}

        try:
            _emit("status", "🚀 تشغيل المتصفح...")
            await self.browser.launch()

            _emit("status", f"🌐 الانتقال إلى {target_url}")
            await self.browser.navigate(target_url)

            # التقاط أول لقطة
            first_screenshot = await self.browser.take_screenshot()
            _emit("screenshot", first_screenshot)
            _emit("status", "✅ الصفحة جاهزة — بدء الاختبار")

            # حلقة التنفيذ مع بث
            retries = 0
            while retries < self.max_retries:
                try:
                    screenshot = await self.browser.take_screenshot()
                    _emit("screenshot", screenshot)

                    # استخراج ARIA tree
                    aria_tree = await self.browser.get_aria_snapshot()

                    _emit("status", "🔍 تحليل الشاشة...")
                    context = test_command.get_context()
                    if aria_tree and aria_tree != "(ARIA snapshot unavailable)":
                        context = f"{context}\n\n{aria_tree}"
                    analysis = await self.vision.analyze_screenshot(
                        screenshot=screenshot,
                        context=context
                    )

                    # بث التفكير إذا توفر
                    if hasattr(test_command, 'memory') and hasattr(test_command, '_think'):
                        _emit("thought", test_command.get_context())

                    _emit("status", "⚡ تنفيذ الإجراء...")
                    action_result = await test_command.execute_step(
                        agent=self, analysis=analysis
                    )

                    # انتظار استقرار الشاشة
                    import asyncio
                    delay = 0.5 if getattr(self, "is_fast_api", False) else 2.0
                    await asyncio.sleep(delay)

                    # بث النتيجة
                    _emit("step_result", action_result)
                    _emit("action", action_result.get("details", ""))

                    if action_result.get("thought"):
                        _emit("thought", action_result["thought"])

                    results["steps"].append(action_result)

                    # التقاط شاشة بعد الإجراء
                    post_screenshot = await self.browser.take_screenshot()
                    _emit("screenshot", post_screenshot)

                    if test_command.is_complete():
                        results["status"] = "passed"
                        _emit("status", "✅ تم إكمال الاختبار بنجاح!")
                        break

                except Exception as step_error:
                    retries += 1
                    _emit("error", f"⚠️ محاولة {retries}: {step_error}")
                    await self._attempt_recovery()

            if results["status"] == "pending":
                results["status"] = "failed"
                _emit("status", "❌ فشل الاختبار.")

        except Exception as e:
            results["status"] = "error"
            results["error"] = str(e)
            _emit("error", f"❌ خطأ حرج: {e}")
        finally:
            await self.browser.close()
            _emit("status", "🔒 تم إغلاق المتصفح.")

        report = self.reporter.generate(results)
        _emit("step_result", {"final_report": report})
        return results

    async def _attempt_recovery(self) -> None:
        """محاولة التعافي من خطأ أثناء التنفيذ.

        تشمل: انتظار تحميل الصفحة، التقاط شاشة جديدة،
        وإعادة تقييم الحالة عبر Gemini Pro.
        """
        logger.info("🔄 محاولة التعافي الذاتي...")

        # انتظار استقرار الصفحة
        await self.browser.wait_for_stable_state()

        # التقاط شاشة جديدة وإعادة التقييم
        screenshot = await self.browser.take_screenshot()
        self.is_thinking = True
        logger.info("🧠 THINKING_START: Analyzing recovery options...")
        recovery_analysis = await self.vision.analyze_for_recovery(screenshot)
        self.is_thinking = False
        logger.info("✅ THINKING_END: Recovery analysis complete")

        logger.info(f"نتيجة التعافي: {recovery_analysis.get('action', 'N/A')}")

    async def plan_and_execute(
        self, target_url: str, goal: str, max_steps: int = 15
    ) -> dict:
        """تشغيل وضع الاختبار الذاتي (ReAct Pattern).

        يقبل هدفاً بلغة طبيعية ويستخدم AutonomousCommand
        لتحقيقه ديناميكياً بدون سيناريو مسبق.

        في كل دورة، Gemini يقرر الخطوة التالية بناءً على:
        - لقطة الشاشة الحالية
        - الهدف المطلوب
        - تاريخ الإجراءات (Short-term Memory)

        Args:
            target_url: عنوان URL المراد اختباره.
            goal: الهدف بلغة طبيعية
                  (مثال: "Log in and verify the secure area page").
            max_steps: الحد الأقصى لعدد خطوات ReAct.

        Returns:
            dict: نتائج الاختبار النهائية.

        Example:
            >>> results = await agent.plan_and_execute(
            ...     target_url="https://the-internet.herokuapp.com/login",
            ...     goal="Log in with username 'tomsmith' and password 'SuperSecretPassword!'"
            ... )
        """
        from basir.commands.autonomous_command import AutonomousCommand

        logger.info("=" * 55)
        logger.info(f"🧠 وضع ReAct الذاتي")
        logger.info(f"🎯 الهدف: {goal}")
        logger.info(f"🌐 URL: {target_url}")
        logger.info(f"📊 الحد الأقصى: {max_steps} خطوة")
        logger.info("=" * 55)

        autonomous_cmd = AutonomousCommand(goal=goal, max_steps=max_steps)
        return await self.run(target_url=target_url, test_command=autonomous_cmd)

