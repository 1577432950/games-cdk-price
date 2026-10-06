# -*- coding: utf-8 -*-
import re
from curl_cffi import requests as creq

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
H = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
def get(u, **kw): return creq.get(u, headers=H, timeout=30, impersonate="chrome", **kw)

# 凤凰: 找 search_data.js 完整地址 + searchURL 上下文
r = get("https://www.fhyx.com/")
for m in re.finditer(r'[\w/\.\-]*search_data\.js[^"\'<> ]*', r.text):
    print("FHYX js:", m.group(0))
    js_url = m.group(0)
    if not js_url.startswith("http"):
        js_url = "https://www.fhyx.com" + ("" if js_url.startswith("/") else "/") + js_url
    j = get(js_url)
    print("   js status", j.status_code, "len", len(j.text), "->", j.text[:300])
i = r.text.find("searchURL")
print("\nFHYX ctx:", re.sub(r"\s+", " ", r.text[i-400:i+500]) if i > 0 else "none")
