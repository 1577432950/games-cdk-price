# -*- coding: utf-8 -*-
import asyncio
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

JS = """
() => {
  const cs=[...document.querySelectorAll('div.fhyxNewListLi')];
  return {count: cs.length, items: cs.slice(0,4).map(c=>{
    const a=c.querySelector('a');
    return {
      text:(c.innerText||'').replace(/\\n+/g,' | ').slice(0,150),
      href: a? a.getAttribute('href'):null,
      price: (c.querySelector('span.price')||{}).innerText,
      old: (c.querySelector('span.oldprice')||{}).innerText,
      title: (c.querySelector('.gameName,.title,h3,h2,a')||{}).innerText,
    };
  })};
}
"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = await b.new_context(user_agent=UA, locale="zh-CN", viewport={"width": 1440, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        pg = await ctx.new_page()
        await pg.goto("https://www.fhyx.com/", wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(3500)
        loc = pg.locator("input[name='keyword']").first
        await loc.fill("赛博朋克2077")
        await pg.wait_for_timeout(500)
        await loc.press("Enter")
        await pg.wait_for_timeout(7000)
        print("URL:", pg.url, "| title:", await pg.title())
        r = await pg.evaluate(JS)
        print("count:", r["count"])
        for it in r["items"]:
            print("  TEXT:", it["text"])
            print("    href:", it["href"], "| price:", it["price"], "| old:", it["old"], "| title:", it["title"])
        await b.close()

asyncio.run(main())
