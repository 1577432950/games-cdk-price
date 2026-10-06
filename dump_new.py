# -*- coding: utf-8 -*-
import sys

sys.path.insert(0, ".")
import core

TASKS = [
    ("2Game", "https://www.2game.com/zh-cn/search?q=cyberpunk",
     ["div.card-content", "div.card", "article", "div[class*='card']"]),
    ("Gamesplanet", "https://us.gamesplanet.com/search?query=cyberpunk",
     ["div.gp-prices", "article", "div[class*='card']", "li", "a[href*='/game/']"]),
    ("Kinguin", "https://www.kinguin.net/listing?phrase=cyberpunk",
     ["div[class*='UgMCw']", "div[class*='ixXPbm']", "a[href*='/product/']", "article"]),
    ("Loaded", "https://www.loaded.com/catalogsearch/result/?q=cyberpunk",
     ["li.product-item", "div.product-item-info", "ol.products-list li"]),
]

JS = """
(sels) => {
  const out = [];
  for (const s of sels) {
    const cs = [...document.querySelectorAll(s)];
    if (!cs.length) { out.push('--- ' + s + ' : 0'); continue; }
    out.push('--- ' + s + ' : ' + cs.length);
    cs.slice(0, 2).forEach(c => {
      const a = c.querySelector('a[href]');
      out.push('   TEXT: ' + (c.innerText || '').replace(/\\s*\\n+\\s*/g, ' | ').trim().slice(0, 130));
      out.push('   HREF: ' + (a ? a.getAttribute('href') : 'none'));
      out.push('   HTML: ' + (c.outerHTML || '').replace(/\\s+/g, ' ').slice(0, 500));
    });
  }
  return out;
}
"""

s = core.BrowserSession(headless=True)
for name, url, sels in TASKS:
    pg = s.new_page()
    print("\n" + "=" * 74 + "\n" + name, "|", url)
    try:
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(9000)
        for line in pg.evaluate(JS, sels):
            print(line[:560])
    except Exception as e:
        print("ERROR", type(e).__name__, str(e)[:150])
    pg.close()
s.close()
