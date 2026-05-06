#!/usr/bin/env python3
"""Slidev E2E: multiple named checks, distinct exit codes, screenshots on failure.

Run via: webapp-testing scripts/with_server.py (see scripts/run-slidev-e2e.sh).
Console errors are logged only (lenient); they do not fail the run."""
from __future__ import annotations

import os
import re
import sys
from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("SLIDEV_URL", "http://127.0.0.1:3030")
MAX_SLIDES = 80
MIN_EXPECTED_TOTAL_SLIDES = 25
TOC_LINK_MAX = 28
TOC_LINK_MIN = 8


def _shot(page: Page, case_id: str, suffix: str = "fail") -> str:
    path = f"/tmp/slidev-e2e-{case_id}-{suffix}.png"
    try:
        page.screenshot(path=path, full_page=True)
    except Exception:
        path = "(screenshot failed)"
    return path


def _within_slide_canvas(page: Page, selector: str) -> tuple[bool, str]:
    ok = page.evaluate(
        """(sel) => {
          const root = document.querySelector('#slide-content');
          const el = document.querySelector(sel);
          if (!root || !el) return false;
          const r = root.getBoundingClientRect();
          const e = el.getBoundingClientRect();
          if (e.top < r.top - 2) return false;
          if (e.bottom > r.bottom + 2) return false;
          return true;
        }""",
        selector,
    )
    return bool(ok), selector


def _fail(page: Page | None, case_id: str, code: int, msg: str) -> None:
    extra = ""
    if page:
        extra = " screenshot=" + _shot(page, case_id)
    print(f"FAIL [{case_id}] exit={code}: {msg}{extra}", file=sys.stderr)
    raise SystemExit(code)


def main() -> None:
    console_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})

        def on_console(msg) -> None:
            if msg.type == "error":
                console_errors.append(msg.text)

        page.on("console", on_console)

        # slide01_title -> 10
        page.goto(f"{BASE}/1", wait_until="networkidle", timeout=120_000)
        title = page.title()
        if "BudgetFlow" not in title or "Slidev" not in title:
            _fail(page, "slide01_title", 10, f"unexpected title: {title!r}")

        # slide01_cover_layout -> 11
        for sel in ("#slide-content h1", "#slide-content .bf-subtitle", "#slide-content .bf-cover-btn"):
            ok, s = _within_slide_canvas(page, sel)
            if not ok:
                _fail(
                    page,
                    "slide01_cover_layout",
                    11,
                    f"element not fully inside #slide-content: {s}",
                )
        print("PASS slide01_title")
        print("PASS slide01_cover_layout")

        # slide02_toc_layout -> 12
        page.goto(f"{BASE}/2", wait_until="networkidle", timeout=90_000)
        body = page.inner_text("body")
        if "主线速览" not in body:
            _fail(page, "slide02_toc_layout", 12, "missing 主线速览")
        if "章节目录" not in body:
            _fail(page, "slide02_toc_layout", 12, "missing 章节目录")
        ok, _ = _within_slide_canvas(page, "#slide-content .bf-toc-card")
        if not ok:
            _fail(page, "slide02_toc_layout", 12, ".bf-toc-card clipped by canvas")
        if "Part I" not in body or "Part II" not in body:
            _fail(page, "slide02_toc_layout", 12, "Toc missing Part I / Part II")
        print("PASS slide02_toc_layout")

        # slide02_toc_depth -> 13
        n = page.locator("#slide-content .slidev-toc a").count()
        if n < TOC_LINK_MIN or n > TOC_LINK_MAX:
            _fail(
                page,
                "slide02_toc_depth",
                13,
                f"Toc link count {n} not in [{TOC_LINK_MIN}, {TOC_LINK_MAX}]",
            )
        print("PASS slide02_toc_depth")

        # slide_nav -> 30
        page.goto(f"{BASE}/1", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(300)
        before = page.url
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(500)
        after = page.url
        if after == before:
            _fail(page, "slide_nav", 30, f"ArrowRight did not change URL: {after}")
        if "/2" not in after and not after.rstrip("/").endswith("2"):
            # hash router fallback
            if after == before:
                _fail(page, "slide_nav", 30, "still on slide 1 after ArrowRight")
        print("PASS slide_nav")

        # slide_related_table -> 21
        related_idx = 0
        for i in range(1, MAX_SLIDES + 1):
            page.goto(f"{BASE}/{i}", wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(350)
            t = page.inner_text("body")
            if "相关工作一览" in t and "§4" in t:
                related_idx = i
                break
        if not related_idx:
            _fail(None, "slide_related_table", 21, "no slide with 相关工作一览 / §4")
        tables = page.locator("#slide-content table").count()
        if tables < 1:
            _fail(page, "slide_related_table", 21, "expected >=1 HTML table on related-work slide")
        raw_bad = "| :--- |" in page.inner_text("#slide-content") and tables == 0
        if raw_bad:
            _fail(page, "slide_related_table", 21, "table not rendered (pipes visible)")
        print("PASS slide_related_table")

        # slide_skill_catalog -> 22
        skill_idx = 0
        for i in range(1, MAX_SLIDES + 1):
            page.goto(f"{BASE}/{i}", wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(300)
            b = page.inner_text("body")
            if "技能索引" in b and "webapp-testing" in b and "brainstorming" in b:
                skill_idx = i
                break
        if not skill_idx:
            _fail(page, "slide_skill_catalog", 22, "skill catalog slide missing or empty")
        print("PASS slide_skill_catalog")

        # slide_footer_total -> 23
        page.goto(f"{BASE}/1", wait_until="networkidle", timeout=90_000)
        footer_text = ""
        ft = page.locator("footer")
        if ft.count():
            footer_text = ft.inner_text()
        else:
            footer_text = page.inner_text("body")
        m = re.search(r"(\d+)\s*/\s*(\d+)", footer_text)
        if not m:
            _fail(page, "slide_footer_total", 23, "could not parse slide x / total in footer/body")
        total = int(m.group(2))
        if total < MIN_EXPECTED_TOTAL_SLIDES:
            _fail(page, "slide_footer_total", 23, f"total slides {total} < {MIN_EXPECTED_TOTAL_SLIDES}")
        print("PASS slide_footer_total")

        if console_errors:
            print(f"WARN console_errors count={len(console_errors)} (lenient, not failing):")
            for line in console_errors[:20]:
                print("  ", line)
            if len(console_errors) > 20:
                print("   ... truncated")

        browser.close()

    print("OK: all E2E cases passed")


if __name__ == "__main__":
    main()
