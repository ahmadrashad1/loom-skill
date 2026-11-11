"""Explore a page before planning: screenshot + interactive elements with
selectors that Playwright can use directly in plan.json."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

COLLECT_JS = r"""
() => {
  const out = [];
  const q = 'a[href],button,input,select,textarea,[role=button],[role=link],[role=tab],[role=menuitem],[contenteditable=true]';
  const roleOf = el => el.getAttribute('role') || ({A:'link',BUTTON:'button',SELECT:'combobox',TEXTAREA:'textbox'}[el.tagName]
     || (el.tagName==='INPUT' ? (['button','submit','reset'].includes(el.type)?'button':(el.type==='checkbox'?'checkbox':(el.type==='radio'?'radio':'textbox'))) : el.tagName.toLowerCase()));
  const nameOf = el => (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder || el.title || '').trim().replace(/\s+/g,' ').slice(0,60);
  for (const el of document.querySelectorAll(q)) {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || st.visibility === 'hidden' || st.display === 'none') continue;
    const role = roleOf(el), name = nameOf(el);
    let sel;
    if (el.id && /^[A-Za-z][\w-]*$/.test(el.id)) sel = '#' + el.id;
    else if (el.getAttribute('data-testid')) sel = `[data-testid="${el.getAttribute('data-testid')}"]`;
    else if (name) sel = `role=${role}[name="${name.replace(/"/g,'\\"')}"]`;
    else if (el.name) sel = `${el.tagName.toLowerCase()}[name="${el.name}"]`;
    else continue;
    out.push({role, name, selector: sel, inViewport: r.top < innerHeight && r.bottom > 0,
              box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]});
  }
  return out;
}
"""


def inspect(url: str, out_dir: Path, width: int = 1920, height: int = 1080,
            full_page: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        shot = out_dir / "page.png"
        page.screenshot(path=str(shot), full_page=full_page)
        elements = page.evaluate(COLLECT_JS)
        info = {"url": page.url, "title": page.title(), "screenshot": str(shot),
                "elements": elements}
        browser.close()
    (out_dir / "elements.json").write_text(json.dumps(info, indent=2))
    return info
