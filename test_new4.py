# -*- coding: utf-8 -*-
"""逐个验证新增站点适配器"""
import sys

sys.path.insert(0, ".")
import core
import sites

KW = sys.argv[1] if len(sys.argv) > 1 else "cyberpunk 2077"
s = core.BrowserSession(headless=True)

for key in ["2game", "gamesplanet", "loaded", "kinguin"]:
    cfg = sites.SITES[key]
    kw = KW
    print("\n" + "=" * 74)
    print(key, "|", cfg["name"], "| kw =", kw)
    try:
        offers = cfg["fn"](kw, page_factory=s.new_page)
        print("  原始条数", len(offers))
        for o in offers[:6]:
            print(f"   {o['title'][:58]!r} {o['price']} {o['currency']} | {o['url'][:70]}")
    except Exception as e:
        print("  ERROR", type(e).__name__, str(e)[:200])

s.close()
