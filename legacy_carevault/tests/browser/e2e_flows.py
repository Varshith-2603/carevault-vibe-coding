"""Browser end-to-end check of CareVault interactions.

Requires: pip install playwright, Google Chrome, and the app running:
    streamlit run app.py --server.port 8599
Run: python tests/browser/e2e_flows.py <output-folder-for-screenshots>
"""
import sys, time, re
from playwright.sync_api import sync_playwright, expect
SP = sys.argv[1]
results = []
def ok(name, cond, extra=""):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name, extra)
def settle(p, t=1.0):
    time.sleep(0.4)
    for _ in range(80):
        if p.locator('[data-testid="stStatusWidget"]').count() == 0: break
        time.sleep(0.2)
    time.sleep(t)
def dialog(p): return p.locator('[role="dialog"]')
def pick(scope, label, text):
    box = scope.get_by_role("combobox", name=re.compile(re.escape(label))).first
    box.click(); time.sleep(0.3); p_ = box.page; p_.keyboard.type(text); time.sleep(0.5); p_.keyboard.press("Enter"); time.sleep(0.3)
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    p = ctx.new_page(); errs=[]
    p.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    p.goto("http://localhost:8599"); p.wait_for_selector(".cv-page-title"); settle(p)

    # 1. Add record with validation
    p.get_by_role("button", name="Add record").first.click(); settle(p)
    p.wait_for_selector("[role=dialog]", timeout=20000)
    ok("add dialog opens", dialog(p).count() == 1)
    d = dialog(p)
    d.get_by_role("button", name="Save record").click(); settle(p)
    ok("validation errors shown", d.locator(".cv-field-error").count() >= 3, d.locator(".cv-field-error").count())
    pick(d, "Hospital or clinic", "Test General Hospital")
    pick(d, "Department", "Neurology")
    pick(d, "Doctor you saw", "Dr. Test Person")
    d.get_by_role("textbox", name=re.compile("Reason for visit")).fill("Headache review"); 
    d.get_by_role("button", name="Save record").click(); settle(p, 1.5)
    d = dialog(p)
    ok("saved → view shows record", d.count() == 1 and "Headache review" in d.inner_text(), )
    ok("marked as added by you", "added by you" in d.inner_text().lower())
    p.screenshot(path=f"{SP}/e2e_view.png")

    # 2. Edit
    d.get_by_role("button", name="Edit").click(); settle(p)
    d = dialog(p); d.get_by_role("textbox", name=re.compile("Reason for visit")).fill("Headache follow-up")
    d.get_by_role("button", name="Save changes").click(); settle(p, 1.5)
    ok("edit saved", "Headache follow-up" in dialog(p).inner_text())

    # 3. Delete with confirmation
    dialog(p).get_by_role("button", name="Delete").click(); settle(p)
    ok("delete confirm shown", "can't be undone" in dialog(p).inner_text())
    p.screenshot(path=f"{SP}/e2e_delete.png")
    dialog(p).get_by_role("button", name="Delete permanently").click(); settle(p, 1.5)
    ok("dialog closed after delete", dialog(p).count() == 0)
    ok("dashboard count back to 14 visits", "14" in p.locator(".st-key-cvstat_visits").inner_text())

    # 4. Global search
    s = p.get_by_placeholder("Search all records…").first
    s.fill("Metoprolol"); s.press("Enter"); settle(p, 1.5)
    title = p.locator(".cv-page-title").inner_text()
    bar = p.locator(".cv-results-bar").first.inner_text()
    ok("search navigates to All Records", title == "All Records", bar)
    ok("search finds results", re.search(r"— (\d+) of", bar) and int(re.search(r"— (\d+) of", bar).group(1)) > 0)
    p.get_by_role("button", name="Clear search").click(); settle(p)
    ok("clear search resets", "All your records" in p.locator(".cv-results-bar").first.inner_text())

    # 5. Filters + reset on visits
    p.locator('[data-testid="stSidebar"] button', has_text="Hospital Visits").click(); settle(p)
    pick(p.locator(".st-key-cvfilters_visits"), "Department", "Cardiology"); settle(p)
    bar = p.locator(".cv-results-bar").first.inner_text()
    ok("department filter applied", "Showing 4 of 14" in bar, bar)
    p.locator('[data-testid="stSidebar"] button', has_text="Dashboard").click(); settle(p)
    p.locator('[data-testid="stSidebar"] button', has_text="Hospital Visits").click(); settle(p)
    bar = p.locator(".cv-results-bar").first.inner_text()
    ok("filter persists across page switch", "Showing 4 of 14" in bar, bar)
    p.get_by_role("button", name="Reset filters").click(); settle(p)
    ok("reset filters", "Showing 14 of 14" in p.locator(".cv-results-bar").first.inner_text())
    p.locator('[data-testid="stSidebar"] button', has_text="Dashboard").click(); settle(p)
    p.locator('[data-testid="stSidebar"] button', has_text="Hospital Visits").click(); settle(p)
    ok("reset survives page switch", "Showing 14 of 14" in p.locator(".cv-results-bar").first.inner_text(),
       p.locator(".cv-results-bar").first.inner_text())

    # 6. Report viewer for processing report + Escape dismissal
    p.locator('[data-testid="stSidebar"] button', has_text="Scans & Diagnostics").click(); settle(p)
    p.get_by_role("button", name="View status").first.click(); settle(p)
    ok("processing report flagged not final", "not final" in dialog(p).inner_text())
    p.screenshot(path=f"{SP}/e2e_report.png")
    p.keyboard.press("Escape"); settle(p)
    ok("escape closes dialog", dialog(p).count() == 0)
    p.locator("[data-testid=stButtonGroup] button", has_text=re.compile(r"^Imaging$")).first.click(); settle(p)
    ok("dialog stays closed after other interaction", dialog(p).count() == 0)

    # 7. Prescription refill
    p.locator('[data-testid="stSidebar"] button', has_text="Prescriptions").click(); settle(p)
    p.get_by_role("button", name="View medication").first.click(); settle(p)
    txt = dialog(p).inner_text()
    before = int(re.search(r"Refills remaining\s*\n?\s*(\d+)", txt, re.I).group(1))
    dialog(p).get_by_role("button", name="Log a refill collected").click(); settle(p, 1.5)
    after = int(re.search(r"Refills remaining\s*\n?\s*(\d+)", dialog(p).inner_text(), re.I).group(1))
    ok("refill decrements", after == before - 1, f"{before}->{after}")
    dialog(p).locator("button", has_text="Close").first.click(); settle(p)
    ok("close button closes", dialog(p).count() == 0)

    # 8. Appointment: calendar + cancel
    p.locator('[data-testid="stSidebar"] button', has_text="Appointments").click(); settle(p)
    p.get_by_role("button", name="View details").first.click(); settle(p)
    with p.expect_download() as dl:
        dialog(p).get_by_role("button", name="Add to calendar").click()
    path = dl.value.path(); body = open(path).read()
    ok("ics download valid", "BEGIN:VEVENT" in body and "DTSTART" in body)
    dialog(p).get_by_role("button", name="Cancel appointment").click(); settle(p)
    dialog(p).get_by_role("button", name="Yes, cancel it").click(); settle(p, 1.5)
    ok("appointment cancelled", "Cancelled" in dialog(p).inner_text())
    dialog(p).locator("button", has_text="Close").first.click(); settle(p)

    # 9. CSV export
    p.locator('[data-testid="stSidebar"] button', has_text="Hospital Visits").click(); settle(p)
    with p.expect_download() as dl:
        p.get_by_role("button", name="Export CSV").click()
    csv = open(dl.value.path(), encoding="utf-8-sig").read().splitlines()
    ok("csv export rows", len(csv) == 15 and csv[0].startswith("Date,Hospital"), len(csv))

    ok("no console errors", not errs, errs[:3])
    b.close()
print(f"\n{sum(r for _, r in results)}/{len(results)} passed")
