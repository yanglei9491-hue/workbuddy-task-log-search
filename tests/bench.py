# -*- coding: utf-8 -*-
"""性能基准：测试集（100 份）与真实库（1480 会话 / 2.4GB）双场景。

每场景跑 3 次取平均，超时保护 120s。
"""
import os
import statistics
import subprocess
import sys
import time

PY = sys.executable
SKILL = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     '..', 'scripts', 'scan.py'))
DS = os.path.join(os.path.expanduser('~'), 'Desktop', '测试数据集')
RUNS = 3
TIMEOUT = 120

CASES = [
    ('测试集 · 当天列表（纯索引）',
     ['--home', DS, '--date', '2026-09-29', '--list']),
    ('测试集 · 全量100份列表',
     ['--home', DS, '--date', '2026-09-29', '--days', '5', '--list']),
    ('测试集 · 全量100份关键词（需读全部jsonl）',
     ['--home', DS, '--date', '2026-09-29', '--days', '5', '--keyword', '脱敏', '--list']),
    ('测试集 · 单个任务正文（含5000条大会话）',
     ['--home', DS, '--date', '2026-09-29', '--title', '超大会话']),
    ('真实库 · 当天列表（1480会话索引）',
     ['--date', '2026-09-29', '--list']),
    ('真实库 · 近7天列表',
     ['--date', '2026-09-29', '--days', '7', '--list']),
    ('真实库 · 近7天关键词（读多份jsonl）',
     ['--date', '2026-09-29', '--days', '7', '--keyword', '视频', '--list']),
    ('真实库 · 单个任务正文',
     ['--date', '2026-09-28', '--id', 'a1b2c3d4']),
]


def run(args):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    t0 = time.perf_counter()
    try:
        p = subprocess.run([PY, SKILL] + args, capture_output=True, env=env,
                           timeout=TIMEOUT)
        dt = time.perf_counter() - t0
        return dt, p.returncode, len(p.stdout)
    except subprocess.TimeoutExpired:
        return float('inf'), -1, 0


print('=' * 78)
print('性能基准  |  每场景 %d 次取平均  |  超时保护 %ds' % (RUNS, TIMEOUT))
print('=' * 78)
rows = []
for name, args in CASES:
    ts, ok = [], True
    for _ in range(RUNS):
        dt, rc, n = run(args)
        ts.append(dt)
        if rc != 0:
            ok = False
    avg = statistics.mean(ts)
    mx = max(ts)
    rows.append((name, avg, mx, ok))
    flag = 'OK ' if ok else 'ERR'
    print('%-4s %-40s 平均 %6.2fs  最大 %6.2fs' % (flag, name, avg, mx))

print('\n线性度验证（测试集：全量列表 vs 全文扫描）：')
print('  说明：列表模式只读 db 索引；关键词模式需逐份读 jsonl 全文。')

import json
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'perf_result.json'), 'w', encoding='utf-8') as f:
    json.dump([{'name': n, 'avg': a, 'max': m, 'ok': o} for n, a, m, o in rows],
              f, ensure_ascii=False, indent=1)
print('\n结果已存 perf_result.json')
