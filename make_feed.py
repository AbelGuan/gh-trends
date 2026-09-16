#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_feed.py — 把历史快照汇总成一个 Atom feed，供 Obsidian（或任何 RSS 阅读器）订阅

生成的 feed 里，每一天是一条 entry：
  标题 = GitHub Trending 2026-09-17
  链接 = <Pages>/reports/daily/2026-09-17.html
  正文 = 当天榜单（可点击的仓库链接 + 语言 / ★ / 今日新增 / 排名变化）

用法：
  python make_feed.py                                  # 输出到 ./feed.xml
  python make_feed.py --base https://abelguan.github.io/gh-trends
  python make_feed.py --limit 60 --out reports/feed.xml
环境变量 PAGES_BASE 也可以代替 --base；没给 base 时链路会退化成相对路径（本地预览用）。
零依赖（标准库）。
"""

import argparse
import glob
import html
import json
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERIOD = {"daily": "今日", "weekly": "本周", "monthly": "本月"}


def load_snapshots(since="daily", lang="", spoken=""):
    tag = "-".join(x for x in (lang, spoken) if x)
    pattern = os.path.join(BASE_DIR, "data", since, ("*_" + tag + ".json") if tag else "*.json")
    out = []
    for p in sorted(glob.glob(pattern)):
        try:
            with open(p, encoding="utf-8") as f:
                snap = json.load(f)
        except Exception:                       # noqa: BLE001
            continue
        if not snap.get("items"):
            continue
        out.append(snap)
    return out


def badge(it):
    ch = it.get("change", "")
    if ch == "new":
        return "🆕 新上榜"
    if ch == "up":
        return f"⬆️{it['delta']}"
    if ch == "down":
        return f"⬇️{abs(it['delta'] or 0)}"
    return ""


def entry_html(snap, top=None):
    """把当天榜单渲染成一段 HTML（文本部分做转义，标签保留）。"""
    label = PERIOD.get(snap.get("since", "daily"), "今日")
    items = snap["items"][:top] if top else snap["items"]
    rows = []
    for it in items:
        bits = [it.get("lang") or "未知语言"]
        if it.get("stars"):
            bits.append("★" + format(it["stars"], ","))
        if it.get("today") is not None:
            bits.append(f"{label} +{format(it['today'], ',')}")
        b = badge(it)
        if b:
            bits.append(b)
        name = html.escape(it["repo"])
        desc = html.escape(it.get("desc") or "")
        rows.append(
            f'<p><b>{it["rank"]}. <a href="{html.escape(it["url"])}">{name}</a></b><br>'
            + html.escape("　".join(bits))
            + (f"<br>{desc}" if desc else "")
            + "</p>"
        )
    return "".join(rows)


def build_feed(snaps, base="", since="daily", feed_title="GitHub Trending 日报"):
    base = (base or "").rstrip("/")
    self_url = (base + "/feed.xml") if base else "feed.xml"
    home = (base + "/") if base else "index.html"
    latest = snaps[-1].get("fetched_at") or (snaps[-1]["date"] + " 00:00:00")
    updated = latest.replace(" ", "T") + "Z"

    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<feed xmlns="http://www.w3.org/2005/Atom">',
           f'  <title>{html.escape(feed_title)}</title>',
           '  <subtitle>每天自动抓取的 GitHub Trending 榜单</subtitle>',
           f'  <link href="{html.escape(home)}" rel="alternate"/>',
           f'  <link href="{html.escape(self_url)}" rel="self"/>',
           f'  <id>{html.escape(self_url)}</id>',
           f'  <updated>{updated}</updated>',
           '  <author><name>gh-trends</name></author>']
    for snap in reversed(snaps):                 # 新的在前
        date = snap.get("date", "")
        link = (base + f"/reports/{since}/{date}.html") if base else f"reports/{since}/{date}.html"
        stamp = (snap.get("fetched_at") or f"{date} 00:00:00").replace(" ", "T") + "Z"
        out += [
            '  <entry>',
            f'    <title>GitHub Trending {html.escape(date)}</title>',
            f'    <link href="{html.escape(link)}"/>',
            f'    <id>{html.escape(link)}</id>',
            f'    <updated>{stamp}</updated>',
            f'    <content type="html">{html.escape(entry_html(snap))}</content>',
            '  </entry>',
        ]
    out.append('</feed>')
    return "\n".join(out) + "\n"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                            # noqa: BLE001
        pass

    p = argparse.ArgumentParser(description="生成 Atom feed（给 Obsidian / RSS 阅读器订阅）")
    p.add_argument("--since", default="daily", choices=["daily", "weekly", "monthly"])
    p.add_argument("--lang", default="")
    p.add_argument("--spoken", default="")
    p.add_argument("--limit", type=int, default=30, help="最多收录最近 N 期")
    p.add_argument("--top", type=int, default=0, help="每期只保留前 N 名（0=全部）")
    p.add_argument("--base", default=os.environ.get("PAGES_BASE", ""),
                   help="Pages 站点前缀，如 https://user.github.io/gh-trends")
    p.add_argument("--out", default=os.path.join(BASE_DIR, "feed.xml"))
    p.add_argument("--title", default="GitHub Trending 日报")
    args = p.parse_args()

    snaps = load_snapshots(args.since, args.lang, args.spoken)
    if not snaps:
        print("没有找到快照，先跑一次 gh_trends.py", file=sys.stderr)
        return 1
    snaps = snaps[-args.limit:]
    xml = build_feed(snaps, args.base, args.since, args.title)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"✅ 已写入 {args.out}（{len(snaps)} 期：{snaps[0]['date']} ~ {snaps[-1]['date']}）")
    if not args.base:
        print("⚠️  没给 --base / PAGES_BASE，feed 里的链接是相对路径，只适合本地预览")
    else:
        print("订阅地址：" + args.base.rstrip("/") + "/feed.xml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
