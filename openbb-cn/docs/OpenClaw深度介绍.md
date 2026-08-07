# OpenClaw AI助手深度介绍

> 这是一份可自由编辑的文档。你可以直接修改 Markdown 内容，
> 改完后推送到 GitHub，我会把它重新渲染成精美的 HTML 演示。
> 
> **修改流程**：克隆 → 修改 → 推送 → 我自动更新演示

---

## 修改记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-04-05 | v1.0 | 初始版本（由马斯克知识库 AI 生成）|

---

## 1. 什么是 OpenClaw？

OpenClaw 是一个**生产级的多 Agent AI 协作平台**。

一个实例支持多个 AI Agent 协同工作，每个 Agent 拥有独立的人设、技能与工作区。通过灵活的工具链集成和持久化知识库，实现**跨渠道、跨任务、跨会话**的智能协作。

### 核心优势

- 🤖 **多 Agent 系统** — 多 Agent 各司其职，binding 配置区分能力边界
- ⚡ **智能任务流** — SQLite 持久化，48 小时超长待机
- 🧠 **持久知识库** — Karpathy 模式，Ingest→Compile→Query→Lint
- 🔒 **企业级安全** — 危险代码扫描，环境变量过滤

---

## 2. 技术背景（可选补充）

> 如果你希望介绍 OpenClaw 的技术背景，可以在这里写相关内容。
> 比如 Transformer 架构、BERT/GPT/MoE 等内容都可以放这里。

---

## 3. 系统架构

### 架构层次

```
🌐 Gateway
    └─ WebSocket / HTTP / 任务调度 / 认证中心 / SSRF防护

⚙ Task Flow
    └─ SQLite持久化 / /tasks命令 / ACP Prompts / 修订版追踪

🤖 Agents（多 Agent）
    ├─ 🚀 马斯克  — AI / LLM / 技术研究 / 知识库
    ├─ 📊 巴菲特  — 金融 / 股票 / AKShare / 数据分析
    └─ ✍️ 希文    — 政务 / 公文 / 党务 / 文字秘书

📦 Skills 层
    └─ Skills / Plugins / Triggers / Experiences / Channel Bindings

🔧 Tools 层
    ├─ 📄 飞书      — 文档 / 云盘 / Wiki / 多维表格
    ├─ 🌐 网页      — Tavily搜索 / Firecrawl抓取
    ├─ 📊 数据      — Excel / Word / PDF / 图片
    └─ ⏰ 定时      — Cron / 心跳 / 自进化
```

---

## 4. 核心功能详解

### 4.1 Task Flow 任务流

**核心特性：**

- SQLite 持久化状态 + 修订版追踪
- /tasks 命令实时查看所有后台任务
- ACP 任务 + Cron + 子 Agent 统一管理
- Sticky Cancel Intent（取消时等子任务完成再停止）
- 阻塞可见（任务被阻塞时父级会话直接显示原因）
- api.runtime.taskFlow 插件开发接口

**三类任务统一调度：**

| 类型 | 说明 | 超时 |
|------|------|------|
| ACP | 主动调用 /task 触发 | 默认48h |
| Cron | 定时任务（信号采集、每日复盘） | 独立配置 |
| Subagent | 子智能体 spawn 隔离会话 | 继承+扩展 |

### 4.2 知识库 Karpathy 模式

**四阶段循环：**

```
Ingest（摄取）→ Compile（编译）→ Query（查询）→ Lint（检查）
 论文/文章      Wiki文章      问答结果      健康报告
```

**价值：** Wiki 是一个**持久复利的产物**。新的矛盾已被标注，交叉引用已在，合成已完成。

### 4.3 多渠道接入

- 飞书 / Telegram / Discord / Signal / Matrix / Slack
- LINE · QQ Bot · Android · macOS
- Voice Wake 语音唤醒（macOS）
- Google Assistant App Actions（Android）
- WhatsApp emoji 反应 · Telegram 审批流

### 4.4 安全加固

**插件危险代码扫描（背景：Cisco AI 安全研究）：**

- 内置静态分析，检测到严重问题时安装直接失败
- 绕过需显式 `--dangerously-force-unsafe-install`
- 发布到 ClawHub 的技能必须通过危险代码扫描

**节点配对权限分离：**

- 旧：配对成功 → 自动获得节点命令权限
- **新：配对成功 + 明确批准 → 才能执行节点命令**

**Shell 环境变量严格过滤：**

```
PYPI_INDEX / pip_proxy        — 包拉取重定向（供应链攻击）
DOCKER_HOST / CONTAINERD_HOST  — 容器劫持
TLS_CERT_PATH / SSL_CERT_DIR  — 证书伪造
GCC_PATH / CLANG_PATH          — 编译器注入
MAVEN_OPTS / GRADLE_OPTS     — JVM依赖劫持
```

---

## 5. 版本演进

### v3.22（2026.3）— 超时革命

- 默认 Agent 超时 **10min → 48h**
- /btw 旁支指令
- Per-Agent 独立推理配置
- 语音 Webhook 加固（64KB/5秒）

### v4.1（2026.4.1）— 安全元年

- 插件危险代码扫描
- 节点配对权限分离
- Shell 环境变量过滤
- xAI/Firecrawl 配置路径重构

### v4.2（2026.4.2）— 任务流重构

- Task Flow SQLite 统一账本
- /tasks 命令 · 阻塞原因可见
- Sticky Cancel Intent
- Before_agent_reply 钩子
- Provider Replay 钩子

**升级注意：**
```bash
openclaw doctor --fix
# 回退方案：v2026.3.13
```

---

## 6. 配套工具

| 工具 | 用途 |
|------|------|
| `pdf-ingest.py` | PDF论文提取（pdfplumber + pymupdf） |
| `md-to-pdf.py` | Markdown → PDF（Light/Dark/Sepia 三主题） |
| `gen_openclaw_ppt.py` | python-pptx 专业PPT生成 |
| `lint-wiki.py` | 知识库健康检查（死链接+孤立文章） |
| `generate_ppt.py` | 百度千帆 AI PPT（100+模板） |

---

## 7. 相关链接

- 📖 官方文档：https://docs.openclaw.ai
- 💬 Discord 社区：https://discord.gg/openclaw
- 📦 插件市场：https://clawhub.ai
- 🐟 水产市场：https://openclawmp.cc

---

## 📝 在这里写下你的内容

> 以下部分是你可以自由编辑的区域。
> 把你的内容写在下面，我会把它渲染到 HTML 演示中。

---

### 你的标题

在这里写你的内容...

---

*最后更新：2026年4月5日 · 由马斯克知识库 AI 生成*
