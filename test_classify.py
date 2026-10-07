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
    assert "已被当前分类筛选隐藏" in notes, notes
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


if __name__ == "__main__":
    ok = True
    ok &= check("本体", BASE, "本体")
    ok &= check("道具", ITEMS, "道具")
    ok &= check("DLC/附加", EXTRAS, "DLC/附加")
    ok &= check("账号", ACCOUNTS, "账号")
    ok &= test_build_rows()
    ok &= test_kinds_filter()
    ok &= test_hidden_hint()
    print("\n" + ("全部通过" if ok else "有失败项！"))
    raise SystemExit(0 if ok else 1)
