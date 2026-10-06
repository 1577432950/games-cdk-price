# -*- coding: utf-8 -*-
import asyncio, sys, json, re
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TARGETS = json.loads(sys.argv[1])
SEL = sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 2

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = await b.new_context(user_agent=UA, locale="zh-CN", viewport={"width": 1440, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        for t in TARGETS:
            pg = await ctx.new_page()
            print("\n" + "=" * 70 + "\nSITE:", t["site"])
            try:
                await pg.goto(t["url"], wait_until="domcontentloaded", timeout=60000)
                await pg.wait_for_timeout(7000)
                loc = pg.locator(SEL)
                n = await loc.count()
                print("count:", n)
                for i in range(min(N, n)):
                    h = await loc.nth(i).inner_text()
                    print(f"\n--- [{i}] TEXT: {re.sub(chr(10)+'+',' | ',h)[:300]}")
                    if len(sys.argv) > 4 and sys.argv[4] == "html":
                        hh = await loc.nth(i).evaluate("e => e.outerHTML")
                        print("    HTML:", re.sub(r"\s+", " ", hh)[:1200])
            except Exception as e:
                print("ERROR", type(e).__name__, e)
            await pg.close()
        await b.close()

asyncio.run(main())
