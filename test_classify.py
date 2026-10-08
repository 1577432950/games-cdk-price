# -*- coding: utf-8 -*-
"""分类器回归测试。

所有样本都来自各站列表页的**真实标题**（主要是 Kinguin），
用来防止「游戏内道具/货币被当成本体」这类误判再次发生。
运行： python test_classify.py
"""
import core

# 期望「本体」——真·游戏本体，绝不能误伤
BASE = [
    "Dying Light 2 Stay Human PC Steam CD Key",
    "Dying Light 2: Reloaded Edition Steam CD Key",
    "Dying Light 2 Stay Human Digital Extras Edition EU XBOX One / Xbox Series X|S CD Key",
    "Hogwarts Legacy Deluxe Edition PC Steam CD Key",
    "Hogwarts Legacy XBOX One CD Key",
    "Elden Ring EU Steam CD Key",
    "Elden Ring US Steam CD Key",
    "ELDEN RING: Shadow of the Erdtree Edition EU PC Steam CD Key",
    "ELDEN RING NIGHTREIGN EU PC Steam CD Key",
    "Cyberpunk 2077 Ultimate Edition PC GOG CD Key",
    "Cyberpunk 2077 EU PC Steam Altergift",
    "Resident Evil Village EU PC Steam CD Key",
    "Resident Evil: Village Gold Edition PC Steam CD Key",
    "消逝的光芒2",
    # 抢先体验期的本体，不是账号
    "Baldur's Gate 3 Early Access Steam CD Key",
    # 负样本：含 skin/gems 字样但不是道具，别被正则误伤
    "Skinwalker Hunt PC Steam CD Key",
    "Gems of War PC Steam CD Key",
]

# 期望「道具」——游戏内道具/货币/掉宝，用户报的就是这类
ITEMS = [
    "Dying Light 2 Stay Human Items > Global > PC > Twitch Drop",
    "Adopt Me Items > Foods > Legendary > Ride-A-Pet Potion > Ride-A-Pet Potion",
    "Apex Legends - 1000 Apex Coins EA App CD Key",
    "Apex Legends - 6700 Apex Coins XBOX One CD Key",
    "Fortnite - 1000 V-Bucks Epic Games CD Key",
    "Rocket League - 500 Credits Steam CD Key",
    "反恐精英2 - 1000 点券 PC CD Key",
]

# 期望「DLC/附加」
EXTRAS = [
    "Dying Light 2 Stay Human - Rahim Bundle DLC PC Steam CD Key",
    "Dying Light 2 Stay Human - Welcome Offer: Essential Starter Kit DLC PC Steam CD Key",
    "ELDEN RING - Shadow of the Erdtree DLC EU PC Steam CD Key",
    "Cyberpunk 2077 - Phantom Liberty DLC GOG CD Key",
    "Hogwarts Legacy - Dark Arts Pack DLC Steam Altergift",
    "Apex Legends - Saviors Pack DLC Steam CD Key",
    "Resident Evil 7 Gold Edition & Village Gold Edition Bundle EU PC Steam CD Key",
]

# 期望「账号」
ACCOUNTS = [
    "Hogwarts Legacy Deluxe Edition Steam Account",
    "Elden Ring PS5 Account",
    "Cyberpunk 2077 Steam Account",
    "ELDEN RING NIGHTREIGN PC Steam Account",
]

# 平台识别样本：(标题, 商品页 URL, 适配器给的平台, 期望平台列表)
# 全部取自各站真实列表页；URL 也要看，因为 Loaded 的平台只写在 slug 里
PLATFORM_CASES = [
    ("ELDEN RING - Shadow of the Erdtree DLC EU PC Steam CD Key",
     "https://www.kinguin.net/cn/category/1/x-pc-steam-cd-key", None, ["Steam"]),
    ("Cyberpunk 2077 - Phantom Liberty DLC GOG CD Key",
     "https://www.kinguin.net/cn/category/2/x-gog-cd-key", None, ["GOG"]),
    ("Alan Wake 2 Epic Games Green Gift Redemption Code",
     "https://www.kinguin.net/cn/category/3/x", None, ["Epic"]),
    ("Elden Ring Xbox One & Xbox Series X",
     "https://www.loaded.com/elden-ring-xbox-one-xbox-series-x-s-ww", None, ["Xbox"]),
    ("Elden Ring PS5 Account", "https://www.kinguin.net/cn/category/4/x-ps5-account",
     None, ["PlayStation"]),
    ("The Legend of Zelda: Tears of the Kingdom US Nintendo Switch CD Key",
     "https://www.kinguin.net/cn/category/5/x-us-nintendo-switch-cd-key", None, ["Switch"]),
    ("Battlefield 2042 PC EA App CD Key",
     "https://www.kinguin.net/cn/category/6/x-pc-ea-app-cd-key", None, ["其他平台"]),
    ("GRAND THEFT AUTO V ENHANCED PC - ROCKSTAR GAMES LAUNCHER",
     "https://www.loaded.com/gta-v-enhanced-pc-rockstar", None, ["其他平台"]),
    ("Starfield - Preorder Bonus DLC Xbox Series X|S / Windows 10 CD Key",
     "https://www.kinguin.net/cn/category/7/x-xbox-windows-10-cd-key", None,
     ["Xbox", "其他平台"]),
    # Loaded 标题只写 "PC"，平台藏在 slug 里 —— 这正是要看 URL 的原因
    ("Starfield PC", "https://www.loaded.com/starfield-pc-steam", None, ["Steam"]),
    ("Battlefield 2042 Gold Edition PC",
     "https://www.loaded.com/battlefield-2042-gold-edition-pc-origin", None, ["其他平台"]),
    ("ELDEN RING NIGHTREIGN PC (Asia)",
     "https://www.loaded.com/elden-ring-nightreign-pc-asia-steam", None, ["Steam"]),
    # 标题和 URL 都没线索 -> 未标注（国内站、Fanatical、GMG 都是这样）
    ("消逝的光芒2", "https://www.sonkwo.hk/sku/106112", None, ["未标注"]),
    ("The Outlast Trials - PC", "https://www.greenmangaming.com/games/the-outlast-trials-pc/",
     None, ["未标注"]),
    # 不能误伤的负样本
    ("Epic Mickey: Power of Illusion", "https://www.loaded.com/epic-mickey-pc-steam",
     None, ["Steam"]),
    ("Assassin's Creed Origins", "https://www.loaded.com/assassins-creed-origins-pc-steam",
     None, ["Steam"]),
    ("Origin of the Species", "https://www.loaded.com/origin-of-the-species-pc-steam",
     None, ["Steam"]),
    # 站点接口直接给的平台优先（Humble 的 delivery_methods）
    ("Cyberpunk 2077", "https://www.humblebundle.com/store/cyberpunk-2077", ["gog"], ["GOG"]),
    ("Dying Light 2 Stay Human: Reloaded Edition",
     "https://www.humblebundle.com/store/dying-light-2-stay-human", ["steam"], ["Steam"]),
]


def check(label, samples, want):
    bad = [(t, core.classify(t)) for t in samples if core.classify(t) != want]
    for t, got in bad:
        print("  ✗ [%s] 期望 %s，实际 %s  ←  %s" % (label, want, got, t))
    print("%s %s：%d/%d" % ("✓" if not bad else "✗", label, len(samples) - len(bad), len(samples)))
    return not bad


def test_build_rows():
    """道具类默认隐藏，传 keep_all=True 才出现。"""
    results = {"kinguin": [
        {"title": "Dying Light 2 Stay Human Items > Global > PC > Twitch Drop",
         "price": 21.84, "currency": "CNY", "list_price": None, "url": "https://x/u1", "note": ""},
        {"title": "Dying Light 2 Stay Human PC Steam CD Key",
         "price": 54.56, "currency": "CNY", "list_price": None, "url": "https://x/u2", "note": ""},
    ]}
    kw = ("消逝的光芒2", "Dying Light 2", {"CNY": 1.0})
    default = [r for r in core.build_rows(results, {}, *kw) if r["cny"] is not None]
    assert len(default) == 1 and default[0]["kind"] == "本体", default
    assert default[0]["cny"] == 54.56, default
    shown = [r for r in core.build_rows(results, {}, *kw, keep_all=True) if r["cny"] is not None]
    assert len(shown) == 2, shown
    print("✓ 默认隐藏道具 / keep_all 时可见")
    return True


def test_kinds_filter():
    """本体 / DLC 两个分类可分别勾选，也可同时勾选。"""
    results = {"kinguin": [
        {"title": "Dying Light 2 Stay Human PC Steam CD Key",
         "price": 54.56, "currency": "CNY", "list_price": None, "url": "https://x/b1", "note": ""},
        {"title": "Dying Light 2 Stay Human - Rahim Bundle DLC PC Steam CD Key",
         "price": 20.94, "currency": "CNY", "list_price": None, "url": "https://x/b2", "note": ""},
    ]}
    kw = ("消逝的光芒2", "Dying Light 2", {"CNY": 1.0})

    def kinds_of(**w):
        return sorted(r["kind"] for r in core.build_rows(results, {}, *kw, **w)
                      if r["cny"] is not None)

    assert kinds_of() == ["DLC/附加", "本体"], kinds_of()          # 默认两者都显示
    assert kinds_of(kinds=["本体"]) == ["本体"], kinds_of(kinds=["本体"])
    assert kinds_of(kinds=["DLC/附加"]) == ["DLC/附加"], kinds_of(kinds=["DLC/附加"])
    assert kinds_of(kinds=[]) == [], kinds_of(kinds=[])
    print("✓ 本体 / DLC 可分别或同时勾选")
    return True


def test_hidden_hint():
    """被分类筛选挡掉时，提示要说清楚，不能显示成「没有匹配商品」。"""
    results = {"kinguin": [
        {"title": "Apex Legends - 1000 Apex Coins EA App CD Key",
         "price": 76.88, "currency": "CNY", "list_price": None, "url": "https://x/u3", "note": ""},
    ]}
    rows = core.build_rows(results, {}, "Apex", "Apex Legends", {"CNY": 1.0})
    notes = " ".join(r.get("note") or "" for r in rows)
    assert "道具 1 条" in notes, notes
    assert "已被当前「版本」筛选隐藏" in notes, notes
    assert "没有匹配商品" not in notes, notes

    # 只勾「本体」时，整站只有 DLC 也要说清楚是 DLC 被挡了
    dlc_only = {"kinguin": [
        {"title": "Dying Light 2 Stay Human - Rahim Bundle DLC PC Steam CD Key",
         "price": 20.94, "currency": "CNY", "list_price": None, "url": "https://x/u4", "note": ""},
    ]}
    rows2 = core.build_rows(dlc_only, {}, "消逝的光芒2", "Dying Light 2", {"CNY": 1.0},
                            kinds=["本体"])
    notes2 = " ".join(r.get("note") or "" for r in rows2)
    assert "DLC/附加 1 条" in notes2, notes2
    assert "没有匹配商品" not in notes2, notes2
    print("✓ 被筛掉时给出「DLC/附加 N 条」这类明确提示")
    return True


def test_platforms():
    """平台识别：标题 / URL / 站点接口三条来源都要用上，认不出就老实标「未标注」。"""
    bad = []
    for title, url, raw, want in PLATFORM_CASES:
        got = core.detect_platforms(title, "", raw, url)
        if got != want:
            bad.append((title, want, got))
    for t, want, got in bad:
        print("  ✗ 期望 %s，实际 %s  ←  %s" % (want, got, t))
    print("%s 平台识别：%d/%d" % ("✓" if not bad else "✗",
                                len(PLATFORM_CASES) - len(bad), len(PLATFORM_CASES)))
    return not bad


def test_platform_filter():
    """平台可多选；「未标注」默认也显示，取消勾选即可只看明确标了平台的。"""
    results = {"kinguin": [
        {"title": "Elden Ring EU Steam CD Key", "price": 100.0, "currency": "CNY",
         "list_price": None, "url": "https://x/s1", "note": ""},
        {"title": "Elden Ring Xbox One CD Key", "price": 200.0, "currency": "CNY",
         "list_price": None, "url": "https://x/s2", "note": ""},
        {"title": "Elden Ring PC", "price": 300.0, "currency": "CNY",
         "list_price": None, "url": "https://x/s3", "note": ""},
    ]}
    kw = ("艾尔登法环", "Elden Ring", {"CNY": 1.0})

    def plats_of(**w):
        return sorted((r["plat"], r["cny"]) for r in core.build_rows(results, {}, *kw, **w)
                      if r["cny"] is not None)

    assert plats_of() == [("Steam", 100.0), ("Xbox", 200.0), ("未标注", 300.0)], plats_of()
    assert plats_of(platforms=["Steam"]) == [("Steam", 100.0)], plats_of(platforms=["Steam"])
    assert plats_of(platforms=["Steam", "Xbox"]) == [("Steam", 100.0), ("Xbox", 200.0)], \
        plats_of(platforms=["Steam", "Xbox"])
    assert plats_of(platforms=None) == plats_of(), plats_of(platforms=None)
    print("✓ 平台多选 / 未标注默认可见 / None 表示不过滤")
    return True


def test_platform_hint():
    """整站只剩别的平台时，提示要指名「平台」被挡，而不是含糊说没货。"""
    results = {"loaded": [
        {"title": "Elden Ring Xbox One & Xbox Series X", "price": 371.49, "currency": "CNY",
         "list_price": None, "url": "https://www.loaded.com/elden-ring-xbox-one", "note": ""},
    ]}
    rows = core.build_rows(results, {}, "艾尔登法环", "Elden Ring", {"CNY": 1.0},
                           platforms=["Steam"])
    notes = " ".join(r.get("note") or "" for r in rows)
    assert "Xbox 1 条" in notes, notes
    assert "已被当前「平台」筛选隐藏" in notes, notes
    assert "没有匹配商品" not in notes, notes

    # 同时被版本和平台挡掉时，两个维度都要说
    both = {"loaded": [
        {"title": "Elden Ring - Shadow of the Erdtree DLC Xbox One CD Key",
         "price": 253.59, "currency": "CNY", "list_price": None,
         "url": "https://www.loaded.com/elden-ring-dlc-xbox-one", "note": ""},
    ]}
    rows2 = core.build_rows(both, {}, "艾尔登法环", "Elden Ring", {"CNY": 1.0},
                            kinds=["本体"], platforms=["Steam"])
    notes2 = " ".join(r.get("note") or "" for r in rows2)
    assert "DLC/附加 1 条" in notes2 and "已被当前「版本」筛选隐藏" in notes2, notes2
    print("✓ 平台被筛掉时给出「Xbox N 条」这类明确提示")
    return True


if __name__ == "__main__":
    ok = True
    ok &= check("本体", BASE, "本体")
    ok &= check("道具", ITEMS, "道具")
    ok &= check("DLC/附加", EXTRAS, "DLC/附加")
    ok &= check("账号", ACCOUNTS, "账号")
    ok &= test_platforms()
    ok &= test_build_rows()
    ok &= test_kinds_filter()
    ok &= test_hidden_hint()
    ok &= test_platform_filter()
    ok &= test_platform_hint()
    print("\n" + ("全部通过" if ok else "有失败项！"))
    raise SystemExit(0 if ok else 1)
