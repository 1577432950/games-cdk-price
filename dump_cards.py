# -*- coding: utf-8 -*-
import asyncio, json
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

TASKS = [
    {"site": "fanatical", "url": "https://www.fanatical.com/zh-hans/search?search=cyberpunk%202077",
     "card": "[class*='hitCardStripe']"},
    {"site": "sonkwo", "url": "https://www.sonkwo.cn/store/search?keyword=%E8%B5%9B%E5%8D%9A%E6%9C%8B%E5%85%8B2077",
     "card": "[class*='SKC-sku'], [class*='sku-item'], [class*='SKC-product']"},
    {"site": "fhyx", "url": "https://www.fhyx.com/list/search?keyword=%E8%B5%9B%E5%8D%9A%E6%9C%8B%E5%85%8B2077",
     "card": "div.fhyxNewListLi"},
]

JS_CARD = """
(sel) => {
  const out=[];
  let cards=[...document.querySelectorAll(sel)];
  if(!cards.length) return ['NO CARDS for '+sel];
  cards.slice(0,3).forEach(c=>{
    const a=c.querySelector('a');
    out.push('TEXT: '+(c.innerText||'').replace(/\\n+/g,' | ').slice(0,180));
    out.push('   A: '+(a? a.getAttribute('href') : 'none'));
    out.push('   CLS: '+(c.className||'').slice(0,120));
    out.push('   HTML: '+(c.outerHTML||'').replace(/\\s+/g,' ').slice(0,700));
    out.push('');
  });
  return out;
}
"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = await b.new_context(user_agent=UA, locale="zh-CN", viewport={"width": 1440, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        for t in TASKS:
            pg = await ctx.new_page()
            print("\n" + "=" * 74)
            print("SITE:", t["site"])
            try:
                await pg.goto(t["url"], wait_until="domcontentloaded", timeout=60000)
                await pg.wait_for_timeout(8000)
                n = await pg.locator(t["card"]).count()
                print("card count:", n)
                for line in await pg.evaluate(JS_CARD, t["card"]):
                    print(line)
            except Exception as e:
                print("ERROR", type(e).__name__, str(e)[:200])
            await pg.close()
        await b.close()

asyncio.run(main())
