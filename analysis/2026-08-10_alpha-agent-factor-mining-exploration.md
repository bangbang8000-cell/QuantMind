# Alpha Agent 因子挖掘 — 探索记录 (2026-08-10)

> 本次会话对 RD-Agent 因子挖掘的完整调查结论,供下次直接查阅,避免重新探索。

## 1. 因子挖掘 LLM 配置链路(已修复)

### 调用链
```
前端 /evolve → launcher._run_evolution → subprocess.popen(run_rd_agent.py)
    └── rd_loop_wrapper._configure_env → RDLoop 子进程 → RD-Agent 内部 litellm
```

### 关键事实
- RD-Agent 用 **litellm** 后端(`rdagent/oai/backend/litellm.py`)
- `LiteLLMSettings.env_prefix = "LITELLM_"`,只读 `LITELLM_` 前缀变量:
  - `LITELLM_CHAT_MODEL`(默认 gpt-4-turbo)
  - `LITELLM_OPENAI_API_KEY`
  - `LITELLM_OPENAI_API_BASE`
- litellm 的 `completion()` HTTP 层还读**标准 `OPENAI_API_KEY`/`OPENAI_BASE_URL`**
- 因此**两套变量都必须设置**:`LITELLM_*`(settings)+ `OPENAI_*`(HTTP 层)

### 修复(已提交 3c14fad)
- **`backend/services/engine/rd_agent/llm_env.py`(新建)**:`build_llm_env(env)` 统一补两套变量
  - key 优先级:`LITELLM_OPENAI_API_KEY` > `DEEPSEEK_API_KEY` > `AI_IDE_LLM_API_KEY` > `OPENAI_API_KEY`
  - base: deepseek(`https://api.deepseek.com`)优先,回退 `OPENAI_BASE_URL`
  - model: deepseek 用 `deepseek/{DEEPSEEK_MODEL}`,回退 `openai/{CHAT_MODEL}`
  - 占位符检测:`your-deepseek-api-key` / `mock-api-key` 视为未配置
- `launcher.py` `_run_evolution` + `rd_loop_wrapper.py` `_configure_env` 都调用 `build_llm_env`

### 实测成功
- `.env` 配 `DEEPSEEK_API_KEY=sk-REDACTED`, `DEEPSEEK_MODEL=deepseek-v4-flash`
- 日志:`LiteLLM completion() model=deepseek-v4-flash; provider=deepseek`
- RD-Agent 生成因子代码(Volume_Ratio_5D / Reversal_5D / Price_Position_20D)+ critic 循环

## 2. 因子执行数据路径问题(已修 workspace 对齐,待验证)

### 根因
- `rd_loop_wrapper._ensure_data_file()` 生成 `daily_pv.h5` 在 `{task_log_dir}/git_ignore_folder/factor_implementation_source_data/`
- 但 RD-Agent workspace 默认 `Path.cwd()/git_ignore_folder/RD-Agent_workspace`
- 进程 cwd 被 `run_rd_agent.py:97 os.chdir(tempfile.gettempdir())` 改成 `/tmp`
- → workspace 和 data_folder 不匹配,因子执行找不到 daily_pv.h5

### 修复(已改代码,待验证)
`rd_loop_wrapper.py` run() 在 _ensure_data_file 后:
```python
os.environ["WORKSPACE_PATH"] = task_log_dir
os.chdir(task_log_dir)
```
验证:`WORKSPACE_PATH` env 能覆盖 RD-Agent workspace(`/tmp/test_workspace` 生效)

### 注意
- `FACTOR_COSTEER_SETTINGS.data_folder` 是相对路径,无法 env 覆盖
- 依赖 cwd=task_log_dir 让它相对解析正确
- `/evolve` 触发的任务仍 `-11 段错误`(可能 launcher 子进程并发/内存问题),需排查

## 3. 前端多市场挖掘/回测(未完成)

### 现状
- `electron/src/features/alpha-research/context-v2/TaskContext.tsx:249`: `market: config.miningMarket || 'a_share'`
- `SettingsPage.tsx`: apiKey 存 localStorage `quantaalpha_config`,不传后端
- `/evolve` API 支持 `market` 参数(a_share/crypto/hong_kong/us_stock/futures)
- 回测默认按 A 股(需要按市场区分)

### 待做
- [ ] 前端市场选择器(期货/港股/美股/A股)接入挖掘
- [ ] 回测按市场区分
- [ ] 前端挖掘任务显示完善
- [ ] 前端设置里的 deepseek key 打通到后端(存 user_profiles.api_key)

## 4. 关键文件
- `backend/services/engine/rd_agent/llm_env.py` — LITELLM env 构建(新建)
- `backend/services/engine/rd_agent/rd_loop_wrapper.py` — env + workspace 对齐
- `backend/services/engine/alpha_agent/launcher.py` — 子进程 env
- `backend/services/engine/routers/alpha_agent.py` — /evolve 端点
- `scripts/alpha_agent/run_rd_agent.py` — 子进程入口(os.chdir 到 /tmp 是坑)
- `rd-agent/rdagent/oai/backend/litellm.py` — LITELLM 前缀定义
- `electron/src/features/alpha-research/` — 前端挖掘页
