"""Take screenshots of footy pages at desktop + mobile widths for visual review."""

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = "http://127.0.0.1:8000"
OUT = Path(__file__).parent.parent / "screenshots"
OUT.mkdir(exist_ok=True)

PAGES: list[tuple[str, str]] = [
    ("index", "/"),
    ("league-pl", "/league/PL"),
    ("league-pl-table", "/league/PL?tab=table"),
    ("league-pl-scorers", "/league/PL?tab=scorers"),
    ("league-cl", "/league/CL"),
]

VIEWPORTS = [
    ("desktop", 1440, 900),
    ("mobile", 390, 844),
]


def run() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for vp_name, w, h in VIEWPORTS:
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
            page = ctx.new_page()
            for slug, path in PAGES:
                url = f"{ROOT}{path}"
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(800)  # fonts settle
                out = OUT / f"{slug}-{vp_name}.png"
                page.screenshot(path=str(out), full_page=True)
                print(f"  ok {out.name} ({out.stat().st_size // 1024}KB)")
            ctx.close()

        # Sample one match-detail page (need a scheduled match id from the DB)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        # Use a known match — Premier League next fixture exists at this URL
        page.goto(f"{ROOT}/league/PL", wait_until="networkidle")
        href = page.evaluate(
            "() => {"
            " const a = document.querySelector('a[href^=\"/match/\"]');"
            " return a ? a.getAttribute('href') : null;"
            "}"
        )
        if href:
            page.goto(f"{ROOT}{href}", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1200)
            out = OUT / "match-detail-desktop.png"
            page.screenshot(path=str(out), full_page=True)
            print(f"  ✓ {out.name} ({out.stat().st_size // 1024}KB)")
        browser.close()


if __name__ == "__main__":
    run()
