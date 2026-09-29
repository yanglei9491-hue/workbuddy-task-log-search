---
name: 会话任务检索
description: 跨会话检索本机 WorkBuddy 的历史任务与对话内容。从本地会话索引库（~/.workbuddy/workbuddy.db 的 sessions 表）列出某天/某工作空间的全部任务会话，再逐个读取对话全文（~/.workbuddy/projects/<工作目录编码>/<会话ID>.jsonl），提取用户需求原文与最终结论，输出清单或 HTML 报告。支持按序号、会话 ID、标题精确命中单个任务，并可导出该任务全部回复轮次。用户提到查我今天的任务、今天做了什么、找某天的任务、跨会话、之前那个会话讲了什么、会话记录、对话日志、任务清单、精确查找某个任务时使用。触发词：今天的任务、今天做了什么、查任务、会话记录、对话日志、跨会话、历史会话、任务清单、精确查找、第几个任务、某个任务。
version: 1.2.2
license: MIT
compatibility: "WorkBuddy >= 1.0"
allowed-tools: [Read, Write, Bash]
metadata:
  category: 10-utility
  agent_created: true
---

# 会话任务检索

解决「跨会话内容看不到」的问题——运行时会话互相隔离，但每个会话的完整对话都**明文落盘**，所以可以按日期/目录检索出历史任务的真实内容。

## 数据位置（核心事实）

| 数据 | 路径 | 内容 |
|------|------|------|
| 会话索引 | `~/.workbuddy/workbuddy.db` → `sessions` 表 | id / cwd / title / custom_title / created_at / last_activity_at / model |
| 对话全文 | `~/.workbuddy/projects/<工作目录编码>/<会话ID>.jsonl` | 每行一条 JSON 记录，明文 |
| 运行中进程 | `~/.workbuddy/sessions/<pid>.json` | sessionId / cwd / endpoint |
| 自动化运行 | `workbuddy.db` → `automation_runs` 表 | thread_title / status / created_at |

**工作目录编码规则**：`E:\workspace\my-project` → `e-workspace-my-project`
（替换 `\` `/` `:` 为 `-`，去首尾 `-`，转小写）

**jsonl 行类型**：`session-meta` / `message`（role=user\|assistant，正文在 `content[].text`）/ `reasoning` / `ai-title` / `file-history-snapshot`

## 执行命令

```bash
# 按实际安装位置调整 SKILL_DIR
SKILL_DIR="$HOME/.workbuddy/skills/10-utility/session-search"
PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SCAN="$SKILL_DIR/scripts/scan.py"

# ---- 浏览 ----
"$PY" "$SCAN"                          # 今天的所有任务
"$PY" "$SCAN" --date 2026-09-28        # 指定某天
"$PY" "$SCAN" --days 3                 # 从指定日往前回溯 3 天（含当天）
"$PY" "$SCAN" --list                   # 只列标题（带编号，快）
"$PY" "$SCAN" --cwd 数据流水线          # 只看某个工作空间
"$PY" "$SCAN" --keyword 报表            # 关键词过滤（标题 或 用户消息命中）
"$PY" "$SCAN" --html                   # 额外输出 HTML 报告到桌面

# ---- 精确命中单个任务（三选一）----
"$PY" "$SCAN" --index 3                # 按 --list 的编号
"$PY" "$SCAN" --id a1b2c3d4            # 按会话 ID 前缀
"$PY" "$SCAN" --title 报表              # 按标题关键词

# ---- 深度导出 ----
"$PY" "$SCAN" --index 3 --all-turns    # 该任务全部回复轮次
"$PY" "$SCAN" --index 3 --full         # 结论不截断
"$PY" "$SCAN" --html --out <路径>       # 自定义 HTML 报告输出位置

# ---- 隔离测试（仅测试用，日常查询不要带）----
"$PY" "$SCAN" --home <数据根目录>       # 指定数据根，默认 ~/.workbuddy
```

## 测试与回归

`tests/` 下是可复现的暴力测试资产：

| 文件 | 作用 |
|------|------|
| `tests/gen_dataset.py` | 生成 100 份对抗性数据集到桌面「测试数据集」 |
| `tests/verify_dataset.py` | 数据集保真度自检（db/jsonl/真值表三方一致） |
| `tests/run_tests.py` | 穷举测试（73 用例 / 12 维度），含稳定性重复执行 |
| `tests/test_bigline.py` | 超大单行 JSON 抗压验证（50MB 单行） |
| `tests/bench.py` | 性能基准（测试集 100 份 + 真实库 1480 会话双场景） |
| `tests/report_gen.py` | 生成 HTML + Markdown 测试报告 |

运行时产物（脚本自动生成，非手工维护，勿作为权威数据引用）：

| 文件 | 由谁生成 |
|------|----------|
| `tests/test_result.json` | `run_tests.py` 每次运行覆盖 |
| `tests/perf_result.json` | `bench.py` 每次运行覆盖 |

```bash
SKILL_DIR="$HOME/.workbuddy/skills/10-utility/session-search"
PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe"
T="$SKILL_DIR/tests"

"$PY" "$T/gen_dataset.py"              # 建数据集（输出到桌面）
"$PY" "$T/verify_dataset.py"           # 校验数据集
"$PY" "$T/run_tests.py"                # 全量测试
"$PY" "$T/run_tests.py" --repeat 10    # 稳定性验证（输出 730 次一致性）
"$PY" "$T/run_tests.py" --only 关键词   # 只跑某类用例
"$PY" "$T/test_bigline.py"             # 超大单行抗压
"$PY" "$T/bench.py"                    # 性能基准
"$PY" "$T/report_gen.py"               # 出报告
```

**回归基线（改动后不得低于）**：准确率 100%（73/73）；稳定性以 `--repeat 10` 输出为准
（730 次零波动）；列表模式约 0.15s、关键词模式 1–2s（随环境浮动，量级参考）。

**输入陷阱护栏（改代码时勿踩回）**

| 级别 | 陷阱 | 正确做法 |
|------|------|----------|
| P2 | `--index 0` 会被 `if args.index:` 的 falsy 判断静默忽略，返回全量且 rc=0 | 数值参数一律用 `is not None` 判断 |
| P3 | 非法日期直接抛 `ValueError`，用户看到 traceback 不知错在哪 | 捕获后输出「日期格式不正确…应为 YYYY-MM-DD」 |

**抗压边界**：50MB 单行 JSON（真实库最大约 60MB 级）下各模式均为亚秒级响应，不崩溃、
输出被截断保护在 100KB。按行读 + 输出截断天然免疫超大单行，无需额外守卫。

## 工作流（用户说"帮我找某个任务"时）

1. 先跑 `--list` 出编号菜单给用户看（或直接按用户给的关键词猜）。
2. 用户指认后，用 `--index N` / `--id` / `--title` 直取全文。
3. 需要过程细节时加 `--all-turns`（一个长任务可能有上百轮）。
4. 结果直接回复，不落文件；用户要报告时才加 `--html`。

## 输出结构

**列表模式**（`--list`）每行一条，带序号便于 `--index` 直取：

```
 1. [a1b2c3d4] 修复登录超时问题              | E:/workspace/2026-09-29-10-38-39
 2. [e5f6a7b8] 整理季度报表脚本              | E:/workspace/data-tools

共 6 个会话
提示：用 --index N 直取第 N 个任务的完整内容
```

**详情模式**（默认，或 `--index`/`--id`/`--title`）。按用户给出的指定方式决定标题行：
带 `--index` 时标题为 `## N. <会话标题>`；带 `--id`/`--title`（或单独使用时）标题为
`精确命中  #N  <会话标题>`。字段为独立行：

```
精确命中  #3  报表脚本重构
   会话 ID  e5f6a7b8-1628-45c9-acd8-5dcc7f45695e
   时间     09-08 13:26 — 09-29 09:27
   目录     E:\workspace\2026-09-08-13-26-55
   模型     custom-local:deepseek-flash

   需求（9 条）:
     [04:12] 先补 1 和 3，4 跑测试
     ...

   最终结论:
     <该会话最后一条 assistant 回复>
```

加 `--all-turns` 时，「最终结论」段替换为「全部回复（N 轮）」，逐轮输出。

## 实现要点（踩过的坑）

1. **JSONL 的 `timestamp` 是毫秒**，与 `sessions` 表的 `created_at` 单位一致；比较时 `秒级时间戳 * 1000`。
2. **`--date` 必须做双侧区间过滤**（`>= lo AND < hi`）。只写下界会让跨天会话串进别的日期（一个会话可从几天前持续到今天），统计口径立即失真。
3. **`--days N` 是往前回溯**（`d_start = d0 - (N-1)`），不是往后。语义：`--date 2026-09-29 --days 3` → 09-27 ~ 09-29。
4. **数值参数用 `is not None` 判断，不能靠真值判断**：`--index 0` 会被 `if args.index:` 的 falsy 判断静默吞掉——不报错、返回全量、返回码 0，与 `--index -1`（正常报错）行为不一致。凡「可能取 0」的参数都适用此条。
5. **必须按日期过滤消息**：不过滤会把几周前的提问混进当天清单。
6. **要过滤系统注入消息**：`<system-reminder>` 块、`You are now in Agent mode...`、`<teammate-message>`、`<task-notification>`、`<cb_summary>`、`Please continue with the conversation...` 都不是用户真实需求，需剔除，否则条数虚高（长会话里系统注入常占多数）。
7. **关键词过滤要同时看标题和正文**：只看标题会漏（关键词常只在对话正文里出现）。`--list` 也走同一套过滤。
8. **`--all-turns` 不能依赖 `precise`**：`--keyword` 命中也应能导出轮次，所以触发条件用 `bool(precise) or args.all_turns`。
9. **同一工作目录下有多个 jsonl**：目录按 cwd 编码，一个 cwd 会有多次会话各一个文件。定位特定会话用 `<会话ID>.jsonl`，不要遍历整个目录。
10. **要捕获 `ValueError` 并给中文提示**：非法日期（如 `2026/09/28`）若不捕获，用户看到的是 Python traceback，不知错在哪。
11. **`Glob` / `Grep` 工具在 `~/.workbuddy/projects` 上会超时或被拒**，用 `Bash ls` 或 Python `glob`/逐行读代替。
12. **读 SQLite 用只读 URI**：`sqlite3.connect('file:...?mode=ro', uri=True)`，避免锁库。
13. Python 解释器用**管理版**（见上方 `PY`），裸 `python` 可能缺依赖。

## 性能特征（真实库 1480 会话 / 2.4GB 实测）

数值为量级参考，随机器负载浮动：

| 模式 | 耗时量级 | 说明 |
|------|----------|------|
| 日期 / 目录 / 序号列表 | ~0.15s | 只读 db 索引，**与数据量无关** |
| 关键词过滤 | 0.2s 级（100 份）/ 1–2s 级（真实库近 7 天） | 需逐份读 jsonl 全文，**唯一随规模增长的路径** |
| 单任务正文 | ~0.15s | 只读目标一个文件 |
| 5000 条大会话解析 | ~0.25s | 单条消息约 0.05ms |

**资源边界**：关键词模式扫描窗口建议不超过 30 天；更大范围先用 `--cwd`/`--list` 收窄。
单次查询无步数上限（无循环），`--days` 线性增长。

> 若会话量再翻数倍，建议为 jsonl 侧加关键词索引，或限制默认扫描窗口。

## 注意事项

- **只读操作**，不修改任何会话文件。
- 对话全文含隐私内容，输出报告默认落在本机，不外传。
- `conversation_search`（云端历史检索）对当天数据**尚未索引**，查昨天/更早可用，查当天必须用本技能读本地文件。
- 会话标题由 `custom_title` 优先，回退 `title`（AI 自动生成）。
