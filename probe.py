# -*- coding: utf-8 -*-
"""一次性探测脚本：试各站候选搜索端点，看谁返回可用数据"""
import json, sys
from curl_cffi import requests as creq

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

def probe(name, url, headers=None, method="get", data=None, show=600):
    h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    if headers:
        h.update(headers)
    try:
        if method == "post":
            r = creq.post(url, headers=h, data=data, timeout=25, impersonate="chrome")
        else:
            r = creq.get(url, headers=h, timeout=25, impersonate="chrome")
        body = r.text[:show].replace("\n", " ")
        print(f"\n=== [{name}] {url}\n  status={r.status_code} len={len(r.text)} ct={r.headers.get('content-type','')[:40]}\n  {body}")
    except Exception as e:
        print(f"\n=== [{name}] {url}\n  ERROR {type(e).__name__}: {e}")

KW = "cyberpunk"

# ---------- 小黑盒 ----------
probe("xhh-1", f"https://api.xiaoheihe.cn/game/search/web?keyword={KW}&page=1&limit=10")
probe("xhh-2", f"https://api.xiaoheihe.cn/bbs/app/api/game/search/?keyword={KW}")
probe("xhh-3", f"https://api.xiaoheihe.cn/game/web/get_search_list?keyword={KW}")
probe("xhh-4", f"https://api.xiaoheihe.cn/search/web?keyword={KW}&type=game")

# ---------- Humble Bundle ----------
probe("hb-1", f"https://www.humblebundle.com/store/api/v1/get_search_results?request=1&page_size=20&sort=bestselling&search={KW}")
probe("hb-2", f"https://www.humblebundle.com/store/api/search?request=1&page_size=20&sort=bestselling&search={KW}")
probe("hb-3", f"https://www.humblebundle.com/store/search?search={KW}")

# ---------- Fanatical ----------
probe("fan-1", f"https://www.fanatical.com/api/v1/products/search?q={KW}")
probe("fan-2", f"https://www.fanatical.com/zh-hans/search?search={KW}")
probe("fan-3", f"https://api.fanatical.com/api/v1/products/search?q={KW}")

# ---------- GreenManGaming ----------
probe("gmg-1", f"https://www.greenmangaming.com/api/v4/navigation/search?query={KW}")
probe("gmg-2", f"https://www.greenmangaming.com/zh/search/?query={KW}")
probe("gmg-3", f"https://www.greenmangaming.com/api/search/v1/products?q={KW}")

# ---------- 杉果 ----------
probe("sk-1", f"https://www.sonkwo.cn/api/v1/search?keyword={KW}")
probe("sk-2", f"https://www.sonkwo.cn/search?keyword={KW}")
probe("sk-3", f"https://api.sonkwo.cn/api/v1/products/search?keyword={KW}")

# ---------- 凤凰 ----------
probe("fh-1", f"https://www.fhyx.com/search?keyword={KW}")
probe("fh-2", f"https://www.fhyx.com/api/search?keyword={KW}")
probe("fh-3", f"https://api.fhyx.com/api/search?keyword={KW}")

# ---------- steampy ----------
probe("spy-1", f"https://steampy.com/search?keyword={KW}")
probe("spy-2", f"https://steampy.com/api/search?keyword={KW}")

# ---------- Steam 中转（取英文名/appid） ----------
probe("steam-1", f"https://store.steampowered.com/api/storesearch/?term={KW}&cc=cn&l=zh-cn")
