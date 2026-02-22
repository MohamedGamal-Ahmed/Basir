"""Browser Controller module - Playwright-based browser interaction.

This module provides the BrowserController class for managing browser
instances, navigating pages, capturing screenshots, and performing
UI interactions. Includes CoordinateMapper for converting Gemini's
normalized coordinates (0-1000) to actual pixel positions.

Typical usage example:

    controller = BrowserController(config={"viewport": {"width": 1920, "height": 1080}})
    await controller.launch()
    await controller.navigate("https://example.com")
    screenshot = await controller.take_screenshot()
    await controller.click_at_normalized(x=500, y=300)
    await controller.close()
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class CoordinateMapper:
    """محوّل الإحداثيات من نظام Gemini إلى بكسلات حقيقية.

    Gemini 3.1 يُرجع إحداثيات في نطاق (0 إلى 1000).
    المتصفح يعمل بالبكسلات مثل (1920x1080).
    هذا الكلاس يربط بين النظامين بدقة.

    Attributes:
        viewport_width: عرض نافذة المتصفح بالبكسل.
        viewport_height: ارتفاع نافذة المتصفح بالبكسل.
        gemini_max: الحد الأقصى لإحداثيات Gemini (افتراضياً 1000).
    """

    GEMINI_COORD_MAX = 1000

    def __init__(self, viewport_width: int = 1920, viewport_height: int = 1080) -> None:
        """تهيئة المحوّل بأبعاد النافذة.

        Args:
            viewport_width: عرض نافذة المتصفح بالبكسل.
            viewport_height: ارتفاع نافذة المتصفح بالبكسل.
        """
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height

    def to_pixels(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        """تحويل إحداثيات Gemini المعيارية إلى بكسلات.

        Args:
            norm_x: الإحداثي الأفقي من Gemini (0-1000).
            norm_y: الإحداثي العمودي من Gemini (0-1000).

        Returns:
            Tuple[int, int]: (pixel_x, pixel_y) الإحداثيات بالبكسل.

        Raises:
            ValueError: إذا كانت الإحداثيات خارج النطاق المتوقع.
        """
        if not (0 <= norm_x <= self.GEMINI_COORD_MAX):
            raise ValueError(
                f"الإحداثي الأفقي {norm_x} خارج النطاق (0-{self.GEMINI_COORD_MAX})"
            )
        if not (0 <= norm_y <= self.GEMINI_COORD_MAX):
            raise ValueError(
                f"الإحداثي العمودي {norm_y} خارج النطاق (0-{self.GEMINI_COORD_MAX})"
            )

        pixel_x = int((norm_x / self.GEMINI_COORD_MAX) * self.viewport_width)
        pixel_y = int((norm_y / self.GEMINI_COORD_MAX) * self.viewport_height)

        return pixel_x, pixel_y

    def to_normalized(self, pixel_x: int, pixel_y: int) -> Tuple[float, float]:
        """تحويل إحداثيات البكسل إلى إحداثيات Gemini المعيارية.

        Args:
            pixel_x: الإحداثي الأفقي بالبكسل.
            pixel_y: الإحداثي العمودي بالبكسل.

        Returns:
            Tuple[float, float]: (norm_x, norm_y) إحداثيات Gemini.
        """
        norm_x = (pixel_x / self.viewport_width) * self.GEMINI_COORD_MAX
        norm_y = (pixel_y / self.viewport_height) * self.GEMINI_COORD_MAX

        return round(norm_x, 2), round(norm_y, 2)


class BrowserController:
    """متحكم المتصفح باستخدام Playwright.

    يوفر واجهة عالية المستوى للتفاعل مع المتصفح:
    فتح/إغلاق، التنقل، التقاط الشاشة، النقر، والكتابة.

    Attributes:
        config: إعدادات المتصفح (viewport, headless, etc.).
        coordinate_mapper: محوّل الإحداثيات بين Gemini والمتصفح.
        browser: مثيل المتصفح من Playwright.
        page: الصفحة النشطة الحالية.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        """تهيئة متحكم المتصفح.

        Args:
            config: إعدادات اختيارية تشمل:
                - viewport: {"width": int, "height": int}
                - headless: bool (تشغيل بدون واجهة مرئية).
        """
        self.config = config or {}
        viewport = self.config.get("viewport", {"width": 1920, "height": 1080})

        self.coordinate_mapper = CoordinateMapper(
            viewport_width=viewport["width"],
            viewport_height=viewport["height"]
        )

        self._browser = None
        self._page = None
        self._playwright = None
        self._streaming = False
        self._streaming_task = None

        logger.info("تم تهيئة BrowserController.")

    async def launch(self) -> None:
        """تشغيل المتصفح وفتح صفحة جديدة (Stealth Mode).

        Raises:
            RuntimeError: إذا فشل تشغيل المتصفح.
        """
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.config.get("headless", True),
                ignore_default_args=["--enable-automation"],
                args=["--disable-blink-features=AutomationControlled"],
            )

            viewport = self.config.get("viewport", {"width": 1920, "height": 1080})
            
            # Stealth User-Agent (Chrome 131)
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
            self._page = await self._browser.new_page(
                viewport=viewport,
                user_agent=user_agent
            )

            # إزالة navigator.webdriver flag
            await self._page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            logger.info("✅ تم تشغيل المتصفح بنجاح (Stealth Mode).")
        except Exception as e:
            raise RuntimeError(f"فشل تشغيل المتصفح: {e}") from e

    async def _inject_virtual_cursor(self) -> None:
        """حقن سكريبت لإنشاء مؤشر ماوس وهمي بتصميم Basir الجذاب (Electric Purple).
        
        يضمن ظهور المؤشر وتتبعه للحركة في البث المباشر (Screencast) 
        ويضيف تأثيراً عند النقر.
        """
        cursor_script = """
        () => {
            if (document.getElementById('basir-v-cursor')) return;
            
            // إنشاء عنصر المؤشر
            const cursor = document.createElement('div');
            cursor.id = 'basir-v-cursor';
            Object.assign(cursor.style, {
                position: 'fixed',
                left: '0px',
                top: '0px',
                width: '20px',
                height: '20px',
                borderRadius: '50%',
                backgroundColor: 'rgba(168, 85, 247, 0.8)', /* Electric Purple */
                border: '2px solid white',
                pointerEvents: 'none', /* لا يتعارض مع النقر الحقيقي */
                zIndex: '2147483647', /* أعلى من كل شيء */
                transform: 'translate(-50%, -50%)',
                boxShadow: '0 0 15px 5px rgba(168, 85, 247, 0.6)',
                transition: 'left 0.1s ease-out, top 0.1s ease-out, transform 0.1s, box-shadow 0.1s'
            });
            document.body.appendChild(cursor);

            // تتبع حركة الماوس
            window.addEventListener('mousemove', (e) => {
                cursor.style.left = e.clientX + 'px';
                cursor.style.top = e.clientY + 'px';
            }, { passive: true });

            // تأثير النقر (Pulse/Shrink)
            window.addEventListener('mousedown', () => {
                cursor.style.transform = 'translate(-50%, -50%) scale(0.6)';
                cursor.style.boxShadow = '0 0 25px 10px rgba(168, 85, 247, 0.9)';
            }, { passive: true });

            window.addEventListener('mouseup', () => {
                cursor.style.transform = 'translate(-50%, -50%) scale(1)';
                cursor.style.boxShadow = '0 0 15px 5px rgba(168, 85, 247, 0.6)';
            }, { passive: true });
        }
        """
        # حقن הסكريبت ليعمل على كل صفحة جديدة وتنقّل (Navigation)
        await self._page.context.add_init_script(cursor_script)
        
        # ونحقنه في الصفحة الحالية فورا
        await self._page.evaluate(cursor_script)

    async def get_aria_snapshot(self) -> str:
        """استخراج شجرة ARIA (Accessibility Tree) كنص."""
        try:
            # بناء السكريبت كسلسلة منفصلة لتجنب مشاكل الـ escape
            js_code = (
                '() => {'
                '  const ROLES = ["button","link","textbox","checkbox","radio",'
                '    "combobox","listbox","option","tab","menuitem",'
                '    "searchbox","slider","switch","navigation","heading",'
                '    "img","dialog","alertdialog","menu","form"];'
                '  let rc = 0;'
                '  const out = [];'
                '  function role(el) {'
                '    var r = el.getAttribute("role");'
                '    if (r) return r;'
                '    var t = el.tagName;'
                '    if (t === "A" && el.href) return "link";'
                '    if (t === "BUTTON") return "button";'
                '    if (t === "INPUT") {'
                '      var tp = (el.type || "text").toLowerCase();'
                '      if (tp === "checkbox") return "checkbox";'
                '      if (tp === "radio") return "radio";'
                '      if (tp === "search") return "searchbox";'
                '      if (tp === "submit" || tp === "button") return "button";'
                '      if (tp === "hidden") return null;'
                '      return "textbox";'
                '    }'
                '    if (t === "TEXTAREA") return "textbox";'
                '    if (t === "SELECT") return "combobox";'
                '    if (t === "NAV") return "navigation";'
                '    if (t === "FORM") return "form";'
                '    if (t === "IMG") return "img";'
                '    if (t === "DIALOG") return "dialog";'
                '    if (t === "MAIN") return "main";'
                '    if (t === "HEADER") return "banner";'
                '    if (t === "FOOTER") return "contentinfo";'
                '    if (t === "ASIDE") return "complementary";'
                '    if (t === "H1" || t === "H2" || t === "H3"'
                '      || t === "H4" || t === "H5" || t === "H6") return "heading";'
                '    return null;'
                '  }'
                '  function nm(el) {'
                '    return el.getAttribute("aria-label")'
                '      || el.getAttribute("alt")'
                '      || el.getAttribute("title")'
                '      || el.getAttribute("placeholder")'
                '      || (el.textContent || "").trim().substring(0, 80)'
                '      || "";'
                '  }'
                '  function vis(el) {'
                '    var s = window.getComputedStyle(el);'
                '    if (s.display === "none" || s.visibility === "hidden") return false;'
                '    if (el.offsetWidth === 0 && el.offsetHeight === 0) return false;'
                '    return true;'
                '  }'
                '  function lvl(el) {'
                '    var t = el.tagName;'
                '    if (t === "H1") return 1; if (t === "H2") return 2;'
                '    if (t === "H3") return 3; if (t === "H4") return 4;'
                '    if (t === "H5") return 5; if (t === "H6") return 6;'
                '    return 0;'
                '  }'
                '  function walk(el, d) {'
                '    if (!el || !vis(el)) return;'
                '    var r = role(el);'
                '    if (r && ROLES.indexOf(r) >= 0) {'
                '      rc++;'
                '      var ref = "e" + rc;'
                '      var n = nm(el).replace(/"/g, String.fromCharCode(39));'
                '      var pad = "";'
                '      for (var i = 0; i < d; i++) pad += "  ";'
                '      var ln = pad + "- " + r;'
                '      if (n) ln += " \\"" + n.substring(0, 100) + "\\"";'
                '      ln += " [ref=" + ref + "]";'
                '      var lv = lvl(el);'
                '      if (lv) ln += " [level=" + lv + "]";'
                '      if (el.disabled) ln += " [disabled]";'
                '      if (el.checked) ln += " [checked]";'
                '      var rect = el.getBoundingClientRect();'
                '      var inVp = rect.top < window.innerHeight && rect.bottom > 0'
                '        && rect.left < window.innerWidth && rect.right > 0;'
                '      if (!inVp) ln += " [offscreen]";'
                '      if (r === "textbox" && el.value) {'
                '        ln += ": \\"" + el.value.substring(0, 50) + "\\"";'
                '      }'
                '      out.push(ln);'
                '    }'
                '    var ch = el.children;'
                '    for (var j = 0; j < ch.length; j++) {'
                '      walk(ch[j], (r && ROLES.indexOf(r) >= 0) ? d + 1 : d);'
                '    }'
                '  }'
                '  walk(document.body, 0);'
                '  return out.join("\\n");'
                '}'
            )
            
            aria_tree = await self._page.evaluate(js_code)
            
            url = self._page.url
            title = await self._page.title()
            header = f"# Page: {title}\n# URL: {url}\n# Interactive Elements:\n"
            
            result = header + (aria_tree or "(no interactive elements found)")
            logger.info(f"🌳 ARIA snapshot: {len(result)} chars, ~{len(result)//4} tokens")
            return result
            
        except Exception as e:
            logger.warning(f"⚠️ فشل استخراج ARIA snapshot: {e}")
            return "(ARIA snapshot unavailable)"

    async def navigate(self, url: str) -> None:
        """الانتقال إلى عنوان URL محدد مع استراتيجية تصفح قوية لتجنب Timeout.

        Args:
            url: عنوان الصفحة المراد الانتقال إليها.
        """
        logger.info(f"الانتقال إلى: {url}")
        try:
            # Adaptive Timeout: مهلة 60 ثانية مع wait_until=load
            await self._page.goto(url, wait_until="load", timeout=60000)
            
            # Adaptive Wait: انتظار قصير (1 ثانية بدل 2) — الصفحة محملة بالفعل
            await self._page.wait_for_timeout(1000)
        except Exception as e:
            # Graceful Error Handling: السماح بالاستمرار إذا فتحت الصفحة جزئياً
            if self._page.url != "about:blank":
                logger.warning(f"⚠️ انتهت مهلة التحميل ولكن الصفحة استجابت بشكل جزئي. ({e})")
                await self._page.wait_for_timeout(1000)
            else:
                logger.error(f"❌ فشل التصفح للرابط {url}: {e}")
                raise

    async def start_streaming(self, callback) -> None:
        """بدء بث مباشر للشاشة مع إظهار الماوس (CDP Screencast).
        
        Args:
            callback: دالة تستقبل الصورة (bytes) عند التقاطها.
        """
        import asyncio
        import base64
        self._streaming = True
        logger.info("🎥 بدء البث المباشر (CDP Screencast)...")
        
        try:
            # 1. إنشاء CDP Session
            self._cdp = await self._page.context.new_cdp_session(self._page)
            
            # 2. حقن مؤشر الماوس الوهمي
            await self._inject_virtual_cursor()

            # 3. إعداد مستمع الـ Screencast
            self._cdp.on("Page.screencastFrame", lambda event: self._handle_screencast_frame(event, callback))

            # 4. بدء الـ Screencast (حوالي 10-15 FPS)
            await self._cdp.send("Page.startScreencast", {
                "format": "jpeg",
                "quality": 50,
                "maxWidth": 1280,
                "maxHeight": 720,
                "everyNthFrame": 1
            })
            
        except Exception as e:
            logger.error(f"❌ فشل بدء الـ Screencast: {e}")

    def _handle_screencast_frame(self, event, callback):
        """معالجة كل فريم قادم من CDP وإرساله للـ Dashboard."""
        import asyncio
        if not self._streaming:
            return
            
        try:
            # البيانات بتيجي Base64 من CDP
            img_data = event.get("data")
            session_id = event.get("sessionId")
            
            if img_data:
                import base64
                frame_bytes = base64.b64decode(img_data)
                callback(frame_bytes)
                
            # إرسال تأكيد للـ CDP عشان يبعت الفريم اللي بعده
            if self._cdp and session_id:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._cdp.send("Page.screencastFrameAck", {"sessionId": session_id}))
                except RuntimeError:
                    pass
        except Exception:
            pass

    async def stop_streaming(self) -> None:
        """إيقاف البث المباشر."""
        self._streaming = False
        try:
            if hasattr(self, "_cdp") and self._cdp:
                try:
                    await self._cdp.send("Page.stopScreencast")
                except Exception:
                    pass
                try:
                    await self._cdp.detach()
                except Exception:
                    pass
                self._cdp = None
        except Exception:
            pass
        logger.info("⏹️ تم إيقاف البث المباشر (CDP).")

    async def take_screenshot(self) -> bytes:
        """التقاط صورة للشاشة الحالية.

        Returns:
            bytes: بيانات الصورة بصيغة PNG.
        """
        screenshot = await self._page.screenshot(type="png", full_page=False)
        logger.debug("تم التقاط لقطة شاشة.")
        return screenshot

    async def click_at_normalized(self, norm_x: float, norm_y: float) -> None:
        """نقر على موقع محدد باستخدام إحداثيات Gemini المعيارية.

        يحوّل الإحداثيات من نظام Gemini (0-1000) إلى بكسلات
        ثم ينفذ النقر.

        Args:
            norm_x: الإحداثي الأفقي من Gemini (0-1000).
            norm_y: الإحداثي العمودي من Gemini (0-1000).
        """
        pixel_x, pixel_y = self.coordinate_mapper.to_pixels(norm_x, norm_y)
        logger.info(f"نقر على ({norm_x}, {norm_y}) -> بكسل ({pixel_x}, {pixel_y})")
        
        # تحريك الماوس أولاً لإظهار الحركة للـ User
        await self._page.mouse.move(pixel_x, pixel_y, steps=10)
        # النقر
        await self._page.mouse.down()
        await self._page.wait_for_timeout(100) # تأثير ضغطة
        await self._page.mouse.up()

    async def type_text(self, text: str, delay: int = 50) -> None:
        """كتابة نص في العنصر المركّز حالياً.

        Args:
            text: النص المراد كتابته.
            delay: تأخير بين الأحرف بالميلي ثانية (لمحاكاة الكتابة البشرية).
        """
        logger.info(f"كتابة نص: '{text[:20]}...'")
        await self._page.keyboard.type(text, delay=delay)

    async def wait_for_stable_state(self, timeout: int = 5000) -> None:
        """انتظار استقرار الصفحة (عدم وجود طلبات شبكية نشطة).

        Args:
            timeout: الحد الأقصى للانتظار بالميلي ثانية.
        """
        try:
            await self._page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            logger.warning("⚠️ انتهت مهلة انتظار استقرار الصفحة.")

    async def close(self) -> None:
        """إغلاق المتصفح وتحرير الموارد."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("تم إغلاق المتصفح.")
