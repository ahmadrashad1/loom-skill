"""In-page JavaScript: visible cursor, click ripple, highlight box, redaction, title cards.

Headless Chromium does not render the OS cursor, so we draw one that follows
the real (Playwright-driven) mouse events.
"""

import html
import json

CURSOR_JS = r"""
(() => {
  const install = () => {
    if (document.getElementById('__loom_cursor')) return;
    const root = document.documentElement;
    if (!root) return;
    const style = document.createElement('style');
    style.id = '__loom_cursor_style';
    style.textContent = `
      #__loom_cursor{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;
        pointer-events:none;transform:translate(var(--x,-100px),var(--y,-100px));
        filter:drop-shadow(0 1px 2px rgba(0,0,0,.45));transition:none}
      .__loom_ripple{position:fixed;z-index:2147483646;pointer-events:none;width:36px;height:36px;
        margin:-18px 0 0 -18px;border-radius:50%;border:3px solid rgba(255,190,40,.95);
        animation:__loom_rip .55s ease-out forwards}
      @keyframes __loom_rip{from{transform:scale(.3);opacity:1}to{transform:scale(1.6);opacity:0}}
      .__loom_hl{position:fixed;z-index:2147483645;pointer-events:none;border-radius:10px;
        box-shadow:0 0 0 4px rgba(255,190,40,.95),0 0 0 9999px rgba(0,0,0,.18);
        transition:opacity .3s}`;
    root.appendChild(style);
    const c = document.createElement('div');
    c.id = '__loom_cursor';
    c.innerHTML = `<svg width="26" height="26" viewBox="0 0 26 26"><path d="M3 2 L3 21 L8 16.5 L11.5 24 L15 22.5 L11.5 15 L18 15 Z"
      fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
    root.appendChild(c);
    const p = window.__loom_pos;
    if (p) { c.style.setProperty('--x', p[0] + 'px'); c.style.setProperty('--y', p[1] + 'px'); }
  };
  if (!window.__loom_listeners) {
    window.__loom_listeners = true;
    document.addEventListener('mousemove', e => {
      window.__loom_pos = [e.clientX, e.clientY];
      install();
      const c = document.getElementById('__loom_cursor');
      if (c) { c.style.setProperty('--x', e.clientX + 'px'); c.style.setProperty('--y', e.clientY + 'px'); }
    }, true);
    document.addEventListener('mousedown', e => {
      const r = document.createElement('div');
      r.className = '__loom_ripple';
      r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
      document.documentElement.appendChild(r);
      setTimeout(() => r.remove(), 650);
    }, true);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();
"""

HIGHLIGHT_JS = r"""
([el, ms]) => {
  const r = el.getBoundingClientRect();
  const d = document.createElement('div');
  d.className = '__loom_hl';
  const pad = 6;
  Object.assign(d.style, {left: (r.left - pad) + 'px', top: (r.top - pad) + 'px',
    width: (r.width + 2 * pad) + 'px', height: (r.height + 2 * pad) + 'px', opacity: 0});
  document.documentElement.appendChild(d);
  requestAnimationFrame(() => d.style.opacity = 1);
  setTimeout(() => { d.style.opacity = 0; setTimeout(() => d.remove(), 350); }, ms);
}
"""


def redact_js(selectors: list[str]) -> str:
    css = ",".join(selectors) + "{filter:blur(9px) !important;}"
    return f"""
(() => {{
  const add = () => {{
    if (document.getElementById('__loom_redact')) return;
    const s = document.createElement('style'); s.id = '__loom_redact';
    s.textContent = {json.dumps(css)};
    (document.head || document.documentElement).appendChild(s);
  }};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
}})();
"""


def title_html(heading: str, sub: str | None) -> str:
    h = html.escape(heading)
    s = f"<p>{html.escape(sub)}</p>" if sub else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;height:100%;}}
body{{display:flex;align-items:center;justify-content:center;
  background:radial-gradient(circle at 30% 20%,#25324a 0%,#111722 60%,#0b0f17 100%);
  font-family:'Inter','Cantarell','Noto Sans',system-ui,sans-serif;color:#f4f6fb}}
.card{{max-width:70%;text-align:left}}
.bar{{width:72px;height:6px;border-radius:3px;background:#ffbe28;margin-bottom:34px}}
h1{{font-size:76px;line-height:1.08;margin:0 0 22px;font-weight:700;letter-spacing:-1.5px}}
p{{font-size:34px;margin:0;color:#b7c0d3;line-height:1.35}}
</style></head><body><div class="card"><div class="bar"></div><h1>{h}</h1>{s}</div></body></html>"""
