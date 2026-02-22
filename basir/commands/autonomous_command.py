"""Autonomous Command module - ReAct (Reasoning + Acting) goal-based testing.

This module provides the AutonomousCommand which enables Basir to
autonomously achieve any natural language goal using the ReAct pattern:

    Observe → Think → Act → Verify → Repeat

Unlike LoginTestCommand (which follows fixed steps), AutonomousCommand
lets Gemini dynamically decide what to do next based on:
- The current screenshot (Observation)
- The goal description
- Action history (Short-term Memory)

This is the key differentiator for the Gemini Live Agent Challenge.

ReAct Loop Flow:
    ┌───────────────────────────────────────────────────────────┐
    │  1. OBSERVE: Take screenshot of current UI state          │
    │  2. THINK:   Send screenshot + goal + history → Gemini    │
    │              Gemini decides: next_action, element, done?  │
    │  3. ACT:     Execute the action via BrowserController     │
    │  4. VERIFY:  Check if goal is reached or obstacle found   │
    │  5. REPEAT:  Until goal reached or max_steps exhausted    │
    └───────────────────────────────────────────────────────────┘

Typical usage example:

    cmd = AutonomousCommand(
        goal="Log in with username 'tomsmith' and password 'SuperSecretPassword!'"
    )
    agent = Agent(config=config)
    results = await agent.run(
        target_url="https://the-internet.herokuapp.com/login",
        test_command=cmd
    )
"""

import logging
from typing import Any, Optional

from basir.commands.base_command import BaseTestCommand

logger = logging.getLogger(__name__)


class ActionMemory:
    """الذاكرة قصيرة المدى (Short-term Memory) للوكيل.

    تحتفظ بتاريخ الإجراءات المتخذة في الجلسة الحالية لمنع
    الحلقات اللانهائية وتوفير سياق لقرارات Gemini.

    Attributes:
        _history: قائمة الإجراءات المتخذة.
        _max_history: الحد الأقصى لعدد الإجراءات المحفوظة.
    """

    DEFAULT_MAX_HISTORY = 20

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY) -> None:
        """تهيئة الذاكرة.

        Args:
            max_history: الحد الأقصى لعدد الإجراءات المحفوظة.
        """
        self._history: list[dict] = []
        self._max_history = max_history

    def add(self, action: dict) -> None:
        """إضافة إجراء للتاريخ.

        يحذف الأقدم إذا تجاوز الحد الأقصى.

        Args:
            action: قاموس الإجراء (type, target, result, etc.).
        """
        self._history.append(action)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get_summary(self) -> str:
        """الحصول على ملخص نصي للتاريخ لإرساله لـ Gemini.

        Returns:
            str: ملخص الإجراءات السابقة مرقّمة.
        """
        if not self._history:
            return "No actions taken yet."

        lines = []
        for i, action in enumerate(self._history, 1):
            action_type = action.get("type", "unknown")
            target = action.get("target", "")
            result = action.get("result", "")
            lines.append(f"  {i}. {action_type}: {target} → {result}")

        return "Previous actions:\n" + "\n".join(lines)

    def detect_loop(self, window: int = 3) -> bool:
        """كشف الحلقات التكرارية في الإجراءات.

        يتحقق إذا كانت آخر N إجراءات متطابقة (نفس النوع والهدف).

        Args:
            window: حجم النافذة للمقارنة.

        Returns:
            bool: True إذا تم اكتشاف حلقة.
        """
        if len(self._history) < window:
            return False

        recent = self._history[-window:]
        keys = [(a.get("type"), a.get("target")) for a in recent]

        # إذا كانت كل الإجراءات في النافذة متطابقة = حلقة
        return len(set(keys)) == 1

    @property
    def count(self) -> int:
        """عدد الإجراءات المسجلة."""
        return len(self._history)

    def clear(self) -> None:
        """مسح التاريخ."""
        self._history.clear()


class AutonomousCommand(BaseTestCommand):
    """أمر اختبار ذاتي مبني على نمط ReAct.

    يقبل هدفاً بلغة طبيعية ويستخدم Gemini لتحديد
    الخطوات اللازمة ديناميكياً بدون سيناريو مسبق.

    في كل دورة من حلقة ReAct:
    - OBSERVE: التقاط لقطة شاشة.
    - THINK: Gemini يحلل الشاشة + الهدف + التاريخ ← يقرر.
    - ACT: تنفيذ القرار (نقر، كتابة، تمرير...).
    - VERIFY: هل تحقق الهدف؟ هل يوجد عائق؟

    Attributes:
        goal: الهدف بلغة طبيعية.
        memory: ذاكرة الإجراءات قصيرة المدى.
        max_steps: الحد الأقصى لعدد الخطوات.
    """

    DEFAULT_MAX_STEPS = 15

    # Prompt الرئيسي لنمط ReAct — يوجه Gemini لاتخاذ القرارات
    REACT_SYSTEM_PROMPT = (
        "You are Basir, an autonomous QA testing agent. "
        "You are given a GOAL to achieve on a webpage.\n\n"
        "For each screenshot, you must respond with a JSON object:\n"
        "{\n"
        '  "thought": "Your reasoning about the current state",\n'
        '  "action_type": "click|type|scroll|wait|done|obstacle",\n'
        '  "target_element": "Description of element to interact with",\n'
        '  "type_text": "Text to type (only if action_type is type)",\n'
        '  "press_enter": true/false (press Enter key after typing),\n'
        '  "coordinates": {"y": <0-1000>, "x": <0-1000>},\n'
        '  "goal_reached": true/false,\n'
        '  "obstacle": "Description of any popup/error blocking the goal (or null)"\n'
        "}\n\n"
        "RULES:\n"
        "- If you see a popup/error/cookie banner, set action_type to 'obstacle' "
        "and describe how to dismiss it.\n"
        "- If the goal is fully achieved, set goal_reached to true and "
        "action_type to 'done'.\n"
        "- NEVER repeat the same action on the same element more than twice.\n"
        "- When typing in a SEARCH box, ALWAYS set press_enter to true.\n"
        "- Provide coordinates for click actions.\n"
        "- Respond with ONLY valid JSON, no extra text."
    )

    def __init__(
        self,
        goal: str,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> None:
        """تهيئة الأمر الذاتي.

        Args:
            goal: الهدف بلغة طبيعية
                  (مثال: "Log in with username 'tomsmith'").
            max_steps: الحد الأقصى لعدد الخطوات قبل التوقف.
        """
        super().__init__(
            name="AutonomousTest",
            description=f"اختبار ذاتي: {goal[:50]}..."
        )
        self.goal = goal
        self.max_steps = max_steps
        self.memory = ActionMemory()

    def get_context(self) -> str:
        """بناء السياق الكامل لـ Gemini (الهدف + التاريخ).

        Returns:
            str: السياق مع الهدف وتاريخ الإجراءات.
        """
        return (
            f"GOAL: {self.goal}\n\n"
            f"STEP: {self._current_step + 1}/{self.max_steps}\n\n"
            f"{self.memory.get_summary()}"
        )

    async def execute_step(self, agent: Any, analysis: dict) -> dict:
        """تنفيذ دورة واحدة من حلقة ReAct.

        Observe → Think → Act → Verify

        Args:
            agent: مثيل Agent للوصول إلى المتصفح والرؤية.
            analysis: تحليل أولي (لا يُستخدم — نستدعي Gemini مباشرة).

        Returns:
            dict: نتيجة الخطوة.
        """
        step_number = self._mark_step()

        logger.info(
            f"🧠 ReAct دورة {step_number}/{self.max_steps}: "
            f"الهدف: '{self.goal[:40]}...'"
        )

        result = {
            "step_number": step_number,
            "step_name": "react_cycle",
            "action": "",
            "success": False,
            "details": "",
            "thought": "",
        }

        # التحقق من حد الخطوات
        if step_number > self.max_steps:
            result["action"] = "max_steps_reached"
            result["details"] = f"تجاوز الحد الأقصى ({self.max_steps} خطوة)."
            self._mark_complete()
            return result

        # كشف الحلقات اللانهائية
        if self.memory.detect_loop():
            logger.warning("🔁 تم اكتشاف حلقة تكرارية! تغيير الاستراتيجية...")
            result["details"] = "Loop detected — changing strategy."
            self.memory.add({
                "type": "loop_break",
                "target": "strategy_change",
                "result": "breaking loop"
            })

        try:
            # 1. OBSERVE: التقاط الشاشة
            screenshot = await agent.browser.take_screenshot()

            # 2. THINK: سؤال Gemini عن القرار التالي
            decision = await self._think(agent, screenshot)

            thought = decision.get("thought", "")
            action_type = decision.get("action_type", "unknown")
            result["thought"] = thought

            logger.info(f"💭 التفكير: {thought[:80]}...")
            logger.info(f"⚡ القرار: {action_type}")

            # 3. ACT: تنفيذ القرار
            if decision.get("goal_reached"):
                result["action"] = "goal_reached"
                result["success"] = True
                result["details"] = f"✅ تحقق الهدف! {thought}"
                self._mark_complete()
                return result

            if action_type == "obstacle":
                result = await self._handle_obstacle(
                    agent, decision, screenshot, result
                )

            elif action_type == "click":
                result = await self._execute_click(agent, decision, result)

            elif action_type == "type":
                result = await self._execute_type(agent, decision, result)

            elif action_type == "scroll":
                result = await self._execute_scroll(agent, decision, result)

            elif action_type == "wait":
                await agent.browser.wait_for_stable_state()
                result["action"] = "wait"
                result["success"] = True
                result["details"] = "انتظار استقرار الصفحة."

            elif action_type == "done":
                result["action"] = "done"
                result["success"] = True
                result["details"] = f"✅ الوكيل قرر الانتهاء: {thought}"
                self._mark_complete()

            else:
                result["action"] = f"unknown: {action_type}"
                result["details"] = f"نوع إجراء غير معروف: {action_type}"

            # تسجيل في الذاكرة
            self.memory.add({
                "type": action_type,
                "target": decision.get("target_element", ""),
                "result": "success" if result["success"] else "failed",
            })

        except Exception as e:
            result["success"] = False
            result["details"] = f"خطأ: {str(e)}"
            logger.error(f"❌ خطأ في دورة ReAct: {e}")
            self.memory.add({
                "type": "error",
                "target": str(e)[:50],
                "result": "failed",
            })

        return result

    async def _think(self, agent: Any, screenshot: bytes) -> dict:
        """مرحلة التفكير — سؤال AI عن القرار التالي.

        يُرسل لقطة الشاشة مع الهدف وتاريخ الإجراءات
        ويطلب من AI تحديد الخطوة التالية.

        Args:
            agent: مثيل Agent.
            screenshot: لقطة الشاشة الحالية.

        Returns:
            dict: قرار AI (action_type, coordinates, etc.).
        """
        import json
        import re

        full_prompt = (
            f"{self.REACT_SYSTEM_PROMPT}\n\n"
            f"---\n"
            f"{self.get_context()}\n"
            f"---\n"
            f"Analyze the screenshot and decide the next action."
        )

        # إضافة ARIA context إذا متاح (مع تقليل الحجم لـ 4000 حرف)
        aria_ctx = getattr(self, '_aria_context', '')
        if aria_ctx:
            # Filter to viewport-only elements (exclude [offscreen])
            lines = aria_ctx.split('\n')
            viewport_lines = [l for l in lines if '[offscreen]' not in l]
            trimmed = '\n'.join(viewport_lines)[:1500]
            full_prompt += f"\n\n--- Page Structure (ARIA, viewport only) ---\n{trimmed}"
            print(f"   📎 ARIA context added ({len(trimmed)} chars, viewport only)")

        # استخدام agent.vision بدلاً من Gemini SDK مباشرة
        # حتى يعمل مع أي provider (Ollama, DeepSeek, Gemini, etc.)
        print(f"\n🧠 [Think] Sending to AI for decision...")
        analysis = await agent.vision.analyze_screenshot(
            screenshot=screenshot,
            context=full_prompt
        )

        raw_text = analysis.get("raw_response", "").strip()
        logger.debug(f"🧠 AI raw response: {raw_text[:200]}")
        print(f"   🧠 AI response ({len(raw_text)} chars): {raw_text[:100]}...")

        # استخراج JSON من الرد
        try:
            # محاولة تنظيف النص من علامات Markdown أو المسافات
            clean = raw_text.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            elif clean.startswith("```"):
                clean = clean[3:]
            
            if clean.endswith("```"):
                clean = clean[:-3]
                
            clean = clean.strip()
            return json.loads(clean)
        except json.JSONDecodeError:
            # fallback: البحث عن JSON مضمّن
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

        # fallback نهائي
        logger.warning(f"⚠️ فشل تحليل JSON من AI: {raw_text[:100]}")
        return {
            "thought": raw_text[:200],
            "action_type": "wait",
            "goal_reached": False,
        }

    async def _execute_click(
        self, agent: Any, decision: dict, result: dict
    ) -> dict:
        """تنفيذ إجراء النقر بناءً على قرار Gemini.

        Args:
            agent: مثيل Agent.
            decision: قرار Gemini مع الإحداثيات.
            result: قاموس النتيجة.

        Returns:
            dict: النتيجة المحدّثة.
        """
        coords = decision.get("coordinates", {})
        norm_x = float(coords.get("x", 500))
        norm_y = float(coords.get("y", 500))
        target = decision.get("target_element", "unknown")

        await agent.browser.click_at_normalized(norm_x, norm_y)

        result["action"] = f"click: {target}"
        result["success"] = True
        result["details"] = f"نقر على '{target}' @ ({norm_x:.0f}, {norm_y:.0f})"
        return result

    async def _execute_type(
        self, agent: Any, decision: dict, result: dict
    ) -> dict:
        """تنفيذ إجراء الكتابة.

        ينقر أولاً على العنصر إذا تم توفير إحداثيات، ثم يكتب النص.

        Args:
            agent: مثيل Agent.
            decision: قرار Gemini مع النص والإحداثيات.
            result: قاموس النتيجة.

        Returns:
            dict: النتيجة المحدّثة.
        """
        text = decision.get("type_text", "")
        target = decision.get("target_element", "unknown")
        coords = decision.get("coordinates", {})

        # النقر على الحقل أولاً إذا توفرت إحداثيات
        if coords:
            norm_x = float(coords.get("x", 500))
            norm_y = float(coords.get("y", 500))
            await agent.browser.click_at_normalized(norm_x, norm_y)

        await agent.browser.type_text(text)

        # الضغط على Enter إذا طلب الموديل ذلك
        if decision.get("press_enter", False):
            await agent.browser._page.keyboard.press("Enter")
            print(f"   ⏎ Pressed Enter after typing")

        result["action"] = f"type: '{text[:15]}...' → {target}"
        result["success"] = True
        result["details"] = f"كتابة '{text}' في '{target}'"
        return result

    async def _execute_scroll(
        self, agent: Any, decision: dict, result: dict
    ) -> dict:
        """تنفيذ إجراء التمرير.

        Args:
            agent: مثيل Agent.
            decision: قرار Gemini.
            result: قاموس النتيجة.

        Returns:
            dict: النتيجة المحدّثة.
        """
        # تمرير لأسفل بمقدار 300 بكسل افتراضياً
        await agent.browser._page.mouse.wheel(0, 300)
        await agent.browser.wait_for_stable_state(timeout=2000)

        result["action"] = "scroll_down"
        result["success"] = True
        result["details"] = "تمرير الصفحة لأسفل."
        return result

    async def _handle_obstacle(
        self, agent: Any, decision: dict, screenshot: bytes, result: dict
    ) -> dict:
        """التعامل مع عائق (popup, error, cookie banner) قبل الاستئناف.

        عندما يكتشف Gemini عائقاً، يحاول إزالته
        (مثلاً: إغلاق popup) قبل العودة للهدف الأصلي.

        Args:
            agent: مثيل Agent.
            decision: قرار Gemini مع وصف العائق.
            screenshot: لقطة الشاشة الحالية.
            result: قاموس النتيجة.

        Returns:
            dict: النتيجة المحدّثة.
        """
        obstacle = decision.get("obstacle", "Unknown obstacle")
        logger.warning(f"🚧 عائق مكتشف: {obstacle}")

        # سؤال Gemini عن كيفية إزالة العائق
        dismiss_x, dismiss_y = await agent.vision.get_element_coordinates(
            screenshot,
            f"Button or link to dismiss/close: {obstacle}"
        )

        await agent.browser.click_at_normalized(dismiss_x, dismiss_y)
        await agent.browser.wait_for_stable_state()

        result["action"] = f"obstacle_dismissed: {obstacle[:30]}"
        result["success"] = True
        result["details"] = (
            f"🚧 عائق: {obstacle} → تم إزالته @ ({dismiss_x:.0f}, {dismiss_y:.0f})"
        )
        return result
