# 贡献指南

最受欢迎的贡献是 **加一个新站点** 或 **修一个改版后失效的站点**。这两件事流程一样，照着做就行。

## 一、先判断这个站能不能抓

按顺序试，能停在前一步就别往后走：

1. **找 JSON 接口**（最稳，优先）—— 打开搜索页，F12 → Network → 勾 Fetch/XHR，输入关键词，
   看有没有返回商品列表的接口。找到了就直接 `http_get()` 调它，不用浏览器。
   参考 `sites.py` 里的 `humble()`。
2. **服务端渲染的 HTML** —— 关掉 JS 刷新（`curl` 一下），看 HTML 里有没有价格。
   有就用 HTTP + 正则/BeautifulSoup，比开浏览器快十倍。
3. **必须浏览器渲染** —— 上面两条都不行，才用 `browser_scrape()`。

**放弃的信号**：返回 403 / "Just a moment…" / "请稍候…" 这类 Cloudflare 拦截页，
说明对方明确不想被自动访问，别硬搞，这个站不值得加。已经确认抓不了的见 README 的排除清单。

## 二、勘察 DOM（走浏览器路线时才需要）

仓库里的 `probe*.py` / `dump_*.py` / `sniff.py` / `dom_*.py` 就是干这个的，挑一个改改就能用。
核心套路：

```python
import core
s = core.BrowserSession(headless=True)      # 优先走系统 Edge/Chrome
pg = s.new_page()
pg.goto(url, wait_until="domcontentloaded", timeout=60000)
pg.wait_for_timeout(9000)                    # SPA 要等渲染
print(pg.evaluate("() => document.body.innerText.slice(0, 500)"))
```

找卡片容器的时候记住两条：

- **别依赖 styled-components / CSS-in-JS 的类名**，那是构建时生成的哈希值，随时会变。
  要么往上找祖先里的 `a[href]` 拿链接（看 `sites.py` 里的 `KINGUIN_JS`），要么用稳定的属性/结构。
- **先用一个确定有结果的关键词验证**。`cyberpunk 2077` 在某些站返回 0 条是因为它压根不卖，
  不是你选择器写错了 —— 我会因此白排查很久，别重蹈覆辙。

## 三、写适配器

在 `sites.py` 里加一个函数，返回这个结构：

```python
[{"title": str, "price": float, "currency": "CNY|USD|GBP|EUR",
  "list_price": float | None, "url": str, "note": str}]
```

然后注册到 `SITES`：

```python
"key": {"name": "显示名", "lang": "cn|en", "kind": "http|browser",
        "fn": your_func, "risk": "授权|C2C"}
```

- `lang`：`"cn"` 的站用中文关键词搜，`"en"` 的用英文名搜
- `risk`：官方授权零售填 `"授权"`，个人卖家 marketplace 填 `"C2C"`（会打红色警告标签）

能用通用卡片抽取就别写 JS：`browser_scrape(page_factory, url, cfg, ...)`，
`cfg` 给 `card` / `title` / `price` / `list` 四个选择器就够，参考 `FANATICAL_CFG`。

## 四、提交前自检

- [ ] `python cdk_price.py 霍格沃茨之遗 --en "Hogwarts Legacy" --sites 你的key` 有结果
- [ ] 换一个**该站确定有货**的游戏再试一次，确认不是偶然
- [ ] 结果里没有混入周边 / 成品账号 / 共享账号（有的话往 `core.py` 的过滤正则里补词）
- [ ] `git status` 里没有你的登录态文件（`*.json` cookie 不该出现）

## 五、其他

- 站点改版导致失效，欢迎提 issue，附上 `--debug` 导出的 `debug_last.json`（记得先删掉里面可能的个人信息）。
- 代码风格随现有文件，别为了格式化大改一片 —— diff 越小越好 review。
