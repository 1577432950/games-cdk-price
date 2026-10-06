# -*- coding: utf-8 -*-
import asyncio
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

JS = """
() => [...document.querySelectorAll('.product-block')].slice(0,5).map(c => {
  const raw = c.getAttribute('ng-init') || '';
  const m = raw.match(/init\\('([^']+)'\\)/);
  let sku='', url='';
  if (m) {
    try {
      const s = m[1] + '='.repeat((4 - m[1].length % 4) % 4);
      const bin = atob(s);
      let str = '';
      for (let i = 0; i < bin.length; i += 2) {
        str += String.fromCharCode(bin.charCodeAt(i) | (bin.charCodeAt(i+1) << 8));
      }
      const j = JSON.parse(str);
      sku = (j.selectedEdition && j.selectedEdition.sku) || '';
      url = (j.selectedEdition && j.selectedEdition.url) || '';
    } catch(e) { sku = 'ERR ' + e.message; }
  }
  return sku + '   ||   ' + url;
})
"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        c = await b.new_context(user_agent=UA, locale="zh-CN", viewport={"width": 1440, "height": 900})
        for q in ["elden+ring", "elden%20ring", "elden", "hogwarts+legacy"]:
            pg = await c.new_page()
            await pg.goto(f"https://www.greenmangaming.com/zh/search/?query={q}",
                          wait_until="domcontentloaded", timeout=60000)
            await pg.wait_for_timeout(8000)
            try:
                await pg.wait_for_selector(".product-block", timeout=10000)
            except Exception:
                pass
            n = await pg.locator(".product-block").count()
            print(f"\nquery={q}  cards={n}")
            for x in await pg.evaluate(JS):
                print("   ", x[:110])
            await pg.close()
        await b.close()

asyncio.run(main())
