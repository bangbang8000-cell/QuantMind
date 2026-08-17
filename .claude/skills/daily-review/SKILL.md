---
name: daily-review
description: "A股每日复盘 — 基于 QuantDB 本地数据的盘后固定复盘：指数、涨跌结构与涨停梯队、量能、行业/概念轮动、资金面、情绪面、个股榜、自选复盘、昨日复盘回顾。用户说「复盘」「每日复盘」「复盘某天」时使用：跑脚本取数 → 按模板写复盘报告 → 转 PDF → 落盘股票报告目录 → 聊天回复速览。触发词：复盘、每日复盘、今日复盘、盘后复盘、复盘20260814"
---

# daily-review — A股每日复盘

盘后固定动作：把 QuantDB 当天数据变成一份结构固定的复盘报告（Markdown + PDF），落盘到前端「股票报告」页可见目录，并在聊天里回复速览。

## ⚠️ 单位铁律（先查 [[quantdb-fields]]，最高优先级）

| 陷阱 | 正确口径 |
|---|---|
| 个股 volume=**股**、amount=**万元** | 指数 volume=**手**、amount=万元 |
| 复盘报告里金额一律换算为**亿元**（万元÷1e4） | 脚本输出的 `*_yi` 字段单位已是亿元 |
| `technical_indicators.pct_change` = **%**；`return_1d/20d` 全 NaN 别用 | 涨跌家数/涨停/连板全用它 |
| `index_daily.preClose` **全 NULL** | 指数涨跌幅用 close 序列自算（脚本已处理） |
| l2_factors 停更 20260227、两融滞后 1 日、北向只有季度快照 | 必须带「数据滞后声明」，禁止当当日数据写 |

## 执行流程（每次复盘固定 5 步）

### 第 1 步：跑取数脚本

```bash
cd <repo>/.claude/skills/daily-review/scripts
python3 daily_review.py --date 20260814              # 指定日；不带 --date 则取最新交易日
python3 daily_review.py --watch 601138.SH,600519.SH  # 可选：自选/持仓股必带
```

输出 `data/reports/daily_review/{YYYY-MM-DD}_stats.json` + `{YYYY-MM-DD}_facts.md`。
脚本兼容宿主机与容器内（数据目录自动探测；容器内路径 `/data/quantdb`，宿主机 `data/quantdb`）。

### 第 2 步：读 facts.md 写复盘报告（Markdown 模板）

**报告 = facts.md 的事实 + 你的解读。facts.md 没有的数字禁止出现在报告里。**

```markdown
# A股每日复盘 2026-08-14（周五）

> **报告日期**：2026-08-14
> **数据截至**：2026-08-14

## 一、盘面速览（结论先行）
2-4 句：指数表现 → 涨跌结构 → 量能 → 主线板块 → 一句话定性（强势/震荡/弱势 + 依据）

## 二、指数与量能
指数表（facts 一、）+ 两市成交额解读（环比/5 日均对照，放量 or 缩量）

## 三、涨跌结构与情绪
涨停/跌停/炸板数量、最高连板与连板梯队、涨跌分布表（facts 二、四）
情绪读数 + 解读：买压/卖压对比、早盘上涨占比 → 追高意愿强还是弱

## 四、板块与主线
行业一级 Top/Bottom（facts 三）、概念 Top；指出当日主线与杀跌方向；
涨停个股聚集在哪些板块（从涨幅榜的 industry 列归纳）

## 五、资金面
两融（注明截至日与滞后天数）、北向季度快照（注明季度口径）、L2 停更声明

## 六、个股榜
涨幅/跌幅/成交额/换手榜解读（facts 六），挑 3-5 只有代表性的说原因判断（无新闻佐证时只描述数据，不编原因）

## 七、自选/持仓复盘（自带 --watch 时才有）
逐只：涨跌幅、量能、技术位（MA20 上下）、当日状态（涨停/炸板/大涨/异动）

## 八、昨日复盘回顾（复盘闭环，连续性的核心）
读上一份复盘（同目录 {上一交易日}.md 或 PDF 前的 md）的「要点与明日关注」，
逐条对照今日实际：命中几条 / 未命中几条 / 打脸的原因是什么（禁止含糊带过）

## 九、要点与明日关注
- 要点：今日市场最重要的 3 条事实
- 明日关注：可被次日验证的 2-4 条明确预期（明天能判断对错的才算，禁止「关注成交量变化」这类废话）

## 数据说明
滞后数据集声明 + 单位说明（从 facts 的数据说明复制）
```

**写作铁律**：每个数字带单位；涨停梯队/连板高度以脚本 stats 的 `market.streaks` 为准；涨跌停判定规则见 REFERENCES/review-methods.md；ST 涨跌幅与新股规则别记错（主板 ST 2026-07-06 起 ±10%）。

### 第 3 步：Markdown → PDF（研报风，复用 stock-market-analysis §7.4 管线）

转换脚本 `backend/scripts/md_to_pdf_report.py`（reportlab，封面/红涨绿跌语义着色/斑马纹表格自动生效）。

**环境分支**（先探测：容器内 `test -d /app/backend` 为真）：

```bash
# —— 宿主机（Claude Code）——
docker cp /tmp/复盘.md quantmind:/tmp/review.md
docker exec quantmind bash -lc "cd /app && python3 backend/scripts/md_to_pdf_report.py /tmp/review.md /tmp/review.pdf"
docker cp quantmind:/tmp/review.pdf /tmp/复盘.pdf

# —— 容器内（QuantBot / QwenPaw）——
python3 /app/backend/scripts/md_to_pdf_report.py /tmp/review.md /tmp/review.pdf
```

### 第 4 步：落盘股票报告目录（必做，只发 /tmp = 未交付）

文件名固定：`每日复盘_{YYYY-MM-DD}.md` / `.pdf`，放 `db/trading_agents_results/每日复盘/`。

```bash
# —— 宿主机：宿主机直接 cp 会 EACCES（目录 owner 是容器 root），必须 docker cp ——
docker cp 复盘.md quantmind:/app/db/trading_agents_results/每日复盘/每日复盘_2026-08-14.md
docker cp 复盘.pdf quantmind:/app/db/trading_agents_results/每日复盘/每日复盘_2026-08-14.pdf

# —— 容器内：直接 cp ——
cp 复盘.md /app/db/trading_agents_results/每日复盘/每日复盘_2026-08-14.md
cp 复盘.pdf /app/db/trading_agents_results/每日复盘/每日复盘_2026-08-14.pdf
```

落盘后 `ls` 确认 md + pdf 都在（前端「股票报告」页 → 每日复盘 文件夹）。

### 第 5 步：聊天回复速览（QuantBot/Claude 直接回答用户用这个格式）

```markdown
**A股复盘 2026-08-14（周五）**

一句话总结：…

指数：上证 +0.01% / 深成 +0.45% / 创业板 +1.12% / 科创50 -0.00% / 北证50 -0.94%
广度：涨 2400 / 跌 2970（涨跌比 0.81）；涨停 64 / 跌停 14 / 炸板 22；最高 5 连板
量能：两市成交额 21,565.76 亿元（环比上一交易日 1.04x；5 日均 21,xxx 亿，量比 x.xx）
主线：行业 Top3 …；概念 Top3 …
资金：两融 xxx 亿（截至 08-13，+xx 亿）；北向 2026Q2 持仓市值 30,685.68 亿元
情绪：买压 0.49 / 卖压 0.51；早盘上涨占比 40.68%
自选：…（有 --watch 才有）

→ 完整复盘报告已落盘「股票报告 → 每日复盘」目录
```

## 复盘日期标注规则

- 用户说「复盘」不带日期 → 最新交易日（脚本默认行为）
- 「复盘 20260814」/「复盘 8月14日」 → `--date 20260814`；非交易日脚本自动取 ≤ 该日期的最近交易日并在报告封面注明**实际复盘日**
- 报告文件名、封面`报告日期/数据截至`、聊天速览标题三处日期必须一致

## 维护

- 单测：`cd scripts && python3 -m pytest tests/ -q -c tests/pytest.ini`（24 用例，覆盖涨跌停判定/连板/分布/板块加权/单位换算/除权检测）
- 涨跌停规则**复用** `backend/services/trade/simulation/services/local_market_data.py`（经 ZTPrice/DTPrice 交叉验证 99.71%），禁止在本 skill 里另写一套
- 改 SKILL.md 后必须同步双副本：`cp -r .claude/skills/daily-review ~/.claude/skills/`（userSettings 优先加载，不同步等于白改）

## 相关技能

- **[[quantdb-fields]]** — 必读：单位/口径速查（本 skill 计算正确性前提）
- **[[stock-market-analysis]]** — 盘后想对某只股票深挖时用（复盘是广度，它是深度）
- **[[quantdb-sdk]]** — QuantDB 数据源背景