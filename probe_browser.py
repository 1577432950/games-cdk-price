# -*- coding: utf-8 -*-
"""用系统 Edge 试探 Cloudflare 站点，并勘察卡片结构"""
import sys

sys.path.insert(0, ".")
import core

TASKS = [
    ("InstantGaming", "https://www.instant-gaming.com/zh/search/?query=cyberpunk%202077"),
    ("GG.deals", "https://gg.deals/zh/games/?title=cyberpunk"),
    ("2Game", "https://www.2game.com/zh-cn/search?q=cyberpunk"),
    ("Gamesplanet", "https://us.gamesplanet.com/search?query=cyberpunk"),
    ("Kinguin", "https://www.kinguin.net/listing?phrase=cyberpunk"),
    ("Loaded(CDKeys)", "https://www.loaded.com/catalogsearch/result/?q=cyberpunk"),
]

JS = """
() => {
  const out = [];
  document.querySelectorAll('*').forEach(e => {
    if (e.children.length === 0) {
      const t = (e.textContent || '').trim();
      if (/[$€£¥][\\d,.]/.test(t) && t.length < 25) {
        let p = e, ch = [];
        for (let i = 0; i < 3 && p; i++) {
          ch.push(p.tagName.toLowerCase() + (typeof p.className === 'string' && p.className
            ? '.' + p.className.trim().split(/\\s+/).slice(0, 2).join('.') : ''));
          p = p.parentElement;
        }
        out.push(t + '  <<<  ' + ch.join(' < '));
      }
    }
  });
  return out.slice(0, 8);
}
"""

s = core.BrowserSession(headless=True)
for name, url in TASKS:
    pg = s.new_page()
    print("\n" + "=" * 72)
    print(f"{name}: {url}")
    try:
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(12000)
        try:
            pg.wait_for_function("() => !/Just a moment|Checking/i.test(document.title)",
                                 timeout=20000)
        except Exception:
            pass
        print("  title:", pg.title(), "| final:", pg.url[:90])
        for x in pg.evaluate(JS):
            print("   ", x[:170])
    except Exception as e:
        print("  ERROR", type(e).__name__, str(e)[:150])
    pg.close()
s.close()
