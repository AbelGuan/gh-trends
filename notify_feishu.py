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
        return "🆕 新上榜"
    if ch == "up":
        return f"⬆️{it['delta']}"
    if ch == "down":
        return f"⬇️{abs(it['delta'] or 0)}"
    return ""


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


def build_card(snap, top, pages_base, with_desc=True):
    label = PERIOD.get(snap.get("since", "daily"), "今日")
    title = f"GitHub Trending {label}榜 · {snap.get('date', '')}"
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": build_lines(snap, top, with_desc)}}]
    if pages_base:
        elements += [
            {"tag": "hr"},
            {"tag": "action", "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看完整看板"},
                "url": pages_base.rstrip("/") + f"/reports/{snap.get('since', 'daily')}/" +
                       f"{snap.get('date', '')}.html",
                "type": "primary",
            }]},
        ]
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": "blue", "title": {"tag": "plain_text", "content": title}},
            "elements": elements,
        },
    }


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
    p.add_argument("--text", action="store_true", help="发纯文本而不是卡片")
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

    build = build_text if args.text else build_card
    payload = build(snap, args.top, args.pages_base, with_desc=not args.no_desc)

    if args.dry_run or not args.webhook:
        if not args.webhook and not args.dry_run:
            print("⚠️  没有配置 FEISHU_WEBHOOK，跳过推送。下面是将要发送的内容：\n", file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    try:
        ok, resp = send(payload, args.webhook, args.secret or None)
    except Exception as e:                  # noqa: BLE001
        print(f"❌ 发送失败：{e}", file=sys.stderr)
        return 2
    print(("✅ 已推送：" if ok else "❌ 飞书返回异常：") + resp)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
