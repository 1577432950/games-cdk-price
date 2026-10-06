# -*- coding: utf-8 -*-
import re
from curl_cffi import requests as creq

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
H = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}

def get(url, **kw):
    return creq.get(url, headers=H, timeout=30, impersonate="chrome", **kw)

# 1) 小黑盒用中文关键词
r = get("https://api.xiaoheihe.cn/game/search/web?keyword=%E8%B5%9B%E5%8D%9A%E6%9C%8B%E5%85%8B&page=1&limit=10")
print("XHH cn:", r.status_code, r.text[:900])

# 2) 凤凰主页找搜索表单
r = get("https://www.fhyx.com/")
print("\nFHYX home:", r.status_code, len(r.text))
for m in re.finditer(r'<form[^>]*>', r.text):
    print("  form:", m.group(0)[:200])
for m in re.finditer(r'(search|Search)[^"\'<> ]{0,30}', r.text):
    s = m.group(0)
    if "search" in s.lower():
        print("  hit:", s[:80])
