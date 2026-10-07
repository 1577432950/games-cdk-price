# -*- coding: utf-8 -*-
"""
核心调度：浏览器会话、并发抓取、汇率、英文名解析、结果整理。
GUI 与 CLI 共用这一层。
"""

import json
import os
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sites
from sites import SITES, UNAVAILABLE

# 打包成 exe 后 __file__ 指向临时解压目录，所以可执行程序所在目录要单独判断
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent

# 登录态与导出文件放用户目录，避免 Program Files 下无写权限、也避免随临时目录丢失
_APPDATA = Path(os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME")
                or str(Path.home()))
STATE_DIR = _APPDATA / "CDKPrice"
DEFAULT_FX = {"USD": 7.10, "GBP": 9.10, "EUR": 7.80, "CNY": 1.0}


# ---------------------------------------------------------------- 浏览器会话

class BrowserSession:
    """优先用系统自带的 Edge / Chrome，都没有才回落到 Playwright 自带的 Chromium。

    stealth=True（默认，抓取用）：隐藏 webdriver 标记 + 关闭沙箱，降低被判定为爬虫的概率。
    stealth=False（手动登录用）：用完全正常的浏览器参数。登录的是真人，不需要伪装，
    伪装标志反而可能让目标站的人机验证（如腾讯滑块）反复触发。
    """

    def __init__(self, headless=True, site_key=None, stealth=True):
        from playwright.sync_api import sync_playwright
        self._sp = sync_playwright().start()
        self.browser = self._launch(headless, stealth)
        self.ctx = self.browser.new_context(
            user_agent=sites.UA, locale="zh-CN", viewport={"width": 1440, "height": 900})
        if stealth:
            self.ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        if site_key:
            self._load_state(site_key)

    def _launch(self, headless, stealth=True):
        args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"] if stealth else []
        for channel in ("msedge", "chrome"):
            try:
                return self._sp.chromium.launch(channel=channel, headless=headless, args=args)
            except Exception:
                continue
        return self._sp.chromium.launch(headless=headless, args=args)

    def _load_state(self, site_key):
        f = STATE_DIR / f"{site_key}.json"
        if not f.exists():
            return
        try:
            self.ctx.add_cookies(json.loads(f.read_text("utf-8")).get("cookies", []))
        except Exception:
            pass

    def new_page(self):
        return self.ctx.new_page()

    def save_state(self, site_key):
        STATE_DIR.mkdir(exist_ok=True)
        self.ctx.storage_state(path=str(STATE_DIR / f"{site_key}.json"))

    def close(self):
        # 三步各自独立 try：任何一步失败都不能拖累后面的关闭动作，
        # 否则会留下关不掉的浏览器窗口（曾经就是 ctx.close() 抛异常导致 browser 没关）
        for fn in (self.ctx.close, self.browser.close, self._sp.stop):
            try:
                fn()
            except Exception:
                pass


def login(site_key, on_ready=None):
    """打开有头浏览器让用户登录一次，保存登录态。on_ready 在浏览器打开后回调。"""
    url = {"steampy": "https://steampy.com/", "sonkwo": "https://www.sonkwo.cn/",
           "fhyx": "https://www.fhyx.com/", "gmg": "https://www.greenmangaming.com/zh/",
           "fanatical": "https://www.fanatical.com/zh-hans/"}.get(site_key, "https://steampy.com/")
    s = BrowserSession(headless=False)
    pg = s.new_page()
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    if on_ready:
        on_ready()
    s.save_state(site_key)
    s.close()
    return str(STATE_DIR / f"{site_key}.json")


# ---------------------------------------------------------------- 汇率 / 英文名

def fetch_fx():
    try:
        from curl_cffi import requests as creq
        r = creq.get("https://api.frankfurter.app/latest?base=USD&symbols=CNY,GBP,EUR",
                     timeout=12, impersonate="chrome")
        d = r.json()["rates"]
        return {"USD": d["CNY"], "GBP": d["CNY"] / d["GBP"],
                "EUR": d["CNY"] / d["EUR"], "CNY": 1.0}
    except Exception:
        return dict(DEFAULT_FX)


def resolve_steam(kw, timeout=10):
    """用 Steam 搜索拿英文名与 appid。失败返回 None（国内网络可能连不通 Steam）。"""
    try:
        from curl_cffi import requests as creq
        out = {"appid": None, "en": None, "zh": None}
        for lang in ("en", "zh-cn"):
            u = ("https://store.steampowered.com/api/storesearch/?term="
                 + urllib.parse.quote(kw) + "&cc=cn&l=" + lang)
            r = creq.get(u, timeout=timeout, impersonate="chrome")
            items = r.json().get("items") or []
            if items:
                out["appid"] = items[0].get("id")
                out["en" if lang == "en" else "zh"] = items[0].get("name")
        return out if out["en"] else None
    except Exception:
        return None


# ---------------------------------------------------------------- 相关度 / 分类


def norm(s):
    return re.sub(r"[\s\_\-\:\'\"\.,!·、（）()\[\]]+", "", (s or "").lower())


def relevance(title, query):
    """0~1 相关度。英文 token 与汉字覆盖率取 min，避免只命中一半关键词的误匹配。"""
    t, q = norm(title), norm(query)
    if not t or not q:
        return 0.0
    if q in t:
        return 1.0
    parts = []
    qt = set(re.findall(r"[a-z0-9]+", q))
    tt = set(re.findall(r"[a-z0-9]+", t))
    if qt:
        parts.append(len(qt & tt) / len(qt))
    qc = set(re.findall(r"[\u4e00-\u9fff]", q))
    tc = set(re.findall(r"[\u4e00-\u9fff]", t))
    if qc:
        parts.append(len(qc & tc) / len(qc))
    return min(parts) if parts else 0.0


MERCH_RE = re.compile(r"周边|手办|玩偶|毛绒|公仔|立牌|海报|服饰|T恤|抱枕|设定集|画集|artbook|merch", re.I)
# 成品号/共享账号不是真正的 CDK，必须滤掉（英文站常见 "Steam Account"）
ACCOUNT_RE = re.compile(
    r"成品账号|账号|初始号|成品号|steam\s*accounts?|\baccounts?\b|离线激活|离线账号"
    r"|\baccess\b|\boffline\s*activ", re.I)
EXTRA_RE = re.compile(r"soundtrack|ost|原声|音乐|dlc|季票|season pass|bundle|合集|同捆", re.I)
NONGAME_URL_RE = re.compile(r"/(book|comic|ebook|merch)/", re.I)


def classify(title, url=""):
    if MERCH_RE.search(title or "") or NONGAME_URL_RE.search(url or ""):
        return "周边"
    if ACCOUNT_RE.search(title or ""):
        return "账号"
    if EXTRA_RE.search(title or ""):
        return "DLC/附加"
    return "本体"


# ---------------------------------------------------------------- 抓取


def _call(key, cfg, kw):
    """真正调一次适配器（http 站不走浏览器）。"""
    if cfg["kind"] == "http":
        return cfg["fn"](kw)
    s = BrowserSession(headless=True, site_key=key)
    try:
        return cfg["fn"](kw, page_factory=s.new_page)
    finally:
        s.close()


def _fallback_kw(kw):
    """多词查询空手而归时的降级词：取最长（最独特）的单词。"""
    toks = [t for t in re.split(r"[\s:：\-–—]+", kw or "") if t]
    if len(toks) < 2:
        return None
    cand = max(toks, key=len)
    # 纯数字（如 2077）单独搜意义不大，退回第一个有字母的词
    if not re.search(r"[a-z\u4e00-\u9fff]", cand, re.I):
        cand = next((t for t in toks if re.search(r"[a-z\u4e00-\u9fff]", t, re.I)), None)
    return cand or None


def _run_site(key, kw, log):
    cfg = SITES[key]
    try:
        rows = _call(key, cfg, kw)
        if not rows:
            fk = _fallback_kw(kw)
            if fk and fk.lower() != kw.lower():
                rows = _call(key, cfg, fk)
                for r in rows:
                    r["note"] = (r.get("note", "") + " 广义词命中").strip()
        return key, rows, None
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        if log:
            log(key, msg)
        return key, [], msg


def collect(kw_cn, kw_en, only=None, workers=3, log=None):
    keys = [k for k in SITES if (not only or k in only)]
    results = {}
    errors = {}

    def kw_of(k):
        return kw_en if SITES[k]["lang"] == "en" else kw_cn

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(_run_site, k, kw_of(k), log): k for k in keys}
        for f in futs:
            k, rows, err = f.result()
            results[k] = rows
            if err:
                errors[k] = err
    return results, errors


# ---------------------------------------------------------------- 结果整理


def build_rows(results, errors, kw_cn, kw_en, fx, keep_all=False):
    rows = []
    for key, offers in results.items():
        name = SITES[key]["name"]
        risk = SITES[key].get("risk", "授权")
        q = kw_en if SITES[key]["lang"] == "en" else kw_cn
        if errors.get(key):
            rows.append({"site": name, "title": f"[抓取失败] {errors[key][:70]}",
                         "price": None, "cny": None, "url": "", "kind": "错误",
                         "list": None, "note": "", "risk": risk})
        got = 0
        for o in offers or []:
            if o.get("note") and o.get("price") is None:
                rows.append({"site": name, "title": "[不可用]", "price": None,
                             "cny": None, "url": o.get("url", ""), "kind": "提示",
                             "list": None, "note": o["note"], "risk": risk})
                continue
            title = o.get("title", "")
            if not keep_all and relevance(title, q) < 0.6:
                continue
            kind = classify(title, o.get("url", ""))
            if not keep_all and kind in ("周边", "账号"):
                continue
            got += 1
            cny = o["price"] * fx.get(o["currency"], 1.0)
            lp = o.get("list_price")
            rows.append({
                "site": name, "title": title, "price": o["price"], "cur": o["currency"],
                "cny": round(cny, 2), "url": o.get("url", ""), "kind": kind,
                "list": round(lp * fx.get(o["currency"], 1.0), 2) if lp else None,
                "note": o.get("note", ""), "risk": risk,
            })
        if got == 0 and not errors.get(key) and not any(
                r["site"] == name and r["kind"] in ("错误", "提示") for r in rows):
            hint = "该站在当前地区/关键词下没有匹配商品"
            if SITES[key].get("need_login"):
                hint = "需要登录：点「登录匹歪」按钮登录一次后再查"
            rows.append({"site": name, "title": "[无匹配结果]", "price": None,
                         "cny": None, "url": "", "kind": "提示", "list": None,
                         "note": hint, "risk": risk})
    rows = _dedupe(rows)
    rows.sort(key=lambda r: (r["cny"] is None, r["cny"] or 0))
    return rows


def _dedupe(rows):
    """同一站点同一商品页只留最便宜的一条（有的站会有大小写重复条目）。"""
    seen = {}
    out = []
    for r in rows:
        if r["cny"] is None or not r["url"]:
            out.append(r)
            continue
        key = (r["site"], re.sub(r"[?#].*$", "", r["url"]).rstrip("/").lower())
        if key in seen:
            old = seen[key]
            if r["cny"] < (old["cny"] or 1e18):
                old.update(r)
            continue
        seen[key] = r
        out.append(r)
    return out
