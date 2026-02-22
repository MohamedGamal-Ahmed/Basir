# 🔭 Project Basir: Autonomous QA Visionary Agent

## 1. هوية المشروع (Project Identity)

> **Basir** (بصير) — وكيل ذكاء اصطناعي عالي الدقة لضمان الجودة.
> مبني لتحدي **Gemini Live Agent Challenge** (فئة UI Navigator).
> يمثل "عيون المطوّر"، قادر على **الرؤية، التفكير، والتفاعل** مع واجهات الويب كمختبر بشري.

### المهمة (Mission)
القضاء على هشاشة أتمتة الاختبارات التقليدية المعتمدة على CSS/XPath
باستخدام **Gemini 3.1 Multimodal Vision** لفهم واجهات المستخدم سياقياً
وتنفيذ حالات اختبار ذاتية التعافي (Self-Healing).

---

## 2. التقنيات المستخدمة (Tech Stack)

| المكون | التقنية | الدور |
|--------|---------|-------|
| 🧠 الذكاء | Gemini 3.1 Flash | تنفيذ سريع + رؤية فورية (Live Streaming) |
| 🧠 التحليل | Gemini 3.1 Pro | استنتاج عالي المستوى + تقارير الأخطاء |
| 🎭 الأوركستريشن | Google ADK | تنسيق عمل الوكيل وإدارة الأدوات |
| 🌐 التفاعل | Playwright (Python) | التحكم في المتصفح + التقاط الشاشة |
| ☁️ السحابة | Vertex AI & Cloud Run | استضافة ونشر الوكيل |

---

## 3. الهيكلية المعمارية (Current Architecture)

```
Basir/
├── ROLE.md                    # هذا الملف - المرجع الأساسي
├── main.py                    # نقطة الدخول (CLI)
├── app.py                     # 🖥️ Streamlit Dashboard (واجهة مباشرة)
├── requirements.txt           # الحزم المطلوبة
│
├── basir/                     # الكود الأساسي
│   ├── __init__.py
│   ├── agent.py               # المنسق + Self-Healing
│   ├── browser_controller.py  # Playwright + CoordinateMapper
│   ├── vision_processor.py    # Gemini Vision + Live Streaming
│   ├── reporter.py            # إنشاء التقارير
│   │
│   └── commands/              # Command Pattern للاختبارات
│       ├── __init__.py
│       ├── base_command.py    # الكلاس الأساسي (Abstract)
│       ├── login_test.py      # اختبار Login (سيناريو ثابت)
│       └── autonomous_command.py  # 🧠 ReAct الذاتي (Goal-based)
│
├── configs/                   # الإعدادات
│   └── settings.yaml
│
├── deploy/                    # ملفات النشر
│   └── Dockerfile
│
└── tests/                     # اختبارات الوحدة
    └── __init__.py
```

### مبادئ معمارية:
- **OOP-First**: كل مكون هو كلاس مستقل وقابل للتوسعة.
- **Command Pattern**: إضافة أنواع اختبارات جديدة بسهولة.
- **ReAct Pattern**: تخطيط ذاتي مبني على (Observe → Think → Act → Verify).
- **Short-term Memory**: تاريخ إجراءات + كشف الحلقات التكرارية.
- **Low Latency**: بث بصري محسّن للتغذية الراجعة "الحية".
- **Self-Healing**: تعافي تلقائي من الأخطاء أثناء التنفيذ.
- **Self-Documenting**: توثيق Google-style docstrings لكل موديول.

---

## 4. خارطة الطريق (Roadmap)

| المرحلة | الوصف | الحالة |
|---------|-------|--------|
| **MVP** | اختبار تدفق تسجيل الدخول (Login Flow) على URL حي | 🔄 قيد العمل |
| **Phase 2** | تقارير أخطاء مع لقطات شاشة موضحة (Annotated Screenshots) | ⏳ |
| **Phase 3** | توليد مجموعات اختبار بلغة طبيعية (Natural Language Test Suites) | ⏳ |

---

## 5. سجل التقدم (Progress Log)

| التاريخ | ما تم إنجازه |
|---------|-------------|
| 2026-02-21 | ✅ إنشاء الهيكل الكامل للمشروع (Boilerplate). جميع الكلاسات جاهزة مع Self-Healing + CoordinateMapper + Live Streaming + Command Pattern. |
| 2026-02-21 | 🔐 **تأمين + مصادقة**: `.gitignore` + Service Account auth في `vision_processor.py`. |
| 2026-02-21 | 🎯 **Precision Navigation**: `get_element_coordinates()` + `login_test.py` مع إحداثيات Gemini الحقيقية. |
| 2026-02-21 | 🧠 **ReAct Pattern**: `autonomous_command.py` + `plan_and_execute(goal)` + ActionMemory + obstacle handling. |
| 2026-02-21 | 🖥️ **Basir Dashboard**: إنشاء `app.py` (Streamlit) مع Live View + Control Room + Reasoning Log + CSS متقدم. إضافة `run_with_callback()` في `agent.py` لبث التحديثات الحية. |
| 2026-02-21 | 🔄 **AI Studio Migration**: تحويل من Vertex AI (billing) إلى Google AI Studio (free). API Key من `.env`. إصلاح viewport_size → viewport. إضافة حفظ screenshots تلقائي. Models: `gemini-1.5-flash` + `gemini-1.5-pro`. |

### الخطوة التالية المتوقعة:
- إطلاق أول جلسة ReAct ناجحة عبر الداشبورد.
- إضافة Annotated Screenshots (Phase 2).

---

## 6. تعليمات استئناف العمل (AI Resume Instructions)

> **عند بداية كل جلسة جديدة، الذكاء الاصطناعي يجب عليه:**

1. **اقرأ هذا الملف أولاً** (`ROLE.md`) لاستعادة السياق الكامل.
2. **راجع حالة الـ Roadmap** وحدد المرحلة الحالية.
3. **افحص الكود الموجود** في مجلد `basir/` لمعرفة آخر التعديلات.
4. **اسأل المستخدم**: "إيه اللي عايز نشتغل عليه النهاردة؟"
5. **التزم بالمبادئ المعمارية** المذكورة أعلاه في أي كود جديد.
6. **حدّث هذا الملف** إذا تغيرت الهيكلية أو تقدمت في خارطة الطريق.