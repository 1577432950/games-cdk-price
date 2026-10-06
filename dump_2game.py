# -*- coding: utf-8 -*-
"""排查 2Game：搜索页到底渲染了什么"""
import sys

sys.path.insert(0, ".")
import core

URL = "https://www.2game.com/zh-cn/search?q=cyberpunk"

JS = """
() => {
  const spans = [...document.querySelectorAll('span.price-main')];
  const cards = [...document.querySelectorAll('div.form-product-card-2game-container')];
  const info = {
    url: location.href,
    title: document.title,
    priceMain: spans.length,
    cardCls: cards.length,
    bodyLen: document.body.innerText.length,
    head: document.body.innerText.replace(/\\s*\\n+\\s*/g, ' | ').slice(0, 400),
  };
  // 找所有 class 含 card 的容器
  const cand = {};
  document.querySelectorAll('[class*="card"]').forEach(e => {
    const k = (typeof e.className === 'string' ? e.className : '').trim().slice(0, 80);
    cand[k] = (cand[k] || 0) + 1;
  });
  info.cardClasses = Object.entries(cand).slice(0, 25);
  // 商品链接
  const links = [...document.querySelectorAll('a[href*="/products/"]')]
    .slice(0, 5).map(a => a.getAttribute('href'));
  info.productLinks = links;
  // 第一个价格节点的祖先链
  if (spans.length) {
    let p = spans[0], chain = [];
    for (let i = 0; i < 8 && p; i++) {
      chain.push(p.tagName.toLowerCase() + (typeof p.className === 'string' && p.className
        ? '.' + p.className.trim().split(/\\s+/).slice(0, 2).join('.') : ''));
      p = p.parentElement;
    }
    info.chain = chain.join('  <  ');
    info.firstCardText = (spans[0].closest('[class*="card"]') || {}).innerText;
  }
  return info;
}
"""

s = core.BrowserSession(headless=True)
pg = s.new_page()
try:
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    for ms in (3000, 5000, 5000):
        pg.wait_for_timeout(ms)
    r = pg.evaluate(JS)
    for k, v in r.items():
        print(f"{k}: {v}")
finally:
    pg.close()
    s.close()
