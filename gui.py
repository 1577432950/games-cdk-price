# -*- coding: utf-8 -*-
"""
游戏 CDK 比价 · 图形界面版

双击运行后在输入框里填中文名（英文名可选），点「开始比价」，
结果表格会列出 站点 / 版本 / 商品名 / 原价 / 现价 / 折合人民币 / 网址。
双击任意一行可用默认浏览器打开该商品页。
"""

import threading
import tkinter as tk
import webbrowser
from queue import Empty, Queue
from tkinter import messagebox, ttk

import core
import report
from sites import SITES, UNAVAILABLE

BG = "#f7f8fa"


class App:
    def __init__(self, root):
        self.root = root
        self.q = Queue()
        self.rows = []
        self.fx = core.DEFAULT_FX
        self.busy = False

        root.title("游戏 CDK 比价")
        root.geometry("1080x680")
        root.minsize(900, 560)
        root.configure(bg=BG)

        self._build_top(root)
        self._build_table(root)
        self._build_bottom(root)

        root.after(120, self._pump)

    # ------------------------------------------------------------ 界面

    def _build_top(self, root):
        top = ttk.Frame(root, padding=(12, 10))
        top.pack(fill="x")

        ttk.Label(top, text="游戏名").grid(row=0, column=0, sticky="w")
        self.e_cn = ttk.Entry(top, width=30, font=("Microsoft YaHei", 11))
        self.e_cn.grid(row=0, column=1, padx=(6, 18), ipady=3)
        self.e_cn.bind("<Return>", lambda e: self.search())

        ttk.Label(top, text="英文名（选填，境外站用）").grid(row=0, column=2, sticky="w")
        self.e_en = ttk.Entry(top, width=26, font=("Microsoft YaHei", 11))
        self.e_en.grid(row=0, column=3, padx=6, ipady=3)
        self.e_en.bind("<Return>", lambda e: self.search())

        self.btn = ttk.Button(top, text="开始比价", command=self.search)
        self.btn.grid(row=0, column=4, padx=(12, 6))

        ttk.Button(top, text="登录匹歪", command=self.login_steampy).grid(row=0, column=5, padx=3)
        ttk.Button(top, text="导出HTML", command=self.export_html).grid(row=0, column=6, padx=3)

        self.kbase_var = tk.BooleanVar(value=True)
        self.kdlc_var = tk.BooleanVar(value=True)
        kbox = ttk.Frame(top)
        kbox.grid(row=0, column=7, padx=10)
        ttk.Label(kbox, text="显示版本:").grid(row=0, column=0)
        ttk.Checkbutton(kbox, text="本体",
                        variable=self.kbase_var).grid(row=0, column=1, padx=(4, 0))
        ttk.Checkbutton(kbox, text="DLC/附加",
                        variable=self.kdlc_var).grid(row=0, column=2, padx=(4, 0))

        # 平台筛选：和网页版同一套词表（core.PLATFORM_ORDER），默认全勾。
        # 「未标注」是标题/接口里都没写平台的商品，默认也显示，取消勾选即可只看明确的。
        self.plat_vars = {}
        pbox = ttk.Frame(top)
        pbox.grid(row=2, column=0, columnspan=8, sticky="w", pady=(8, 0))
        ttk.Label(pbox, text="显示平台:").grid(row=0, column=0, sticky="w")
        for i, p in enumerate(core.PLATFORM_ORDER):
            v = tk.BooleanVar(value=True)
            self.plat_vars[p] = v
            ttk.Checkbutton(pbox, text=p, variable=v).grid(row=0, column=i + 1, padx=(0, 10))

        ttk.Label(top, text="检查要查的站点:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.site_vars = {}
        box = ttk.Frame(top)
        box.grid(row=1, column=1, columnspan=7, sticky="w", pady=(10, 0))
        for i, (k, cfg) in enumerate(SITES.items()):
            v = tk.BooleanVar(value=True)
            self.site_vars[k] = v
            ttk.Checkbutton(box, text=cfg["name"], variable=v).grid(row=0, column=i, padx=(0, 12))

    def _build_table(self, root):
        wrap = ttk.Frame(root, padding=(12, 0))
        wrap.pack(fill="both", expand=True)

        cols = ("site", "kind", "plat", "title", "list", "price", "cny", "url")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=16)
        heads = [("site", "站点", 90), ("kind", "版本", 80), ("plat", "平台", 86),
                 ("title", "商品名", 280),
                 ("list", "原价 ¥", 90), ("price", "现价", 120),
                 ("cny", "折合 ¥", 100), ("url", "网址", 300)]
        for c, txt, w in heads:
            self.tree.heading(c, text=txt)
            anchor = "e" if c in ("list", "price", "cny") else "w"
            self.tree.column(c, width=w, anchor=anchor, stretch=(c in ("title", "url")))

        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.tree.tag_configure("best", foreground="#d4380d")
        self.tree.tag_configure("none", foreground="#999999")
        self.tree.bind("<Double-1>", self.open_row)

    def _build_bottom(self, root):
        bot = ttk.Frame(root, padding=(12, 8))
        bot.pack(fill="x")
        self.status = ttk.Label(bot, text="输入游戏名后点「开始比价」。双击结果行可打开商品页。")
        self.status.pack(side="left")
        self.pb = ttk.Progressbar(bot, mode="indeterminate", length=160)
        self.pb.pack(side="right")

    # ------------------------------------------------------------ 交互

    def search(self):
        kw = self.e_cn.get().strip()
        if not kw:
            messagebox.showwarning("提示", "请先填游戏名")
            return
        if self.busy:
            return
        only = {k for k, v in self.site_vars.items() if v.get()} or None
        kinds = []
        if self.kbase_var.get():
            kinds.append("本体")
        if self.kdlc_var.get():
            kinds.append("DLC/附加")
        if not kinds:
            messagebox.showwarning("提示", "请至少勾选「本体」或「DLC/附加」其中一个")
            return
        platforms = [p for p, v in self.plat_vars.items() if v.get()]
        if not platforms:
            messagebox.showwarning("提示", "请至少勾选一个平台")
            return
        self.busy = True
        self.btn.configure(state="disabled", text="比价中…")
        self.status.configure(text="正在获取汇率…")
        self.pb.start(12)
        for i in self.tree.get_children():
            self.tree.delete(i)

        en = self.e_en.get().strip()
        threading.Thread(target=self._work, args=(kw, en, only, kinds, platforms),
                         daemon=True).start()

    def _work(self, kw, en, only, kinds, platforms):
        try:
            self.q.put(("status", "正在获取汇率…"))
            fx = core.fetch_fx()
            self.fx = fx
            kw_en = en
            if not kw_en:
                self.q.put(("status", "正在解析英文名…"))
                info = core.resolve_steam(kw)
                kw_en = info["en"] if info else kw
            self.q.put(("status", f"正在抓取各站（英文名：{kw_en}），大约需要半分钟…"))
            results, errors = core.collect(kw, kw_en, only)
            rows = core.build_rows(results, errors, kw, kw_en, fx, kinds=kinds,
                                   platforms=platforms)
            self.q.put(("done", rows, kw, kw_en))
        except Exception as e:
            self.q.put(("error", f"{type(e).__name__}: {e}"))

    def login_steampy(self):
        if self.busy:
            return
        self.busy = True
        self.btn.configure(state="disabled")

        def w():
            ev = threading.Event()

            def ask():
                messagebox.showinfo(
                    "登录匹歪",
                    "接下来会打开一个浏览器窗口。\n"
                    "请在里面登录 SteamPY（匹歪）账号，登录完成后回到本窗口点「确定」。")
                ev.set()

            self.root.after(0, ask)
            ev.wait()
            try:
                core.login("steampy")
                self.q.put(("status", "匹歪登录态已保存，可以正常查询了"))
            except Exception as e:
                self.q.put(("error", f"登录失败：{type(e).__name__}: {e}"))
            finally:
                self.q.put(("free", ""))

        threading.Thread(target=w, daemon=True).start()

    def export_html(self):
        if not self.rows:
            messagebox.showinfo("提示", "还没有结果，先查一次再导出")
            return
        kw = self.e_cn.get().strip() or "比价结果"
        path = report.write_html(self.rows, core.ROOT / "比价结果.html", kw, self.fx)
        webbrowser.open(str(path))
        self.status.configure(text=f"已生成 {path}")

    def open_row(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        url = self.tree.item(sel[0], "values")[-1]
        if url and url.startswith("http"):
            webbrowser.open(url)

    # ------------------------------------------------------------ 主线程轮询

    def _pump(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self.status.configure(text=msg[1])
                elif kind == "done":
                    self.rows = msg[1]
                    self._fill(msg[1], msg[2], msg[3])
                    self.busy = False
                    self.btn.configure(state="normal", text="开始比价")
                    self.pb.stop()
                elif kind == "error":
                    self.busy = False
                    self.btn.configure(state="normal", text="开始比价")
                    self.pb.stop()
                    self.status.configure(text=msg[1])
                    messagebox.showerror("出错", msg[1])
                elif kind == "free":
                    self.busy = False
                    self.btn.configure(state="normal", text="开始比价")
                    self.pb.stop()
        except Empty:
            pass
        self.root.after(120, self._pump)

    def _fill(self, rows, kw, kw_en):
        best = next((r["cny"] for r in rows if r["cny"]), None)
        for r in rows:
            if r["cny"] is None:
                note = r.get("note") or r["title"]
                self.tree.insert("", "end",
                                 values=(r["site"], "", "", note, "", "", "",
                                         r.get("url", "")),
                                 tags=("none",))
                continue
            tag = ("best",) if r["cny"] == best else ()
            self.tree.insert("", "end", values=(
                r["site"], r["kind"], r.get("plat", ""), r["title"],
                f'{r["list"]:.2f}' if r["list"] else "-",
                f'{r["price"]:.2f} {r["cur"]}',
                f'¥{r["cny"]:.2f}{"  ★最低" if r["cny"] == best else ""}',
                r["url"]), tags=tag)
        shown = sum(1 for r in rows if r["cny"] is not None)
        tip = f'「{kw}」共 {shown} 条报价，按折合人民币升序。双击行打开商品页。'
        for reason in UNAVAILABLE.values():
            tip += "  ※ " + reason
        self.status.configure(text=tip)


def main():
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
