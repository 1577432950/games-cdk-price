# -*- coding: utf-8 -*-
"""
游戏 CDK 比价 · 本地网页版

运行后自动打开浏览器，在页面里输入中文名/英文名即可比价，
结果以表格展示（站点 / 版本 / 商品名 / 原价 / 现价 / 折合人民币 / 网址），网址可直接点击。

    python web_app.py            # 启动并自动开浏览器
    python web_app.py --port 8765

打包成 exe 后双击即用。
"""

import argparse
import json
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import core
from sites import SITES, UNAVAILABLE

JOBS = {}
JOBS_LOCK = threading.Lock()
_LOGIN_SESSION = {"ref": None}


# ------------------------------------------------------------------ 任务

def _run_job(job_id, kw_cn, kw_en_in, sites, keep_all):
    def put(**kw):
        with JOBS_LOCK:
            JOBS[job_id].update(kw)

    try:
        put(state="running", status="正在获取汇率…")
        fx = core.fetch_fx()
        put(fx=fx)

        kw_en = kw_en_in
        if not kw_en:
            put(status="正在解析英文名…")
            info = core.resolve_steam(kw_cn)
            kw_en = info["en"] if info else kw_cn

        put(status=f"正在抓取 {len(sites)} 个站点（英文名：{kw_en}），大约需要 30~60 秒…")
        results, errors = core.collect(kw_cn, kw_en, sites or None)
        rows = core.build_rows(results, errors, kw_cn, kw_en, fx, keep_all=keep_all)
        put(state="done", status="完成", rows=rows)
    except Exception as e:
        put(state="error", status=f"{type(e).__name__}: {e}")


def new_job(kw_cn, kw_en, sites, keep_all):
    job_id = str(int(time.time() * 1000))
    with JOBS_LOCK:
        JOBS[job_id] = {"id": job_id, "state": "running", "status": "排队中…",
                        "rows": [], "fx": core.DEFAULT_FX}
    threading.Thread(target=_run_job, args=(job_id, kw_cn, kw_en, sites, keep_all),
                     daemon=True).start()
    return job_id


# ------------------------------------------------------------------ 页面

PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>游戏 CDK 比价</title>
<style>
:root{--bd:#e3e6ea;--muted:#8a9099;--accent:#d4380d}
*{box-sizing:border-box}
body{margin:0;background:#f5f6f8;color:#222;
 font-family:-apple-system,"Microsoft YaHei","PingFang SC",sans-serif;font-size:14px}
header{background:#fff;border-bottom:1px solid var(--bd);padding:16px 24px}
header h1{margin:0;font-size:18px;font-weight:600}
header .sub{color:var(--muted);font-size:12px;margin-top:4px}
main{max-width:1180px;margin:0 auto;padding:20px 24px 60px}
.card{background:#fff;border:1px solid var(--bd);border-radius:8px;padding:16px 18px;margin-bottom:16px}
.row{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end}
label{display:block;font-size:12px;color:var(--muted);margin-bottom:5px}
input[type=text]{height:34px;padding:0 10px;border:1px solid var(--bd);border-radius:6px;
 font-size:14px;width:220px;font-family:inherit}
input[type=text]:focus{outline:none;border-color:#1668dc}
button{height:34px;padding:0 18px;border:0;border-radius:6px;background:#1668dc;color:#fff;
 font-size:14px;cursor:pointer;font-family:inherit}
button:hover{background:#0f56b8} button:disabled{background:#b8c4d4;cursor:not-allowed}
button.ghost{background:#fff;color:#444;border:1px solid var(--bd)}
.chk{display:flex;flex-wrap:wrap;gap:14px;margin-top:12px;font-size:13px}
.chk label{display:inline-flex;align-items:center;gap:5px;color:#333;margin:0}
.status{padding:10px 14px;border-radius:6px;background:#eef3fb;color:#31537e;font-size:13px}
.status.err{background:#fdecea;color:#a8201a}
table{width:100%;border-collapse:collapse;background:#fff;font-size:13px}
th,td{border-bottom:1px solid var(--bd);padding:9px 10px;text-align:left;vertical-align:top}
th{background:#fafbfc;font-weight:600;color:#555;position:sticky;top:0}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.best{color:var(--accent);font-weight:700}
.tag{font-size:11px;padding:1px 5px;border-radius:3px;white-space:nowrap}
.auth{background:#eaf6ec;color:#237804} .c2c{background:#fff1f0;color:#a8071a}
tr.none td{color:#999}
a{color:#1668dc;text-decoration:none;word-break:break-all} a:hover{text-decoration:underline}
.bar{height:3px;background:#e6ebf2;border-radius:3px;overflow:hidden;margin-top:10px}
.bar i{display:block;height:100%;width:35%;background:#1668dc;animation:mv 1.1s infinite}
@keyframes mv{0%{margin-left:-35%}100%{margin-left:100%}}
.tip{color:var(--muted);font-size:12px;margin-top:10px}
</style></head><body>
<header><h1>游戏 CDK 比价</h1>
<div class="sub">输入游戏名，一次比价 Humble / Fanatical / 绿人GMG / 杉果 / 凤凰 / 匹歪 / 2Game / Gamesplanet / Loaded / Kinguin，统一折算人民币</div>
</header>
<main>
<div class="card">
  <div class="row">
    <div><label>游戏名（中文或英文）</label><input id="cn" type="text" placeholder="如 霍格沃茨之遗"></div>
    <div><label>英文名（选填，境外站用）</label><input id="en" type="text" placeholder="如 Hogwarts Legacy"></div>
    <div><button id="go">开始比价</button></div>
    <div><button id="login" class="ghost">登录匹歪</button></div>
    <div><button id="quit" class="ghost">退出程序</button></div>
  </div>
  <div class="chk">
    <span>站点：</span>
    __SITES__
    <label><input id="all" type="checkbox"> 显示全部（含DLC/周边）</label>
  </div>
  <div class="tip">双击结果行可打开商品页。中国区没货的站点会显示「无匹配结果」，这不是抓取失败。<br>
  <span class="tag auth">授权</span> 官方授权零售，货源正规；
  <span class="tag c2c">C2C 灰市</span> 个人卖家 marketplace，便宜但有黑卡封号风险，自行判断。</div>
</div>

<div id="st" class="status" style="display:none"></div>

<div class="card" id="wrap" style="display:none;padding:0;overflow:hidden">
  <table><thead><tr>
    <th style="width:90px">站点</th><th style="width:78px">渠道</th><th style="width:80px">版本</th><th>商品名</th>
    <th style="width:90px" class="num">原价 ¥</th><th style="width:110px" class="num">现价</th>
    <th style="width:100px" class="num">折合 ¥</th><th style="width:330px">网址</th>
  </tr></thead><tbody id="tb"></tbody></table>
</div>
<div id="note" class="tip"></div>
</main>
<script>
const $=s=>document.querySelector(s);
let job=null, timer=null;
$('#cn').addEventListener('keydown',e=>{if(e.key==='Enter')start()});
$('#en').addEventListener('keydown',e=>{if(e.key==='Enter')start()});
$('#go').addEventListener('click',start);
$('#quit').addEventListener('click',()=>{fetch('/api/quit',{method:'POST'});
  document.body.innerHTML='<main><div class="card">已退出，可关闭本页。</div></main>'});
$('#login').addEventListener('click',async()=>{
  const r=await fetch('/api/login/start',{method:'POST'}).then(r=>r.json());
  $('#st').style.display='block'; $('#st').className='status';
  $('#st').textContent=r.msg||'已打开浏览器';
  const btn=$('#login'); btn.textContent='完成登录'; btn.disabled=false;
  btn.onclick=async()=>{
    const r2=await fetch('/api/login/finish',{method:'POST'}).then(r=>r.json());
    $('#st').textContent=r2.msg||'已保存'; btn.textContent='登录匹歪'; btn.disabled=false;
    btn.onclick=null; $('#login').addEventListener('click',()=>location.reload());
  };
});

function start(){
  const cn=$('#cn').value.trim(); if(!cn){alert('请先填游戏名');return}
  const sites=[...document.querySelectorAll('.site:checked')].map(e=>e.value);
  $('#go').disabled=true; $('#tb').innerHTML=''; $('#wrap').style.display='none';
  $('#st').style.display='block'; $('#st').className='status';
  $('#st').innerHTML='正在提交…<div class="bar"><i></i></div>';
  fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({cn,en:$('#en').value.trim(),sites,all:$('#all').checked})
  }).then(r=>r.json()).then(d=>{job=d.id; poll()});
}

function poll(){
  fetch('/api/job?id='+job).then(r=>r.json()).then(d=>{
    if(d.state==='running'||d.state==='queued'){
      $('#st').innerHTML=(d.status||'处理中')+'<div class="bar"><i></i></div>';
      timer=setTimeout(poll,900); return;
    }
    $('#go').disabled=false;
    if(d.state==='error'){$('#st').className='status err';$('#st').textContent=d.status;return}
    $('#st').className='status';
    render(d.rows||[],d.status||'');
  });
}

function tag(risk){
  return risk==='C2C' ? '<span class="tag c2c">C2C 灰市</span>' : '<span class="tag auth">授权</span>';
}
function render(rows,status){
  const tb=$('#tb'); tb.innerHTML='';
  const best=(rows.find(r=>r.cny!==null)||{}).cny;
  for(const r of rows){
    const tr=document.createElement('tr');
    if(r.cny===null){
      tr.className='none';
      tr.innerHTML=`<td>${r.site}</td><td>${tag(r.risk)}</td>`
        +`<td colspan="5">${r.note||r.title}</td><td>${r.url||''}</td>`;
    }else{
      const star=(r.cny===best)?' ★':'';
      tr.innerHTML=`<td>${r.site}</td><td>${tag(r.risk)}</td><td>${r.kind}</td><td>${r.title}</td>`
        +`<td class="num">${r.list?r.list.toFixed(2):'-'}</td>`
        +`<td class="num">${r.price.toFixed(2)} ${r.cur}</td>`
        +`<td class="num ${r.cny===best?'best':''}">¥${r.cny.toFixed(2)}${star}</td>`
        +`<td>${r.url?`<a href="${r.url}" target="_blank">${r.url}</a>`:''}</td>`;
    }
    tr.addEventListener('dblclick',()=>{if(r.url)window.open(r.url,'_blank')});
    tb.appendChild(tr);
  }
  $('#wrap').style.display='block';
  $('#st').textContent=status||`共 ${rows.filter(r=>r.cny!==null).length} 条报价`;
}
__NOTE__
</script></body></html>"""


def build_page():
    sites_html = "".join(
        f'<label><input class="site" type="checkbox" value="{k}" checked> {c["name"]}</label>'
        for k, c in SITES.items())
    note = "".join(f'$("#note").textContent+="※ {v} ";' for v in UNAVAILABLE.values())
    return PAGE.replace("__SITES__", sites_html).replace("__NOTE__", note)


# ------------------------------------------------------------------ HTTP


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, build_page(), "text/html; charset=utf-8")
        elif path == "/api/job":
            q = urlparse(self.path).query
            jid = dict(kv.split("=", 1) for kv in q.split("&") if "=" in kv).get("id", "")
            with JOBS_LOCK:
                job = JOBS.get(jid, {"state": "error", "status": "任务不存在"})
            self._send(200, json.dumps(job, ensure_ascii=False))
        else:
            self._send(404, '{"error":"not found"}')

    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8") if n else ""

        if path == "/api/search":
            d = json.loads(raw or "{}")
            jid = new_job(d.get("cn", ""), d.get("en", ""), d.get("sites") or [],
                          bool(d.get("all")))
            self._send(200, json.dumps({"id": jid}))

        elif path == "/api/login/start":
            try:
                s = core.BrowserSession(headless=False)
                s.new_page().goto("https://steampy.com/", wait_until="domcontentloaded",
                                  timeout=60000)
                _LOGIN_SESSION["ref"] = s
                self._send(200, json.dumps(
                    {"msg": "已打开浏览器窗口，登录 SteamPY 后回到本页点『完成登录』"},
                    ensure_ascii=False))
            except Exception as e:
                self._send(200, json.dumps(
                    {"msg": f"打开浏览器失败：{type(e).__name__}: {e}"}, ensure_ascii=False))

        elif path == "/api/login/finish":
            s = _LOGIN_SESSION.get("ref")
            try:
                if s:
                    s.save_state("steampy")
                    s.close()
                _LOGIN_SESSION["ref"] = None
                self._send(200, json.dumps({"msg": "匹歪登录态已保存，可以正常查询了"},
                                           ensure_ascii=False))
            except Exception as e:
                self._send(200, json.dumps({"msg": f"保存失败：{type(e).__name__}: {e}"},
                                           ensure_ascii=False))

        elif path == "/api/quit":
            self._send(200, '{"ok":true}')
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        else:
            self._send(404, '{"error":"not found"}')


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    ap = argparse.ArgumentParser(description="游戏 CDK 比价（本地网页版）")
    ap.add_argument("--port", type=int, default=0, help="端口，默认随机")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    a = ap.parse_args()

    port = a.port or free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"服务已启动: {url}", flush=True)
    print("浏览器若未自动打开，请手动访问上面的地址。", flush=True)
    print("用完点页面上的「退出程序」，或直接关闭本窗口。", flush=True)
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
