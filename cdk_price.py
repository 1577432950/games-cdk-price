#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
游戏 CDK 多站比价工具 · 命令行版

    python cdk_price.py 赛博朋克2077
    python cdk_price.py 艾尔登法环 --en "Elden Ring"
    python cdk_price.py 霍格沃茨之遗 --html r.html
    python cdk_price.py --login steampy          # 匹歪需先登录一次

想双击运行图形界面，请用 gui.py（或打包出的 exe）。
"""

import argparse
import json
import unicodedata
from pathlib import Path

import core
import report
from sites import SITES, UNAVAILABLE


def disp_len(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad(s, width, align="left"):
    gap = max(0, width - disp_len(s))
    return s + " " * gap if align == "left" else " " * gap + s


def print_table(rows, kw, fx):
    print("\n" + "=" * 96)
    print(f"  游戏: {kw}     汇率: 1 USD = {fx['USD']:.3f} CNY | 1 GBP = "
          f"{fx['GBP']:.3f} CNY | 1 EUR = {fx['EUR']:.3f} CNY")
    print("=" * 96)
    print(" ".join([pad("站点", 10), pad("渠道", 8), pad("版本", 10), pad("商品名", 36),
                    pad("原价", 11, "r"), pad("现价", 16, "r"), pad("≈人民币", 12, "r")]))
    print("-" * 96)
    if not rows:
        print("  没有抓到任何结果。检查关键词，或用 --en 指定英文名后重试。")
    best = min((r["cny"] for r in rows if r["cny"]), default=None)
    for r in rows:
        risk = "C2C灰市" if r.get("risk") == "C2C" else "授权"
        if r["cny"] is None:
            print(pad(r["site"], 10), pad(risk, 8), pad(r["kind"], 10), pad(r["title"][:34], 36))
            if r.get("note"):
                print(" " * 32 + "-> " + r["note"])
            continue
        p = f"{r['price']:.2f} {r['cur']}"
        lst = f"{r['list']:.2f}" if r["list"] else "-"
        tag = "  ★最低" if r["cny"] == best else ""
        print(" ".join([pad(r["site"], 10), pad(risk, 8), pad(r["kind"], 10),
                        pad(r["title"][:34], 36),
                        pad(lst, 11, "r"), pad(p, 16, "r"),
                        pad(f"¥{r['cny']:.2f}{tag}", 12, "r")]))
    print("-" * 96)
    for r in rows:
        if r["cny"] is not None and r["url"]:
            print(f"  ¥{r['cny']:>8.2f}  {r['site']:<8} {r['title'][:34]:<34} {r['url']}")
    print()


def resort(rows, key="cny", desc=False):
    """重新排序：空价格行（提示/错误）固定沉底，不参与排序。"""
    nice = [r for r in rows if r["cny"] is not None]
    none = [r for r in rows if r["cny"] is None]
    if key == "price":
        # 现价跨币种不可直接比，仍按折合价排
        nice.sort(key=lambda r: r["cny"], reverse=desc)
    elif key == "list":
        # 无原价的沉到有效值之后（升序降序都一样）
        withlp = [r for r in nice if r["list"]]
        nolp = [r for r in nice if not r["list"]]
        withlp.sort(key=lambda r: (r["list"], r["cny"] or 0), reverse=desc)
        nice = withlp + nolp
    else:
        nice.sort(key=lambda r: r["cny"], reverse=desc)
    return nice + none


def main():
    ap = argparse.ArgumentParser(description="游戏 CDK 多站比价（命令行版）")
    ap.add_argument("game", nargs="?", help="游戏名（中文或英文）")
    ap.add_argument("--en", help="英文名（境外站用它搜索）")
    ap.add_argument("--sites", help="只查指定站点，逗号分隔，如 humble,gmg,sonkwo")
    ap.add_argument("--json", help="结果写入 JSON 文件")
    ap.add_argument("--csv", help="结果写入 CSV 文件")
    ap.add_argument("--html", help="生成可点击链接的 HTML 比价报告")
    ap.add_argument("--top", type=int, default=0, help="只显示最便宜的 N 条")
    ap.add_argument("--all", action="store_true", help="保留 DLC/原声/周边等全部结果")
    ap.add_argument("--fx", type=float, help="手动指定 1 USD 兑多少 CNY")
    ap.add_argument("--login", metavar="SITE", help="打开浏览器登录指定站点并保存登录态")
    ap.add_argument("--debug", action="store_true", help="把原始抓取结果存到 debug_last.json")
    ap.add_argument("--sort", default="cny",
                    help="排序依据：cny(折合人民币，默认) / price(现价) / list(原价)")
    ap.add_argument("--desc", action="store_true", help="按价格从高到低排序（默认从低到高）")
    a = ap.parse_args()

    if a.login:
        print("浏览器已打开，请登录后回到这里按回车……")
        f = core.login(a.login, on_ready=lambda: input())
        print("登录态已保存到", f)
        return
    if not a.game:
        ap.error("请输入游戏名，例如: python cdk_price.py 赛博朋克2077")

    print("正在获取汇率…", end="", flush=True)
    fx = core.fetch_fx()
    if a.fx:
        fx["USD"] = a.fx
    print(" 完成")

    kw_cn, kw_en = a.game, a.en
    if not kw_en:
        print("正在解析英文名…", end="", flush=True)
        info = core.resolve_steam(a.game)
        if info:
            kw_en = info["en"]
            print(f" {kw_en} (Steam appid {info['appid']})")
        else:
            kw_en = a.game
            print(" 失败（Steam 不可达），境外站将用原名搜索，建议加 --en 指定英文名")

    only = set(s.strip() for s in a.sites.split(",")) if a.sites else None
    if only:
        bad = only - set(SITES)
        if bad:
            print("忽略未知站点:", ", ".join(bad))

    print("正在抓取: " + ", ".join(SITES[k]["name"] for k in SITES if not only or k in only))
    results, errors = core.collect(kw_cn, kw_en, only)
    if a.debug:
        Path("debug_last.json").write_text(
            json.dumps({"results": results, "errors": errors}, ensure_ascii=False, indent=2),
            "utf-8")

    rows = core.build_rows(results, errors, kw_cn, kw_en, fx, keep_all=a.all)
    rows = resort(rows, a.sort, a.desc)
    if a.top:
        rows = rows[: a.top]
    print_table(rows, f"{kw_cn}" + (f" / {kw_en}" if kw_en and kw_en != kw_cn else ""), fx)

    if a.json:
        print("JSON 已写入", report.write_json(rows, a.json))
    if a.csv:
        print("CSV 已写入", report.write_csv(rows, a.csv))
    if a.html:
        print("HTML 已写入", report.write_html(
            rows, a.html, f"{kw_cn}" + (f" / {kw_en}" if kw_en and kw_en != kw_cn else ""), fx))

    for k, reason in UNAVAILABLE.items():
        if not only or k in only:
            print(f"※ {reason}")


if __name__ == "__main__":
    main()
