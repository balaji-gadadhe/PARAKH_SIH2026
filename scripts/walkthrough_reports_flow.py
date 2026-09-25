"""
Browser walkthrough of the D-029 report-to-inbox flow (headless Chromium
via Playwright). Drives the real UI end-to-end and fails on any console
error, failed request, or broken assertion. Screenshots land in
`scripts/walkthrough_shots/` (gitignored).

Prereqs: backend on :8000, frontend dev server on :3000.
Run:  ./venv/Scripts/python.exe scripts/walkthrough_reports_flow.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, ConsoleMessage, Response

FRONT = "http://localhost:3000"
BACK = "http://127.0.0.1:8000"
SHOTS = Path(__file__).resolve().parent / "walkthrough_shots"
MP_NAME = "Shri Harbhajan Singh (2022-28)"
WORK_ID = "80673|Shri Harbhajan Singh (2022-28)|Sitting Rajya Sabha|Punjab"

import urllib.request
import urllib.error


def api_get(path: str) -> dict:
    with urllib.request.urlopen(BACK + path) as r:
        return json.loads(r.read())


issues: list[str] = []
passed = 0


def ok(label: str) -> None:
    global passed
    passed += 1
    print(f"  PASS {label}")


def fail(label: str, detail: str = "") -> None:
    issues.append(f"{label} {detail}")
    print(f"  FAIL {label} {detail}")


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)


def expect(cond: bool, label: str, detail: str = "") -> bool:
    if cond:
        ok(label)
        return True
    fail(label, detail)
    return False


console_errors: list[str] = []
failed_requests: list[str] = []


def on_console(msg: ConsoleMessage) -> None:
    if msg.type == "error":
        console_errors.append(msg.text[:200])


def on_response(response: Response) -> None:
    if response.status >= 400:
        failed_requests.append(f"{response.status} {response.url[:150]}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    SHOTS.mkdir(exist_ok=True)
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", on_console)
        page.on("response", on_response)

        # [0] Home loads
        print("\n[0] Public homepage")
        page.goto(FRONT, wait_until="networkidle")
        expect(page.locator("text=Smart India Hackathon").count() > 0, "homepage renders")

        # [1] MoSPI login
        print("\n[1] MoSPI login -> dashboard")
        page.goto(FRONT + "/login?role=mospi", wait_until="networkidle")
        page.locator("input").nth(0).fill("mospi-demo")
        page.locator("input").nth(1).fill("demo")
        page.locator("button[type=submit]:has-text('Login')").click()
        page.wait_for_url("**/dashboard**", timeout=15_000)
        expect("role=mospi" in page.url, "landed on MoSPI dashboard", page.url)

        # [2] Works tab -> investigate the CRITICAL work
        print("\n[2] Works tab -> Investigate work 80673")
        page.locator("nav button:has-text('Works')").click()
        page.wait_for_selector("table tbody tr", timeout=20_000)
        search = page.locator("input[placeholder*='Search']").first
        search.fill("80673|")
        page.wait_for_timeout(900)  # debounce + fetch
        row = page.locator("a:has-text('Investigate')").first
        expect(row.count() > 0, "Investigate link present")
        row.click()
        page.wait_for_url("**/investigation/**", timeout=15_000)
        page.wait_for_selector("text=Report this work", timeout=20_000)
        ok("dossier page loads with Report CTA")
        shot(page, "01_dossier")

        # [3] Report modal -> deliver
        print("\n[3] Report modal -> deliver to MP")
        page.locator("button:has-text('Report this work')").click()
        expect(page.locator("text=Report work 80673").count() > 0, "modal opens")
        preview = page.locator("text=Will be delivered to:").locator("..").inner_text()
        expect(MP_NAME in preview, "delivery preview shows target MP", preview[:120])
        page.locator("textarea").fill("Browser walkthrough: please review this flagged work")
        shot(page, "02_report_modal")
        page.locator("button:has-text('Submit report')").click()
        page.wait_for_selector("text=Report delivered", timeout=10_000)
        expect(
            page.locator("text=appears in their Alerts tab").count() > 0,
            "success screen confirms inbox delivery",
        )
        shot(page, "03_report_delivered")
        page.locator("button:has-text('Close')").click()

        # [4] Back link returns to MoSPI dashboard
        print("\n[4] Back link")
        page.locator("a:has-text('Back to')").first.click()
        page.wait_for_url("**/dashboard**", timeout=15_000)
        expect("role=mospi" in page.url, "back link returns to MoSPI dashboard", page.url)

        # [5] Isolation: another MP's inbox must be empty
        print("\n[5] Scope isolation (different MP)")
        other = api_get("/api/reports?role=mp&mp=Another%20MP%20Entirely")
        expect(other["total"] == 0, "other MP inbox empty (API isolation)")

        # [6] Target MP: login -> picker -> dashboard -> Alerts inbox
        print("\n[6] MP login -> Alerts inbox")
        page.goto(FRONT + "/login?role=mp", wait_until="networkidle")
        page.wait_for_selector("input", timeout=10_000)
        page.locator("input").nth(0).fill("mp-demo")
        page.locator("input").nth(1).fill("demo")
        page.locator("button[type=submit]:has-text('Login')").click()
        picker_input = page.wait_for_selector(
            "input[placeholder*='Search MP']", timeout=15_000
        )
        picker_input.fill(MP_NAME)
        page.wait_for_timeout(700)
        page.locator(f"button:has-text('{MP_NAME}')").first.click()
        page.wait_for_url("**/dashboard?role=mp**", timeout=15_000)
        expect(
            "mp=Shri%20Harbhajan" in page.url, "MP dashboard with identity", page.url
        )
        page.locator("nav button:has-text('Alerts')").click()
        page.wait_for_selector("text=This needs your attention", timeout=20_000)
        # Collapsed-by-default dropdown: wait for the inbox fetch to resolve —
        # the NEW badge appears on the header row; expand to see the rows.
        page.wait_for_selector(r"text=/\d+ new/", timeout=20_000)
        expect(
            page.locator(r"text=/\d+ new/").first.count() > 0,
            "NEW-count badge visible on collapsed header",
        )
        page.locator("button:has-text('This needs your attention')").first.click()
        page.wait_for_selector("text=Reported by", timeout=20_000)  # rows loaded
        shot(page, "04_mp_alerts_inbox")
        inbox_items = page.locator("section:has-text('This needs your attention') li")
        expect(inbox_items.count() > 0, "inbox shows reports for this MP")
        expect(
            page.locator("text=MoSPI Audit Cell").first.count() > 0,
            "report shows who sent it",
        )
        expect(
            page.locator("text=Browser walkthrough").first.count() > 0,
            "report comment visible",
        )

        # [6b] Bell icon in the header shows the unread count
        print("\n[6b] Bell badge")
        bell = page.locator("button[aria-label*='Notifications']")
        expect(bell.count() == 1, "bell button present in header")
        expect(
            bell.locator("span").count() > 0, "bell shows unread-count badge"
        )

        # [7] Acknowledge + confirm-guarded clear-all
        print("\n[7] Acknowledge the report")
        ack_btn = page.locator("button:has-text('Acknowledge')").first
        expect(ack_btn.count() > 0, "Acknowledge button present")
        expect(
            page.locator("button:has-text('Clear all')").count() > 0,
            "Clear all button present",
        )
        # Two-click guard: first click arms it (button label changes),
        # nothing is deleted until the second click.
        page.locator("button:has-text('Clear all')").click()
        expect(
            page.locator("button:has-text('Really clear all?')").count() == 1,
            "clear requires second confirmation click",
        )
        expect(
            page.locator("text=Reported by").count() > 0,
            "no deletion after first click (rows still present)",
        )
        page.locator("button:has-text('Really clear all?')").click()
        page.wait_for_timeout(1200)
        expect(
            page.locator("text=No reports addressed to you yet").count() > 0,
            "second click clears the inbox",
        )
        shot(page, "06_cleared")

        # [7b] Re-report so acknowledge flow still has a row to work with
        api_post = None
        import urllib.request as _ur
        _req = _ur.Request(
            BACK + "/api/reports",
            data=json.dumps(
                {
                    "project_id": WORK_ID,
                    "reported_by_role": "MoSPI Audit Cell",
                    "target_role": "MP",
                    "comment": "Re-seeded after clear test",
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _ur.urlopen(_req) as _r:
            api_post = json.loads(_r.read())
        expect(api_post is not None and api_post.get("status") == "NEW", "re-seeded a report")
        page.locator("button:has-text('Refresh')").click()
        page.wait_for_timeout(800)

        # [7c] Expandable report detail: click the row chevron -> snapshot loads
        row_toggle = page.locator("button[aria-expanded]").filter(
            has=page.locator("span")
        ).last
        row_toggle.click()
        page.wait_for_selector("text=Why it is flagged", timeout=15_000)
        expect(
            page.locator("text=Why it is flagged — engine scores").count() == 1,
            "expanded detail shows engine score strip",
        )
        expect(
            page.locator("text=recommended").first.count() > 0,
            "expanded detail shows financial facts",
        )
        shot(page, "07_report_detail")
        row_toggle.click()  # collapse again

        ack_btn = page.locator("button:has-text('Acknowledge')").first
        ack_btn.click()
        page.wait_for_timeout(1200)
        expect(page.locator("text=Acknowledged").count() > 0, "status flips to ACKNOWLEDGED")
        expect(
            page.locator(r"text=/\d+ new/").first.count() == 0,
            "NEW badge disappears after ack (live header refresh)",
        )
        shot(page, "05_acknowledged")

        # [8] Deep-link refresh on ?tab=alerts
        print("\n[8] Deep-link refresh on ?tab=alerts")
        base = page.url.split("&tab=")[0]
        page.goto(base + "&tab=alerts", wait_until="networkidle")
        page.wait_for_timeout(1000)
        expect(
            page.locator("nav button:has-text('Alerts')")
            .filter(has_not=page.locator("x"))  # placeholder; count check below
            .count()
            >= 0,
            "placeholder",
        ) if False else None
        active = page.locator("nav button.bg-primary-tint:has-text('Alerts')")
        expect(active.count() == 1, "Alerts tab active after refresh")

        # [9] Console / network hygiene
        print("\n[9] Hygiene")
        real_console = [e for e in console_errors if "favicon" not in e.lower()]
        expect(len(real_console) == 0, "no console errors", "; ".join(real_console[:3]))
        real_net = [r for r in failed_requests if "favicon" not in r]
        expect(len(real_net) == 0, "no failed network requests", "; ".join(real_net[:3]))

        browser.close()

    print(f"\n{'='*60}")
    print(f"Walkthrough: {passed} passed, {len(issues)} failed in {time.time()-t0:.0f}s")
    if issues:
        print("ISSUES:")
        for i in issues:
            print(" -", i)
        return 1
    print("ALL GREEN - report-to-inbox flow works in a real browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
