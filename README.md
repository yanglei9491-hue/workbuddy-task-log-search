# WorkBuddy Session Search

**一个用于 WorkBuddy 的技能：跨会话检索本机历史任务与对话内容。**

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
| 会话索引 | `~/.workbuddy/workbuddy.db` → `sessions` 表 | id / cwd / title / created_at / last_activity_at / model |
| 对话全文 | `~/.workbuddy/projects/<工作目录编码>/<会话ID>.jsonl` | 每行一条 JSON，明文，含用户需求与 AI 回复 |
| 运行中进程 | `~/.workbuddy/sessions/<pid>.json` | sessionId / cwd / endpoint |
| 自动化运行 | `workbuddy.db` → `automation_runs` 表 | thread_title / status / created_at |

**工作目录编码规则**：`E:\workspace\my-project` → `e-workspace-my-project`
（替换 `\` `/` `:` 为 `-`，去首尾 `-`，转小写）

**jsonl 行类型**：`session-meta` / `message`（role=user\|assistant，正文在 `content[].text`）
/ `reasoning` / `ai-title` / `file-history-snapshot`

> 全程**只读**，不修改任何会话文件。

---

## 安装

把本目录整体放进 WorkBuddy 技能目录：

```
~/.workbuddy/skills/<分类>/session-search/
├── SKILL.md
├── scripts/
│   └── scan.py
└── tests/
```

也可以直接克隆到技能目录：

```bash
git clone https://github.com/yanglei9491-hue/workbuddy-session-search.git \
          ~/.workbuddy/skills/10-utility/session-search
```

## 使用

```bash
PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SCAN="$HOME/.workbuddy/skills/10-utility/session-search/scripts/scan.py"

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
```

### 参数表

| 参数 | 作用 |
|------|------|
| `--date YYYY-MM-DD` | 指定日期（默认今天） |
| `--days N` | 从指定日往前回溯 N 天 |
| `--cwd <关键词>` | 按工作目录过滤 |
| `--keyword <词>` | 按关键词过滤（标题 + 用户消息） |
| `--list` | 只列标题，带编号 |
| `--index N` | 按 `--list` 编号精确命中 |
| `--id <前缀>` | 按会话 ID 前缀命中 |
| `--title <词>` | 按标题命中 |
| `--all-turns` | 导出全部回复轮次 |
| `--full` | 结论不截断 |
| `--html` | 输出 HTML 报告 |
| `--out <路径>` | 自定义报告输出位置 |
| `--home <目录>` | 指定数据根（**仅用于测试**） |

---

## 测试与回归

`tests/` 下是可复现的验证资产。设计要点：期望值由**独立参考实现**计算
（直接读 db + jsonl 按规格重算），不复用被测代码，避免「自己考自己」。

| 文件 | 作用 |
|------|------|
| `gen_dataset.py` | 生成 100 份对抗性数据集（含重复标题、跨天会话、边界时间戳、中文/特殊字符路径、空会话、系统注入消息、5000 条大会话等） |
| `verify_dataset.py` | 数据集保真度自检（db / jsonl / 真值表三方一致） |
| `run_tests.py` | 穷举测试（73 用例 / 12 维度），支持 `--repeat N` 稳定性验证 |
| `test_bigline.py` | 超大单行 JSON 抗压（50MB 单行） |
| `bench.py` | 性能基准（测试集 + 真实库双场景） |
| `report_gen.py` | 生成 HTML + Markdown 测试报告 |

```bash
PY="$HOME/.workbuddy/binaries/python/versions/3.13.12/python.exe"
T="$HOME/.workbuddy/skills/10-utility/session-search/tests"

"$PY" "$T/gen_dataset.py"              # 建数据集（默认输出到桌面）
"$PY" "$T/verify_dataset.py"           # 校验数据集
"$PY" "$T/run_tests.py"                # 全量测试
"$PY" "$T/run_tests.py" --repeat 10    # 稳定性验证（730 次一致性）
"$PY" "$T/run_tests.py" --only 关键词   # 只跑某类用例
"$PY" "$T/test_bigline.py"             # 超大单行抗压
"$PY" "$T/bench.py"                    # 性能基准
"$PY" "$T/report_gen.py"               # 出报告
```

**当前基线**：准确率 **100%（73/73）**；稳定性以 `--repeat 10` 输出为准（730 次零波动）；
列表模式约 0.15s、关键词模式 1–2s（量级参考，随环境浮动）。

## 性能特征

| 模式 | 耗时量级 | 说明 |
|------|----------|------|
| 日期 / 目录 / 序号列表 | ~0.15s | 只读 db 索引，**与数据量无关** |
| 关键词过滤 | 0.2s 级（100 份）/ 1–2s 级（真实库近 7 天） | 需逐份读 jsonl 全文，**唯一随规模增长的路径** |
| 单任务正文 | ~0.15s | 只读目标一个文件 |
| 5000 条大会话解析 | ~0.25s | 单条消息约 0.05ms |

**资源边界**：关键词模式扫描窗口建议不超过 30 天；更大范围先用 `--cwd` / `--list` 收窄。

**抗压边界**：50MB 单行 JSON 下各模式均为亚秒级响应，不崩溃、输出被截断保护在 100KB。
按行读 + 输出截断天然免疫超大单行。

---

## 已知的坑（改代码时勿踩回）

| 级别 | 陷阱 | 正确做法 |
|------|------|----------|
| 高 | `--date` 只过滤下界会让跨天会话串进别的日期（一个会话可从几天前持续到今天） | 必须做双侧区间 `>= lo AND < hi` |
| 高 | 数值参数靠真值判断：`--index 0` 会被 `if args.index:` 静默吞掉，不报错、返回全量、返回码 0 | 一律用 `is not None` |
| 中 | 消息不过滤会混入几周前的提问 | 按日期区间过滤每条消息 |
| 中 | 系统注入消息不是用户需求，会让条数虚高 | 剔除 `<system-reminder>` / `<teammate-message>` / `<task-notification>` 等 |
| 中 | 关键词只看标题会漏（关键词常只在对话正文里） | 标题 + 正文一起匹配 |
| 低 | 非法日期直接抛 `ValueError`，用户看到 traceback 不知错在哪 | 捕获后输出中文提示 |

---

## 适用范围与限制

- **仅适用于本机 WorkBuddy 数据**。依赖 `~/.workbuddy/` 下的会话索引与 jsonl 结构；
  WorkBuddy 版本升级若改变存储格式，需同步调整。
- **不适用于云端历史检索**。`conversation_search` 类云端检索对当天数据尚未索引；
  查当天必须读本地文件。
- **不修改任何数据**。全程只读。
- **对话全文含隐私内容**，生成的报告默认落在本机，请注意分享范围。

## 许可证

MIT License，见 [LICENSE](LICENSE)。
