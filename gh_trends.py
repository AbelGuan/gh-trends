#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gh_trends.py — GitHub Trending 每日抓取 / 存档 / 看板

用法示例：
  python gh_trends.py                      # 今日 daily 榜，打印到终端并归档
  python gh_trends.py --open               # 顺带打开本地 HTML 看板
  python gh_trends.py --since weekly       # 周榜 / monthly 月榜
  python gh_trends.py --lang python        # 只看某个语言（python/javascript/rust...）
  python gh_trends.py --spoken zh          # 只看中文项目（zh/en/...）
  python gh_trends.py --limit 10           # 只看前 10
  python gh_trends.py --history            # 列出历史报告
  python gh_trends.py --open-latest        # 打开最近一次的看板

零依赖（只用标准库）。数据落在 ./data，报告落在 ./reports，两个目录都可以直接同步/备份。
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# ---------------------------------------------------------------- 抓取 / 解析


def fetch(url, tries=3, timeout=30):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept-Language": "en-US,en;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:            # noqa: BLE001
            last = e
            if i < tries - 1:
                time.sleep(2 * (i + 1))
    raise RuntimeError(f"抓取失败：{url} -> {last}")


def _clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _num(s):
    try:
        return int(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_trending(page_html):
    items = []
    for art in re.findall(r'<article class="Box-row".*?</article>', page_html, re.S):
        m = re.search(r'<h2[^>]*>.*?href="(/[^"]+)"', art, re.S)
        if not m:
            continue
        repo = m.group(1).strip("/")

        d = re.search(r'<p class="col-9[^"]*"[^>]*>(.*?)</p>', art, re.S)
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', art)
        stars = re.search(r'stargazers"[^>]*>\s*<svg.*?</svg>\s*([\d,]+)', art, re.S)
        forks = re.search(r'forks"[^>]*>\s*<svg.*?</svg>\s*([\d,]+)', art, re.S)
        today = re.search(r'([\d,]+)\s*stars?\s*(today|this week|this month)', art)
        contrib = re.findall(r'alt="@([^"]+)"', art)

        items.append({
            "repo": repo,
            "url": "https://github.com/" + repo,
            "desc": _clean(d.group(1)) if d else "",
            "lang": html.unescape(lang.group(1)).strip() if lang else "",
            "stars": _num(stars.group(1)) if stars else None,
            "forks": _num(forks.group(1)) if forks else None,
            "today": _num(today.group(1)) if today else None,
            "period": today.group(2) if today else "",
            "contributors": contrib,
        })
    for i, it in enumerate(items, 1):
        it["rank"] = i
    return items


# ---------------------------------------------------------------- 存档 / 变化


def snap_path(since, day, lang="", spoken=""):
    tag = "-".join(x for x in (lang, spoken) if x)
    fn = f"{day}{('_' + tag) if tag else ''}.json"
    d = os.path.join(DATA_DIR, since)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, fn)


def load_prev(since, day, lang="", spoken=""):
    """找到同一榜单在上一次（非今天）的存档。"""
    d = os.path.join(DATA_DIR, since)
    if not os.path.isdir(d):
        return None
    tag = "-".join(x for x in (lang, spoken) if x)
    pat = re.compile((re.escape(tag) + r"\.json$") if tag else r"^\d{4}-\d{2}-\d{2}\.json$")
    cands = sorted(f for f in os.listdir(d) if f.endswith(".json") and pat.search(f) and f[:10] < day)
    if not cands:
        return None
    try:
        with open(os.path.join(d, cands[-1]), encoding="utf-8") as f:
            return json.load(f)
    except Exception:                     # noqa: BLE001
        return None


def annotate(items, prev):
    """给每个项目打上「相对上次」的变化标签。"""
    prev_map = {it["repo"]: it for it in (prev or {}).get("items", [])}
    prev_day = (prev or {}).get("date")
    for it in items:
        p = prev_map.get(it["repo"])
        it["prev_day"] = prev_day
        if not p:
            it["change"] = "new" if prev else ""
            it["delta"] = None
            continue
        it["change"] = "up" if it["rank"] < p["rank"] else ("down" if it["rank"] > p["rank"] else "same")
        it["delta"] = it["rank"] - p["rank"]
    return items


# ---------------------------------------------------------------- 终端渲染

C = {"reset": "\033[0m", "dim": "\033[2m", "bold": "\033[1m", "cyan": "\033[36m",
     "green": "\033[32m", "red": "\033[31m", "yellow": "\033[33m", "magenta": "\033[35m"}
PERIOD = {"daily": "今日", "weekly": "本周", "monthly": "本月"}


def render_terminal(items, meta, color=True):
    def c(s, k):
        return f"{C[k]}{s}{C['reset']}" if color else s

    out = []
    out.append(c(f"GitHub Trending · {meta['since']}"
                 + (f" · {meta['lang']}" if meta["lang"] else "")
                 + (f" · spoken={meta['spoken']}" if meta["spoken"] else ""), "bold"))
    out.append(c(f"抓取时间 {meta['fetched_at']}   共 {len(items)} 项", "dim"))
    out.append("")
    if not items:
        out.append("（今天热门里没有匹配项）")
        return "\n".join(out)

    wrank, wrepo = 3, max(len(i["repo"]) for i in items)
    for it in items:
        mark = {"new": c("★新", "yellow"), "up": c(f"↑{it['delta']}", "green"),
                "down": c(f"↓{abs(it['delta'] or 0)}", "red"), "same": "  "}.get(it.get("change", ""), "  ")
        today = "+" + format(it["today"], ",") if it["today"] is not None else "-"
        star = f"{it['stars']:,}" if it["stars"] is not None else "?"
        line = (f"{it['rank']:>3}. {it['repo']:<{wrepo}}  {star:>9} ★  "
                f"{today:>8} {PERIOD.get(meta['since'], '今日')}  {(it['lang'] or '-'):<12} {mark}")
        out.append(line.rstrip())
        if it["desc"]:
            out.append("    " + c(it["desc"][:110], "dim"))
    return "\n".join(out)


# ---------------------------------------------------------------- Markdown / HTML


def render_md(items, meta):
    lines = [f"# GitHub Trending · {meta['since']} · {meta['date']}", ""]
    lines.append(f"> 抓取时间：{meta['fetched_at']}　共 **{len(items)}** 个项目")
    if meta["lang"]:
        lines.append(f"> 语言过滤：`{meta['lang']}`")
    if meta["spoken"]:
        lines.append(f"> 口语过滤：`{meta['spoken']}`")
    if meta.get("prev_date"):
        lines.append(f"> 对比基准：{meta['prev_date']}")
    lines += ["", f"| # | 变化 | 仓库 | 语言 | ★ 总数 | {PERIOD.get(meta['since'], '今日')}新增 | 简介 |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for it in items:
        ch = {"new": "🆕 新上榜", "up": f"⬆️ {it['delta']}", "down": f"⬇️ {abs(it['delta'] or 0)}",
              "same": "—"}.get(it.get("change", ""), "")
        desc = (it["desc"] or "").replace("|", "\\|")
        lines.append(f"| {it['rank']} | {ch} | [{it['repo']}]({it['url']}) | {it['lang'] or '-'} | "
                     f"{it['stars']:,} | {('+' + format(it['today'], ',')) if it['today'] is not None else '-'} | {desc} |")
    lines.append("")
    return "\n".join(lines)


HTML_HEAD = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.55 -apple-system,"Segoe UI",Roboto,"Helvetica Neue","PingFang SC","Microsoft YaHei",sans-serif}}
a{{color:#58a6ff;text-decoration:none}} a:hover{{text-decoration:underline}}
header{{position:sticky;top:0;background:#0d1117ee;backdrop-filter:blur(8px);border-bottom:1px solid #21262d;padding:16px 24px}}
h1{{margin:0;font-size:19px}} .meta{{color:#8b949e;font-size:13px;margin-top:5px}}
main{{max-width:1080px;margin:0 auto;padding:20px 24px 60px}}
.card{{display:grid;grid-template-columns:56px 1fr;gap:14px;background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin-bottom:10px}}
.rank{{font:600 22px/1.2 ui-monospace,SFMono-Regular,Consolas,monospace;color:#8b949e;text-align:center}}
.rank small{{display:block;font-size:11px;font-weight:500;margin-top:4px}}
.up{{color:#3fb950}} .down{{color:#f85149}} .new{{color:#d29922}}
.name{{font-size:16px;font-weight:600;word-break:break-all}}
.desc{{color:#c9d1d9;margin:4px 0 8px;font-size:14px}}
.tags{{display:flex;flex-wrap:wrap;gap:8px;font-size:12.5px;color:#8b949e}}
.tag{{background:#21262d;border-radius:20px;padding:2px 10px}}
.tag b{{color:#e6edf3;font-weight:600}}
.hot{{background:#3d2c00;color:#d29922}} .hot b{{color:#d29922}}
.empty{{color:#8b949e;padding:40px 0;text-align:center}}
nav{{margin:0 0 16px;font-size:13px;color:#8b949e}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
td,th{{padding:7px 10px;border-bottom:1px solid #21262d;text-align:left}}
th{{color:#8b949e;font-weight:600}}
</style></head><body>
"""


def render_html(items, meta, extra_nav=""):
    def esc(s):
        return html.escape(s or "")

    rows = []
    for it in items:
        ch = it.get("change", "")
        badge = {"new": '<span class="new">NEW</span>',
                 "up": f'<span class="up">▲{it["delta"]}</span>',
                 "down": f'<span class="down">▼{abs(it["delta"] or 0)}</span>',
                 "same": '<span style="color:#484f58">—</span>'}.get(ch, "")
        rows.append(f"""<div class="card">
  <div class="rank">{it['rank']}<small>{badge}</small></div>
  <div>
    <div class="name"><a href="{esc(it['url'])}" target="_blank" rel="noopener">{esc(it['repo'])}</a></div>
    <div class="desc">{esc(it['desc'])}</div>
    <div class="tags">
      <span class="tag">{esc(it['lang'] or '未知语言')}</span>
      <span class="tag">★ <b>{it['stars']:,}</b></span>
      {f'<span class="tag hot">{PERIOD.get(meta["since"], "今日")} <b>+{it["today"]:,}</b></span>' if it['today'] is not None else ''}
      <span class="tag">fork <b>{it['forks']:,}</b></span>
      {f'<span class="tag">上次 #{it.get("prev_rank", "")}</span>' if it.get("change") in ("up", "down") else ''}
    </div>
  </div>
</div>""")

    head = f"""<header><h1>GitHub Trending · {esc(meta['since'])}
{esc('· ' + meta['lang']) if meta['lang'] else ''}{esc('· ' + meta['spoken']) if meta['spoken'] else ''}</h1>
<div class="meta">{esc(meta['date'])} · 抓取于 {esc(meta['fetched_at'])} · 共 {len(items)} 项
{esc('· 对比 ' + meta['prev_date']) if meta.get('prev_date') else ''}</div></header>"""
    body = f'<main>{extra_nav}' + ("".join(rows) or '<div class="empty">今天热门里没有匹配项</div>') + "</main>"
    return HTML_HEAD.format(title=f"GitHub Trending {meta['date']}") + head + body + "</body></html>"


def render_index():
    """把历史报告串成一个索引页。"""
    entries = []
    for since in sorted(os.listdir(DATA_DIR)) if os.path.isdir(DATA_DIR) else []:
        d = os.path.join(DATA_DIR, since)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d), reverse=True):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    snap = json.load(fh)
            except Exception:             # noqa: BLE001
                continue
            day = snap.get("date", f[:10])
            tag = f"{since}" + (f" · {snap['lang']}" if snap.get("lang") else "") + \
                  (f" · {snap['spoken']}" if snap.get("spoken") else "")
            top = ", ".join(i["repo"] for i in snap.get("items", [])[:3])
            rel = f"reports/{since}/{f[:-5]}.html"
            entries.append((day, tag, rel, top, len(snap.get("items", []))))
    entries.sort(reverse=True)
    trs = "".join(
        f'<tr><td>{html.escape(d)}</td><td>{html.escape(t)}</td><td>{n}</td>'
        f'<td><a href="{html.escape(r)}">看板</a></td><td style="color:#8b949e">{html.escape(top)}</td></tr>'
        for d, t, r, top, n in entries)
    body = ("<main><h1 style='font-size:20px'>GitHub Trending 历史</h1>"
            "<div class='meta' style='color:#8b949e;margin-bottom:16px'>"
            f"共 {len(entries)} 份快照</div>"
            "<table><tr><th>日期</th><th>榜单</th><th>项目数</th><th>报告</th><th>前三</th></tr>"
            + trs + "</table></main>")
    path = os.path.join(REPORT_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(HTML_HEAD.format(title="GitHub Trending 历史") + body + "</body></html>")
    return path


# ---------------------------------------------------------------- 主流程


def open_file(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)            # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:                # noqa: BLE001
        print(f"（打不开浏览器：{e}）", file=sys.stderr)


def build(args):
    since = args.since
    now = datetime.now()
    day = now.strftime("%Y-%m-%d")

    url = "https://github.com/trending"
    if args.lang:
        url += "/" + urllib.parse.quote(args.lang.strip())
    q = [f"since={since}"]
    if args.spoken:
        q.append("spoken_language_code=" + urllib.parse.quote(args.spoken.strip()))
    url += "?" + "&".join(q)

    items = parse_trending(fetch(url))
    if args.limit:
        items = items[:args.limit]
    prev = load_prev(since, day, args.lang, args.spoken)
    annotate(items, prev)

    meta = {"date": day, "since": since, "lang": args.lang or "", "spoken": args.spoken or "",
            "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"), "url": url,
            "prev_date": (prev or {}).get("date")}

    # 存档
    if not args.no_save:
        with open(snap_path(since, day, args.lang, args.spoken), "w", encoding="utf-8") as f:
            json.dump({**meta, "items": items}, f, ensure_ascii=False, indent=1)

        odir = os.path.join(REPORT_DIR, since)
        os.makedirs(odir, exist_ok=True)
        stem = day + "".join("_" + x for x in (args.lang, args.spoken) if x)
        md_path = os.path.join(odir, stem + ".md")
        html_path = os.path.join(odir, stem + ".html")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(render_md(items, meta))
        nav = '<nav><a href="../../index.html">← 历史</a> · <a href="../%s.md">Markdown 版</a></nav>' % (
            os.path.join(since, stem).replace(os.sep, "/"))
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(render_html(items, meta, nav))
        render_index()
    else:
        md_path = html_path = None

    return items, meta, md_path, html_path


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Windows 控制台中文/emoji
    except Exception:                              # noqa: BLE001
        pass

    p = argparse.ArgumentParser(description="GitHub Trending 每日抓取 / 存档 / 看板")
    p.add_argument("--since", default="daily", choices=["daily", "weekly", "monthly"])
    p.add_argument("--lang", default="", help="语言过滤，如 python / javascript / rust")
    p.add_argument("--spoken", default="", help="口语过滤，如 zh / en")
    p.add_argument("--limit", type=int, default=0, help="只显示前 N 个")
    p.add_argument("--no-save", action="store_true", help="只看不存档")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--open", action="store_true", help="生成后用浏览器打开看板")
    p.add_argument("--open-latest", action="store_true", help="打开最近一次的看板")
    p.add_argument("--history", action="store_true", help="列出历史报告")
    args = p.parse_args()

    if args.open_latest:
        since_dir = os.path.join(REPORT_DIR, args.since)
        if not os.path.isdir(since_dir):
            print("还没有任何报告，先跑一次不带参数的命令。")
            return 1
        files = sorted(f for f in os.listdir(since_dir) if f.endswith(".html"))
        if not files:
            print("还没有任何报告。")
            return 1
        open_file(os.path.join(since_dir, files[-1]))
        return 0

    if args.history:
        idx = render_index()
        rows = []
        for since in sorted(os.listdir(DATA_DIR)) if os.path.isdir(DATA_DIR) else []:
            d = os.path.join(DATA_DIR, since)
            if os.path.isdir(d):
                js = sorted(f for f in os.listdir(d) if f.endswith(".json"))
                rows.append((since, len(js), js[0][:10] if js else "-", js[-1][:10] if js else "-"))
        for s, n, first, last in rows:
            print(f"{s:<8} {n:>4} 份   最早 {first}   最新 {last}")
        print(f"\n索引页：{idx}")
        return 0

    items, meta, md, hp = build(args)
    if items:
        print(render_terminal(items, meta, color=not args.no_color))
    if hp:
        print(f"\n报告已归档：{hp}")
        print(f"历史索引：{os.path.join(REPORT_DIR, 'index.html')}")
        if args.open:
            open_file(hp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
