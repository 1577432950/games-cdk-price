# -*- coding: utf-8 -*-
"""找到价格节点 → 往上追溯卡片容器与标题"""
import sys

sys.path.insert(0, ".")
import core

TASKS = [
    ("2Game", "https://www.2game.com/zh-cn/search?q=cyberpunk", "span.price-main"),
    ("Gamesplanet", "https://us.gamesplanet.com/search?query=cyberpunk", "span.price_current"),
    ("Kinguin", "https://www.kinguin.net/listing?phrase=cyberpunk", "span.min"),
    ("Loaded", "https://www.loaded.com/catalogsearch/result/?q=cyberpunk", "span.price"),
]

JS = """
(sel) => {
  const out = [];
  [...document.querySelectorAll(sel)].slice(0, 3).forEach(e => {
    const price = (e.textContent || '').trim();
    let p = e, chain = [];
    for (let i = 0; i < 6 && p; i++) {
      chain.push(p.tagName.toLowerCase() + (typeof p.className === 'string' && p.className
        ? '.' + p.className.trim().split(/\\s+/).slice(0, 3).join('.') : ''));
      p = p.parentElement;
    }
    // 找到第一个既含价格又含链接的祖先，当作卡片
    let card = e, href = '';
    for (let i = 0; i < 6 && card; i++) {
      const a = card.querySelector('a[href]');
      if (a && card.innerText && card.innerText.length < 400) {
        href = a.getAttribute('href') || '';
        break;
      }
      card = card.parentElement;
    }
    out.push({
      price,
      chain: chain.join('  <  '),
      cardText: (card ? card.innerText : '').replace(/\\s*\\n+\\s*/g, ' | ').trim().slice(0, 120),
      href,
      cardCls: card ? (card.className || '').slice(0, 90) : '',
    });
  });
  return out;
}
"""

s = core.BrowserSession(headless=True)
for name, url, sel in TASKS:
    pg = s.new_page()
    print("\n" + "=" * 74 + "\n" + name, "| sel:", sel)
    try:
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(9000)
        for r in pg.evaluate(JS, sel):
            print("  价格:", r["price"])
            print("  链  :", r["chain"][:250])
            print("  卡片:", r["cardText"])
            print("  类名:", r["cardCls"])
            print("  链接:", r["href"][:110])
            print()
    except Exception as e:
        print("ERROR", type(e).__name__, str(e)[:150])
    pg.close()
s.close()
