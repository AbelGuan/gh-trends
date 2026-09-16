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
python notify_feishu.py --top 5            # 只推前 5 名
python notify_feishu.py --text             # 用纯文本消息（排障用）
python notify_feishu.py --pages-base https://user.github.io/gh-trends
```

凭据从环境变量读：`FEISHU_WEBHOOK`、`FEISHU_SECRET`（开了签名校验才需要）、`PAGES_BASE`。
没配 webhook 时会自动跳过推送（打印内容后正常退出），所以 Actions 上漏配 secret 不会把流程弄挂。

## 说明与已知限制

- 数据源是 GitHub 的非官方趋势页（`github.com/trending`），没有官方 API；页面改版可能让解析失效，届时改 `parse_trending()` 里的正则即可。
- 抓取失败会自动重试 3 次（间隔 2s / 4s）。
- 抓取时间用的是本机时间；同名日期重复运行会覆盖当天快照。
