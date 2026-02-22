# 🔭 Project Basir: Co-Pilot for the Web

## 1. هوية المشروع (Project Identity)

> **Basir** (بصير) — مساعد ذكاء اصطناعي (Co-Pilot) شخصي لتصفح الويب.
> يمثل "يد المستخدم"، قادر على **الرؤية، التفكير، والتفاعل** مع واجهات الويب لتنفيذ المهام بدلاً منه.
> يستبدل هشاشة الـ Scripts بـ **رؤية AI وشجرة الإتاحة (ARIA)** لفهم واجهات المستخدم سياقياً وتلبية النوايا (Intent-Based).

### المهمة (Mission)
تحويل المتصفح من أداة يدوية إلى وكيل ينفذ نوايا المستخدم بالاعتماد على نماذج AI لتوفير تجربة Co-Pilot للويب.
| المكون | التقنية | الدور |
|--------|---------|-------|
| 🧠 الإدراك (Perception) | Gemini 2.5 Flash/Pro + ARIA | فهم مزدوج: للرؤية والشجرة الهيكلية للعناصر |
| 🌐 التفاعل | Playwright (Python) | التنقل والمحاكاة التفاعلية للبشر |
| 🖥️ الشفافية | Streamlit | لوحة تحكم تظهر تفكير الوكيل (Human-in-the-Loop) |
| 📦 التكامل | Google ADK | وكيل موحد يلتزم بمعايير بناء الوكلاء |

---

## 3. الهيكلية المعمارية (Architecture)

```
Basir/
├── README.md                      # التوثيق الرئيسي (GitHub)
├── Role.md                        # هذا الملف — المرجع الداخلي للمشروع
├── main.py                        # نقطة الدخول (CLI)
├── app.py                         # 🖥️ Streamlit Dashboard (واجهة حية)
├── requirements.txt               # الحزم المطلوبة
│
├── basir/                         # الكود الأساسي (Core Engine)
│   ├── __init__.py
│   ├── agent.py                   # 🎯 المنسق + Self-Healing + ReAct
│   ├── browser_controller.py      # 🌐 Playwright + CoordinateMapper + Virtual Cursor
│   ├── vision_processor.py        # 👁️ Gemini Vision + Live Streaming + ARIA Snapshot
│   ├── reporter.py                # 📊 JSON Test Reports
│   │
│   └── commands/                  # Command Pattern
│       ├── __init__.py
│       ├── base_command.py        # Abstract Base Class
│       ├── login_test.py          # سيناريو Login ثابت
│       └── autonomous_command.py  # 🧠 ReAct — اختبار ذاتي بهدف طبيعي
│
├── configs/
│   └── settings.yaml              # إعدادات المشروع (Provider + Models + Browser)
│
├── assets/
│   └── banner.png                 # صورة البانر للـ README
│
├── deploy/
│   └── Dockerfile                 # نشر الحاوية
│
└── tests/                         # اختبارات الوحدة
    └── __init__.py
```

### مبادئ معمارية:
- **OOP-First**: كل مكون هو كلاس مستقل وقابل للتوسعة.
- **Command Pattern**: إضافة أنواع اختبارات جديدة بإنشاء كلاس يرث `BaseTestCommand`.
- **ReAct Pattern**: تخطيط ذاتي مبني على (Observe → Think → Act → Verify).
- **Short-term Memory**: تاريخ إجراءات + كشف الحلقات التكرارية.
- **Self-Healing**: تعافي تلقائي من الأخطاء أثناء التنفيذ (حتى `max_retries`).
- **Multi-Provider**: دعم 4 مزودي AI — تبديل بسطر واحد في `settings.yaml`.
- **CoordinateMapper**: تحويل إحداثيات Gemini (0-1000) → بكسلات حقيقية.
- **CDP Screencast**: بث مباشر عبر Chrome DevTools Protocol مع مؤشر وهمي.
- **Self-Documenting**: توثيق Google-style docstrings لكل موديول.

---

## 4. المكونات الأساسية (Core Components)

### 🎯 Agent (`basir/agent.py`)
المنسق الرئيسي — يربط بين جميع المكونات:
- `run()` — تشغيل اختبار بسيناريو ثابت (LoginTest).
- `plan_and_execute()` — تشغيل وضع ReAct الذاتي بهدف طبيعي.
- `run_with_callback()` — بث تحديثات حية للـ Dashboard.
- `_execute_with_healing()` — تنفيذ مع self-healing.
- `_attempt_recovery()` — محاولة تعافي من خطأ.

### 🌐 BrowserController (`basir/browser_controller.py`)
- `launch()` — تشغيل Chromium في Stealth Mode.
- `navigate()` — تصفح مع استراتيجية قوية ضد Timeout.
- `take_screenshot()` — التقاط لقطة شاشة PNG.
- `click_at_normalized()` — نقر بإحداثيات Gemini.
- `type_text()` — كتابة نص بمحاكاة بشرية.
- `start_streaming()` / `stop_streaming()` — بث CDP مباشر.
- `get_aria_snapshot()` — استخراج شجرة Accessibility.
- `_inject_virtual_cursor()` — مؤشر ماوس بتصميم Electric Purple.

### 👁️ VisionProcessor (`basir/vision_processor.py`)
- `analyze_screenshot()` — تحليل صورة واحدة (Flash).
- `get_element_coordinates()` — إحداثيات عنصر محدد.
- `_optimize_screenshot()` — ضغط وتقليل حجم الصور.
- `LiveSession` — جلسة بث مباشر مع Gemini.

### 📊 Reporter (`basir/reporter.py`)
- `generate()` — إنشاء تقرير من نتائج الاختبار.
- `save()` — حفظ التقرير بصيغة JSON.
- `format_summary()` — ملخص نصي للطباعة.

---

## 5. خارطة الطريق (Roadmap)

| المرحلة | الوصف | الحالة |
|---------|-------|--------|
| **MVP** | اختبار تدفق Login على URL حي | 🔄 قيد العمل |
| **Phase 2** | تقارير أخطاء مع Annotated Screenshots | ⏳ مخطط |
| **Phase 3** | توليد مجموعات اختبار بلغة طبيعية | ⏳ مخطط |
| **Phase 4** | تكامل CI/CD وتنفيذ متوازي | ⏳ مخطط |

---

## 6. سجل التقدم (Progress Log)

| التاريخ | ما تم إنجازه |
|---------|-------------|
| 2026-02-22 | 🚀 **رفع المشروع على GitHub** + إنشاء README.md احترافي + تحديث Role.md. |
| 2026-02-21 | 🖥️ **Basir Dashboard**: إنشاء `app.py` (Streamlit) مع Live View + Control Room + Reasoning Log. |
| 2026-02-21 | 🧠 **ReAct Pattern**: `autonomous_command.py` + ActionMemory + كشف الحلقات. |
| 2026-02-21 | 🎯 **Precision Navigation**: `CoordinateMapper` + `get_element_coordinates()`. |
| 2026-02-21 | 🔄 **AI Studio Migration**: تحويل من Vertex AI إلى Google AI Studio (Free). |
| 2026-02-21 | 🔐 **تأمين**: `.gitignore` + Service Account auth. |
| 2026-02-21 | ✅ **إنشاء الهيكل الكامل**: جميع الكلاسات + Self-Healing + Command Pattern. |

### الخطوة التالية المتوقعة:
- إطلاق أول جلسة ReAct ناجحة عبر الداشبورد.
- إضافة Annotated Screenshots (Phase 2).

---

## 7. تعليمات استئناف العمل (AI Resume Instructions)

> **عند بداية كل جلسة جديدة، الذكاء الاصطناعي يجب عليه:**

1. **اقرأ هذا الملف أولاً** (`Role.md`) لاستعادة السياق الكامل.
2. **راجع حالة الـ Roadmap** وحدد المرحلة الحالية.
3. **افحص الكود الموجود** في مجلد `basir/` لمعرفة آخر التعديلات.
4. **اسأل المستخدم**: "إيه اللي عايز نشتغل عليه النهاردة؟"
5. **التزم بالمبادئ المعمارية** المذكورة أعلاه في أي كود جديد.
6. **حدّث هذا الملف** إذا تغيرت الهيكلية أو تقدمت في خارطة الطريق.

---

## 8. التشغيل السريع (Quick Reference)

```bash
# CLI — سيناريو ثابت
python main.py --url https://the-internet.herokuapp.com/login

# CLI — وضع ReAct الذاتي
python main.py --mode autonomous --url https://example.com --goal "Navigate to login and test it"

# Dashboard حية
streamlit run app.py
```

### مزود الـ AI:
```yaml
# configs/settings.yaml
api:
  provider: "google_ai"
```