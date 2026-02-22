"""Login Test Command - MVP test for login flow validation.

This module provides the LoginTestCommand which tests a standard
login flow on a web page using Gemini Vision for element detection:
    find form → enter credentials → click submit → verify success.

This is the first concrete implementation of the Command Pattern
and serves as the MVP for the Gemini Live Agent Challenge.

Flow:
    ┌─────────────────────────────────────────────────────┐
    │  1. Screenshot → VisionProcessor.get_element_coords │
    │  2. Gemini returns normalized (x, y) in 0-1000     │
    │  3. BrowserController.click_at_normalized(x, y)    │
    │  4. CoordinateMapper → pixel click → Playwright    │
    │  5. Repeat for each step until login complete       │
    └─────────────────────────────────────────────────────┘

Typical usage example:

    cmd = LoginTestCommand(
        username="tomsmith",
        password="SuperSecretPassword!"
    )
    agent = Agent(config=config)
    results = await agent.run(
        target_url="https://the-internet.herokuapp.com/login",
        test_command=cmd
    )
"""

import logging
from typing import Any

from basir.commands.base_command import BaseTestCommand

logger = logging.getLogger(__name__)


class LoginTestCommand(BaseTestCommand):
    """أمر اختبار تسجيل الدخول (MVP) باستخدام Gemini Vision.

    يختبر تدفق تسجيل الدخول بتحديد المواقع عبر Gemini:
    1. التقاط شاشة + سؤال Gemini عن إحداثيات حقل Username.
    2. النقر على الحقل وإدخال اسم المستخدم.
    3. سؤال Gemini عن إحداثيات حقل Password.
    4. النقر على الحقل وإدخال كلمة المرور.
    5. سؤال Gemini عن إحداثيات زر Login.
    6. النقر على الزر والتحقق من النجاح.

    Attributes:
        username: اسم المستخدم للاختبار.
        password: كلمة المرور للاختبار.
    """

    STEPS = [
        "find_and_fill_username",
        "find_and_fill_password",
        "find_and_click_submit",
        "verify_success",
    ]

    def __init__(self, username: str, password: str) -> None:
        """تهيئة أمر اختبار تسجيل الدخول.

        Args:
            username: اسم المستخدم للاختبار.
            password: كلمة المرور للاختبار.
        """
        super().__init__(
            name="LoginTest",
            description="اختبار تدفق تسجيل الدخول باستخدام Gemini Vision."
        )
        self.username = username
        self.password = password

    def get_context(self) -> str:
        """الحصول على سياق الخطوة الحالية لتوجيه Gemini.

        Returns:
            str: توجيه لـ Gemini بناءً على الخطوة الحالية.
        """
        step_contexts = {
            "find_and_fill_username": (
                "Login page. Find the Username input field. "
                "Return its center coordinates."
            ),
            "find_and_fill_password": (
                "Username entered. Find the Password input field. "
                "Return its center coordinates."
            ),
            "find_and_click_submit": (
                "Credentials entered. Find the Login/Submit button. "
                "Return its center coordinates."
            ),
            "verify_success": (
                "Login button clicked. Check if login was successful. "
                "Look for success indicators (Secure Area, Welcome, Logout)."
            ),
        }

        current_step_name = self._get_current_step_name()
        return step_contexts.get(current_step_name, "Check page state.")

    async def execute_step(self, agent: Any, analysis: dict) -> dict:
        """تنفيذ الخطوة الحالية من سيناريو تسجيل الدخول.

        كل خطوة تستخدم VisionProcessor.get_element_coordinates()
        للحصول على إحداثيات العنصر، ثم BrowserController
        للنقر والكتابة.

        Args:
            agent: مثيل Agent للوصول إلى المتصفح والرؤية.
            analysis: تحليل Gemini للشاشة الحالية (غير مستخدم
                      هنا لأننا نستدعي get_element_coordinates مباشرة).

        Returns:
            dict: نتيجة الخطوة تشمل step_number, action, success, details.
        """
        step_name = self._get_current_step_name()
        step_number = self._mark_step()

        logger.info(f"🔄 تنفيذ خطوة {step_number}/{len(self.STEPS)}: {step_name}")

        result = {
            "step_number": step_number,
            "step_name": step_name,
            "action": "",
            "success": False,
            "details": "",
        }

        try:
            if step_name == "find_and_fill_username":
                result = await self._find_and_fill_username(agent, result)

            elif step_name == "find_and_fill_password":
                result = await self._find_and_fill_password(agent, result)

            elif step_name == "find_and_click_submit":
                result = await self._find_and_click_submit(agent, result)

            elif step_name == "verify_success":
                result = await self._verify_success(agent, result)
                if result["success"]:
                    self._mark_complete()

        except Exception as e:
            result["success"] = False
            result["details"] = f"خطأ: {str(e)}"
            logger.error(f"❌ فشل في خطوة {step_name}: {e}")

        return result

    def _get_current_step_name(self) -> str:
        """الحصول على اسم الخطوة الحالية.

        Returns:
            str: اسم الخطوة أو "complete" إذا انتهت جميع الخطوات.
        """
        if self._current_step < len(self.STEPS):
            return self.STEPS[self._current_step]
        return "complete"

    async def _find_and_fill_username(
        self, agent: Any, result: dict
    ) -> dict:
        """اكتشاف حقل Username عبر Gemini والنقر عليه وكتابة اسم المستخدم.

        Flow:
            Screenshot → get_element_coordinates("Username input") →
            click_at_normalized(x, y) → type_text(username)

        Args:
            agent: مثيل Agent.
            result: قاموس النتيجة لتحديثه.

        Returns:
            dict: النتيجة المحدّثة.
        """
        # التقاط لقطة شاشة
        screenshot = await agent.browser.take_screenshot()

        # سؤال Gemini عن إحداثيات حقل اسم المستخدم
        norm_x, norm_y = await agent.vision.get_element_coordinates(
            screenshot, "Username input field"
        )

        # النقر على الحقل
        await agent.browser.click_at_normalized(norm_x, norm_y)

        # كتابة اسم المستخدم
        await agent.browser.type_text(self.username)

        result["action"] = "اكتشاف حقل Username والنقر والكتابة"
        result["success"] = True
        result["details"] = (
            f"تم: Gemini أعطى ({norm_x:.0f}, {norm_y:.0f}) → "
            f"كتابة '{self.username}'"
        )
        return result

    async def _find_and_fill_password(
        self, agent: Any, result: dict
    ) -> dict:
        """اكتشاف حقل Password عبر Gemini والنقر عليه وكتابة كلمة المرور.

        Args:
            agent: مثيل Agent.
            result: قاموس النتيجة.

        Returns:
            dict: النتيجة المحدّثة.
        """
        screenshot = await agent.browser.take_screenshot()

        norm_x, norm_y = await agent.vision.get_element_coordinates(
            screenshot, "Password input field"
        )

        await agent.browser.click_at_normalized(norm_x, norm_y)
        await agent.browser.type_text(self.password)

        result["action"] = "اكتشاف حقل Password والنقر والكتابة"
        result["success"] = True
        result["details"] = (
            f"تم: Gemini أعطى ({norm_x:.0f}, {norm_y:.0f}) → "
            f"كتابة كلمة المرور"
        )
        return result

    async def _find_and_click_submit(
        self, agent: Any, result: dict
    ) -> dict:
        """اكتشاف زر Login عبر Gemini والنقر عليه.

        Args:
            agent: مثيل Agent.
            result: قاموس النتيجة.

        Returns:
            dict: النتيجة المحدّثة.
        """
        screenshot = await agent.browser.take_screenshot()

        norm_x, norm_y = await agent.vision.get_element_coordinates(
            screenshot, "Login button"
        )

        await agent.browser.click_at_normalized(norm_x, norm_y)

        # انتظار استقرار الصفحة بعد النقر
        await agent.browser.wait_for_stable_state()

        result["action"] = "اكتشاف زر Login والنقر"
        result["success"] = True
        result["details"] = f"تم: Gemini أعطى ({norm_x:.0f}, {norm_y:.0f}) → نقر"
        return result

    async def _verify_success(
        self, agent: Any, result: dict
    ) -> dict:
        """التحقق من نجاح تسجيل الدخول عبر تحليل Gemini للشاشة.

        Args:
            agent: مثيل Agent.
            result: قاموس النتيجة.

        Returns:
            dict: النتيجة المحدّثة.
        """
        screenshot = await agent.browser.take_screenshot()

        # تحليل الشاشة بالكامل للتحقق من النجاح
        analysis = await agent.vision.analyze_screenshot(
            screenshot,
            context=(
                "Check if login was successful. "
                "Look for: 'Secure Area', 'Welcome', 'Logout' button, "
                "or success messages. "
                "Respond with JSON: {\"login_success\": true/false, \"evidence\": \"...\"}"
            )
        )

        raw = analysis.get("raw_response", "").lower()

        # التحقق من وجود مؤشرات نجاح
        success_indicators = ["secure area", "welcome", "logout", "success", "true"]
        is_success = any(indicator in raw for indicator in success_indicators)

        result["action"] = "التحقق من نجاح تسجيل الدخول"
        result["success"] = is_success
        result["details"] = (
            f"{'✅ نجح' if is_success else '❌ فشل'} تسجيل الدخول | "
            f"Gemini: {analysis.get('raw_response', 'N/A')[:100]}"
        )
        return result
