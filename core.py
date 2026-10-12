# -*- coding: utf-8 -*-
"""
核心调度：浏览器会话、并发抓取、汇率、英文名解析、结果整理。
GUI 与 CLI 共用这一层。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
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

# 登录用的浏览器调试端口。端口活着 = 有个浏览器可以被「接管」，
# 接管之后登录页会作为**新标签**开在它当前窗口里，而不是另弹一个窗口。
# 用户自己那个浏览器如果带 --remote-debugging-port 启动，这里就能认出它。
LOGIN_DEBUG_PORT = int(os.environ.get("CDK_DEBUG_PORT") or 9222)
# 自己起的登录窗口也开在这个端口上，下次登录就能接管它、只开新标签
_DEBUG_PORT_CANDIDATES = tuple(dict.fromkeys(
    (LOGIN_DEBUG_PORT, 9222, 9223)))


# 探本机回环地址必须绕开系统代理。
# 走代理的话请求会被转发出去、拿到 502/407 之类的应答，看起来就像「这个端口上
# 没有浏览器」—— 于是明明活着也接管不了，还会被误判成「端口没起来」。
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _debug_port_alive(port, timeout=0.8):
    """这个端口上有没有一个可接管的浏览器？"""
    try:
        with _NO_PROXY_OPENER.open(
                f"http://127.0.0.1:{int(port)}/json/version", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def find_attachable_browser(ports=None):
    """找一个能被接管的浏览器，返回它的调试端口；没有返回 None。"""
    for p in (ports or _DEBUG_PORT_CANDIDATES):
        if _debug_port_alive(p):
            return p
    return None


# 用户自己的浏览器怎么找。profile 用真实目录，这样书签、插件、已登录的站点都在。
BROWSER_SPECS = {
    "edge": {
        "name": "Microsoft Edge",
        "exe": [r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"],
        "profile": r"%LOCALAPPDATA%\Microsoft\Edge\User Data",
        "procs": ("msedge.exe",),
    },
    "chrome": {
        "name": "Google Chrome",
        "exe": [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"],
        "profile": r"%LOCALAPPDATA%\Google\Chrome\User Data",
        "procs": ("chrome.exe",),
    },
}


# 登录专用窗口的数据目录。
# 用户自己的 Edge / Chrome 正在跑时，Chromium 不允许第二个进程共用同一份用户数据目录，
# 这时退到这份独立目录另起一个「登录专用」窗口：既不动他正在用的窗口（关掉会丢标签页），
# 又能把登录态自己留住 —— 下次登录直接接管它，只开新标签。
LOGIN_PROFILE_DIR = (Path(os.environ.get("LOCALAPPDATA")
                          or os.environ.get("XDG_DATA_HOME")
                          or str(Path.home())) / "CDKPrice" / "browser-profile")

# junction（目录联接）放这儿。名字里带 profile-link，一眼能看出是「指向真实 profile 的入口」。
PROFILE_LINK_ROOT = (Path(os.environ.get("LOCALAPPDATA")
                          or os.environ.get("XDG_DATA_HOME")
                          or str(Path.home())) / "CDKPrice")


def _profile_link(key, profile):
    """给真实 profile 建一个 junction，返回联接路径；建不了返回 None。

    **为什么要绕这一下**（本机 Edge 153 实测出来的）：
    Chromium 136 起出于安全，**在默认用户数据目录上会直接忽略 --remote-debugging-port**。
    用真实 profile 路径启动，进程起得来（十来个），但调试端口永远不监听 ——
    表现就是「浏览器明明开了，却怎么都接管不了」。
    换成指向**同一份** profile 的 junction 路径，端口 0.5 秒就起来了。
    profile 还是那一份，书签、扩展、已登录的站点一个不少。

    已存在且指向正确就复用；指向别的目标就换个名字，不去删它（删除是不可逆的）。
    """
    if os.name != "nt":
        return None                      # junction 是 Windows 的东西
    try:
        PROFILE_LINK_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    target = str(Path(profile).resolve())
    try:
        real_target = os.path.realpath(target).lower()
    except OSError:
        real_target = target.lower()

    for n in range(1, 5):
        link = PROFILE_LINK_ROOT / (f"{key}-profile-link" if n == 1
                                    else f"{key}-profile-link-{n}")
        if link.exists() or link.is_symlink():
            try:
                if os.path.realpath(link).lower() == real_target:
                    return link          # 已经是我们要的那条路
            except OSError:
                pass
            continue                     # 指向别处，换个名字，不删它
        try:
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), target],
                           capture_output=True, timeout=15)
        except Exception:
            return None
        try:
            if link.exists() and os.path.realpath(link).lower() == real_target:
                return link
        except OSError:
            pass
    return None


# 起「登录专用窗口」（独立数据目录）时，把真实 profile 里**读得到**的东西搬过去。
# 目的不是完整克隆，而是让用户能感知到的东西跟过去：已登录的站点、书签、表单。
# Cookies 通常搬不动（Edge 开着时被独占锁），但匹歪的令牌在 Local Storage 里 ——
# 实测这部分能复制成功，所以「不用重新登录」这件事在独立窗口上也成立。
_PROFILE_SYNC_FILES = (
    "Local State",
    "Default/Preferences",
    "Default/Secure Preferences",
    "Default/Login Data",
    "Default/Web Data",
    "Default/Bookmarks",
    "Default/Network/Cookies",        # 拿得到就拿，拿不到拉倒
)
_PROFILE_SYNC_DIRS = (
    "Default/Local Storage",
    "Default/Session Storage",
    "Default/IndexedDB",
)


def _sync_profile_bits(src, dst, max_files=4000):
    """把真实 profile 里能读的部分复制到独立目录，返回成功搬运的条目数。

    尽力而为：任何一项被锁住都只是跳过，绝不影响启动。
    先写 `.tmp` 再原子改名 —— 半截的 Preferences / Login Data 会让浏览器出怪问题。
    """
    src, dst = Path(src), Path(dst)
    if not src.exists():
        return 0
    try:
        if src.resolve() == dst.resolve():
            return 0                  # 同一份目录，不用搬
    except OSError:
        return 0
    done = 0
    for rel in _PROFILE_SYNC_FILES:
        s = src / rel
        if not s.is_file():
            continue
        try:
            d = dst / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            tmp = d.with_name(d.name + ".syncing")
            shutil.copy2(s, tmp)
            os.replace(tmp, d)
            done += 1
        except OSError:
            continue
    for rel in _PROFILE_SYNC_DIRS:
        s = src / rel
        if not s.is_dir():
            continue
        n = 0
        try:
            for root, _dirs, files in os.walk(s):
                for fn in files:
                    if n >= max_files:
                        break
                    sp = Path(root) / fn
                    dp = dst / sp.relative_to(src)
                    try:
                        dp.parent.mkdir(parents=True, exist_ok=True)
                        tmp = dp.with_name(dp.name + ".syncing")
                        shutil.copy2(sp, tmp)
                        os.replace(tmp, dp)
                        n += 1
                    except OSError:
                        continue
        except OSError:
            pass
        if n:
            done += 1
    return done


def _browser_exe(key):
    for c in BROWSER_SPECS[key]["exe"]:
        p = Path(os.path.expandvars(c))
        if p.exists():
            return p
    return None


def _running_pids(names):
    """这些进程名有几个在跑；拿不到 psutil 就返回 None（= 不知道）。"""
    try:
        import psutil
    except Exception:
        return None
    n = 0
    try:
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() in names:
                n += 1
    except Exception:
        return None
    return n


def launch_debug_browser(port=None, prefer=None, isolated=False):
    """带调试端口启动一个浏览器窗口，返回 (ok, msg)。

    启动起来之后，登录页就能作为新标签开在它当前那个窗口里。

    先按「用户自己的数据目录」试 —— 书签、插件、已登录的站点都在，最省事。
    注意走的是 `_profile_link()` 建的 **junction 路径**，不是 profile 原始路径：
    Chromium 136+ 在默认目录上会忽略调试端口，直连必然起不来（见 `_profile_link` 的说明）。
    同一份 profile，换个入口路径，端口就能起来。

    但他那个浏览器正开着时，同一份 profile 不能被两个进程共用，
    这时**不会**去动他正在用的窗口（关掉会丢标签页和未提交内容），
    而是换一份独立数据目录另起一个**登录专用**窗口。
    所以两条路都不需要用户先退出浏览器，按钮永远不会走进死胡同。

    isolated=True 时跳过他的数据目录，直接用独立目录起登录专用窗口。

    数据目录到底被占没被占，最终以「调试端口有没有起来」为准：
    Chromium 在目录被占用时新进程会静悄悄退出，只有端口不会骗人。
    """
    port = int(port or LOGIN_DEBUG_PORT)
    if _debug_port_alive(port):
        return True, f"端口 {port} 上已经有可接管的浏览器了，直接点「登录匹歪」即可"

    keys = [prefer] if prefer in BROWSER_SPECS else ["edge", "chrome"]
    key = next((k for k in keys if _browser_exe(k)), None)
    if not key:
        return False, "没找到 Edge 或 Chrome，没法用这个方式"
    cfg = BROWSER_SPECS[key]
    own = Path(os.path.expandvars(cfg["profile"]))

    # psutil 说他的浏览器没在跑（或不知道），才值得先试他自己的数据目录；
    # 明确开着（n>0）就跳过，省掉一次注定失败的等待。
    n = _running_pids(cfg["procs"])
    tries = []
    if not isolated and own.exists() and not n:
        link = _profile_link(key, own)
        if link:
            tries.append((link, False))
    tries.append((LOGIN_PROFILE_DIR, True))

    flags = 0
    for attr in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        flags |= getattr(subprocess, attr, 0)

    last = ""
    # 两次尝试各自计时（合计最多 20 秒）：一次失败不该把另一次的机会也吃掉。
    for profile, isolated in tries:
        try:
            profile.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        if isolated:
            # 独立目录是空的。先把真实 profile 里读得到的登录态/书签搬过去，
            # 这样用户在这个新窗口里也是「已经登录过」的样子，不用重新登。
            _sync_profile_bits(own, profile)
        cmd = [str(_browser_exe(key)), f"--remote-debugging-port={port}",
               f"--user-data-dir={profile}",
               "--no-first-run", "--no-default-browser-check"]
        if isolated:
            # 独立目录是全新的，Edge 会自作主张弹「登录以同步」确认页，压掉它。
            # 只对独立目录加：用他自己数据目录时不能动他的同步设置。
            cmd.append("--disable-sync")
        try:
            subprocess.Popen(cmd, creationflags=flags, close_fds=True)
        except Exception as e:
            last = f"启动失败：{type(e).__name__}: {e}"
            continue
        deadline = time.time() + (8 if not isolated else 12)
        while time.time() < deadline:
            if _debug_port_alive(port):
                if isolated:
                    return True, (
                        f"{cfg['name']} 正开着，没法共用同一份浏览器数据，"
                        "所以另起了一个**登录专用**窗口（独立数据目录，不动你正在用的那个）。"
                        "现在点「登录匹歪」，登录页会作为新标签开在那个新窗口里；"
                        "这个窗口留着，以后登录都直接在里面开新标签")
                return True, (f"{cfg['name']} 已带调试端口启动，现在点「登录匹歪」，"
                              "登录页会作为新标签开在它当前窗口里")
            time.sleep(0.5)
        last = f"{cfg['name']} 起来了但调试端口 {port} 没监听上"

    return False, (last or "没能启动浏览器") + "，可以换个端口再试（设环境变量 CDK_DEBUG_PORT）"


def browser_situation():
    """现在能不能把登录页开进**用户自己那个**浏览器窗口？

    - "attachable"  ：已经有带调试端口的浏览器，直接接管，登录页 = 它当前窗口的新标签
    - "can_launch"  ：他的浏览器没在跑，用他自己的数据目录起一个就行 ——
                      走 junction 路径（同一份 profile），所以端口起得来，
                      起来的就是他平时的浏览器，书签和登录态都在
    - "need_restart"：他正开着浏览器，但那个实例没开调试端口 ——
                      Chromium 不支持事后加端口，只能重启它一次
                      （重启时同样走 junction，否则端口起不来）
    - "none"        ：没找到 Edge / Chrome
    """
    if find_attachable_browser():
        return "attachable"
    key = next((k for k in ("edge", "chrome") if _browser_exe(k)), None)
    if not key:
        return "none"
    if _running_pids(BROWSER_SPECS[key]["procs"]):
        return "need_restart"
    return "can_launch"


def restart_browser_debug(port=None, prefer=None, grace=4):
    """把用户自己的浏览器重启到「带调试端口」的状态，返回 (ok, msg)。

    这是「登录页开在你当前那个窗口的新标签里」的**唯一**前提：Chromium 不支持
    给一个已经跑起来的实例事后开调试端口，只能让它重启一次。

    **这是个有代价的操作，得跟用户说清楚**：本机 Edge 153 实测，`taskkill` 不带 /F
    （礼貌请求）关不掉它 —— 主进程和后台进程根本不响应，25 秒都退不干净，最后只能强杀。
    强杀之后 Edge 把上次退出记成 Crashed，`--restore-last-session` 也不认，
    **标签页回不来**（书签、登录态、扩展都还在，那些是存在 profile 里的）。
    所以无损的那条路（浏览器关着时直接起 / 另起登录专用窗口）才是首选。

    关的时候仍然先软后硬：软关能让有窗口的那部分走正常关闭流程、尽量把状态落盘，
    所以先给几秒宽限，再由强杀收尾。

    起来时 `--user-data-dir` 走 junction 路径（**不是** profile 原始路径）——
    否则 Chromium 136+ 会忽略调试端口，重启完还是接管不了（见 `_profile_link`）。
    """
    port = int(port or LOGIN_DEBUG_PORT)
    if _debug_port_alive(port):
        return True, "浏览器已经带调试端口在跑了，不用重启"

    keys = [prefer] if prefer in BROWSER_SPECS else ["edge", "chrome"]
    key = next((k for k in keys if _browser_exe(k)), None)
    if not key:
        return False, "没找到 Edge 或 Chrome，没法用这个方式"
    cfg = BROWSER_SPECS[key]
    exe_name = cfg["procs"][0]
    profile = Path(os.path.expandvars(cfg["profile"]))
    if not profile.exists():
        return False, f"没找到 {cfg['name']} 的用户数据目录：{profile}"
    # 直连默认目录会拿不到调试端口，走 junction 才是能用的那条路。
    # 建不出联接就退回原路径（老版本 Chromium 上照样能用）。
    data_dir = _profile_link(key, profile) or profile

    for soft in (True, False):
        if not _running_pids(cfg["procs"]):
            break
        cmd = ["taskkill", "/IM", exe_name] + ([] if soft else ["/F"])
        try:
            subprocess.run(cmd, capture_output=True, timeout=grace + 4)
        except subprocess.TimeoutExpired:
            pass                 # 多半被确认框挡住了，交给下一轮强杀
        except Exception as e:
            return False, f"关闭 {cfg['name']} 失败：{type(e).__name__}: {e}"
        deadline = time.time() + (grace if soft else 6)
        while time.time() < deadline:
            if not _running_pids(cfg["procs"]):
                break
            time.sleep(0.5)
    if _running_pids(cfg["procs"]):
        return False, (f"{cfg['name']} 没能在预期时间内退出 —— 可能有个确认对话框挡着，"
                       "手动关掉它再试一次")

    flags = 0
    for attr in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        flags |= getattr(subprocess, attr, 0)
    try:
        subprocess.Popen([str(_browser_exe(key)), f"--remote-debugging-port={port}",
                          f"--user-data-dir={data_dir}", "--restore-last-session",
                          "--no-first-run", "--no-default-browser-check"],
                         creationflags=flags, close_fds=True)
    except Exception as e:
        return False, f"启动失败：{type(e).__name__}: {e}"

    deadline = time.time() + 20
    while time.time() < deadline:
        if _debug_port_alive(port):
            return True, (f"{cfg['name']} 已带调试端口重启，之后登录都会开在它当前窗口的"
                          "新标签里。刚才那几个标签页可能回不来了 —— 书签、登录态、"
                          "扩展都还在，要用的页面手动重开一下就行")
        time.sleep(0.5)
    return False, f"{cfg['name']} 重启了但调试端口 {port} 没监听上"



# ---------------------------------------------------------------- 浏览器会话

class BrowserSession:
    """优先用系统自带的 Edge / Chrome，都没有才回落到 Playwright 自带的 Chromium。

    stealth=True（默认，抓取用）：隐藏 webdriver 标记 + 关闭沙箱，降低被判定为爬虫的概率。
    stealth=False（手动登录用）：用完全正常的浏览器参数。登录的是真人，不需要伪装，
    伪装标志反而可能让目标站的人机验证（如腾讯滑块）反复触发。
    """

    def __init__(self, headless=True, site_key=None, stealth=True, debug_port=None):
        from playwright.sync_api import sync_playwright
        self._sp = sync_playwright().start()
        self.attached = False          # True = 接管的是别人（通常是用户）的浏览器
        self.owned = False             # True = 这个窗口是我们自己起的（可以清标签）
        self.browser = self._launch(headless, stealth, debug_port)
        ctx_kw = {"user_agent": sites.UA, "locale": "zh-CN",
                  "viewport": {"width": 1440, "height": 900}}
        # 登录态整体交给 storage_state 还原：它同时带 cookie 和 localStorage。
        # 之前只 add_cookies() 是错的 —— 匹歪的 token 存在 localStorage 里，
        # 只还原 cookie 等于没登录（表现就是「登录了也搜不到游戏」）。
        if site_key:
            f = STATE_DIR / f"{site_key}.json"
            if f.exists():
                try:
                    json.loads(f.read_text("utf-8"))      # 坏文件先挡掉，别让 new_context 抛错
                    ctx_kw["storage_state"] = str(f)
                except Exception:
                    pass
        self.ctx = self.browser.new_context(**ctx_kw)
        if stealth:
            self.ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

    @classmethod
    def attach(cls, port, owned=False):
        """接管一个已经开着调试端口的浏览器（CDP），复用它的窗口和登录态。

        接管之后 new_page() 是**在当前窗口里开新标签**，而不是新开一个窗口 ——
        这正是「登录开在我现在的浏览器里」想要的效果。
        注意：接管的浏览器不是我们起的，close() 时只断开、绝不能关掉它。

        owned=True 表示这个窗口其实是**我们自己刚起的**（独立数据目录那种）。
        它和用户自己那个浏览器走同一套接管逻辑，区别只在于允许我们清理多余标签。
        """
        from playwright.sync_api import sync_playwright
        s = cls.__new__(cls)
        s._sp = sync_playwright().start()
        s.attached = True
        s.owned = bool(owned)
        s.browser = s._sp.chromium.connect_over_cdp(f"http://127.0.0.1:{int(port)}")
        ctxs = s.browser.contexts
        # 复用它已有的上下文（= 用户日常那个 profile），没有才新建
        s.ctx = ctxs[0] if ctxs else s.browser.new_context()
        return s

    @classmethod
    def for_login(cls, site_key="steampy", isolated=False):
        """登录专用会话：能接管就接管，接不了才自己起窗口。

        接管优先，因为那通常就是用户自己正在用的浏览器 —— 登录页会作为新标签
        开在他当前那个窗口里。自己起的窗口也会打开调试端口，于是**下次**登录
        能接管它，同样只开新标签、不再重复弹窗。

        isolated=True 时跳过接管，直接用独立数据目录起一个登录专用窗口。
        自己起窗口统一走 launch_debug_browser（Popen 一个持久数据目录的实例），
        好处是窗口关掉再开还是同一份 profile，登录态能自己留住。
        """
        if not isolated:
            port = find_attachable_browser()
            if port:
                try:
                    return cls.attach(port)
                except Exception:
                    pass
        ok, _ = launch_debug_browser(port=LOGIN_DEBUG_PORT, isolated=isolated)
        if ok:
            port = find_attachable_browser()
            if port:
                try:
                    return cls.attach(port, owned=True)
                except Exception:
                    pass
        # 兜底：连 Popen 都起不来时，退回 Playwright 自带的启动方式
        s = cls(headless=False, site_key=site_key, stealth=False,
                debug_port=LOGIN_DEBUG_PORT)
        s.owned = True                 # 自己起的窗口，允许清理多余标签
        return s

    def _launch(self, headless, stealth=True, debug_port=None):
        args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"] if stealth else []
        if debug_port:
            # 留着调试端口，下次登录就能接管这个窗口（只开新标签，不再弹新窗口）
            args = args + [f"--remote-debugging-port={int(debug_port)}"]
        for channel in ("msedge", "chrome"):
            try:
                return self._sp.chromium.launch(channel=channel, headless=headless, args=args)
            except Exception:
                continue
        return self._sp.chromium.launch(headless=headless, args=args)

    def new_page(self):
        return self.ctx.new_page()

    def save_state(self, site_key):
        STATE_DIR.mkdir(exist_ok=True)
        self.ctx.storage_state(path=str(STATE_DIR / f"{site_key}.json"))

    def close(self, keep_window=False):
        """关掉会话。

        keep_window=True（或接管模式下）只断开连接、**不关浏览器窗口**：
        接管的可能是用户自己的浏览器，关掉它等于把人家的窗口关了；
        自己起的窗口留着则能让下次登录复用它、只开新标签。
        """
        if self.attached or keep_window:
            # 只停掉 Playwright 驱动 = 断开 CDP 连接，对方浏览器不受影响
            try:
                self._sp.stop()
            except Exception:
                pass
            return
        # 三步各自独立 try：任何一步失败都不能拖累后面的关闭动作，
        # 否则会留下关不掉的浏览器窗口（曾经就是 ctx.close() 抛异常导致 browser 没关）
        for fn in (self.ctx.close, self.browser.close, self._sp.stop):
            try:
                fn()
            except Exception:
                pass



def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def steampy_wait_login(s, pg, initial="", page_gone=None, timeout=900, poll=2,
                       require_change=True):
    """等用户在窗口里完成匹歪登录，成功返回 True。

    `initial` 是窗口刚打开时页面里已有的令牌（可能是 storage_state 还原来的旧登录态）。
    判定成功要求令牌**变成另一个**，不能只看「当前有有效令牌」：否则本机已经登录过时，
    用户点「重新登录」想换号，窗口一开就被判成功然后自动关掉，根本没法换。

    require_change=False 时改为「页面上有有效令牌就算登录」：接管用户自己的浏览器时，
    他很可能早就登录着匹歪了，这时没必要逼他退出再登一遍。

    page_gone 是可选回调，返回 True 表示用户把窗口关了。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page_gone and _safe(page_gone, True):
            # 关窗后再确认一次：用户可能刚登录完就顺手把窗口关了。
            # 但页面关掉之后就读不到令牌了，所以再退一步看磁盘上已有的登录态 ——
            # 本来就有旧登录态、只是不想换号了的用户，不该被报成「没检测到登录」。
            return steampy_logged_in(s, pg) or steampy_check() == "ok"
        tok = steampy_token(pg)
        if tok and (tok != initial or not require_change) and steampy_logged_in(s, pg):
            return True
        time.sleep(poll)
    return False


def login(site_key, on_ready=None):
    """打开浏览器让用户登录一次，保存登录态。on_ready 在浏览器打开后回调。

    匹歪的令牌存在 localStorage 里，所以要等它真的登录成功再保存；
    其它站点沿用「打开 → 回调 → 保存」的老流程。

    会优先接管一个已开着调试端口的浏览器（通常就是用户自己那个），
    这样登录页开在他当前窗口的新标签里，而不是另弹一个窗口。
    """
    url = {"steampy": "https://steampy.com/", "sonkwo": "https://www.sonkwo.cn/",
           "fhyx": "https://www.fhyx.com/", "gmg": "https://www.greenmangaming.com/zh/",
           "fanatical": "https://www.fanatical.com/zh-hans/"}.get(site_key, "https://steampy.com/")
    s = BrowserSession.for_login(site_key)
    pg = s.new_page()
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    if on_ready:
        on_ready()
    if site_key == "steampy":
        print("请在弹出的窗口里登录匹歪，登录成功后会自动保存…", flush=True)
        initial = steampy_token(pg)          # 还原出来的旧登录态，不能当成「刚登录」
        # 本机已经登录着匹歪时，用户点登录多半是想换号 —— 这时必须等令牌真的换掉；
        # 本机没登录过，那页面上现成的有效令牌直接采用就好（接管用户浏览器时很常见）。
        if steampy_wait_login(s, pg, initial, lambda: pg.is_closed(),
                              require_change=steampy_check() == "ok"):
            print("已检测到登录成功。", flush=True)
        else:
            print("窗口已关闭，未检测到新的登录。", flush=True)
    s.save_state(site_key)
    if s.attached:
        _safe(pg.close, None)                # 只关我们开的那个标签，别动用户的浏览器
    s.close(keep_window=s.attached)
    return str(STATE_DIR / f"{site_key}.json")


# ---------------------------------------------------------------- 匹歪登录态

def steampy_token(pg):
    """取匹歪的登录令牌。

    匹歪的登录态**不是 cookie**：站点自己的 app.js 里，令牌放在 localStorage 的
    accessToken 键里，每次请求以同名 header 带上去
    （`headers:{accessToken: localStorage.getItem("accessToken")}`）。
    所以只还原 cookie 等于没登录 —— 这正是「登录了也搜不到游戏」的原因。
    """
    try:
        return pg.evaluate("() => localStorage.getItem('accessToken')") or ""
    except Exception:
        return ""


def steampy_token_from_state():
    """取匹歪 accessToken，没有就返回 ""（抓取适配器与登录态校验都用它）。

    令牌就在 storage_state 文件的 origins[].localStorage 里，所以不用开浏览器。
    注意本地 userInfo 里的 nickName / username 存的其实是邮箱和内部账号串，
    不适合拿来展示，这里只取令牌。
    """
    f = STATE_DIR / "steampy.json"
    if not f.exists():
        return ""
    try:
        st = json.loads(f.read_text("utf-8"))
        for origin in st.get("origins") or []:
            for item in origin.get("localStorage") or []:
                if item.get("name") == "accessToken":
                    return item.get("value") or ""
    except Exception:
        pass
    return ""


def steampy_check():
    """校验本地匹歪登录态是否还有效，返回 state 字符串：

    "ok"      令牌有效，可以正常比价
    "none"    本地根本没登录过
    "expired" 有令牌但服务端说失效了（匹歪会在令牌失效时清掉它）
    "unknown" 网络不通或响应看不懂 —— 这种情况不能谎报「未登录」，
              否则用户明明登录过却看到按钮退回未登录态，会以为又坏了
    """
    token = steampy_token_from_state()
    if not token:
        return "none"
    try:
        r = sites.http_get("https://steampy.com/xboot/user/info",
                           headers={**sites.HEADERS, "accessToken": token},
                           timeout=10)
        d = r.json()          # curl_cffi 的 .text 是属性不是方法，用 .json()
    except Exception:
        return "unknown"
    if not isinstance(d, dict):
        return "unknown"
    if d.get("success") is True:
        return "ok"
    return "expired" if d else "unknown"


def steampy_logged_in(s, pg):
    """带 accessToken 去问匹歪的用户接口，success 为 true 才算登录成功。

    不带这个 header 时服务端一律回「您还未登录」，带一个无效值才回
    「登录已失效」—— 所以判断登录态必须自己把这个 header 补上。
    """
    token = steampy_token(pg)
    if not token:
        return False
    try:
        r = s.ctx.request.get("https://steampy.com/xboot/user/info",
                              headers={"accessToken": token}, timeout=10000)
        return json.loads(r.text() or "{}").get("success") is True
    except Exception:
        return False


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


def _http_retry(url, timeout=6, tries=3, **kw):
    """带重试的 GET。这个网络环境访问 Steam 偶发 `CONNECT tunnel failed, 502`，
    单次失败就放弃的话，英文名解析会时好时坏（表现为「同一个词有时能搜到有时不能」）。
    失败时会等满整个 timeout 才抛，所以超时给短一点、多试几次更划算。
    """
    from curl_cffi import requests as creq
    last = None
    for i in range(tries):
        try:
            r = creq.get(url, timeout=timeout, impersonate="chrome", **kw)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:
            last = e
        if i < tries - 1:
            time.sleep(0.6 * (i + 1))
    raise last


def resolve_steam(kw, timeout=6):
    """用 Steam 搜索拿英文名与 appid。失败返回 None（国内网络可能连不通 Steam）。

    坑：`api/storesearch` **只认英文关键词**，拿中文去搜一律返回 0 条
    （实测「消逝的光芒2」「生化危机8」都是 total=0）。而英文站（Fanatical /
    GMG / Humble …）必须用英文名搜，于是「只填中文名」时它们会**静默**变成
    「该站没有匹配商品」—— 看着像站点没货，其实是关键词没解析出来。

    所以中文关键词走第二条路：`search/suggest`（支持中文，国区译名也能匹配）
    拿 appid，再用 `api/appdetails?l=en` 换成英文名。
    """
    def get(url):
        return _http_retry(url, timeout=timeout)

    out = {"appid": None, "en": None, "zh": None}
    cjk = bool(re.search(r"[\u4e00-\u9fff]", kw or ""))

    # 1) 关键词是英文时 storesearch 最准。中文关键词一律返回 0 条，直接跳过 ——
    #    既省两次必然落空的请求，也避开它偶发的 502 抖动（每次要等满超时）。
    if not cjk:
        for lang in ("en", "zh-cn"):
            try:
                u = ("https://store.steampowered.com/api/storesearch/?term="
                     + urllib.parse.quote(kw) + "&cc=cn&l=" + lang)
                items = get(u).json().get("items") or []
            except Exception:
                items = []
            if items:
                out["appid"] = items[0].get("id")
                out["en" if lang == "en" else "zh"] = items[0].get("name")
        if out["en"]:
            return out

    # 2) 中文关键词（或上一步没命中）：suggest 拿 appid → appdetails 换英文名
    try:
        u = ("https://store.steampowered.com/search/suggest?term="
             + urllib.parse.quote(kw) + "&f=games&cc=cn&l=schinese&use_store_query=1")
        ids = re.findall(r'data-ds-appid="(\d+)"', get(u).text or "")
    except Exception:
        ids = []
    if ids:
        out["appid"] = ids[0]
        try:
            u = ("https://store.steampowered.com/api/appdetails?appids="
                 + ids[0] + "&l=en&filters=basic")
            out["en"] = ((get(u).json().get(ids[0]) or {}).get("data") or {}).get("name")
        except Exception:
            pass
    return out if out["en"] else None


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
# 注意：\baccess\b 要排除 "Early Access"（抢先体验期的本体，不是账号）
ACCOUNT_RE = re.compile(
    r"成品账号|账号|初始号|成品号|steam\s*accounts?|\baccounts?\b|离线激活|离线账号"
    r"|(?<!early )\baccess\b|\boffline\s*activ", re.I)
EXTRA_RE = re.compile(r"soundtrack|ost|原声|音乐|dlc|季票|season pass|bundle|合集|同捆", re.I)
NONGAME_URL_RE = re.compile(r"/(book|comic|ebook|merch)/", re.I)

# 游戏内道具 / 货币 / 掉宝 —— 同样不是游戏本体，绝不能算成「本体」报价。
# 下面每条都来自 Kinguin 列表页的真实样本：
#   "Dying Light 2 Stay Human Items > Global > PC > Twitch Drop"   ← 用户报的那条
#   "Adopt Me Items > Foods > Legendary > Ride-A-Pet Potion > ..."
#   "Apex Legends - 1000 Apex Coins EA App CD Key"
ITEM_RE = re.compile(
    r"twitch\s*drop|in-?game\s*items?|游戏内(道具|物品)|掉宝"
    r"|\bitems?\s*>|>\s*items?\b"                      # Kinguin 的面包屑分类节点
    r"|\b\d+\s+(?:\w+\s+){0,2}(?:coins?|credits?|points|gems?|tokens?)\b"
    r"|\b(?:apex\s*coins?|v-?bucks|riot\s*points|minecoins|steam\s*credits?)\b"
    r"|cosmetics?|\bskins?\b|\bemotes?\b|皮肤|外观|饰品|时装|道具|点券|钻石|宝石",
    re.I)

# 默认展示的分类。界面上「本体」「DLC/附加」两个勾选框就是这两个值，
# 其余分类（道具/周边/账号）不提供勾选，永远不展示。
DEFAULT_KINDS = ("本体", "DLC/附加")


# ---------------------------------------------------------------- 平台识别

# 平台词表全部取自各站真实列表页标题，别凭印象加词。样本：
#   "ELDEN RING - Shadow of the Erdtree DLC EU PC Steam CD Key"     -> Steam
#   "Cyberpunk 2077 - Phantom Liberty DLC GOG CD Key"               -> GOG
#   "Alan Wake 2 Epic Games Green Gift Redemption Code"             -> Epic
#   "Elden Ring Xbox One & Xbox Series X"                           -> Xbox
#   "Elden Ring PS5 Account"                                        -> PlayStation
#   "Zelda: Tears of the Kingdom US Nintendo Switch CD Key"         -> Switch
#   "Battlefield 2042 PC EA App CD Key"                             -> 其他平台
# 一条标题可能同时命中多个（"Starfield ... Xbox Series X|S / Windows 10 CD Key"），
# 全部收下，展示时用 / 连接。
#
# 注意几个刻意收紧的地方，避免误伤游戏名：
#   - Epic 只认 "Epic Games" / "EGS"，不认单独的 "Epic"（否则 "Epic Mickey" 会中招）
#   - Switch 只认 "Nintendo Switch" 或独立单词 switch
#   - Origin 用 (?!\s+of\b) 排除 "Origin of ..." 这类游戏名（"Origins" 因词边界天然不匹配）
PLATFORM_PATTERNS = (
    ("Steam",       re.compile(r"\bsteam\b", re.I)),
    ("Epic",        re.compile(r"\bepic\s*games\b|\begs\b", re.I)),
    ("GOG",         re.compile(r"\bgog\b|gog\.com", re.I)),
    ("Xbox",        re.compile(r"\bxbox\b", re.I)),
    ("PlayStation", re.compile(r"\bplaystation\b|\bps[45]\b|\bpsn\b", re.I)),
    ("Switch",      re.compile(r"\bnintendo\s*switch\b|\bswitch\b", re.I)),
    ("其他平台",     re.compile(
        r"\bea\b|\borigin\b(?!\s+of\b)"
        r"|\bubisoft\b|\buplay\b|\bubisoft\s*connect\b"
        r"|\bbattle\.?net\b|\bblizzard\b|\brockstar\b"
        r"|\bmicrosoft\s*store\b|\bwindows\s*(?:10|11)\b", re.I)),
)

# 界面上「显示平台」的勾选框就是这些值，顺序即展示顺序。
# 「未标注」= 标题和站点接口里都没有平台线索（国内站、多数授权零售站都是这样）。
PLATFORM_ORDER = ("Steam", "Epic", "GOG", "Xbox", "PlayStation", "Switch",
                  "其他平台", "未标注")
DEFAULT_PLATFORMS = PLATFORM_ORDER
UNKNOWN_PLATFORM = "未标注"

# 适配器直接给的结构化平台名（Humble 的 delivery_methods 等）-> 统一标签
_RAW_PLATFORM = {
    "steam": "Steam", "epic": "Epic", "epic games": "Epic", "egs": "Epic",
    "gog": "GOG", "gog.com": "GOG",
    "xbox": "Xbox", "xbox one": "Xbox", "xbox series": "Xbox",
    "nintendo": "Switch", "nintendo switch": "Switch", "switch": "Switch",
    "playstation": "PlayStation", "psn": "PlayStation",
    "origin": "其他平台", "ea": "其他平台", "ea app": "其他平台",
    "uplay": "其他平台", "ubisoft": "其他平台", "ubisoft connect": "其他平台",
    "battlenet": "其他平台", "battle.net": "其他平台", "blizzard": "其他平台",
    "rockstar": "其他平台", "microsoft": "其他平台",
}


def _canon_platform(v):
    """把适配器给的结构化平台名归一成界面上的标签，认不出返回 None。"""
    return _RAW_PLATFORM.get(str(v or "").strip().lower())


def _url_platform_text(url):
    """URL 里也藏着平台信息，而且比标题还准。

    看 Loaded 的真实商品页就能发现，它的 slug 结尾直接写死了发放方式，
    标题里反而只有含糊的 "PC"：

        .../battlefield-2042-pc-steam          标题 "Battlefield 2042 PC (Steam)"
        .../battlefield-2042-gold-edition-pc-origin   标题 "Battlefield 2042 Gold Edition PC"
        .../cyberpunk-2077-ultimate-edition-pc-gog    标题 "... PC (GOG)"
        .../starfield-pc-steam                  标题 "Starfield PC"

    只取路径最后一段的末尾几个词，避免游戏名里恰好出现平台词就误判。
    """
    if not url:
        return ""
    seg = urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return " ".join(seg.replace("-", " ").replace("_", " ").split()[-4:])


def detect_platforms(title="", note="", raw=None, url=""):
    """返回这条商品所属的平台列表；认不出来就是 ["未标注"]。

    raw 是适配器直接给的结构化平台（比如 Humble 的 delivery_methods），比标题可靠，
    排在最前。识别不出就老实说不知道 —— 宁可标「未标注」，也不猜。
    """
    found = []
    for x in (raw if isinstance(raw, (list, tuple)) else [raw]):
        c = _canon_platform(x)
        if c and c not in found:
            found.append(c)
    text = f"{title or ''} {note or ''} {_url_platform_text(url)}"
    for label, pat in PLATFORM_PATTERNS:
        if label not in found and pat.search(text):
            found.append(label)
    if not found:
        return [UNKNOWN_PLATFORM]
    # 按 PLATFORM_ORDER 排序，保证同一条商品每次展示的标签顺序都一样
    return sorted(found, key=lambda x: PLATFORM_ORDER.index(x)
                  if x in PLATFORM_ORDER else 99)


def classify(title, url=""):
    if MERCH_RE.search(title or "") or NONGAME_URL_RE.search(url or ""):
        return "周边"
    if ACCOUNT_RE.search(title or ""):
        return "账号"
    if ITEM_RE.search(title or ""):
        return "道具"
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


def build_rows(results, errors, kw_cn, kw_en, fx, kinds=DEFAULT_KINDS,
               platforms=DEFAULT_PLATFORMS, keep_all=False):
    """kinds：允许保留的版本分类；platforms：允许保留的平台。

    两者传 None 都表示「该项不过滤」。
    keep_all=True 是 kinds=None 的简写，留给命令行 `--all` 用。
    """
    if keep_all:
        kinds = None
    rows = []
    for key, offers in results.items():
        name = SITES[key]["name"]
        risk = SITES[key].get("risk", "授权")
        q = kw_en if SITES[key]["lang"] == "en" else kw_cn
        if errors.get(key):
            rows.append({"site": name, "title": f"[抓取失败] {errors[key][:70]}",
                         "price": None, "cny": None, "url": "", "kind": "错误",
                         "list": None, "plat": "", "note": "", "risk": risk})
        got = 0
        hidden = {}
        hidden_plat = {}
        for o in offers or []:
            if o.get("note") and o.get("price") is None:
                rows.append({"site": name, "title": "[不可用]", "price": None,
                             "cny": None, "url": o.get("url", ""), "kind": "提示",
                             "list": None, "plat": "", "note": o["note"], "risk": risk})
                continue
            title = o.get("title", "")
            # 适配器标了 trusted 的，说明这份结果就是站点自己的搜索接口吐出来的，
            # 不用再拿相关度猜一遍 —— 中文站常返回纯英文标题（匹歪就是这样），
            # 再筛一次会把「消逝的光芒2 → Dying Light 2: Digital Extras Edition」
            # 这类完全正确的命中误杀。
            if not keep_all and not o.get("trusted") and relevance(title, q) < 0.6:
                continue
            kind = classify(title, o.get("url", ""))
            if kinds is not None and kind not in kinds:
                hidden[kind] = hidden.get(kind, 0) + 1
                continue
            plats = detect_platforms(title, o.get("note", ""), o.get("platform"),
                                     o.get("url", ""))
            plat = "/".join(plats)
            if platforms is not None and not (set(plats) & set(platforms)):
                hidden_plat[plat] = hidden_plat.get(plat, 0) + 1
                continue
            got += 1
            cny = o["price"] * fx.get(o["currency"], 1.0)
            lp = o.get("list_price")
            rows.append({
                "site": name, "title": title, "price": o["price"], "cur": o["currency"],
                "cny": round(cny, 2), "url": o.get("url", ""), "kind": kind,
                "plat": plat,
                "list": round(lp * fx.get(o["currency"], 1.0), 2) if lp else None,
                "note": o.get("note", ""), "risk": risk,
            })
        if got == 0 and not errors.get(key) and not any(
                r["site"] == name and r["kind"] in ("错误", "提示") for r in rows):
            hint = "该站在当前地区/关键词下没有匹配商品"
            if SITES[key].get("need_login"):
                hint = "需要登录：点「登录匹歪」按钮登录一次后再查"
            elif hidden or hidden_plat:
                # 有货、但都被筛选挡掉了，别让用户误以为「没货」。
                # 分开统计「版本」和「平台」，只勾本体时不会误报成「没有匹配商品」。
                bits = []
                if hidden:
                    bits.append("、".join(f"{k} {n} 条" for k, n in sorted(hidden.items())))
                if hidden_plat:
                    bits.append("、".join(f"{k} {n} 条"
                                          for k, n in sorted(hidden_plat.items())))
                which = ("版本" if hidden and not hidden_plat else
                         "平台" if hidden_plat and not hidden else "版本/平台")
                hint = f"该站只找到 {'；'.join(bits)}，已被当前「{which}」筛选隐藏"
            rows.append({"site": name, "title": "[无匹配结果]", "price": None,
                         "cny": None, "url": "", "kind": "提示", "list": None,
                         "plat": "", "note": hint, "risk": risk})
    rows = _dedupe(rows)
    rows.sort(key=lambda r: (r["cny"] is None, r["cny"] or 0))
    return rows


# 只认这些公认的跟踪参数，别的 query 参数一律保留 —— 有的站把商品 id 放在
# query 里（匹歪就是 /hotGameDetail?gameId=xxx），整条砍掉会把不同商品并成一条。
_DEDUPE_NOISE = re.compile(r"^(utm_|_ga|gclid|fbclid|ref$|referrer$|spm$)", re.I)


def _url_key(url):
    """把商品页 URL 归一化成去重用的键：小写、去尾斜杠、只去掉跟踪参数。"""
    u = (url or "").strip()
    if not u:
        return ""
    p = urllib.parse.urlsplit(u)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not _DEDUPE_NOISE.match(k)]
    q.sort()
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(),
                                    p.path.rstrip("/"), urllib.parse.urlencode(q), ""))


def _dedupe(rows):
    """同一站点同一商品页只留最便宜的一条（有的站会有大小写重复条目）。"""
    seen = {}
    out = []
    for r in rows:
        if r["cny"] is None or not r["url"]:
            out.append(r)
            continue
        key = (r["site"], _url_key(r["url"]))
        if key in seen:
            old = seen[key]
            if r["cny"] < (old["cny"] or 1e18):
                old.update(r)
            continue
        seen[key] = r
        out.append(r)
    return out
