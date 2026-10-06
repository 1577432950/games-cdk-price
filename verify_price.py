# -*- coding: utf-8 -*-
import asyncio, json
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

GMG_JS = """
() => [...document.querySelectorAll('.product-block')].slice(0,4).map(c => {
  const m = (c.getAttribute('ng-init')||'').match(/init\\('([^']+)'\\)/);
  if(!m) return 'no ng-init';
  const s = m[1] + '='.repeat((4 - m[1].length % 4) % 4);
  const bin = atob(s);
  let str='';
  for (let i=0;i<bin.length;i+=2) str += String.fromCharCode(bin.charCodeAt(i) | (bin.charCodeAt(i+1)<<8));
  const j = JSON.parse(str);
  const e = j.selectedEdition || {};
  return {sku:e.sku, rrp:e.rrp, cur:e.currentPrice, url:e.url, txt:(c.innerText||'').replace(/\\s*\\n+\\s*/g,' | ').trim().slice(0,120)};
})
"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        c = await b.new_context(user_agent=UA, locale="zh-CN", viewport={"width": 1440, "height": 900})

        pg = await c.new_page()
        await pg.goto("https://www.greenmangaming.com/zh/search/?query=hogwarts+legacy",
                      wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(8000)
        print("=== GMG 原始数据 ===")
        for x in await pg.evaluate(GMG_JS):
            print(json.dumps(x, ensure_ascii=False)[:320])
        await pg.close()

        pg = await c.new_page()
        await pg.goto("https://www.fhyx.com/", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(3000)
        loc = pg.locator("input[name='keyword']").first
        await loc.fill("霍格沃茨之遗")
        await loc.press("Enter")
        await pg.wait_for_timeout(6500)
        print("\n=== 凤凰 原始卡片文本 ===")
        rows = await pg.evaluate("""
            () => [...document.querySelectorAll('div.fhyxNewListLi')].slice(0,5).map(c => ({
              raw: (c.innerText||'').replace(/\\s*\\n+\\s*/g,' | ').trim().slice(0,150),
              price: (c.querySelector('span.price')||{}).innerText,
              old: (c.querySelector('span.oldprice')||{}).innerText,
            }))""")
        for r in rows:
            print(json.dumps(r, ensure_ascii=False)[:280])
        await pg.close()
        await b.close()

asyncio.run(main())
