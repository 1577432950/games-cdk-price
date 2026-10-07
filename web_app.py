# -*- coding: utf-8 -*-
"""
游戏 CDK 比价 · 本地网页版

运行后自动打开浏览器，在页面里输入中文名/英文名即可比价，
结果以表格展示（站点 / 渠道 / 版本 / 商品名 / 原价 / 现价 / 折合人民币 / 网址），网址可直接点击。

匹歪（SteamPY）需要登录才能搜到商品，页面上的「登录匹歪」按钮会开一个有头浏览器
让你登录一次，登录态存到本机，之后查询就能正常返回匹歪的价格。

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

# 匹歪登录：状态在后台线程与 HTTP 线程之间共享，用锁保护
LOGIN = {"state": "idle", "msg": ""}
LOGIN_LOCK = threading.Lock()


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


# ------------------------------------------------------------------ 匹歪登录

def _login_set(**kw):
    with LOGIN_LOCK:
        LOGIN.update(kw)


def _login_snapshot():
    with LOGIN_LOCK:
        return dict(LOGIN)


def _login_worker():
    """打开有头浏览器让用户登录匹歪。

    登录过程中每 2 秒存一次登录态，用户登录完直接关掉浏览器窗口即可 ——
    不需要再回页面点「完成登录」（关窗后浏览器上下文已销毁，那种做法会保存失败）。
    """
    s = None
    try:
        s = core.BrowserSession(headless=False, site_key="steampy")
        pg = s.new_page()
        pg.goto("https://steampy.com/", wait_until="domcontentloaded", timeout=60000)
        _login_set(state="waiting",
                   msg="浏览器窗口已打开，请完成登录；登录成功后直接关闭该窗口即可")

        deadline = time.time() + 900          # 最多等 15 分钟，避免线程常驻
        while time.time() < deadline:
            if not s.browser.is_connected():
                break
            try:
                s.save_state("steampy")
            except Exception:
                break
            time.sleep(2)
        _login_set(state="done", msg="匹歪登录态已保存，现在可以正常比价了")
    except Exception as e:
        _login_set(state="error", msg=f"登录失败：{type(e).__name__}: {e}")
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass


def start_login():
    with LOGIN_LOCK:
        # starting 是 worker 接手前的过渡态，也要挡住，否则连点会开出两个窗口
        if LOGIN["state"] in ("starting", "waiting"):
            return False
        LOGIN.update(state="starting", msg="正在打开浏览器窗口…")
    threading.Thread(target=_login_worker, daemon=True).start()
    return True


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
.chk{margin-top:14px}
.chkhead{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:9px}
.chkhead>span{font-size:12px;color:var(--muted)}
.chkhead .allbox{display:inline-flex;align-items:center;gap:5px;font-size:13px;color:#333;margin:0}
.sites{display:grid;grid-template-columns:repeat(auto-fill,minmax(275px,1fr));gap:9px}
.srow{border:1px solid var(--bd);border-radius:7px;padding:9px 11px;background:#fcfdfe;
 transition:border-color .15s,box-shadow .15s}
.srow:hover{border-color:#c3d4ea;box-shadow:0 1px 5px rgba(22,104,220,.07)}
.slab{display:flex;align-items:center;gap:6px;margin:0;font-size:13px;color:#222}
.slab b{font-weight:600}
.sdesc{color:#8a9099;font-size:11.5px;line-height:1.6;margin-top:5px;padding-left:20px}
.needlogin{font-size:11px;color:#b06b00;background:#fff7e6;border-radius:3px;padding:1px 5px;white-space:nowrap}
.status{padding:10px 14px;border-radius:6px;background:#eef3fb;color:#31537e;font-size:13px}
.status.err{background:#fdecea;color:#a8201a}
table{width:100%;border-collapse:collapse;background:#fff;font-size:13px}
th,td{border-bottom:1px solid var(--bd);padding:9px 10px;text-align:left;vertical-align:top}
th{background:#fafbfc;font-weight:600;color:#555;position:sticky;top:0}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.best{color:var(--accent);font-weight:700}
th.sortable{cursor:pointer;user-select:none;white-space:nowrap}
th.sortable:hover{background:#f0f4f9;color:#1668dc}
th.sortable i{font-style:normal;color:#bfc8d4;margin-left:3px;font-size:11px}
th.sortable.on{color:#1668dc}
th.sortable.on i{color:#1668dc}
.tag{font-size:11px;padding:1px 5px;border-radius:3px;white-space:nowrap}
.auth{background:#eaf6ec;color:#237804} .c2c{background:#fff1f0;color:#a8071a}
tr.none td{color:#999}
a{color:#1668dc;text-decoration:none;word-break:break-all} a:hover{text-decoration:underline}
.bar{height:3px;background:#e6ebf2;border-radius:3px;overflow:hidden;margin-top:10px}
.bar i{display:block;height:100%;width:35%;background:#1668dc;animation:mv 1.1s infinite}
@keyframes mv{0%{margin-left:-35%}100%{margin-left:100%}}
.tip{color:var(--muted);font-size:12px;margin-top:10px}
footer{border-top:1px solid var(--bd);background:#fbfcfd;padding:14px 24px 26px;color:#7a828c;font-size:12px;line-height:1.85}
footer .fw{max-width:1180px;margin:0 auto}
footer b{color:#5a626c;font-weight:600}
footer .ftitle{display:flex;align-items:center;gap:8px;font-size:13px;color:#444;font-weight:600;margin-bottom:8px}
footer .ftitle::before{content:"";width:3px;height:13px;background:#1668dc;border-radius:2px}
footer p{margin:0 0 5px}
footer .fx{margin-top:9px;padding-top:9px;border-top:1px dashed #e3e6ea;color:#98a0aa}
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
    <div class="chkhead"><span>比价站点</span>
      <label class="allbox"><input id="all" type="checkbox"> 显示全部（含DLC/周边）</label>
    </div>
    <div class="sites">__SITES__</div>
  </div>
  <div class="tip">双击结果行可打开商品页。中国区没货的站点会显示「无匹配结果」，这不是抓取失败。<br>
  <span class="tag auth">授权</span> 官方授权零售，货源正规；
  <span class="tag c2c">C2C 灰市</span> 个人卖家 marketplace，便宜但有黑卡封号风险，自行判断。</div>
</div>

<div id="st" class="status" style="display:none"></div>

<div class="card" id="wrap" style="display:none;padding:0;overflow:hidden">
  <table><thead><tr>
    <th style="width:90px">站点</th><th style="width:78px">渠道</th><th style="width:80px">版本</th><th>商品名</th>
    <th style="width:90px" class="num sortable" data-k="list">原价 ¥<i></i></th>
    <th style="width:110px" class="num sortable" data-k="price">现价<i></i></th>
    <th style="width:100px" class="num sortable" data-k="cny">折合 ¥<i></i></th>
    <th style="width:330px">网址</th>
  </tr></thead><tbody id="tb"></tbody></table>
</div>
<div id="note" class="tip"></div>
</main>
<footer><div class="fw">
  <div class="ftitle">声明</div>
  <p>本工具是<b>完全免费、开源</b>的本地比价小工具，无任何收费项目、无会员、无广告，也不收集你的任何搜索记录或个人信息——你的查询只在你自己的电脑和这些游戏商店之间完成。</p>
  <p>页面展示的价格、区服、库存均由各商店公开页面实时抓取并自动换算，<b>仅供参考</b>。受汇率波动、区域定价、限时促销、页面改版等因素影响，可能与商店实际结算金额存在出入，<b>请以商店下单页的最终价格为准</b>。</p>
  <p>本工具与文中提及的任何游戏平台、发行商均无关联，所有商标、游戏名称及素材版权归其各自所有者所有。"授权"与"C2C 灰市"标签系依据公开信息作出的<b>粗略分类</b>，不构成对任何渠道的官方背书、推荐或担保。请你自行判断渠道可靠性与账号风险，因购买、激活、退款等产生的任何纠纷或损失，本工具作者不承担责任。</p>
  <p class="fx">MIT License · 仅供学习交流使用 · 请勿用于商业用途或高频抓取</p>
</div></footer>
<script>
const $=s=>document.querySelector(s);
let job=null, timer=null;
$('#cn').addEventListener('keydown',e=>{if(e.key==='Enter')start()});
$('#en').addEventListener('keydown',e=>{if(e.key==='Enter')start()});
$('#go').addEventListener('click',start);
$('#quit').addEventListener('click',()=>{fetch('/api/quit',{method:'POST'});
  document.body.innerHTML='<main><div class="card">已退出，可关闭本页。</div></main>'});

// 登录匹歪：开浏览器 → 轮询状态 → 关窗即完成
$('#login').addEventListener('click',async()=>{
  const btn=$('#login');
  btn.disabled=true; btn.textContent='等待登录…';
  $('#st').style.display='block'; $('#st').className='status';
  $('#st').innerHTML='正在打开浏览器窗口…';
  try{
    const r=await fetch('/api/login/start',{method:'POST'}).then(r=>r.json());
    $('#st').innerHTML=r.msg||'浏览器窗口已打开';
    if(!r.ok){btn.disabled=false; btn.textContent='登录匹歪'; return}
    const t=setInterval(async()=>{
      let s;
      try{ s=await fetch('/api/login/status').then(r=>r.json()); }catch(e){ return }
      if(s.msg) $('#st').innerHTML=s.msg;
      if(s.state==='done'||s.state==='error'){
        clearInterval(t);
        btn.disabled=false; btn.textContent='登录匹歪';
        $('#st').className = (s.state==='error') ? 'status err' : 'status';
      }
    },1500);
  }catch(e){
    btn.disabled=false; btn.textContent='登录匹歪';
    $('#st').className='status err'; $('#st').textContent='登录请求失败：'+e;
  }
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
    $('#wrap').style.display='block';
    render(d.rows||[]);
  });
}

function tag(risk){
  return risk==='C2C' ? '<span class="tag c2c">C2C 灰市</span>' : '<span class="tag auth">授权</span>';
}

let DATA=[], SORT={k:'cny', dir:1};   // 默认按折合人民币升序

function sorted(){
  const {k,dir}=SORT;
  // 空价格行永远沉底，不参与排序
  const rows=DATA.filter(r=>r.cny!==null);
  const none=DATA.filter(r=>r.cny===null);
  rows.sort((a,b)=>{
    let x=a[k], y=b[k];
    if(k==='price'){ x=a.cny; y=b.cny; }        // 现价跨币种不可直接比，按折合价排
    if(x===null||x===undefined) x=Infinity;
    if(y===null||y===undefined) y=Infinity;
    if(x===y) return (a.cny||0)-(b.cny||0);
    return (x-y)*dir;
  });
  return rows.concat(none);
}

function render(rows){
  DATA=rows;
  const tb=$('#tb'); tb.innerHTML='';
  // ★ 永远标记全场最低价，不随排序方式变化
  let best=null;
  for(const r of DATA) if(r.cny!==null && (best===null || r.cny<best)) best=r.cny;
  for(const r of sorted()){
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
  const n=DATA.filter(r=>r.cny!==null).length;
  $('#st').textContent=SORT.k==='cny'
    ? `共 ${n} 条报价（按折合人民币${SORT.dir>0?'升序':'降序'}，点表头可改）`
    : `共 ${n} 条报价`;
}

function bindSort(){
  document.querySelectorAll('th.sortable').forEach(th=>{
    const k=th.dataset.k;
    th.querySelector('i').textContent = (SORT.k===k) ? (SORT.dir>0?'▲':'▼') : '⇅';
    th.classList.toggle('on', SORT.k===k);
    th.onclick=()=>{
      if(SORT.k===k) SORT.dir=-SORT.dir;
      else { SORT.k=k; SORT.dir=1; }        // 换列时默认升序（便宜在前）
      document.querySelectorAll('th.sortable').forEach(x=>{
        const kk=x.dataset.k;
        x.classList.toggle('on', kk===SORT.k);
        x.querySelector('i').textContent = (kk===SORT.k) ? (SORT.dir>0?'▲':'▼') : '⇅';
      });
      render(DATA);
    };
  });
}
bindSort();
__NOTE__
</script></body></html>"""


def build_page():
    site_blocks = []
    for k, c in SITES.items():
        risk = ("授权" if c.get("risk") == "授权" else "C2C")
        cls = "auth" if risk == "授权" else "c2c"
        tip = c.get("need_login")
        login = '<span class="needlogin">需登录</span>' if tip else ""
        site_blocks.append(
            f'<div class="srow">'
            f'<label class="slab"><input class="site" type="checkbox" value="{k}" checked>'
            f'<b>{c["name"]}</b>'
            f'<span class="tag {cls}">{risk}</span>{login}</label>'
            f'<div class="sdesc">{c.get("desc", "")}</div>'
            f'</div>')
    sites_html = "".join(site_blocks)
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
        elif path == "/api/login/status":
            self._send(200, json.dumps(_login_snapshot(), ensure_ascii=False))
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
            if start_login():
                self._send(200, json.dumps(
                    {"ok": True, "msg": "正在打开浏览器窗口，请稍候…"},
                    ensure_ascii=False))
            else:
                self._send(200, json.dumps(
                    {"ok": False, "msg": "已经有一个登录窗口在进行中，请先完成它"},
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
