# -*- coding: utf-8 -*-
"""
各站点搜索适配器（同步版本，GUI 与 CLI 共用）。

每个适配器返回 Offer 列表：
    Offer = {
        title, price, currency, list_price, url, note
    }
price 为 float 原始币种金额，currency 为 ISO 代码（CNY / USD / GBP / EUR）。
"""

import base64
import json
import re
import urllib.parse

from curl_cffi import requests as creq

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}

# ---------------------------------------------------------------- 价格解析

_PRICE_RE = re.compile(r"(US\$|CN¥|RMB¥|￥|¥|£|\$|€)\s*([\d,]+(?:\.\d{1,2})?)")
_CUR_MAP = {"US$": "USD", "$": "USD", "¥": "CNY", "￥": "CNY",
            "CN¥": "CNY", "RMB¥": "CNY", "£": "GBP", "€": "EUR"}


def parse_price(text):
    """从任意文本里抠出 (金额, 币种)。失败返回 (None, None)。"""
    if not text:
        return None, None
    m = _PRICE_RE.search(text)
    if not m:
        return None, None
    try:
        return float(m.group(2).replace(",", "")), _CUR_MAP[m.group(1)]
    except ValueError:
        return None, None


def http_get(url, timeout=25, **kw):
    return creq.get(url, headers=HEADERS, timeout=timeout, impersonate="chrome", **kw)


# ---------------------------------------------------------------- Humble Bundle

def humble(kw, **_):
    """Humble 有公开的 JSON 搜索接口，无需浏览器，最快最稳。"""
    url = ("https://www.humblebundle.com/store/api/search?request=1"
           f"&page_size=20&sort=bestselling&search={urllib.parse.quote(kw)}")
    r = http_get(url)
    data = r.json()
    out = []
    for item in data.get("results", []):
        if "game" not in item.get("content_types", ["game"]):
            continue
        cur = (item.get("current_price") or {}).get("amount")
        ccy = (item.get("current_price") or {}).get("currency", "USD")
        if cur is None:
            continue
        full = (item.get("full_price") or {}).get("amount")
        out.append({
            "title": item.get("human_name", ""),
            "price": float(cur),
            "currency": ccy,
            "list_price": float(full) if full else None,
            "url": "https://www.humblebundle.com/store/" + (item.get("human_url") or item.get("machine_name", "")),
            "note": "",
        })
    return out


# ---------------------------------------------------------------- 通用浏览器卡片抽取

JS_EXTRACT = """
(cfg) => {
  const pick = (el, sels) => {
    for (const s of sels) {
      const e = el.querySelector(s);
      if (e) {
        const t = (e.innerText || e.getAttribute('title') || '').trim();
        if (t) return t;
      }
    }
    return '';
  };
  const cards = [...document.querySelectorAll(cfg.card)];
  return cards.slice(0, cfg.limit).map(c => {
    let href = '';
    const a = c.querySelector('a[href]');
    if (a) href = a.getAttribute('href') || '';
    const priceEl = cfg.price ? c.querySelector(cfg.price) : null;
    const listEl  = cfg.list  ? c.querySelector(cfg.list)  : null;
    return {
      title: pick(c, cfg.title),
      raw:   (c.innerText || '').replace(/\\s*\\n+\\s*/g, ' | ').trim().slice(0, 300),
      price: priceEl ? priceEl.innerText.trim() : '',
      list:  listEl  ? listEl.innerText.trim()  : '',
      href:  href,
    };
  });
}
"""


def browser_scrape(page_factory, url, cfg, wait=7000, pre=None):
    """打开页面 -> 抽取卡片。pre 为可选的交互前置流程（同步函数）。"""
    page = page_factory()
    try:
        if pre:
            pre(page)
        else:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(wait)
        try:
            page.wait_for_selector(cfg["card"], timeout=12000)
        except Exception:
            pass
        return page.evaluate(JS_EXTRACT, {
            "card": cfg["card"], "title": cfg["title"],
            "price": cfg.get("price", ""), "list": cfg.get("list", ""),
            "limit": cfg.get("limit", 30),
        })
    finally:
        try:
            page.close()
        except Exception:
            pass


def _abs(base, href):
    if not href:
        return base
    if href.startswith("http"):
        return href
    return urllib.parse.urljoin(base, href)


def _to_offers(rows, base):
    out = []
    for r in rows:
        title = (r.get("title") or "").strip()
        if not title:
            parts = [p.strip() for p in r.get("raw", "").split("|") if p.strip()]
            title = parts[0] if parts else ""
        price, ccy = parse_price(r.get("price", ""))
        if price is None:
            price, ccy = parse_price(r.get("raw", ""))
        if price is None:
            continue
        lp, _ = parse_price(r.get("list", ""))
        out.append({
            "title": title, "price": price, "currency": ccy or "CNY",
            "list_price": lp, "url": _abs(base, r.get("href", "")), "note": "",
        })
    return out


# ---------------------------------------------------------------- Fanatical

FANATICAL_CFG = {
    "card": "div.hitCardStripe",
    "title": [".hitCardStripe__seoName", "[class*='seoName']", "h3", "h2", "a[title]"],
    "price": ".card-price",
    "list": "[class*='was-price'], .card-was-price, s, del",
}


def fanatical(kw, page_factory=None, **_):
    url = "https://www.fanatical.com/zh-hans/search?search=" + urllib.parse.quote(kw)
    rows = browser_scrape(page_factory, url, FANATICAL_CFG, wait=8000)
    return _to_offers(rows, "https://www.fanatical.com")


# ---------------------------------------------------------------- GreenManGaming

def _gmg_decode(payload):
    """GMG 卡片把商品 JSON 以 UTF-16LE 编码后 base64 塞进 ng-init。"""
    s = payload + "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.b64decode(s).decode("utf-16-le"))
    except Exception:
        return None


GMG_JS = """
() => {
  return [...document.querySelectorAll('.product-block')].map(c => {
    let data = {};
    try {
      const raw = c.getAttribute('ng-init') || '';
      const m = raw.match(/init\\('([^']+)'\\)/);
      if (m) data = {__b64: m[1]};
    } catch (e) {}
    return {
      __b64: data.__b64 || '',
      raw:   (c.innerText||'').replace(/\\s*\\n+\\s*/g,' | ').trim().slice(0,200),
    };
  });
}
"""


def gmg(kw, page_factory=None, **_):
    url = "https://www.greenmangaming.com/zh/search/?query=" + urllib.parse.quote(kw)
    page = page_factory()
    rows = []
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        try:
            page.wait_for_selector(".product-block", timeout=12000)
        except Exception:
            pass
        rows = page.evaluate(GMG_JS)
    finally:
        try:
            page.close()
        except Exception:
            pass

    out = []
    for r in rows:
        d = _gmg_decode(r["__b64"]) if r.get("__b64") else None
        ed = (d or {}).get("selectedEdition") or {}
        title = ed.get("sku", "")
        cur = ed.get("currentPrice")
        rrp = ed.get("rrp")
        price, ccy = parse_price(str(cur)) if cur else (None, None)
        if price is None:
            price, ccy = parse_price(r.get("raw", ""))
        if price is None:
            continue
        lp, _ = parse_price(str(rrp)) if rrp else (None, None)
        out.append({
            "title": title, "price": price, "currency": ccy or "CNY",
            "list_price": lp,
            "url": _abs("https://www.greenmangaming.com", ed.get("url") or ""),
            "note": "",
        })
    return out


# ---------------------------------------------------------------- 杉果

SONKWO_CFG = {
    "card": ".SKC-sku-item-container.search-result-item-sku, .search-result-item-sku",
    "title": [".sku-name", "[class*='sku-name']", "h3", "h2"],
    "price": ".SKC-sale-price, [class*='sale-price']",
    "list": ".SKC-list-price, [class*='list-price']",
}


def sonkwo(kw, page_factory=None, **_):
    url = "https://www.sonkwo.cn/store/search?keyword=" + urllib.parse.quote(kw)
    rows = browser_scrape(page_factory, url, SONKWO_CFG, wait=8000)
    return _to_offers(rows, "https://www.sonkwo.cn")


# ---------------------------------------------------------------- 凤凰游戏

FHYX_CFG = {
    "card": "div.fhyxNewListLi",
    "title": [".gameName", ".listName", "[class*='name']", "h3", "h2", "a[title]"],
    "price": "span.price",
    "list": "span.oldprice",
}


def fhyx(kw, page_factory=None, **_):
    def pre(page):
        # 凤凰直接访问搜索页会空白，必须从首页走搜索框
        page.goto("https://www.fhyx.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        loc = page.locator("input[name='keyword']").first
        loc.fill(kw)
        page.wait_for_timeout(400)
        loc.press("Enter")
        page.wait_for_timeout(6500)

    rows = browser_scrape(page_factory, "about:blank", FHYX_CFG, wait=0, pre=pre)
    return _to_offers(rows, "https://www.fhyx.com")


# ---------------------------------------------------------------- 匹歪 SteamPY

STEAMPY_CFG = {
    "card": "div.exLi",
    "title": [".gameName", "[class*='game-name']", "[class*='name']", "h3", "h2"],
    "price": ".price-wap .c_0, .price-wap div:first-child",
    "list": ".price-wap .c_3",
}


def steampy(kw, page_factory=None, **_):
    def pre(page):
        # 匹歪的搜索框在未登录时隐藏；已登录（有 storage_state）则可直接用
        page.goto("https://steampy.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4500)
        box = page.locator("input[placeholder='搜索游戏']").first
        try:
            box.fill(kw, timeout=6000)
        except Exception:
            page.evaluate(
                """(kw) => {
                    const i = document.querySelector("input[placeholder='搜索游戏']");
                    if (!i) return;
                    let p = i;
                    while (p && p !== document.body) {
                        p.style.display = 'block';
                        p.style.visibility = 'visible';
                        p.style.opacity = '1';
                        p = p.parentElement;
                    }
                    i.value = kw;
                    i.dispatchEvent(new Event('input', {bubbles: true}));
                }""", kw)
            page.wait_for_timeout(1200)
            page.keyboard.press("Enter")
        else:
            page.wait_for_timeout(800)
            box.press("Enter")
        page.wait_for_timeout(6500)

    rows = browser_scrape(page_factory, "about:blank", STEAMPY_CFG, wait=0, pre=pre)
    if not rows:
        return [{
            "title": "", "price": None, "currency": "CNY", "list_price": None,
            "url": "https://steampy.com/",
            "note": "匹歪搜索需登录：先点「登录匹歪」按钮登录一次",
        }]
    return _to_offers(rows, "https://steampy.com")


# ---------------------------------------------------------------- Kinguin（C2C 灰市）

KINGUIN_JS = """
() => {
  const out = [];
  document.querySelectorAll('span.min').forEach(e => {
    const price = (e.textContent || '').trim();
    // styled-components 的类名是哈希值，不能依赖，只能往上找带商品链接的祖先
    let card = e.parentElement, href = '', title = '';
    for (let i = 0; i < 6 && card; i++) {
      const a = card.querySelector('a[href*="/category/"]');
      if (a) {
        href = a.getAttribute('href') || '';
        const lines = (card.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
        title = lines[0] || '';
        break;
      }
      card = card.parentElement;
    }
    if (title) out.push({title, price, href});
  });
  return out.slice(0, 30);
}
"""


def kinguin(kw, page_factory=None, **_):
    url = "https://www.kinguin.net/listing?phrase=" + urllib.parse.quote(kw)
    page = page_factory()
    rows = []
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(9000)
        try:
            page.wait_for_selector("span.min", timeout=12000)
        except Exception:
            pass
        rows = page.evaluate(KINGUIN_JS)
    finally:
        try:
            page.close()
        except Exception:
            pass
    out = []
    for r in rows:
        price, ccy = parse_price(r.get("price", ""))
        if price is None:
            continue
        out.append({
            "title": r.get("title", ""), "price": price, "currency": ccy or "CNY",
            "list_price": None, "url": r.get("href", "") or "https://www.kinguin.net/",
            "note": "",
        })
    return out


# ---------------------------------------------------------------- 站点注册表

# lang: cn -> 用中文关键词搜索；en -> 用英文关键词搜索
# kind: http -> 纯接口；browser -> 需要浏览器渲染
def _mk(name, lang, cfg, base, risk="授权"):
    """生成基于通用卡片抽取的适配器。"""

    def fn(kw, page_factory=None, **_):
        url = cfg["url"](kw)
        return _to_offers(browser_scrape(page_factory, url, cfg, wait=cfg.get("wait", 8000)), base)

    return {"name": name, "lang": lang, "kind": "browser", "fn": fn, "risk": risk}


SITES = {
    "humble":    {"name": "Humble",  "lang": "en", "kind": "http",    "fn": humble, "risk": "授权"},
    "fanatical": {"name": "Fanatical", "lang": "en", "kind": "browser", "fn": fanatical, "risk": "授权"},
    "gmg":       {"name": "绿人GMG", "lang": "en", "kind": "browser", "fn": gmg, "risk": "授权"},
    "sonkwo":    {"name": "杉果",    "lang": "cn", "kind": "browser", "fn": sonkwo, "risk": "授权"},
    "fhyx":      {"name": "凤凰",    "lang": "cn", "kind": "browser", "fn": fhyx, "risk": "授权"},
    "steampy":   {"name": "匹歪",    "lang": "cn", "kind": "browser", "fn": steampy,
                  "risk": "C2C", "need_login": True},
    # 以下为新增站
    "2game": _mk("2Game", "en", {
        "url": lambda kw: "https://www.2game.com/zh-cn/search?q=" + urllib.parse.quote(kw),
        "card": "div.form-product-card-2game-container",
        "title": [], "price": "span.price-main",
        "list": "span.price-old, [class*='old-price'], s, del",
    }, "https://www.2game.com", "授权"),
    "gamesplanet": _mk("Gamesplanet", "en", {
        "url": lambda kw: "https://us.gamesplanet.com/search?query=" + urllib.parse.quote(kw),
        "card": "div.game_list",
        "title": [], "price": "span.price_current",
        "list": "span.price_base strike, span.price_base",
    }, "https://us.gamesplanet.com", "授权"),
    "loaded": _mk("Loaded(原CDKeys)", "en", {
        "url": lambda kw: "https://www.loaded.com/catalogsearch/result/?q=" + urllib.parse.quote(kw),
        "card": "div.product-info",
        "title": [], "price": "span.price",
        "list": "[class*='old-price'], span.old-price, s",
    }, "https://www.loaded.com", "授权"),
    "kinguin":   {"name": "Kinguin⚠", "lang": "en", "kind": "browser", "fn": kinguin, "risk": "C2C"},
}

# 小黑盒：网页端已无搜索入口，旧的 /game/search/web 接口对任何关键词都返回空列表
UNAVAILABLE = {
    "xiaoheihe": "小黑盒网页端已关闭站内搜索（xiaoheihe.cn 只剩下载落地页），"
                 "旧接口 api.xiaoheihe.cn/game/search/web 对任意关键词均返回空，无法比价。",
}
