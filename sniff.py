# -*- coding: utf-8 -*-
"""嗅探 SPA 站点的 XHR/Fetch JSON 接口"""
import asyncio, sys, json, re
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

def walk(o, path="", depth=0, out=None):
    out = out if out is not None else []
    if depth > 4:
        return out
    if isinstance(o, dict):
        for k, v in o.items():
            p = f"{path}.{k}" if path else k
            if isinstance(v, (dict, list)):
                walk(v, p, depth + 1, out)
            else:
                s = str(v)
                if len(s) < 60:
                    out.append((p, s))
    elif isinstance(o, list) and o:
        walk(o[0], path + "[0]", depth + 1, out)
    return out

async def main():
    url = sys.argv[1]
    kw_hint = sys.argv[2] if len(sys.argv) > 2 else ""
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = await b.new_context(user_agent=UA, locale="zh-CN", viewport={"width": 1440, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        pg = await ctx.new_page()
        seen = {}

        async def on_resp(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct:
                    return
                if resp.status != 200:
                    return
                j = await resp.json()
            except Exception:
                return
            u = resp.url
            key = re.sub(r"\d+", "#", u.split("?")[0])
            if key in seen:
                return
            seen[key] = True
            print("\n" + "=" * 70)
            print("URL:", u[:200])
            print("STATUS:", resp.status)
            for pth, v in walk(j)[:45]:
                print(f"   {pth[:55]:55s} = {v}")

        pg.on("response", lambda r: asyncio.create_task(on_resp(r)))
        await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(9000)
        await b.close()

asyncio.run(main())
