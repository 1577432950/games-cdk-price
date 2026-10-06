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

# 杉果搜索页的卡片 DOM 里没有商品链接（点击靠 JS 事件），拿不到详情页 URL。
# 改用它的公开接口：searchWord 是唯一生效的搜索参数，返回体里带 id，
# 详情页是 https://www.sonkwo.hk/sku/{id}（注意是 .hk 域名，.cn/sku/ 会 404）。
SONKWO_API = "https://api.sonkwo.cn/product/sku/page"
SONKWO_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sonkwo.cn/",
    "Origin": "https://www.sonkwo.cn",
}


def sonkwo(kw, **_):
    r = creq.get(SONKWO_API, params={"locale": "js", "searchWord": kw,
                                     "page": 1, "page_size": 20},
                 headers=SONKWO_HEADERS, timeout=25, impersonate="chrome")
    data = (r.json() or {}).get("data") or {}
    out = []
    for it in data.get("list") or []:
        names = it.get("skuNames") or {}
        title = names.get("chs") or names.get("en") or names.get("default") or ""
        names_en = names.get("en") or ""
        # 中英文名都带上，方便后面相关度过滤命中
        if names_en and names_en.lower() not in title.lower():
            title = f"{title} {names_en}".strip()
        sale = it.get("salePrice")
        if not sale or sale >= 999999:      # 999999 是未上架占位价
            continue
        listp = it.get("listPrice")
        if listp and listp >= 999999:
            listp = None
        sid = it.get("id")
        out.append({
            "title": title,
            "price": float(sale),
            "currency": "CNY",
            "list_price": float(listp) if listp else None,
            "url": f"https://www.sonkwo.hk/sku/{sid}" if sid else "https://www.sonkwo.cn/",
            "note": "",
        })
    return out


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
def _mk(name, lang, cfg, base, risk="授权", desc=""):
    """生成基于通用卡片抽取的适配器。"""

    def fn(kw, page_factory=None, **_):
        url = cfg["url"](kw)
        return _to_offers(browser_scrape(page_factory, url, cfg, wait=cfg.get("wait", 8000)), base)

    return {"name": name, "lang": lang, "kind": "browser", "fn": fn, "risk": risk,
            "desc": desc, "site": base}


SITES = {
    "humble":    {"name": "Humble",  "lang": "en", "kind": "http",    "fn": humble, "risk": "授权",
                  "desc": "美国老牌慈善捆绑包商店，月包/慈善包出名，常有独家优惠价。",
                  "site": "https://www.humblebundle.com/"},
    "fanatical": {"name": "Fanatical", "lang": "en", "kind": "browser", "fn": fanatical, "risk": "授权",
                  "desc": "英国授权零售商，常年高折扣，Bundle 打包价低，适合捡漏。",
                  "site": "https://www.fanatical.com/zh-hans/"},
    "gmg":       {"name": "绿人GMG", "lang": "en", "kind": "browser", "fn": gmg, "risk": "授权",
                  "desc": "Green Man Gaming，英国授权零售商，折扣券体系多，国区可下单。",
                  "site": "https://www.greenmangaming.com/zh/"},
    "sonkwo":    {"name": "杉果",    "lang": "cn", "kind": "http",    "fn": sonkwo, "risk": "授权",
                  "desc": "国内老牌正版数字发行平台，人民币结算、中文客服，国区游戏最省心。",
                  "site": "https://www.sonkwo.cn/"},
    "fhyx":      {"name": "凤凰",    "lang": "cn", "kind": "browser", "fn": fhyx, "risk": "授权",
                  "desc": "凤凰游戏商城（fhyx.com），国内正版零售，常见国产单机与国区激活码。",
                  "site": "https://www.fhyx.com/"},
    "steampy":   {"name": "匹歪",    "lang": "cn", "kind": "browser", "fn": steampy,
                  "risk": "C2C", "need_login": True,
                  "desc": "SteamPY，国内 Steam 交易市场（C2C），玩家自由挂单，价格常最低但需登录。",
                  "site": "https://steampy.com/"},
    # 以下为新增站
    "2game": _mk("2Game", "en", {
        "url": lambda kw: "https://www.2game.com/zh-cn/search?q=" + urllib.parse.quote(kw),
        "card": "div.form-product-card-2game-container",
        "title": [], "price": "span.price-main",
        "list": "span.price-old, [class*='old-price'], s, del",
    }, "https://www.2game.com", "授权", desc="授权零售站，有中文站且直接显示人民币价，付款方便。"),
    "gamesplanet": _mk("Gamesplanet", "en", {
        "url": lambda kw: "https://us.gamesplanet.com/search?query=" + urllib.parse.quote(kw),
        "card": "div.game_list",
        "title": [], "price": "span.price_current",
        "list": "span.price_base strike, span.price_base",
    }, "https://us.gamesplanet.com", "授权", desc="德国授权零售商，上架快、区域选区多，欧区价格参考。"),
    "loaded": _mk("Loaded(原CDKeys)", "en", {
        "url": lambda kw: "https://www.loaded.com/catalogsearch/result/?q=" + urllib.parse.quote(kw),
        "card": "div.product-info",
        "title": [], "price": "span.price",
        "list": "[class*='old-price'], span.old-price, s",
    }, "https://www.loaded.com", "授权", desc="原 CDKeys 改名而来，老牌授权站，全球区 key 库存全。"),
    "kinguin":   {"name": "Kinguin⚠", "lang": "en", "kind": "browser", "fn": kinguin, "risk": "C2C",
                  "desc": "Kinguin 灰色市场（C2C），个人卖家挂单，低价但存在黑卡 key 被回收风险。",
                  "site": "https://www.kinguin.net/"},
}

# 已探测但无法接入的站点说明（暂时留空，有新的不可用站点再往里加）
UNAVAILABLE = {}
