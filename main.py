"""Basir QA Agent - Main Entry Point.

This is the main entry point for running the Basir Autonomous QA
Testing Agent. It loads configuration, initializes the Agent,
and executes the specified test command.

Usage:
    python main.py

    # أو مع تحديد URL:
    python main.py --url https://example.com/login
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

import yaml

# تحميل متغيرات البيئة من .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from basir.agent import Agent
from basir.commands.login_test import LoginTestCommand

# إعداد نظام اللوغات
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-25s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("basir.main")


def load_config(config_path: str = "configs/settings.yaml") -> dict:
    """تحميل إعدادات المشروع من ملف YAML.

    Args:
        config_path: مسار ملف الإعدادات.

    Returns:
        dict: قاموس الإعدادات.
    """
    path = Path(config_path)
    if not path.exists():
        logger.warning(f"ملف الإعدادات غير موجود: {config_path}. استخدام الافتراضي.")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logger.info(f"تم تحميل الإعدادات من: {config_path}")
    return config or {}


def parse_args() -> argparse.Namespace:
    """تحليل وسائط سطر الأوامر.

    Returns:
        argparse.Namespace: الوسائط المحلّلة.
    """
    parser = argparse.ArgumentParser(
        description="Basir - Autonomous QA Testing Agent 🔭",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url",
        type=str,
        default="https://the-internet.herokuapp.com/login",
        help="عنوان URL الهدف للاختبار.",
    )
    parser.add_argument(
        "--username",
        type=str,
        default="tomsmith",
        help="اسم المستخدم لاختبار تسجيل الدخول.",
    )
    parser.add_argument(
        "--password",
        type=str,
        default="SuperSecretPassword!",
        help="كلمة المرور لاختبار تسجيل الدخول.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/settings.yaml",
        help="مسار ملف الإعدادات.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["scripted", "autonomous"],
        default="scripted",
        help="وضع الاختبار: scripted (سيناريو ثابت) أو autonomous (ReAct ذاتي).",
    )
    parser.add_argument(
        "--goal",
        type=str,
        default="Log in with username 'tomsmith' and password 'SuperSecretPassword!' and verify we reach the secure area",
        help="الهدف بلغة طبيعية (للوضع الذاتي فقط).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="الحد الأقصى لخطوات ReAct (للوضع الذاتي).",
    )
    return parser.parse_args()


async def main() -> None:
    """الدالة الرئيسية لتشغيل وكيل ضمان الجودة."""
    args = parse_args()

    print("=" * 55)
    print("  🔭 Basir - Autonomous QA Visionary Agent")
    print("=" * 55)

    # تحميل الإعدادات
    config = load_config(args.config)

    # تهيئة الوكيل
    agent_config = {
        "max_retries": config.get("agent", {}).get("max_retries", 3),
        "browser": config.get("browser", {}),
        "vision": {
            "flash_model": config.get("models", {}).get("flash"),
            "pro_model": config.get("models", {}).get("pro"),
        },
        "reporter": config.get("reporter", {}),
        "api": config.get("api", {}),
        "groq_models": config.get("groq_models", {}),
        "deepseek_models": config.get("deepseek_models", {}),
        "ollama_models": config.get("ollama_models", {}),
    }

    agent = Agent(config=agent_config)

    # Pre-flight check: test Ollama connectivity
    provider = config.get("api", {}).get("provider", "google_ai")
    if provider == "ollama":
        print("\n🔌 Testing Ollama connectivity...")
        is_reachable = await agent.vision.check_connectivity()
        if not is_reachable:
            print("❌ FATAL: Cannot reach Ollama. Aborting.")
            print("   → Run 'ollama serve' in a separate terminal first.")
            print("   → Then run 'ollama pull llama3.2-vision' to download the model.")
            sys.exit(1)
        print("✅ Ollama pre-flight check passed!\n")

    # اختيار وضع الاختبار
    if args.mode == "autonomous":
        # وضع ReAct الذاتي
        logger.info(f"🧠 الوضع: ذاتي (ReAct) | الهدف: {args.goal[:50]}...")
        results = await agent.plan_and_execute(
            target_url=args.url,
            goal=args.goal,
            max_steps=args.max_steps,
        )
    else:
        # وضع سيناريو ثابت (LoginTestCommand)
        logger.info(f"📋 الوضع: سيناريو ثابت (LoginTest)")
        test_cmd = LoginTestCommand(
            username=args.username,
            password=args.password,
        )
        results = await agent.run(target_url=args.url, test_command=test_cmd)

    # عرض الملخص
    summary = agent.reporter.format_summary(agent.reporter.generate(results))
    print(summary)

    # حفظ التقرير
    report = agent.reporter.generate(results)
    saved_path = agent.reporter.save(report)
    logger.info(f"📄 التقرير محفوظ في: {saved_path}")


if __name__ == "__main__":
    asyncio.run(main())
