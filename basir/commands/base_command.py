"""Base Command module - Abstract base class for test commands.

This module defines the BaseTestCommand abstract class that all
test commands must inherit from. Implements the Command Pattern
to allow easy addition of new test types.

Typical usage example:

    class MyCustomTest(BaseTestCommand):
        async def execute_step(self, agent, analysis):
            # تنفيذ خطوة الاختبار
            ...
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseTestCommand(ABC):
    """الكلاس الأساسي المجرّد لأوامر الاختبار (Command Pattern).

    يحدد الواجهة التي يجب أن تنفذها جميع أوامر الاختبار.
    كل أمر يمثل نوعاً محدداً من الاختبارات (Login, Checkout, etc.).

    لإضافة اختبار جديد:
    1. أنشئ ملفاً جديداً في basir/commands/
    2. ارث من BaseTestCommand
    3. نفّذ الدوال المجردة: execute_step(), is_complete(), get_context()

    Attributes:
        name: اسم أمر الاختبار.
        description: وصف الاختبار.
        _completed: هل تم إكمال الاختبار.
        _current_step: رقم الخطوة الحالية.
    """

    def __init__(self, name: str, description: str = "") -> None:
        """تهيئة أمر الاختبار.

        Args:
            name: اسم أمر الاختبار.
            description: وصف ما يقوم به الاختبار.
        """
        self.name = name
        self.description = description
        self._completed = False
        self._current_step = 0

        logger.info(f"تم إنشاء أمر اختبار: {self.name}")

    @abstractmethod
    async def execute_step(self, agent: Any, analysis: dict) -> dict:
        """تنفيذ خطوة واحدة من الاختبار.

        يتم استدعاؤها تكرارياً في حلقة Agent الرئيسية.
        كل استدعاء يمثل خطوة واحدة في سيناريو الاختبار.

        Args:
            agent: مثيل Agent للوصول إلى المتصفح والأدوات.
            analysis: نتيجة تحليل Gemini لحالة الشاشة الحالية.

        Returns:
            dict: نتيجة الخطوة تشمل:
                - step_number: رقم الخطوة.
                - action: الإجراء الذي تم تنفيذه.
                - success: هل نجحت الخطوة.
                - details: تفاصيل إضافية.
        """
        pass

    @abstractmethod
    def get_context(self) -> str:
        """الحصول على السياق الحالي لتوجيه Gemini.

        يُرسل مع كل لقطة شاشة ليعرف Gemini ماذا يبحث عنه.

        Returns:
            str: وصف نصي للحالة المتوقعة والإجراء المطلوب.
        """
        pass

    def is_complete(self) -> bool:
        """التحقق مما إذا تم إكمال جميع خطوات الاختبار.

        Returns:
            bool: True إذا اكتمل الاختبار.
        """
        return self._completed

    def _mark_step(self) -> int:
        """تسجيل انتهاء خطوة وزيادة العدّاد.

        Returns:
            int: رقم الخطوة الحالية.
        """
        self._current_step += 1
        return self._current_step

    def _mark_complete(self) -> None:
        """تحديد الاختبار كمكتمل."""
        self._completed = True
        logger.info(f"✅ اكتمل أمر الاختبار: {self.name}")
