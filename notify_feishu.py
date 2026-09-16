#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notify_feishu.py — 把当天抓到的 GitHub Trending 推送到飞书群机器人

凭据（二选一，环境变量优先）：
  FEISHU_WEBHOOK   群机器人 webhook 地址，形如 https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
  FEISHU_SECRET    开了「签名校验」才需要；没开就留空（那就得配「自定义关键词」）

用法：
  python notify_feishu.py                     # 推送今天的数据（读 ./data/daily/<今天>.json）
  python notify_feishu.py --top 5             # 只推前 5
  python notify_feishu.py --dry-run           # 只打印将要发送的 JSON，不发
  python notify_feishu.py --text              # 用纯文本消息（最保守，排障用）
  python notify_feishu.py --pages-base https://user.github.io/repo
                                              # 卡片底部加一个「打开完整看板」按钮

环境变量 PAGES_BASE 也可以代替 --pages-base；未提供则不显示按钮。
零依赖（标准库）。
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERIOD = {"daily": "今日", "weekly": "本周", "monthly": "本月"}
LOCAL_FILES = ("feishu.local.json", ".env")


def load_local_config():
    """从项目目录里的 feishu.local.json 或 .env 读凭据（两者都已 gitignore）。

    feishu.local.json 形如：
        {"webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
         "secret": "xxx", "pages_base": "https://user.github.io/repo"}
    .env 形如：
        FEISHU_WEBHOOK=https://...
        FEISHU_SECRET=xxx
    """
    cfg = {}
    j = os.path.join(BASE_DIR, "feishu.local.json")
    if os.path.isfile(j):
        try:
            with open(j, encoding="utf-8") as f:
                cfg = {k: v for k, v in json.load(f).items() if isinstance(v, str)}
        except Exception as e:                  # noqa: BLE001
            print(f"⚠️  读不了 {j}：{e}", file=sys.stderr)
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.isfile(env_file):
        try:
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    cfg.setdefault(k.strip().lower().replace("feishu_", "").replace("pages_", ""),
                                   v.strip().strip('"').strip("'"))
        except Exception as e:                  # noqa: BLE001
            print(f"⚠️  读不了 {env_file}：{e}", file=sys.stderr)
    return cfg


def gen_sign(secret, timestamp):
    """飞书签名校验：HmacSHA256(key=f"{timestamp}\\n{secret}", msg="") 再 base64。"""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def load_snapshot(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def latest_snapshot(since="daily"):
    d = os.path.join(BASE_DIR, "data", since)
    if not os.path.isdir(d):
        return None, None
    files = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    if not files:
        return None, None
    p = os.path.join(d, files[-1])
    return load_snapshot(p), p


def change_badge(it):
    ch = it.get("change", "")
    if ch == "new":
        return "🆕"
    if ch == "up":
        return f"⬆️{abs(it['delta'] or 0)}"
    if ch == "down":
        return f"⬇️{abs(it['delta'] or 0)}"
    return ""


MEDALS = ("🥇", "🥈", "🥉")
GREY = lambda s: f"<font color='grey'>{s}</font>"      # noqa: E731
RED = lambda s: f"<font color='red'>{s}</font>"        # noqa: E731


def overview(snap, top):
    """三行概览：上榜数/新上榜 · 今日最热 · 语言分布。"""
    items = snap["items"]
    label = PERIOD.get(snap.get("since", "daily"), "今日")
    news = [i for i in items if i.get("change") == "new"]
    lines = [f"📊 {label}上榜 **{len(items)}** 个"
             + (f"　🆕 新上榜 **{len(news)}** 个" if news else "")]
    langs = Counter(i["lang"] for i in items if i.get("lang"))
    if langs:
        dist = " · ".join(f"{lang}×{n}" for lang, n in langs.most_common(3))
        lines.append("🧩 " + GREY("语言分布：" + dist))
    return "\n".join(lines)


def hot_board(snap, n=3):
    """涨星最猛榜：按今日新增 star 排，不看名次。"""
    if n <= 0:
        return ""
    items = [i for i in snap["items"] if i.get("today")]
    if not items:
        return ""
    label = PERIOD.get(snap.get("since", "daily"), "今日")
    top = sorted(items, key=lambda i: i["today"], reverse=True)[:n]
    lines = [f"🔥 {label}涨星最猛"]
    for k, it in enumerate(top, 1):
        badge = change_badge(it)
        lines.append(f"{k}. [{it['repo']}]({it['url']}) " + RED(f"+{it['today']:,}")
                     + (GREY(f" · ★ {it['stars']:,}") if it.get("stars") else "")
                     + (f"　{badge}" if badge else ""))
    return "\n".join(lines)


def change_board(snap, limit=5):
    """名次变化榜：上升最猛 / 掉得最狠 / 新上榜 / 掉出榜单。"""
    items = snap["items"]
    ups = [i for i in items if i.get("change") == "up"]
    downs = [i for i in items if i.get("change") == "down"]
    news = [i for i in items if i.get("change") == "new"]
    dropped = snap.get("dropped") or []
    lines = []
    if ups:
        b = max(ups, key=lambda i: abs(i["delta"]))
        lines.append(f"⬆️ 上升最猛 **[{b['repo']}]({b['url']})** "
                     + GREY(f"#{b['prev_rank']} → #{b['rank']}"))
    if downs:
        w = max(downs, key=lambda i: abs(i["delta"]))
        lines.append(f"⬇️ 掉得最狠 **[{w['repo']}]({w['url']})** "
                     + GREY(f"#{w['prev_rank']} → #{w['rank']}"))
    if news:
        lines.append("🆕 新上榜：" + " / ".join(
            f"[{i['repo']}]({i['url']})" for i in news[:limit]))
    if dropped:
        lines.append("👋 掉出榜单：" + " / ".join(
            f"[{d['repo']}]({d['url']})" for d in dropped[:limit]))
    return "\n".join(lines)


def item_uniform(it, label, with_desc=True, width=76):
    """统一格式：一行数据 + 一行简介（十名一视同仁）。"""
    head = f"**{it['rank']}.** **[{it['repo']}]({it['url']})**"
    meta = [it.get("lang") or "未知语言"]
    if it.get("stars"):
        meta.append(f"★{it['stars']:,}")
    if it.get("forks"):
        meta.append(f"fork {it['forks']:,}")
    if it.get("today") is not None:
        meta.append(f"{label} +{it['today']:,}")
    badge = change_badge(it)
    if badge:
        meta.append(badge)
    rows = [head + "　" + GREY("　".join(meta))]
    if with_desc:
        d = it.get("desc") or "（该仓库未提供简介）"
        rows.append(GREY(d if len(d) <= width else d[:width] + "…"))
    return "\n".join(rows)


def item_block(it, label, with_desc=True, width=70):
    """前三名：奖牌 + 名字 + 数据行 + 简介。"""
    medal = MEDALS[it["rank"] - 1] if it["rank"] <= 3 else f"**{it['rank']}.**"
    head = f"{medal} **[{it['repo']}]({it['url']})**"
    meta = [GREY(it.get("lang") or "未知语言")]
    if it.get("stars"):
        meta.append(GREY(f"★ {it['stars']:,}"))
    if it.get("today") is not None:
        meta.append(RED(f"{label} +{it['today']:,}"))
    if it.get("forks"):
        meta.append(GREY(f"fork {it['forks']:,}"))
    badge = change_badge(it)
    if badge:
        meta.append(badge)
    lines = [head, "　".join(meta)]
    if with_desc and it.get("desc"):
        d = it["desc"]
        lines.append(GREY(d if len(d) <= width else d[:width] + "…"))
    return "\n".join(lines)


def item_line(it, label):
    """第四名之后：一行一条，紧凑。"""
    parts = [f"**{it['rank']}.** [{it['repo']}]({it['url']})"]
    tags = [it.get("lang") or "未知语言"]
    if it.get("stars"):
        tags.append(f"★{it['stars']:,}")
    if it.get("today") is not None:
        tags.append(f"+{it['today']:,}")
    badge = change_badge(it)
    if badge:
        tags.append(badge)
    parts.append(GREY("　".join(tags)))
    return "　".join(parts)


def build_lines(snap, top, with_desc=True, width=64, plain=False):
    label = PERIOD.get(snap.get("since", "daily"), "今日")
    lines = []
    for it in snap["items"][:top]:
        badge = change_badge(it)
        head = (f"{it['rank']}. {it['repo']}" if plain
                else f"**{it['rank']}. [{it['repo']}]({it['url']})**")
        meta = [it.get("lang") or "未知语言"]
        if it.get("stars"):
            meta.append(f"★{it['stars']:,}")
        if it.get("today") is not None:
            meta.append(f"{label} +{it['today']:,}")
        if badge:
            meta.append(badge)
        if plain:
            meta.append(it["url"])
        lines.append(head)
        lines.append("　".join(meta))
        if with_desc and it.get("desc"):
            desc = it["desc"]
            lines.append(desc if len(desc) <= width else desc[:width] + "…")
        lines.append("")
    return "\n".join(lines).strip()


def build_card(snap, top, pages_base, with_desc=True, style="uniform", hot=3):
    label = PERIOD.get(snap.get("since", "daily"), "今日")
    date = snap.get("date", "")
    items = snap["items"][:top]

    if style == "compact":
        elements = [{"tag": "div", "text": {"tag": "lark_md",
                    "content": "\n".join(item_line(i, label) for i in items)}}]
    elif style == "medal":
        top3 = [i for i in items if i["rank"] <= 3]
        rest = [i for i in items if i["rank"] > 3]
        elements = [
            {"tag": "div", "text": {"tag": "lark_md", "content": overview(snap, top)}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md",
             "content": "\n\n".join(item_block(i, label, with_desc) for i in top3)}},
        ]
        if rest:
            elements += [
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md",
                 "content": "\n".join(item_line(i, label) for i in rest)}},
            ]
    else:                                   # uniform：默认，十名统一格式
        elements = [{"tag": "div", "text": {"tag": "lark_md", "content": overview(snap, top)}}]
        board = change_board(snap)
        if board:
            elements += [{"tag": "hr"},
                         {"tag": "div", "text": {"tag": "lark_md", "content": board}}]
        hots = hot_board(snap, hot)
        if hots:
            elements += [{"tag": "hr"},
                         {"tag": "div", "text": {"tag": "lark_md", "content": hots}}]
        elements += [
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md",
             "content": "\n\n".join(item_uniform(i, label, with_desc) for i in items)}},
        ]

    elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [{
        "tag": "plain_text",
        "content": f"抓取于 {snap.get('fetched_at', '')} · 数据来自 github.com/trending",
    }]})

    url = (pages_base.rstrip("/") + f"/reports/{snap.get('since', 'daily')}/{date}.html"
           if pages_base else "")
    if url:
        elements.append({"tag": "action", "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": "📊 完整看板"},
             "url": url, "type": "primary"},
            {"tag": "button", "text": {"tag": "plain_text", "content": "📝 Markdown 版"},
             "url": url[:-5] + ".md", "type": "default"},
        ]})

    card = {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {
            "tag": "plain_text", "content": f"🚀 GitHub Trending {label}榜 · {date}"}},
        "elements": elements,
    }
    if url:
        card["card_link"] = {"url": url, "pc_url": url, "ios_url": url, "android_url": url}
    return {"msg_type": "interactive", "card": card}


def build_card_simple(snap, top, pages_base, with_desc=True):
    """降级版卡片：只用最老的元素（div + action），万一 fancy 版被飞书拒绝就用它。"""
    label = PERIOD.get(snap.get("since", "daily"), "今日")
    date = snap.get("date", "")
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {
            "tag": "plain_text", "content": f"GitHub Trending {label}榜 · {date}"}},
        "elements": [{"tag": "div", "text": {
            "tag": "lark_md", "content": build_lines(snap, top, with_desc)}}],
    }
    if pages_base:
        card["elements"].append({"tag": "action", "actions": [{
            "tag": "button", "text": {"tag": "plain_text", "content": "查看完整看板"},
            "url": pages_base.rstrip("/") + f"/reports/{snap.get('since', 'daily')}/{date}.html",
            "type": "primary"}]})
    return {"msg_type": "interactive", "card": card}


def build_text(snap, top, pages_base, with_desc=True):
    label = PERIOD.get(snap.get("since", "daily"), "今日")
    body = [f"GitHub Trending {label}榜 · {snap.get('date', '')}", ""]
    body.append(build_lines(snap, top, with_desc, plain=True))
    if pages_base:
        body.append("")
        body.append("完整看板：" + pages_base.rstrip("/") +
                    f"/reports/{snap.get('since', 'daily')}/{snap.get('date', '')}.html")
    return {"msg_type": "text", "content": {"text": "\n".join(body)}}


def send(payload, webhook, secret=None, timeout=20):
    body = dict(payload)
    if secret:
        ts = str(int(time.time()))
        body = {"timestamp": ts, "sign": gen_sign(secret, ts), **body}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode("utf-8", "replace")
    try:
        res = json.loads(txt)
    except Exception:                       # noqa: BLE001
        return False, txt
    ok = res.get("code") == 0 or res.get("StatusCode") == 0
    return ok, txt


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                       # noqa: BLE001
        pass

    p = argparse.ArgumentParser(description="把 GitHub Trending 推到飞书群机器人")
    p.add_argument("--since", default="daily", choices=["daily", "weekly", "monthly"])
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--webhook", default="")
    p.add_argument("--secret", default="")
    p.add_argument("--pages-base", default="")
    p.add_argument("--no-desc", action="store_true", help="不带简介，卡片更短")
    p.add_argument("--hot", type=int, default=3,
                   help="「涨星最猛」显示前 N 名（默认 3，0=不显示）")
    p.add_argument("--text", action="store_true", help="发纯文本而不是卡片")
    p.add_argument("--style", default="uniform", choices=["uniform", "medal", "compact"],
                   help="uniform=十名统一格式（默认）；medal=前三名奖牌加宽；compact=每名一行")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    local = load_local_config()
    args.webhook = args.webhook or os.environ.get("FEISHU_WEBHOOK", "") or local.get("webhook", "")
    args.secret = args.secret or os.environ.get("FEISHU_SECRET", "") or local.get("secret", "")
    args.pages_base = (args.pages_base or os.environ.get("PAGES_BASE", "")
                       or local.get("pages_base", "") or local.get("base", ""))

    snap, path = latest_snapshot(args.since)
    if not snap:
        print(f"没找到 {args.since} 的快照，先跑一次 gh_trends.py --since {args.since}", file=sys.stderr)
        return 1
    print(f"使用快照：{path}（{snap.get('date')}，{len(snap['items'])} 项）")

    kwargs = {} if args.text else {"style": args.style, "hot": args.hot}
    payload = (build_text if args.text else build_card)(
        snap, args.top, args.pages_base, with_desc=not args.no_desc, **kwargs)

    if args.dry_run or not args.webhook:
        if not args.webhook and not args.dry_run:
            print("⚠️  没有配置 FEISHU_WEBHOOK，跳过推送。下面是将要发送的内容：\n", file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    # 依次降级：漂亮卡片 → 简化卡片 → 纯文本，保证至少有一条能发出去
    attempts = ([(payload, "卡片")] if args.text else
                [(payload, "卡片"),
                 (build_card_simple(snap, args.top, args.pages_base, not args.no_desc), "简化卡片"),
                 (build_text(snap, args.top, args.pages_base, not args.no_desc), "纯文本")])
    for i, (pl, name) in enumerate(attempts):
        try:
            ok, resp = send(pl, args.webhook, args.secret or None)
        except Exception as e:                  # noqa: BLE001
            print(f"❌ {name}发送异常：{e}", file=sys.stderr)
            continue
        if ok:
            print(f"✅ 已推送（{name}）：{resp}")
            return 0
        print(f"⚠️  {name}发送失败：{resp}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
