---
name: workbuddy-task-log-search
displayName: workbuddy任务日志查找
description: 跨会话检索本机 WorkBuddy 的历史任务与对话内容。从本地会话索引库（~/.workbuddy/workbuddy.db 的 sessions 表，默认过滤已删除会话）列出用户选定时间范围（当天/最近一周/最近一个月/全部）的全部任务，再逐个读取对话全文（~/.workbuddy/projects/<工作目录编码>/<会话ID>.jsonl），提取用户需求原文与最终结论，输出清单、详情或 HTML 报告。支持按序号、会话 ID、标题精确命中单个任务（ID/标题未指定日期时默认可全局检索），并可导出该任务全部回复轮次。触发场景：查我今天的任务、查下对话日志、查下任务日志、查下对话、今天做了什么、找某天的任务、跨会话、之前那个会话讲了什么、会话记录、对话日志、任务清单、精确查找某个任务。不适用：本技能只读本机 WorkBuddy 会话记录，不检索微信文章/网页/普通文件内容，不做通用网络搜索，也不读取工具调用轨迹（只读对话正文）；此类请求请勿使用本技能。
version: 2.1.0
license: MIT
compatibility: "WorkBuddy >= 1.0"
allowed-tools: [Read, Write, Bash, AskUserQuestion]
metadata:
  category: 10-utility
  agent_created: true
---

# workbuddy任务日志查找

解决「跨会话内容看不到」的问题——运行时会话互相隔离，但每个会话的完整对话都**明文落盘**，所以可以按日期/目录检索出历史任务的真实内容。

## 数据位置（核心事实）

| 数据 | 路径 | 内容 |
|------|------|------|
| 会话索引 | `~/.workbuddy/workbuddy.db` → `sessions` 表 | id / cwd / title / custom_title / created_at / last_activity_at / model（默认过滤 `deleted_at` 非空的会话） |
| 对话全文 | `~/.workbuddy/projects/<工作目录编码>/<会话ID>.jsonl` | 每行一条 JSON 记录，明文 |
| 运行中进程 | `~/.workbuddy/sessions/<pid>.json` | sessionId / cwd / endpoint |
| 自动化运行 | `workbuddy.db` → `automation_runs` 表 | thread_title / status / created_at |

**工作目录编码规则**：`E:\workspace\my-project` → `e-workspace-my-project`
（替换 `\` `/` 为 `-`，**删除** `:`，去首尾 `-`，转小写）

**jsonl 行类型**：`session-meta` / `message`（role=user\|assistant，正文在 `content[].text`）/ `reasoning` / `function_call` / `function_call_result` / `ai-title` / `file-history-snapshot`

**★ 只读对话正文，不读工具轨迹（回答"默认读多少"）**：`scan.py:110` 是 `if o.get('type') != 'message': continue` —— **刻意跳过** `function_call` / `function_call_result`。实测单会话行数分布（636KB 样本）：`function_call` 44 / `function_call_result` 42 / `message` 仅 7 → 工具轨迹可占行数与体积的 80%+，但**一律不读**。后果：
- 写在**正文里**的信息（结论、路径、清单、结论表格）→ **能检索到**
- 只存在于**工具输出**里、正文未复述的信息（如 `ls` 原始回显、报错堆栈）→ **检索不到**
- 想让它能被检索，就得在回复正文里**复述**一次（这也是"产出物清单要写进正文"的实际价值）

## 不适用场景（负向触发 · 别用错技能）

| 用户诉求 | 是否用本技能 | 应该用什么 |
|----------|--------------|------------|
| 查本机 WorkBuddy 的历史任务 / 对话 / 任务日志 | ✅ 用 | 本技能 |
| 搜微信公众号文章、网页、新闻 | ❌ 不用 | 微信搜索 / 网络搜索类技能 |
| 在本机文件系统里找某个文件或文件内容 | ❌ 不用 | 文件检索（Glob / Grep / `ls`） |
| 查云端已索引的历史会话（昨天及更早） | ⚠️ 可用但非必需 | `conversation_search`（当天数据未索引，**查当天必须用本技能**） |
| 想找回**工具调用 / 命令回显**里的原始输出 | ❌ 做不到 | 直接读 `~/.workbuddy/projects/**/*.jsonl`；本技能刻意跳过工具轨迹 |

**判定口诀**：只处理「本机 WorkBuddy 会话记录」这**一类**数据；一旦跨到微信 / 网页 / 普通文件 / 网络搜索，一律不接。

## 执行命令

```bash
PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SCAN="$HOME/.workbuddy/skills/10-utility/workbuddy任务日志查找/scripts/scan.py"

# ---- 浏览 ----
"$PY" "$SCAN"                          # 今天的任务（裸跑仅为 CLI 兼容）
"$PY" "$SCAN" --date 2026-09-28        # 指定某天
"$PY" "$SCAN" --days 3                 # 最近 3 天
"$PY" "$SCAN" --all                    # 全部时间（与 --date/--days 互斥）
"$PY" "$SCAN" --list                   # 只列标题（带编号，快）
"$PY" "$SCAN" --cwd 数据流水线          # 只看某个工作空间
"$PY" "$SCAN" --keyword 报表            # 关键词过滤（标题 或 用户消息命中）
"$PY" "$SCAN" --include-deleted        # 包含已删除的会话（默认只保留未删除）
"$PY" "$SCAN" --html                   # 额外输出 HTML 报告到桌面

# ---- 精确命中单个任务（三选一）----
"$PY" "$SCAN" --index 3                # 按 --list 的编号
"$PY" "$SCAN" --id a1b2c3d4            # 按会话 ID 前缀（未给日期时全局检索）
"$PY" "$SCAN" --title 报表              # 按标题关键词（未给日期时全局检索）

# ---- 深度导出 ----
"$PY" "$SCAN" --index 3 --all-turns    # 该任务全部回复轮次
"$PY" "$SCAN" --index 3 --full         # 结论不截断
"$PY" "$SCAN" --html --out <路径>       # 自定义 HTML 报告输出位置

# ---- 隔离测试（仅测试用，日常查询不要带）----
"$PY" "$SCAN" --home <数据根目录>       # 指定数据根，默认 ~/.workbuddy
```

## 交互工作流（用户说"查下对话日志 / 查下任务日志 / 查下对话"等时）

1. **先看用户原话是否已含时间范围**（今天/当天、最近一周、这个月/最近一个月、全部/所有）：
   - 已含 → 直接按下方映射表执行，不再提问。
   - 未含 → 用 AskUserQuestion 提问（单选）：
     - header：时间范围
     - question：要查哪个时间范围的对话/任务日志？
     - 选项：
       1. 当天（Recommended）—— 今天 00:00 至今的会话
       2. 最近一周 —— 含今天往前 7 天
       3. 最近一个月 —— 含今天往前 30 天
       4. 全部 —— 本机全部历史会话（结果多时自动用紧凑格式全量列出）

   **Based on user choice:**
   - 当天 → `--list`（详情复跑用裸 `--index N`）
   - 最近一周 → `--days 7 --list`（详情复跑 `--days 7 --index N`）
   - 最近一个月 → `--days 30 --list`（详情复跑 `--days 30 --index N`）
   - 全部 → `--all --list`（详情复跑 `--all --index N`）

2. 把编号清单**原样呈现**给用户（大范围不截断、不概括、不抽样）。

3. 用户报编号后，**带与上一步完全相同的时间范围参数**跑 `--index N`，输出需求原文 + 最终结论。

4. 结果多时提示收窄手段：`--keyword` / `--cwd`；用户要报告时加 `--html`。

> `--id`/`--title` 与 `--list` 合用时，编号是该会话在**当前时间范围列表中的原始位置**（不是 1..N 连号）——这是为了 `--index 同编号` 能原样回取；想要连号小列表就先 `--list` 全览再 `--index N`。

## 测试与回归

`tests/` 下是可复现的暴力测试资产：

| 文件 | 作用 |
|------|------|
| `tests/gen_dataset.py` | 生成 328 份对抗性数据集到桌面「测试数据集」 |
| `tests/verify_dataset.py` | 数据集保真度自检（db/jsonl/真值表三方一致） |
| `tests/run_tests.py` | 穷举测试（86 用例 / 16 维度），含稳定性重复执行 |
| `tests/test_bigline.py` | 超大单行 JSON 抗压验证（50MB 单行） |
| `tests/bench.py` | 性能基准（测试集 328 份 + 真实库双场景） |
| `tests/report_gen.py` | 生成 HTML + Markdown 测试报告 |

运行时产物（脚本自动生成，**不入发布包**）：

| 文件 | 由谁生成 | 说明 |
|------|----------|------|
| `tests/test_result.json` | `run_tests.py` | 每次运行覆盖，含本机耗时/会话数等**机器特定**数据 |
| `tests/perf_result.json` | `bench.py` | 同上 |

这两个 JSON 不是手工维护的资产，**勿作为权威数据引用**；发布前请删除（已在 `.gitignore` 中忽略）。

```bash
PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe"
T="$HOME/.workbuddy/skills/10-utility/workbuddy任务日志查找/tests"

"$PY" "$T/gen_dataset.py"              # 建数据集（输出到桌面）
"$PY" "$T/verify_dataset.py"           # 校验数据集
"$PY" "$T/run_tests.py"                # 全量测试
"$PY" "$T/run_tests.py" --repeat 10    # 稳定性验证（输出 860 次一致性）
"$PY" "$T/run_tests.py" --only 关键词   # 只跑某类用例
"$PY" "$T/test_bigline.py"             # 超大单行抗压
"$PY" "$T/bench.py"                    # 性能基准
"$PY" "$T/report_gen.py"               # 出报告
```

**回归基线（改动后不得低于）**：准确率 100%（86/86）；稳定性以 `--repeat 10` 输出为准
（860 次零波动）；列表模式约 0.15s、关键词模式 1–2s（随环境浮动，量级参考）。

**输入陷阱护栏（改代码时勿踩回）**

| 级别 | 陷阱 | 正确做法 |
|------|------|----------|
| P2 | `--index 0` 会被 `if args.index:` 的 falsy 判断静默忽略，返回全量且 rc=0 | 数值参数一律用 `is not None` 判断 |
| P3 | 非法日期直接抛 `ValueError`，用户看到 traceback 不知错在哪 | 捕获后输出「日期格式不正确…应为 YYYY-MM-DD」 |

**抗压边界**：50MB 单行 JSON（真实库最大约 60MB 级）下各模式均为亚秒级响应，不崩溃、
输出被截断保护在 100KB。按行读 + 输出截断天然免疫超大单行，无需额外守卫。

## 输出结构

**列表模式**（`--list`）每行一条，带序号便于 `--index` 直取（默认富格式，含目录列）：

```
 1. [a1b2c3d4] 修复登录超时问题               | E:/workspace/2026-09-08-13-26-55
 2. [e5f6a7b8] 整理季度报表脚本               | E:/workspace/data-tools

共 2 个会话
提示：用 --index N 直取第 N 个任务的完整内容
```

**紧凑格式**（结果超过 200 行时自动切换，省略目录列，保全量输出不截断）：

```
 318. [c0de0148] 批量填充 318
 319. [c0de0149] 批量填充 319
 320. [c0de014a] 批量填充 320

共 320 个会话
（结果较多，已切换紧凑格式：省略目录列；完整目录/正文用 --index N 查看）
```

**详情模式**（默认浏览，或 `--index`/`--id`/`--title` 精确命中）。标题行分两种，判定依据是
是否给了「精确定位参数」——`--index`、`--id`、`--title` **任给其一**即视为精确命中：

- 给了任一（精确命中）→ `精确命中  #N  <会话标题>`
- 三者都未给（默认浏览）→ `## N. <会话标题>`

字段为独立行：

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
14. **`--id`/`--title` 未显式给 `--date`/`--days`/`--all` 时默认全局检索**（修掉"精确命中只查当天"的坑）；`--index` 是例外——它绑定当次 `--list` 的编号，复跑必须带与 `--list` 相同的时间范围参数，否则编号对不上。
15. **默认过滤已删除会话**：DB 查询默认拼 `deleted_at is null`，`--include-deleted` 去掉该条件；过滤条件先用 `pragma table_info` 判列存在再拼（老版本库/测试库可能没有该列，直接写 SQL 会崩）。
16. **`--all` = 全时间窗**（lo=0 / hi=2^63-1）：`collect()` 的消息级窗口判断对该区间等价于不过滤；SQL 侧不拼时间条件。`--all` 与 `--date`/`--days` 互斥，同时给出报错退出。
17. **`--days` 默认值是 `None` 而非 0**：None 表示"用户没给时间参数"（供 id/title 判定是否走全局）；`--days 0` 与不给都等价 1 天，既有契约不变。
18. **紧凑格式契约**：列表超 200 行切换紧凑格式（省略目录列）。行首 `N. [id8]` 与页脚 `共 N 个会话` 是测试正则（`RE_LINE`/`RE_TOTAL`）的依赖，改动会使 86 用例比对失效。
19. **行号引用会漂移**：本文件中引用 `scan.py:NNN` 处，改码后必须按最终行号校准。

## 性能特征（真实库 1493 会话 / 2.4GB 实测）

数值为量级参考，随机器负载浮动：

| 模式 | 耗时量级 | 说明 |
|------|----------|------|
| 日期 / 目录 / 序号列表 | ~0.15s | 只读 db 索引，**与数据量无关** |
| 关键词过滤 | 0.2s 级（测试集）/ 1–2s 级（真实库近 7 天） | 需逐份读 jsonl 全文，**唯一随规模增长的路径** |
| 单任务正文 | ~0.15s | 只读目标一个文件 |
| 5000 条大会话解析 | ~0.25s | 单条消息约 0.05ms |
| `--all --list` | ~0.2s | 只读 db 索引，与数据量无关 |
| `--all --keyword` | 约 17–25 秒（全量 2468 份 jsonl / 2.37GB 外推） | 全时间窗 + 关键词是唯一重负载组合，可接受但勿频繁 |
| `--all --html` | 数十秒且报告巨大 | 会读取全部会话正文，慎用；建议先 `--keyword`/`--cwd` 收窄 |

**时间窗口口径**：裸跑（无任何时间参数）= 今天，仅为 CLI 兼容；技能工作流一律显式传参。
`--all` = 全部时间、`--date` 指定某天、`--days N` 往前回溯 N 天（含当天）。

**资源边界**：关键词模式扫描窗口建议不超过 30 天；更大范围先用 `--cwd`/`--list` 收窄，
或直接用 `--all --list`（列表不读全文，无成本）。
单次查询无步数上限（无循环），`--days` 线性增长。

> 若会话量再翻数倍，建议为 jsonl 侧加关键词索引，或限制默认扫描窗口。

## 注意事项

- **只读操作**，不修改任何会话文件。
- 对话全文含隐私内容，输出报告默认落在本机，不外传。
- 已删除会话默认不出现；确需查（如找回误删任务）加 `--include-deleted`。
- `--index N` 的 N 只在"同一次时间范围"内有效；用户换了范围问"第 3 个"，必须用新范围重跑 `--list`。
- 紧凑格式是为"大范围全量列出"设计的：编号连续、不截断；只看编号选任务即可，目录信息用 `--index N` 补看。
- `--all --html` 会读全部正文（数十秒、产出超大 HTML），非必要不用。
- `conversation_search`（云端历史检索）对当天数据**尚未索引**，查昨天/更早可用，查当天必须用本技能读本地文件。
- 会话标题由 `custom_title` 优先，回退 `title`（AI 自动生成）。
- **环境依赖 1 · 解释器路径**：命令块里的 `PY` 硬编码管理版 Python（`~/.workbuddy/binaries/python/versions/3.13.12/python.exe`）。换 WorkBuddy 版本或 Python 版本后该路径会失效，需替换为当前管理版路径（`ls ~/.workbuddy/binaries/python/versions/` 可查看；用裸 `python` 可能缺依赖）。
- **环境依赖 2 · 桌面路径**：`--html` 默认输出到 `os.path.join(os.path.expanduser('~'), 'Desktop')`，即假定桌面目录名为英文 `Desktop`（Windows 默认如此）。若系统把桌面本地化为中文名，请用 `--out <路径>` 显式指定。
- **环境依赖 3 · 输出编码**：`scan.py` 启动时会调用 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 固化输出编码，避免 GBK 控制台下遇到非 GBK 字符（如标题含 emoji）抛 `UnicodeEncodeError`。`errors='replace'` 保证不崩，但极少数不可编码字符会显示为替换符。
