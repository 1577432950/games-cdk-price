# -*- coding: utf-8 -*-
"""DOM 勘察：打开各站搜索页，输出候选选择器命中情况与样例文本"""
import asyncio, sys, json
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

CANDIDATES = [
    "a[href*='/game/']", ".product", ".product-item", ".product-card", ".card",
    ".search-result", ".search-result-item", "[class*='product']", "[class*='Product']",
    "[class*='game']", "[class*='Game']", "[class*='item']", "[class*='Item']",
    "li", ".goods", ".goods-item", ".prod", "[data-product]", "[data-sku]",
]

TARGETS = json.loads(sys.argv[1])

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = await b.new_context(user_agent=UA, locale="zh-CN",
                                  viewport={"width": 1440, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        for t in TARGETS:
            pg = await ctx.new_page()
            print("\n" + "=" * 70)
            print("SITE:", t["site"], "\nURL:", t["url"])
            try:
                await pg.goto(t["url"], wait_until="domcontentloaded", timeout=60000)
                await pg.wait_for_timeout(6000)
                print("title:", await pg.title())
                print("final url:", pg.url)
                for sel in CANDIDATES:
                    try:
                        n = await pg.locator(sel).count()
                    except Exception:
                        continue
                    if 0 < n <= 200:
                        try:
                            txt = (await pg.locator(sel).first.inner_text())[:160].replace("\n", " | ")
                        except Exception:
                            txt = ""
                        print(f"  {sel:28s} n={n:4d}  e.g. {txt}")
            except Exception as e:
                print("  ERROR", type(e).__name__, e)
            await pg.close()
        await b.close()

asyncio.run(main())
