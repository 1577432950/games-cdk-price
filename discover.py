# -*- coding: utf-8 -*-
"""自动发现搜索入口：打开首页 -> 找搜索框 -> 输入 -> 回车 -> 记录 URL 与结果 DOM"""
import asyncio, json, re, sys
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

SITES = [
    {"name": "xiaoheihe", "home": "https://xiaoheihe.cn/home", "kw": "赛博朋克2077"},
    {"name": "steampy",   "home": "https://steampy.com/",      "kw": "赛博朋克2077"},
    {"name": "sonkwo",    "home": "https://www.sonkwo.cn/",    "kw": "赛博朋克2077"},
    {"name": "fhyx",      "home": "https://www.fhyx.com/",     "kw": "赛博朋克2077"},
]

async def try_search(pg, kw):
    sels = [
        "input[type='search']",
        "input[placeholder*='搜索']", "input[placeholder*='Search']", "input[placeholder*='search']",
        "input[placeholder*='游戏']", "input[placeholder*='关键词']",
        "input[name*='keyword']", "input[name*='kw']", "input[name*='q']", "input[name*='search']",
        "#search", ".search-input input", ".searchInput", "input.search",
    ]
    for s in sels:
        try:
            loc = pg.locator(s).first
            if await loc.count() == 0:
                continue
            if not await loc.is_visible():
                continue
            await loc.click(timeout=4000)
            await loc.fill(kw, timeout=4000)
            await pg.wait_for_timeout(600)
            await loc.press("Enter")
            await pg.wait_for_timeout(6000)
            return s
        except Exception:
            continue
    return None

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = await b.new_context(user_agent=UA, locale="zh-CN", viewport={"width": 1440, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        for s in SITES:
            pg = await ctx.new_page()
            print("\n" + "=" * 72)
            print("SITE:", s["name"], "| kw:", s["kw"])
            try:
                await pg.goto(s["home"], wait_until="domcontentloaded", timeout=60000)
                await pg.wait_for_timeout(4000)
                used = await try_search(pg, s["kw"])
                print("  input selector:", used)
                print("  RESULT URL:", pg.url)
                print("  title:", await pg.title())
                info = await pg.evaluate("""() => {
                    const out=[];
                    document.querySelectorAll('*').forEach(e=>{
                      if(e.children.length===0){
                        const t=(e.textContent||'').trim();
                        if(/[¥￥$][\\d,.]/.test(t) && t.length<25){
                          let p=e,ch=[];
                          for(let i=0;i<4&&p;i++){ch.push(p.tagName.toLowerCase()+(typeof p.className==='string'&&p.className?'.'+p.className.trim().split(/\\s+/).slice(0,2).join('.'):''));p=p.parentElement;}
                          out.push(t+' <<< '+ch.join(' < '));
                        }
                      }
                    });
                    return out.slice(0,14);
                }""")
                for x in info:
                    print("   ", x[:200])
            except Exception as e:
                print("  ERROR", type(e).__name__, str(e)[:200])
            await pg.close()
        await b.close()

asyncio.run(main())
