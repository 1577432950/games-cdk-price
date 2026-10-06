# -*- coding: utf-8 -*-
"""探测更多 CDK 站点：能否访问 + 搜索结果是否服务端渲染（决定抓取难度）"""
import urllib.parse as up
from curl_cffi import requests as creq

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
KW = "cyberpunk"

# (名称, 搜索URL模板, 是否中国玩家常用, 类型)
CANDS = [
    ("Instant Gaming", "https://www.instant-gaming.com/en/search/?query={kw}", "授权"),
    ("Instant Gaming 中文", "https://www.instant-gaming.com/zh/search/?query={kw}", "授权"),
    ("GG.deals", "https://gg.deals/games/?title={kw}", "聚合"),
    ("GG.deals 中文", "https://gg.deals/zh/games/?title={kw}", "聚合"),
    ("CDKeys", "https://www.cdkeys.com/catalogsearch/result/?q={kw}", "授权(灰)"),
    ("2Game", "https://2game.com/search?q={kw}", "授权"),
    ("GamersGate", "https://www.gamersgate.com/games?search={kw}", "授权"),
    ("Nuuvem", "https://www.nuuvem.com/br/search?q={kw}", "授权"),
    ("IndieGala", "https://www.indiegala.com/search?q={kw}", "授权"),
    ("Gamesplanet", "https://us.gamesplanet.com/search?query={kw}", "授权"),
    ("GameBillet", "https://gamebillet.com/search?q={kw}", "授权"),
    ("WinGameStore", "https://www.wingamestore.com/search/?SearchTerm={kw}", "授权"),
    ("Kinguin", "https://www.kinguin.net/catalogsearch/result/?q={kw}", "C2C"),
    ("Eneba", "https://www.eneba.com/store/pc/all-games?search={kw}", "C2C"),
    ("Gamivo", "https://www.gamivo.com/search?q={kw}", "C2C"),
    ("G2A", "https://www.g2a.com/search?query={kw}", "C2C"),
    ("AllKeyShop", "https://www.allkeyshop.com/blog/catalogue/search/?search={kw}", "聚合"),
]

for name, tpl, kind in CANDS:
    url = tpl.format(kw=up.quote(KW))
    try:
        r = creq.get(url, headers=H, timeout=25, impersonate="chrome", allow_redirects=True)
        t = r.text
        hit = t.lower().count("cyberpunk")
        priceish = sum(t.count(x) for x in ["$", "€", "£", "¥"])
        print(f"{name:22s} [{kind:7s}] {r.status_code} len={len(t):>7} "
              f"kw命中={hit:>4} 价格符号={priceish:>5} final={r.url[:80]}")
    except Exception as e:
        print(f"{name:22s} [{kind:7s}] ERR {type(e).__name__}: {str(e)[:70]}")
