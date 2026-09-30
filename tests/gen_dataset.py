# -*- coding: utf-8 -*-
"""构造 328 份对抗性测试数据集，用于暴力测试「workbuddy会话查找」技能。

输出到桌面「测试数据集」文件夹，结构模拟真实 ~/.workbuddy：
    测试数据集/
    ├── workbuddy.db           # sessions 表，328 条记录
    ├── projects/<cwd编码>/<会话ID>.jsonl
    ├── _ground_truth.json     # 真值表（期望结果的唯一依据）
    └── README.md

覆盖的对抗场景：
  · 重复标题（10 份同名）
  · 跨天会话（created 一天、last_activity 另一天）
  · 边界时间戳 00:00:00.000 / 23:59:59.999
  · 中文路径 / 特殊字符路径 / 大小写混合路径
  · 空会话（无 message）/ 仅系统注入消息 / 仅 user 无 assistant
  · 重复用户消息（测去重）
  · 关键词仅命中正文、仅命中标题、命中系统消息、越界消息命中
  · 共享 8 位前缀的会话 ID
  · 1 份超大会话（5000 条消息）用于性能压测
  · 已删除会话 6 份（测 deleted_at 默认过滤与 --include-deleted 兜底）
  · 远古会话 2 份（落在 2026-09-20，任何日期窗口之外，测 --all 与窗口区分）
  · 批量填充 220 份（只落 d25-d28，把 5 日窗口推到 320 行触发紧凑格式）

用法：
    python gen_dataset.py [输出目录]
"""
import datetime
import json
import os
import shutil
import sqlite3
import sys
import uuid

DESKTOP = os.path.join(os.path.expanduser('~'), 'Desktop')
DEFAULT_OUT = os.path.join(DESKTOP, '测试数据集')

# 五个基准日期
D = {
    'd25': datetime.date(2026, 9, 25),
    'd26': datetime.date(2026, 9, 26),
    'd27': datetime.date(2026, 9, 27),
    'd28': datetime.date(2026, 9, 28),
    'd29': datetime.date(2026, 9, 29),
}

# 工作目录池（含中文、大小写、特殊字符，覆盖路径编码边界）
CWDS = [
    'E:/workspace/quality-test',
    'E:/workspace/数据流水线',
    'E:/workspace/通知服务',
    'E:\\workspace\\视频尺寸转换',
    'e:/workspace/UPPER-case-path',
    'E:/workspace/含特殊字符-（测试）#1',
    'E:/workspace/2026-09-28-10-08-54',
    'E:/workspace/cad-project',
]

# 重复标题（10 份共用）
DUP_TITLE = '重复任务名-数据清洗'
# 关键词标记
KW_TITLE = '会议纪要'          # 只在标题出现
KW_BODY = '量子纠缠'          # 只在正文出现
KW_BOTH = '脱敏'             # 标题与正文都有
KW_NONE = '不存在的关键词XYZ'  # 谁都没有
KW_SYSTEM = '渗透测试'        # 只在系统注入消息里出现
KW_OUTOFRANGE = '史前消息'     # 只在区间外的消息里出现


def ts(d, hh=10, mm=0, ss=0, ms=0):
    return int(datetime.datetime(d.year, d.month, d.day, hh, mm, ss,
                                 ms * 1000).timestamp() * 1000)


def encode_cwd(p):
    p = p.replace(chr(92), '-').replace('/', '-').replace(':', '')
    return p.strip('-').lower()


def msg(mid, off, role, text):
    return {
        'id': mid,
        'timestamp': off,
        'type': 'message',
        'role': role,
        'content': [{'type': 'input_text' if role == 'user' else 'text',
                     'text': text}],
    }


def build_specs():
    """返回 328 份会话规格（确定性）。"""
    specs = []
    n = 0

    def add(cwd, title, custom, created, last, msgs, note='', deleted=False,
            sid=None):
        nonlocal n
        n += 1
        # 前 8 位唯一且可读，便于比对与人工核对（不用 uuid.UUID(int=n)，
        # 那会让小 n 的 id8 全为 00000000，丧失区分度）
        sid = sid or ('%08x-0000-4000-8000-%012x' % (0xc0de0000 + n, n))
        specs.append({
            'seq': n,
            'id': sid,
            'cwd': cwd,
            'title': title,
            'custom_title': custom,
            'created_at': created,
            'last_activity_at': last,
            'deleted_at': (last + 60000) if deleted else None,
            'msgs': msgs,
            'note': note,
        })

    # ---- ① 常规会话 49 份：分布在 5 天 ----
    days = ['d25', 'd26', 'd27', 'd28', 'd29']
    for i in range(49):
        dd = days[i % 5]
        d = D[dd]
        cwd = CWDS[i % len(CWDS)]
        base = (i + 1) * 7
        msgs = [
            msg('m1', ts(d, 9, 0) + base, 'user', '常规需求 %d：处理第 %d 批数据' % (i, i)),
            msg('m2', ts(d, 9, 1) + base, 'assistant', '已处理第 %d 批，用时 %d 秒' % (i, base)),
            {
                'id': 'meta1', 'timestamp': ts(d, 9, 0), 'type': 'session-meta',
                'sessionId': '', 'meta': {},
            },
            {
                'id': 'ttl1', 'timestamp': ts(d, 9, 0), 'type': 'ai-title',
                'aiTitle': '自动标题 %d' % i,
            },
        ]
        add(cwd, '常规任务 %d' % i, None, ts(d, 9, 0), ts(d, 9, 5) + base, msgs,
            '常规')

    # ---- ② 重复标题 10 份（跨 cwd、跨天）----
    for i in range(10):
        dd = days[i % 5]
        d = D[dd]
        cwd = CWDS[i % len(CWDS)]
        msgs = [
            msg('m1', ts(d, 14, 0) + i, 'user', '重复标题任务第 %d 次执行' % i),
            msg('m2', ts(d, 14, 1) + i, 'assistant', '第 %d 次完成' % i),
        ]
        add(cwd, '重复任务 %d' % i, DUP_TITLE, ts(d, 14, 0), ts(d, 14, 2) + i,
            msgs, '重复标题')

    # ---- ③ 跨天会话 5 份：created 在 D4，last_activity 在 D5 ----
    for i in range(5):
        cwd = CWDS[i % len(CWDS)]
        msgs = [
            msg('m1', ts(D['d28'], 21, 0) + i, 'user', '跨天任务起于 09-28'),
            msg('m2', ts(D['d29'], 8, 0) + i, 'assistant', '跨天任务完成于 09-29'),
        ]
        add(cwd, '跨天任务 %d' % i, None, ts(D['d28'], 21, 0),
            ts(D['d29'], 8, 1) + i, msgs, '跨天：应归 09-29')

    # ---- ④ 边界时间戳 6 份 ----
    for i in range(3):
        cwd = CWDS[i % len(CWDS)]
        d = D['d27']
        msgs = [msg('m1', ts(d, 0, 0, 0, 0) + i, 'user', '零点整任务 %d' % i)]
        add(cwd, '零点任务 %d' % i, None, ts(d, 0, 0, 0, 0),
            ts(d, 0, 0, 0, 0) + i, msgs, '边界 00:00:00.000')
    for i in range(3):
        cwd = CWDS[i % len(CWDS)]
        d = D['d27']
        msgs = [msg('m1', ts(d, 23, 59, 59, 999) - i, 'user', '末刻任务 %d' % i)]
        add(cwd, '末刻任务 %d' % i, None, ts(d, 23, 59, 59, 999) - i,
            ts(d, 23, 59, 59, 999) - i, msgs, '边界 23:59:59.999')

    # ---- ⑤ 空会话 5 份（无 message 行）----
    for i in range(5):
        cwd = CWDS[i % len(CWDS)]
        d = D['d26']
        msgs = [
            {'id': 'meta', 'timestamp': ts(d, 11, 0) + i, 'type': 'session-meta',
             'sessionId': '', 'meta': {}},
            {'id': 'ttl', 'timestamp': ts(d, 11, 0), 'type': 'ai-title',
             'aiTitle': '空会话 %d' % i},
        ]
        add(cwd, '空会话 %d' % i, None, ts(d, 11, 0), ts(d, 11, 0) + i, msgs,
            '无消息：查询应查不到')

    # ---- ⑥ 仅系统注入消息 5 份 ----
    for i in range(5):
        cwd = CWDS[i % len(CWDS)]
        d = D['d26']
        msgs = [
            msg('m1', ts(d, 12, 0) + i, 'user',
                '<teammate-message teammate_id="x">渗透测试 汇报</teammate-message>'),
            msg('m2', ts(d, 12, 1) + i, 'user',
                'You are now in Agent mode. Continue with the task.'),
            msg('m3', ts(d, 12, 2) + i, 'user',
                '<task-notification>渗透测试 completed</task-notification>'),
        ]
        add(cwd, '系统消息会话 %d' % i, None, ts(d, 12, 0), ts(d, 12, 2) + i,
            msgs, '仅系统消息：应过滤，查询查不到')

    # ---- ⑦ 仅 user 无 assistant 4 份 ----
    for i in range(4):
        cwd = CWDS[i % len(CWDS)]
        d = D['d25']
        msgs = [msg('m1', ts(d, 15, 0) + i, 'user', '只有提问没有回答 %d' % i)]
        add(cwd, '仅提问 %d' % i, None, ts(d, 15, 0), ts(d, 15, 0) + i, msgs,
            '仅 user')

    # ---- ⑧ 重复用户消息去重 3 份 ----
    for i in range(3):
        cwd = CWDS[i % len(CWDS)]
        d = D['d28']
        dup_txt = '重复消息内容 %d' % i
        msgs = [
            msg('m1', ts(d, 13, 0) + i, 'user', dup_txt),
            msg('m2', ts(d, 13, 1) + i, 'user', dup_txt),
            msg('m3', ts(d, 13, 2) + i, 'user', dup_txt),
            msg('m4', ts(d, 13, 3) + i, 'assistant', '收到'),
        ]
        add(cwd, '重复消息 %d' % i, None, ts(d, 13, 0), ts(d, 13, 3) + i, msgs,
            '同一文本重复 3 次：应去重为 1')

    # ---- ⑨ 关键词分布 10 份 ----
    # 标题含 KW_TITLE
    for i in range(2):
        cwd = CWDS[i]
        d = D['d28']
        msgs = [msg('m1', ts(d, 16, 0) + i, 'user', '请转写这段录音')]
        add(cwd, '%s任务 %d' % (KW_TITLE, i), None, ts(d, 16, 0),
            ts(d, 16, 0) + i, msgs, '标题含关键词')
    # 正文含 KW_BODY（标题不含）
    for i in range(2):
        cwd = CWDS[i + 2]
        d = D['d28']
        msgs = [msg('m1', ts(d, 16, 10) + i, 'user', '帮我查%s的资料' % KW_BODY)]
        add(cwd, '普通查询 %d' % i, None, ts(d, 16, 10), ts(d, 16, 10) + i, msgs,
            '正文含关键词')
    # 标题+正文都含 KW_BOTH
    for i in range(2):
        cwd = CWDS[i + 4]
        d = D['d28']
        msgs = [msg('m1', ts(d, 16, 20) + i, 'user', '执行%s流程' % KW_BOTH)]
        add(cwd, '%s工作台 %d' % (KW_BOTH, i), None, ts(d, 16, 20),
            ts(d, 16, 20) + i, msgs, '标题+正文都含')
    # 都不含
    for i in range(2):
        cwd = CWDS[i + 6]
        d = D['d28']
        msgs = [msg('m1', ts(d, 16, 30) + i, 'user', '普通任务内容')]
        add(cwd, '无关键词任务 %d' % i, None, ts(d, 16, 30), ts(d, 16, 30) + i,
            msgs, '不含关键词')
    # 只在区间外消息含 KW_OUTOFRANGE（会话 last_activity 在 d28，但该消息在 d20）
    for i in range(2):
        cwd = CWDS[i]
        d = D['d28']
        old = datetime.date(2026, 9, 20)
        msgs = [
            msg('m1', ts(old, 10, 0) + i, 'user', '%s 老内容' % KW_OUTOFRANGE),
            msg('m2', ts(d, 16, 40) + i, 'user', '当天的新需求'),
        ]
        add(cwd, '跨区间关键词 %d' % i, None, ts(old, 10, 0),
            ts(d, 16, 40) + i, msgs, '关键词仅在区间外消息：查 d28 不应命中')

    # ---- ⑩ 共享前缀的会话 ID 2 份（前缀 abcd123 命中 2 条）----
    for i in range(2):
        cwd = CWDS[i]
        d = D['d25']
        msgs = [msg('m1', ts(d, 17, 0) + i, 'user', '前缀共享任务 %d' % i)]
        add(cwd, '前缀共享 %d' % i, None, ts(d, 17, 0), ts(d, 17, 0) + i, msgs,
            '前缀共享')
        specs[-1]['id'] = 'abcd123%d-0000-4000-8000-%012d' % (i + 4, i + 1)

    # ---- ⑪ 性能压测：1 份 5000 条消息的大会话 ----
    d = D['d29']
    big = []
    for k in range(5000):
        role = 'user' if k % 2 == 0 else 'assistant'
        big.append(msg('b%d' % k, ts(d, 10, 0) + k, role,
                       '压测消息 %d %s' % (k, '内容' * 20)))
    add('E:/workspace/perf-stress', '超大会话 5000 条', None,
        ts(d, 10, 0), ts(d, 10, 0) + 5000, big, '性能压测')

    # ---- ⑫ 已删除会话 6 份（deleted_at 非空；落 d25×2 / d28×2 / d29×2）----
    # d29 的 2 份被默认过滤后不可见 → d29 可见数维持 17，I-index 越界负例不受影响
    dd_map = ['d25', 'd25', 'd28', 'd28', 'd29', 'd29']
    for i in range(6):
        d = D[dd_map[i]]
        msgs = [
            msg('m1', ts(d, 18, 0) + i, 'user', '已删除会话的内容 %d' % i),
            msg('m2', ts(d, 18, 1) + i, 'assistant', '已删除会话的结论 %d' % i),
        ]
        add(CWDS[i % len(CWDS)], '已删除的任务 %d' % i, None, ts(d, 18, 0),
            ts(d, 18, 1) + i, msgs, '已删除：默认应过滤', deleted=True,
            sid='de1e%04d-0000-4000-8000-%012d' % (i + 1, i + 1))

    # ---- ⑬ 远古会话 2 份（last_activity 落在 2026-09-20，任何日期窗口之外）----
    old = datetime.date(2026, 9, 20)
    for i in range(2):
        msgs = [
            msg('m1', ts(old, 10, 0) + i, 'user', '远古需求 %d' % i),
            msg('m2', ts(old, 10, 1) + i, 'assistant', '远古结论 %d' % i),
        ]
        add(CWDS[0], '远古任务 %d' % i, None, ts(old, 10, 0),
            ts(old, 10, 1) + i, msgs, '远古：仅 --all 或足够长的 --days 能命中',
            sid='f005%04d-0000-4000-8000-%012d' % (i + 1, i + 1))

    # ---- ⑭ 批量填充 220 份（只落 d25-d28，把 5 日窗口推到 320 行触发紧凑格式）----
    # 专用 cwd（不含任何用例的 cwd 关键词）；标题/正文不含任何用例关键词；
    # 20 点整无人占用，last_activity 加毫秒级偏移保证全库唯一
    fdays = ['d25', 'd26', 'd27', 'd28']
    for i in range(220):
        d = D[fdays[i % 4]]
        msgs = [
            msg('m1', ts(d, 20, 0) + i, 'user', '填充消息 %d' % i),
            msg('m2', ts(d, 20, 0) + 1000 + i, 'assistant', '填充回复 %d' % i),
        ]
        add('E:/bulk/filler-zone', '批量填充 %d' % i, None, ts(d, 20, 0),
            ts(d, 20, 1) + i, msgs, '批量填充（紧凑格式）')

    return specs


def safe_reset(path):
    """删除前做两道校验，防止路径参数误用导致不可逆删数据。

    规则：① 目标必须在用户桌面下；② 目录名须含测试标识（test/测试）。
    不满足则直接退出，不做任何删除。
    """
    path = os.path.abspath(path)
    desktop = os.path.abspath(os.path.join(os.path.expanduser('~'), 'Desktop'))
    if not path.startswith(desktop + os.sep):
        raise SystemExit('拒绝删除：目标不在桌面下 → %s\n'
                         '（本脚本只允许重建桌面下的测试目录）' % path)
    base = os.path.basename(path).lower()
    if 'test' not in base and '测试' not in base:
        raise SystemExit('拒绝删除：目录名不含测试标识 → %s' % path)
    if os.path.exists(path):
        shutil.rmtree(path)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    proj = os.path.join(out, 'projects')

    safe_reset(out)
    os.makedirs(proj, exist_ok=True)

    specs = build_specs()
    assert len(specs) == 328, '期望 328 份，实际 %d' % len(specs)

    # 建 db
    db = os.path.join(out, 'workbuddy.db')
    con = sqlite3.connect(db)
    con.execute('''create table sessions(
        id TEXT primary key, cwd TEXT, user_id TEXT, title TEXT, custom_title TEXT,
        status TEXT, created_at INTEGER, updated_at INTEGER, deleted_at INTEGER,
        is_playground INTEGER, model TEXT, last_activity_at INTEGER,
        source_mode TEXT)''')
    truth = []
    for s in specs:
        con.execute(
            'insert into sessions(id,cwd,title,custom_title,status,created_at,'
            'updated_at,last_activity_at,model,source_mode,deleted_at) '
            'values(?,?,?,?,?,?,?,?,?,?,?)',
            (s['id'], s['cwd'], s['title'], s['custom_title'], 'completed',
             s['created_at'], s['last_activity_at'], s['last_activity_at'],
             'custom-local:test-model', 'test', s['deleted_at']))
        # 写 jsonl
        sub = os.path.join(proj, encode_cwd(s['cwd']))
        os.makedirs(sub, exist_ok=True)
        lines = [{'type': 'session-meta', 'id': str(uuid.uuid4()),
                  'sessionId': s['id'], 'timestamp': s['created_at'], 'meta': {}}]
        for m in s['msgs']:
            m = dict(m)
            m['sessionId'] = s['id']
            m['cwd'] = s['cwd']
            lines.append(m)
        with open(os.path.join(sub, s['id'] + '.jsonl'), 'w',
                  encoding='utf-8') as f:
            for ln in lines:
                f.write(json.dumps(ln, ensure_ascii=False) + '\n')

        truth.append({
            'seq': s['seq'], 'id': s['id'], 'id8': s['id'][:8],
            'cwd': s['cwd'], 'title': s['custom_title'] or s['title'],
            'title_field': s['title'], 'custom_title': s['custom_title'],
            'created_at': s['created_at'], 'last_activity_at': s['last_activity_at'],
            'deleted': bool(s['deleted_at']), 'deleted_at': s['deleted_at'],
            'date': datetime.datetime.fromtimestamp(
                s['last_activity_at'] / 1000).strftime('%Y-%m-%d'),
            'note': s['note'],
            'msg_count': len(s['msgs']),
        })
    con.commit()
    con.close()

    with open(os.path.join(out, '_ground_truth.json'), 'w',
              encoding='utf-8') as f:
        json.dump(truth, f, ensure_ascii=False, indent=1)

    readme = '''# 测试数据集（328 份）

模拟 `~/.workbuddy` 结构，用于暴力测试「workbuddy会话查找」技能。

| 项 | 值 |
|---|---|
| 会话数 | 328 |
| 日期范围 | 2026-09-20 ~ 2026-09-29（含 2 份远古会话落在 09-20） |
| 工作目录 | 9 个（含中文、大小写混合、特殊字符、批量填充专区） |
| 总消息数 | %d |

## 对抗场景分布

| 场景 | 份数 | 备注 |
|---|---|---|
| 常规会话 | 50 | 均匀分布在 5 天 |
| 重复标题 | 10 | 共用标题「%s」 |
| 跨天会话 | 5 | created 09-28 / last_activity 09-29 |
| 边界时间戳 | 6 | 3 份 00:00:00.000 + 3 份 23:59:59.999 |
| 空会话（无消息） | 5 | 查询应查不到 |
| 仅系统注入消息 | 5 | 应被过滤 |
| 仅 user 无 assistant | 4 | — |
| 重复用户消息 | 3 | 同一文本 3 次，应去重 |
| 关键词分布 | 10 | 标题/正文/都有/都无/区间外 |
| 共享 ID 前缀 | 2 | `abcd1234...` |
| 性能压测 | 1 | 5000 条消息 |
| 已删除会话 | 6 | `de1e` 前缀；默认过滤，`--include-deleted` 可见 |
| 远古会话 | 2 | `f005` 前缀，last_activity 在 09-20，仅 `--all`/长窗口命中 |
| 批量填充 | 220 | `c0de` 前缀，只落 d25-d28，5 日窗口 320 行触发紧凑格式 |

## 计数口径（供用例比对）

- db 共 328 行；`deleted_at` 非空 6 行 → 默认可见 322
- `--days 5`（d25-d29）默认可见 320（6 份已删除中落在该窗口的 6 份不可见；
  d29 可见数维持 17，I-index 越界负例的生命线）
- `--all` 默认可见 322；`--all --include-deleted` 328

真值表见 `_ground_truth.json`（期望结果的唯一依据）。
''' % (sum(s['msg_count'] for s in truth), DUP_TITLE)
    with open(os.path.join(out, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme)

    print('数据集已生成：%s' % out)
    print('  会话数：%d' % len(specs))
    print('  db：%s' % db)
    print('  消息总数：%d' % sum(s['msg_count'] for s in truth))
    bydate = {}
    for t in truth:
        bydate[t['date']] = bydate.get(t['date'], 0) + 1
    print('  按日期分布：%s' % json.dumps(bydate, ensure_ascii=False))


if __name__ == '__main__':
    main()
