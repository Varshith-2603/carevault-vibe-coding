"""Full-page screenshots at several widths, with a horizontal-overflow check.

Requires playwright + Chrome and the app running on port 8599.
Run: python tests/browser/screenshots.py <out-dir> 1920,1440,390 "Dashboard|Hospital Visits"
"""
import sys, time
from playwright.sync_api import sync_playwright
OUT = sys.argv[1]; URL = "http://localhost:8599"
widths = [int(w) for w in sys.argv[2].split(",")] if len(sys.argv) > 2 else [1440]
pages = sys.argv[3].split("|") if len(sys.argv) > 3 else ["Dashboard"]
def wait_ready(p):
    p.wait_for_selector(".cv-page-title", timeout=60000)
    for _ in range(60):
        if p.locator('[data-testid="stStatusWidget"]').count() == 0: break
        time.sleep(0.25)
    time.sleep(1.2)
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True)
    for w in widths:
        ctx = b.new_context(viewport={"width": w, "height": 900}, device_scale_factor=1)
        p = ctx.new_page()
        errors = []
        p.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        p.goto(URL); wait_ready(p)
        for name in pages:
            if name != "Dashboard":
                if w > 768:
                    p.locator('[data-testid="stSidebar"] button', has_text=name).first.click()
                else:
                    p.locator('.st-key-cv_mobile_nav_wrap [data-testid="stSelectbox"] [role="combobox"], .st-key-cv_mobile_nav_wrap [data-testid="stSelectbox"] input').first.click()
                    p.get_by_role("option", name=name, exact=True).click()
                wait_ready(p)
            fn = f"{OUT}/{name.replace(' ','_').replace('&','and')}_{w}.png"
            h = p.evaluate("() => document.querySelector('[data-testid=stMain]').scrollHeight")
            p.set_viewport_size({"width": w, "height": min(h, 6000)}); time.sleep(3)
            p.screenshot(path=fn)
            p.set_viewport_size({"width": w, "height": 900})
            sw = p.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
            print(name, w, "scrollWidth/inner:", sw, "console errors:", errors[:3])
        ctx.close()
    b.close()
