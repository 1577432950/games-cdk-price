# -*- coding: utf-8 -*-
"""命令行版：用带调试端口的参数启动你自己的 Edge / Chrome。

网页版界面上就有这个按钮（「用我自己的浏览器」），一般用不着这个脚本；
留着是给不方便开界面、或者想写进快捷方式的场景。

用法：
    python debug_browser.py              # 自动挑 Edge / Chrome
    python debug_browser.py --chrome     # 指定用 Chrome
    python debug_browser.py --port 9223  # 换端口（要和本程序一致）

原理：本程序登录时会先找一个开着调试端口的浏览器并「接管」它 ——
接管之后登录页就是那个浏览器当前窗口里的一个新标签，而不是另弹一个窗口。
启动用的还是你自己的 profile，书签、插件、已登录的网站都在。

注意：同一个 profile 不能被两个进程同时使用，所以**先完全退出浏览器**再跑；
没退干净的话脚本会检测到并提示你，不会去杀你的浏览器。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="用带调试端口的方式启动你自己的浏览器")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--edge", action="store_true", help="用 Microsoft Edge")
    g.add_argument("--chrome", action="store_true", help="用 Google Chrome")
    ap.add_argument("--port", type=int, default=core.LOGIN_DEBUG_PORT,
                    help=f"调试端口，默认 {core.LOGIN_DEBUG_PORT}")
    a = ap.parse_args()

    prefer = "edge" if a.edge else ("chrome" if a.chrome else None)
    ok, msg = core.launch_debug_browser(a.port, prefer)
    print(("OK：" if ok else "没能启动：") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
