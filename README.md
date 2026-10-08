# WorkBuddy Task Log Search · workbuddy任务日志查找

**一个用于 WorkBuddy 的技能（显示名 `workbuddy任务日志查找`；`SKILL.md` 的 `name` 为 ASCII slug `workbuddy-task-log-search`）：跨会话检索本机历史任务与对话内容。**

WorkBuddy 的每个会话运行在独立的上下文沙箱里，互相看不见。但每个会话的完整对话都会
**明文落盘**在本地，因此可以被检索。这个技能就是把「我今天都跑了哪些任务」这个问题
变成一条命令。

> 本项目是 **WorkBuddy 技能**（Skill），遵循 WorkBuddy 的 `SKILL.md` 规范。
> 目录根部即技能本体，克隆后放入 WorkBuddy 技能目录即可使用。

---

## 它解决什么问题

WorkBuddy 的会话是隔离的——在 A 会话里无法直接看到 B 会话在做什么。这带来一个实际困扰：

- 「我昨天那个转写任务的结果在哪？」
- 「今天一共开了几个任务？分别是什么？」
- 「之前那个会话最后得出的结论是什么？」

答案是：**这些内容一直都在你的磁盘上**，只是需要一个检索入口。

## 数据从哪来

| 数据 | 位置 | 内容 |
|------|------|------|
| 会话索引 | `~/.workbuddy/workbuddy.db` → `sessions` 表 | id / cwd / title / custom_title / created_at / last_activity_at / model（**默认过滤已删除会话**，`--include-deleted` 可查） |
| 对话全文 | `~/.workbuddy/projects/<工作目录编码>/<会话ID>.jsonl` | 每行一条 JSON，明文，含用户需求与 AI 回复 |
| 运行中进程 | `~/.workbuddy/sessions/<pid>.json` | sessionId / cwd / endpoint |
| 自动化运行 | `workbuddy.db` → `automation_runs` 表 | thread_title / status / created_at |

**工作目录编码规则**：`E:\workspace\my-project` → `e-workspace-my-project`
（替换 `\` `/` 为 `-`，**删除** `:`，去首尾 `-`，转小写）

**jsonl 行类型**：`session-meta` / `message`（role=user\|assistant，正文在 `content[].text`）
/ `reasoning` / `function_call` / `function_call_result` / `ai-title` / `file-history-snapshot`

> 全程**只读**，不修改任何会话文件。只读对话正文（`type == message`），
> 不读工具轨迹（`function_call` / `function_call_result`）——想被检索到的信息，
> 必须写在回复正文里。

---

## 安装

把本目录整体放进 WorkBuddy 技能目录。**目录名可用中文显示名**（如
`workbuddy任务日志查找`），技能实名以 `SKILL.md` 的 `name` 字段为准（必须是
ASCII slug，如 `workbuddy-task-log-search`）：

```
~/.workbuddy/skills/<分类>/<任意目录名>/
├── SKILL.md
├── scripts/
│   └── scan.py
└── tests/
```

也可以直接克隆到技能目录：

```bash
git clone https://github.com/yanglei9491-hue/workbuddy-session-search.git \
          ~/.workbuddy/skills/10-utility/workbuddy任务日志查找
```

## 使用

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
```

### 交互方式（在 WorkBuddy 里说话就能用）

对 WorkBuddy 说「查下对话日志」「查下任务日志」「查下对话」等即可触发。
触发后技能会先问你要查哪个时间范围（当天 / 最近一周 / 最近一个月 / 全部），
再按选择检索；原话里已带时间范围（如「查下今天的对话日志」）则不再追问。

### 参数表

| 参数 | 作用 |
|------|------|
| `--date YYYY-MM-DD` | 指定日期（默认今天） |
| `--days N` | 从指定日往前回溯 N 天（`--days 0` 等价 1 天；与 `--all` 互斥） |
| `--all` | 全部时间（与 `--date/--days` 互斥） |
| `--cwd <关键词>` | 按工作目录过滤 |
| `--keyword <词>` | 按关键词过滤（标题 + 用户消息） |
| `--list` | 只列标题，带编号 |
| `--index N` | 按 `--list` 编号精确命中（复跑须带与 `--list` 相同的时间范围参数） |
| `--id <前缀>` | 按会话 ID 前缀命中（未给日期时全局检索） |
| `--title <词>` | 按标题命中（未给日期时全局检索） |
| `--include-deleted` | 包含已删除的会话 |
| `--all-turns` | 导出全部回复轮次 |
| `--full` | 结论不截断 |
| `--html` | 输出 HTML 报告 |
| `--out <路径>` | 自定义报告输出位置 |
| `--home <目录>` | 指定数据根（**仅用于测试**） |

### 输出格式

- **列表模式**：默认富格式（标题 + 目录列）；结果超过 200 行自动切换**紧凑格式**
  （省略目录列，编号连续不截断，大范围也能完整列出）。
- `--id`/`--title` 与 `--list` 合用时，编号是该会话在**当前时间范围列表中的原始位置**
  （不是 1..N 连号）——这是为了 `--index 同编号` 能原样回取。

---

## 测试与回归

`tests/` 下是可复现的验证资产。设计要点：期望值由**独立参考实现**计算
（直接读 db + jsonl 按规格重算），不复用被测代码，避免「自己考自己」。

| 文件 | 作用 |
|------|------|
| `gen_dataset.py` | 生成 328 份对抗性数据集（重复标题、跨天会话、边界时间戳、中文/特殊字符路径、空会话、系统注入消息、5000 条大会话、已删除会话、远古会话、220 份批量填充） |
| `verify_dataset.py` | 数据集保真度自检（db / jsonl / 真值表三方一致） |
| `run_tests.py` | 穷举测试（86 用例 / 16 维度），支持 `--repeat N` 稳定性验证 |
| `test_bigline.py` | 超大单行 JSON 抗压（50MB 单行；同时是老 schema 缺 `deleted_at` 列时的兼容哨兵） |
| `bench.py` | 性能基准（测试集 + 真实库双场景） |
| `report_gen.py` | 生成 HTML + Markdown 测试报告（版本从 SKILL.md 动态读取） |

```bash
PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe"
T="$HOME/.workbuddy/skills/10-utility/workbuddy任务日志查找/tests"

"$PY" "$T/gen_dataset.py"              # 建数据集（默认输出到桌面）
"$PY" "$T/verify_dataset.py"           # 校验数据集
"$PY" "$T/run_tests.py"                # 全量测试
"$PY" "$T/run_tests.py" --repeat 10    # 稳定性验证（860 次一致性）
"$PY" "$T/run_tests.py" --only 关键词   # 只跑某类用例
"$PY" "$T/test_bigline.py"             # 超大单行抗压
"$PY" "$T/bench.py"                    # 性能基准
"$PY" "$T/report_gen.py"               # 出报告
```

**当前基线**：准确率 **100%（86/86）**；稳定性以 `--repeat 10` 输出为准（860 次零波动）；
列表模式约 0.15s、关键词模式 1–2s（量级参考，随环境浮动）。

## 性能特征

| 模式 | 耗时量级 | 说明 |
|------|----------|------|
| 日期 / 目录 / 序号列表 | ~0.15s | 只读 db 索引，**与数据量无关** |
| 关键词过滤 | 0.2s 级（测试集）/ 1–2s 级（真实库近 7 天） | 需逐份读 jsonl 全文，**唯一随规模增长的路径** |
| 单任务正文 | ~0.15s | 只读目标一个文件 |
| 5000 条大会话解析 | ~0.25s | 单条消息约 0.05ms |
| `--all --list` | ~0.2s | 只读 db 索引，与数据量无关 |
| `--all --keyword` | 约 17–25 秒（全量 jsonl 外推） | 全时间窗 + 关键词是唯一重负载组合，可接受但勿频繁 |

**资源边界**：关键词模式扫描窗口建议不超过 30 天；更大范围先用 `--cwd`/`--list` 收窄，
或直接用 `--all --list`（列表不读全文，无成本）。

**抗压边界**：50MB 单行 JSON 下各模式均为亚秒级响应（实测 4 种模式均 `rc=0`、<1s），
不崩溃；**单条消息**输出被截断保护在 100000 字符（约 100KB，**非全局输出上限**）。
按行读 + 输出截断天然免疫超大单行。

---

## 已知的坑（改代码时勿踩回）

| 级别 | 陷阱 | 正确做法 |
|------|------|----------|
| 高 | `--date` 只过滤下界会让跨天会话串进别的日期（一个会话可从几天前持续到今天） | 必须做双侧区间 `>= lo AND < hi` |
| 高 | 拼 `deleted_at is null` 前不判列存在：老版本库/测试库没有该列会直接崩 | 先 `pragma table_info` 判列再拼条件 |
| 高 | 紧凑格式改动行首 `N. [id8]` 或页脚「共 N 个会话」：测试正则（`RE_LINE`/`RE_TOTAL`）依赖这两个契约 | 两种格式都必须保持行首与页脚文案不变 |
| 中 | 数值参数靠真值判断：`--index 0` 会被 `if args.index:` 静默吞掉，不报错、返回全量、返回码 0 | 一律用 `is not None` |
| 中 | 消息不过滤会混入几周前的提问 | 按日期区间过滤每条消息（`--all` 的 lo=0/hi=2^63-1 对该判断等价于不过滤） |
| 中 | 系统注入消息不是用户需求，会让条数虚高 | 剔除 `<system-reminder>` / `<teammate-message>` / `<task-notification>` 等 |
| 中 | 关键词只看标题会漏（关键词常只在对话正文里） | 标题 + 正文一起匹配 |
| 低 | 非法日期直接抛 `ValueError`，用户看到 traceback 不知错在哪 | 捕获后输出中文提示 |
| 低 | `--days` 默认值用 0 无法区分「用户没给时间参数」与「给了 0」 | 默认值用 `None`；`--days 0` 与不给都等价 1 天 |

---

## 适用范围与限制

- **仅适用于本机 WorkBuddy 数据**。依赖 `~/.workbuddy/` 下的会话索引与 jsonl 结构；
  WorkBuddy 版本升级若改变存储格式，需同步调整。`bench.py` 的「真实库」用例使用
  示意会话 ID（`a1b2c3d4`），在他人机器上会如预期报未命中（ERR）——这是占位符，
  不是缺陷。
- **不适用于云端历史检索**。`conversation_search` 类云端检索对当天数据尚未索引；
  查当天必须读本地文件。
- **不修改任何数据**。全程只读；已删除会话默认不出现，`--include-deleted` 才会纳入。
- **对话全文含隐私内容**，生成的报告默认落在本机，请注意分享范围；本仓库的示例数据
  均为示意值。
- **不适用于非 WorkBuddy 的检索**。本技能只处理「本机 WorkBuddy 会话记录」这**一类**数据：
  不检索微信文章 / 网页 / 普通文件内容，不做通用网络搜索；这类请求请交给对应的搜索或
  文件检索技能。也不读工具调用轨迹（`function_call` / `function_call_result`），
  只想找回命令回显请直接读 `~/.workbuddy/projects/**/*.jsonl`。

## 版本与变更

| 版本 | 变更 |
|------|------|
| **2.1.0** | 更名 `workbuddy任务日志查找`（`name` 改为 ASCII slug `workbuddy-task-log-search`）；**固化输出编码**（`sys.stdout/stderr.reconfigure(encoding='utf-8', errors='replace')`），修复 GBK 控制台下遇非 GBK 字符（如标题含 emoji）抛 `UnicodeEncodeError` 的问题；补 `LICENSE` 文件；补「不适用场景」负向触发声明；修正 `--index` 标题行文档与实际输出不一致；`tests/` 运行时产物改为不入发布包（`.gitignore`）；`bench.py` 移除硬编码真实会话 ID（改示意值 `a1b2c3d4` + `BENCH_SESSION_ID` 环境变量） |
| 2.0.0 | 时间范围交互化 + 三项行为升级；更名 `workbuddy会话查找` |
| 1.0.0 | 首版 |

**环境依赖**：① 命令块中的 `PY` 硬编码管理版 Python（`~/.workbuddy/binaries/python/versions/3.13.12/python.exe`），换 WorkBuddy / Python 版本后需替换为当前管理版路径；② `--html` 默认输出到 `~/Desktop`（假定桌面目录名为英文 `Desktop`），若系统桌面为本地化名称请用 `--out` 显式指定。

## 许可证

MIT License，见 [LICENSE](LICENSE)。
