"""Reporter module - Test result and bug report generation.

This module provides the Reporter class for generating structured
test reports using results from the Agent's test execution lifecycle.
Uses Gemini 3.1 Pro for synthesizing detailed, human-readable bug reports.

Typical usage example:

    reporter = Reporter()
    report = reporter.generate(test_results)
    reporter.save(report, path="reports/login_test.json")
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Reporter:
    """منشئ التقارير لنتائج الاختبارات وتقارير الأخطاء.

    يقوم بتجميع نتائج الخطوات، الأخطاء المكتشفة، ولقطات الشاشة
    في تقرير منظّم قابل للقراءة والتصدير.

    Attributes:
        config: إعدادات التقارير (مسار الحفظ، التنسيق، etc.).
        output_dir: مجلد حفظ التقارير.
    """

    DEFAULT_OUTPUT_DIR = "reports"

    def __init__(self, config: Optional[dict] = None) -> None:
        """تهيئة منشئ التقارير.

        Args:
            config: إعدادات اختيارية تشمل:
                - output_dir: مسار مجلد حفظ التقارير.
                - format: تنسيق التقرير ("json" أو "html").
        """
        self.config = config or {}
        self.output_dir = Path(
            self.config.get("output_dir", self.DEFAULT_OUTPUT_DIR)
        )
        logger.info(f"تم تهيئة Reporter. مسار الحفظ: {self.output_dir}")

    def generate(self, test_results: dict) -> dict:
        """إنشاء تقرير منظّم من نتائج الاختبار.

        Args:
            test_results: قاموس نتائج الاختبار من Agent.run()
                يحتوي على: url, status, steps, bugs, error.

        Returns:
            dict: التقرير المنظّم مع بيانات وصفية (metadata).
        """
        report = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "agent_version": "0.1.0",
                "tool": "Basir QA Agent"
            },
            "summary": {
                "target_url": test_results.get("url", "N/A"),
                "status": test_results.get("status", "unknown"),
                "total_steps": len(test_results.get("steps", [])),
                "bugs_found": len(test_results.get("bugs", [])),
            },
            "steps": test_results.get("steps", []),
            "bugs": test_results.get("bugs", []),
        }

        if "error" in test_results:
            report["error"] = test_results["error"]

        status_emoji = "✅" if report["summary"]["status"] == "passed" else "❌"
        logger.info(
            f"{status_emoji} التقرير: {report['summary']['status']} "
            f"| خطوات: {report['summary']['total_steps']} "
            f"| أخطاء: {report['summary']['bugs_found']}"
        )

        return report

    def save(self, report: dict, filename: Optional[str] = None) -> Path:
        """حفظ التقرير كملف JSON.

        Args:
            report: التقرير المنظّم من generate().
            filename: اسم الملف (اختياري، يتم توليده تلقائياً إذا لم يُحدد).

        Returns:
            Path: مسار الملف المحفوظ.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"basir_report_{timestamp}.json"

        filepath = self.output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"💾 تم حفظ التقرير في: {filepath}")
        return filepath

    def format_summary(self, report: dict) -> str:
        """تنسيق ملخص التقرير كنص قابل للطباعة.

        Args:
            report: التقرير المنظّم.

        Returns:
            str: ملخص نصي للتقرير.
        """
        summary = report.get("summary", {})
        lines = [
            "=" * 50,
            "📊 تقرير Basir QA Agent",
            "=" * 50,
            f"🌐 URL: {summary.get('target_url', 'N/A')}",
            f"📌 الحالة: {summary.get('status', 'unknown')}",
            f"📝 عدد الخطوات: {summary.get('total_steps', 0)}",
            f"🐛 أخطاء مكتشفة: {summary.get('bugs_found', 0)}",
            f"🕐 الوقت: {report.get('metadata', {}).get('generated_at', 'N/A')}",
            "=" * 50,
        ]
        return "\n".join(lines)
