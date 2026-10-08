# -*- coding: utf-8 -*-
"""结果导出：HTML / JSON / CSV。"""

import csv
import json
from pathlib import Path

TPL = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{kw} - CDK 比价</title>
<style>
body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;margin:32px;color:#222;background:#fff}}
h1{{font-size:20px;margin-bottom:4px}} .sub{{color:#888;font-size:13px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{border:1px solid #e3e3e3;padding:8px 10px;text-align:left}}
th{{background:#f6f7f9}} .num{{text-align:right;font-variant-numeric:tabular-nums}}
.price{{font-weight:700;color:#d4380d}} tr.none td{{color:#999;background:#fafafa}}
tr:hover td{{background:#f9fbff}} a{{color:#1668dc}}
.tag{{font-size:11px;padding:1px 5px;border-radius:3px;white-space:nowrap;margin-left:4px}}
.auth{{background:#eaf6ec;color:#237804}} .c2c{{background:#fff1f0;color:#a8071a}}
.tip{{margin:10px 0 16px;padding:8px 12px;background:#fffbe6;border:1px solid #ffe58f;
border-radius:4px;font-size:13px;color:#8c6d1f}}
</style></head><body>
<h1>{kw} · CDK 比价结果</h1>
<div class="sub">汇率 1 USD = {usd:.3f} CNY ｜ 1 GBP = {gbp:.3f} CNY
｜ 1 EUR = {eur:.3f} CNY ｜ 按折合人民币升序</div>
<div class="tip">渠道说明：<span class="tag auth">授权</span> 为官方授权零售，
有正规货源；<span class="tag c2c">C2C 灰市</span> 为个人卖家 marketplace，
价格更低但有黑卡封号风险，请自行判断。</div>
<table><tr><th>站点</th><th>渠道</th><th>版本</th><th>平台</th><th>商品名</th><th>原价 ¥</th>
<th>现价</th><th>折合 ¥</th><th>网址</th></tr>
{rows}
</table></body></html>"""


def _tag(risk):
    if (risk or "") == "C2C":
        return '<span class="tag c2c">C2C 灰市</span>'
    return '<span class="tag auth">授权</span>'


def write_html(rows, path, kw, fx):
    trs = []
    best = next((r["cny"] for r in rows if r["cny"]), None)
    for r in rows:
        if r["cny"] is None:
            note = r.get("note") or r["title"]
            trs.append(f'<tr class="none"><td>{r["site"]}</td><td>{_tag(r.get("risk"))}</td>'
                       f'<td colspan="6">{note}</td>'
                       f'<td>{r.get("url","")}</td></tr>')
            continue
        star = " ★" if r["cny"] == best else ""
        price = f'{r["price"]:.2f} {r["cur"]}'
        url = (f'<a href="{r["url"]}" target="_blank">{r["url"]}</a>'
               if r["url"] else "")
        trs.append(
            f'<tr><td>{r["site"]}</td><td>{_tag(r.get("risk"))}</td>'
            f'<td>{r["kind"]}</td><td>{r.get("plat", "")}</td><td>{r["title"]}</td>'
            f'<td class="num">{r["list"] if r["list"] else "-"}</td>'
            f'<td class="num">{price}</td>'
            f'<td class="num price">¥{r["cny"]:.2f}{star}</td><td>{url}</td></tr>')
    html = TPL.format(kw=kw, usd=fx["USD"], gbp=fx["GBP"], eur=fx["EUR"],
                      rows="\n".join(trs))
    Path(path).write_text(html, "utf-8")
    return str(path)


def write_json(rows, path):
    Path(path).write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    return str(path)


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["站点", "渠道", "类型", "平台", "商品名", "原价(CNY)", "现价", "币种",
                    "折合CNY", "网址"])
        for r in rows:
            w.writerow([r["site"], r.get("risk", ""), r["kind"], r.get("plat", ""),
                        r["title"], r["list"] or "",
                        r["price"] or "", r.get("cur", ""), r["cny"] or "", r["url"]])
    return str(path)
