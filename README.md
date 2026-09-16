# gh-trends · GitHub 每日趋势

零依赖（只用 Python 标准库）的 GitHub Trending 抓取 / 存档 / 看板工具。
每天跑一次，就有一份带**排名变化**的本地报告，历史全部留档，可直接用浏览器翻。

## 快速开始

```bash
python gh_trends.py          # 今日 daily 榜：终端打印 + 归档报告
python gh_trends.py --open   # 同上，并自动用浏览器打开 HTML 看板
```

Windows 上也可以直接双击 **`trends.cmd`**（等价于 `python gh_trends.py --open`）。

## 常用参数

| 参数 | 说明 |
| --- | --- |
| `--since daily\|weekly\|monthly` | 日榜 / 周榜 / 月榜（默认 daily） |
| `--lang python` | 只看某个语言，如 `python` `javascript` `rust` `go` |
| `--spoken zh` | 只看中文项目（`en` / `zh` / `ja` …） |
| `--limit 10` | 只看前 N 个 |
| `--open` | 生成后用浏览器打开看板 |
| `--open-latest` | 打开最近一次的看板 |
| `--history` | 列出已存档的历史报告 |
| `--no-save` | 只看不存档（试用参数时用） |
| `--no-color` | 终端输出不带颜色 |

## 输出物放哪

```
gh-trends/
├─ gh_trends.py                     # 主程序
├─ trends.cmd                       # Windows 双击即可
├─ data/<daily|weekly|monthly>/*.json   # 原始快照（用来算排名变化）
└─ reports/
   ├─ index.html                    # 历史索引（所有日期的列表）
   └─ <since>/2026-09-17.html/.md   # 每天一份：HTML 看板 + Markdown
```

- **HTML 看板**：暗色卡片、可点进仓库、显示 ★ 总数 / 今日新增 / fork / 语言；相对上一次快照标出 `NEW` / `▲上升` / `▼下降`。
- **Markdown**：同样的表格，方便丢进笔记软件或提交到别的仓库。
- **JSON 快照**：`--since`、语言、口语各存一份，互不干扰。

## 排名变化是怎么算的

每次运行都会存一份当天的 JSON；生成报告时会自动找同一榜单**上一次（非今天）**的快照做对比：

- `NEW` = 上次没上榜
- `▲n` / `▼n` = 名词升降（n = 名词差）
- `—` = 名次没变

所以**第一次跑不会有变化标记，从第二天开始才有意义**。

## 挂到每天自动跑

### 方案一：GitHub Actions（推荐，不需要本机开机）

见 **`部署清单.md`**（建仓库 → 飞书机器人 → Secrets → 跑一次 → 可选开 Pages）。
用到的文件：

- `.github/workflows/daily.yml` —— 每天 UTC 01:10（北京 09:10）抓取 + 推送 + 提交回仓库
- `notify_feishu.py` —— 飞书群机器人推送（支持签名校验 / 关键词、卡片和纯文本两种格式）

### 方案二：本机 Windows 计划任务（要求机器开着）

先手动跑通，再决定要不要注册计划任务。命令形如：

```bat
schtasks /create /tn "GitHub Trending 每日" ^
  /tr "\"C:\Users\guant\AppData\Local\Programs\Python\Python313\python.exe\" \"D:\Pi\Chat\gh-trends\gh_trends.py\"" ^
  /sc daily /st 09:00 /f
```

- 只生成报告、不弹浏览器 → 用上面的写法，之后 `--open-latest` 或直接点 `reports/index.html` 看。
- 想每天自动弹出来 → 把 `/tr` 换成 `"D:\Pi\Chat\gh-trends\trends.cmd"`。
- 删除：`schtasks /delete /tn "GitHub Trending 每日" /f`

> 注：这个任务只是本机抓取 + 生成文件；开发这步不需要，但推送飞书时会把当天名单发到你的群。抓的是公开页面 `https://github.com/trending`。

## 推送脚本 notify_feishu.py

```bash
python notify_feishu.py --dry-run          # 只打印将发送的 JSON，不发
python notify_feishu.py --hot 5            # 「涨星最猛」展示前 5（默认 3，0=不展示）
python notify_feishu.py --odd 5            # 「涨星速度异常」展示前 5（默认 3，0=不展示）
python notify_feishu.py --top 5            # 榜单只推前 5 名
python notify_feishu.py --style medal      # 前三名奖牌 + 加宽数据行
python notify_feishu.py --style compact    # 每人一行，不带简介
python notify_feishu.py --no-desc          # 卡片更短，不带简介
python notify_feishu.py --text             # 用纯文本消息（排障用）
python notify_feishu.py --pages-base https://user.github.io/gh-trends
```

卡片长什么样（默认 `--style uniform`，十名一视同仁）：

```
🚀 GitHub Trending 今日榜 · 2026-09-17        ← 蓝色标题栏，整张卡可点
📊 今日上榜 21 个　🆕 新上榜 2 个
🧩 语言分布：TypeScript×5 · Python×5 · JavaScript×3
──────
⬆️ 上升最猛 owner/repo  #9 → #3          ← 名次变化榜
⬇️ 掉得最狠 owner/repo  #4 → #9
🆕 新上榜：repo-a / repo-b
👋 掉出榜单：repo-c
──────
🔥 今日涨星最猛                            ← 按今日 +N 排，不看名次
1. owner/repo +3,215 · ★ 31,689
2. owner/repo +1,532 · ★ 34,991　⬆️6
3. owner/repo +1,249 · ★ 7,041
──────
💥 涨星速度异常（今日新增 ÷ 昨日星数）     ← 找“小仓爆火”
1. owner/repo +31.1%　今日 +1,036 · ★ 4,368
2. owner/repo +25.7%　今日 +1,136 · ★ 5,552
3. owner/repo +21.6%　今日 +1,249 · ★ 7,041
──────
1. owner/repo　Go　★31,689　fork 2,251　今日 +3,215
简介一行…                                 ← 十条全部带简介，想看个大概

2. owner/repo　…
…
──────
〔抓取时间 · 数据来源〕
〔📊 完整看板〕〔📝 Markdown 版〕
```

三个值得一行：

- **两个涨星榜互补**：「最猛」看绝对增量（大仓库占优），「速度异常」看相对增速（小仓库容易露头）。
  分母用 `stars - today`（昨日星数）而不是当前总星，否则今天的增长会把自己的分母撞大。
  默认过滤 `昨日星数 < 500` 或 `今日新增 < 50` 的项目，避免小数仓/微小波动制造假异常
  （阈值在 `odd_board(min_stars=, min_today=)`，想调就改这里）。

- **名次变化榜**需要“昨天”的对比基准。「上升/下降/新上榜」来自今天的快照，
  **「掉出榜单」需要昨天的名单** —— 所以快照 JSON 里多了一个 `dropped` 字段（旧快照没有也不报错，最多是少一行）。
- **只用了飞书卡片 1.0 的元素**（`div`/`lark_md`/`hr`/`note`/`action`），颜色只用官方明确支持的 `red`/`grey`，
  因为 webhook 机器人**不能发图片**（飞书图片必须先上传换 `img_key`，那个要自建应用）。
- **三级降级**：漂亮卡片 → 简化卡片（只留 div+按钮）→ 纯文本。任何一级发送失败自动退到下一级，
  不会因为某个飞书版本不认新元素而丢掉当天的推送。

凭据从环境变量读：`FEISHU_WEBHOOK`、`FEISHU_SECRET`（开了签名校验才需要）、`PAGES_BASE`。
也可以放本地 `feishu.local.json`（已 gitignore）。没配 webhook 时会自动跳过推送（打印内容后正常退出）。

## 推送到 Obsidian（走 Atom feed，不动你的笔记库）

`make_feed.py` 把历史快照汇总成一个 Atom feed，挂在 GitHub Pages 上：

```bash
python make_feed.py --base https://<用户名>.github.io/gh-trends   # 输出 ./feed.xml
```

参数：`--limit 30`（收录最近 N 期）、`--top 10`（每期只取前 N 名，控制体积）、`--out`（输出路径）。
Actions 里已经在每次抓取后自动跑这一步，所以订阅地址固定是：

```
https://<用户名>.github.io/gh-trends/feed.xml
```

Obsidian 侧（二选一，推荐前者）：

1. **RSS 插件订阅**：社区插件市场搜 `RSS`，装上后在插件设置里添加订阅源，填上面的 feed 地址，
   指定一个落盘目录（如 `Inbox/GitHub-Trends`）。之后每天自动多一篇笔记，**不需要把 vault 变成 git 仓库、不需要 PAT**。
2. **vault 变 git 仓库**：vault 建 git 仓库 + 装 `Obsidian Git` 插件定时 pull，让 Actions 直接往 vault 的某个子目录提交。
   控制力最强，代价是 vault 要变仓库、要存一个能写 vault 的 PAT，且手机端插件支持相对受限。

> 选方案 1 的话，建议先把 Pages 打开（见 `部署清单.md` 第 5 步），否则 feed 地址不可访问。
> 想改期名/期数，直接改 `make_feed.py` 里的 `feed_title` 或命令行参数。

## 说明与已知限制

- 数据源是 GitHub 的非官方趋势页（`github.com/trending`），没有官方 API；页面改版可能让解析失效，届时改 `parse_trending()` 里的正则即可。
- 抓取失败会自动重试 3 次（间隔 2s / 4s）。
- 抓取时间用的是本机时间；同名日期重复运行会覆盖当天快照。
