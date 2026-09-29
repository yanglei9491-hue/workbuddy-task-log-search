# -*- coding: utf-8 -*-
"""验证「超大单行 JSON」风险：构造 50MB 单行会话，看被测技能是否退化。

背景：adewale/claude-history-explorer 专门加了 MAX_LINE_BYTES=10MB 守卫，
github 上多个同类工具都提到超大单行会拖垮解析。本机真实库已有 60MB 级文件，
故需实测本技能是否有此风险。
"""
import datetime
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

PY = sys.executable
SKILL = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     '..', 'scripts', 'scan.py'))
D = os.path.join(os.path.expanduser('~'), 'Desktop', '超大单行测试')
CWD = 'E:/workspace/bigline'
SID = 'fade0001-0000-4000-8000-000000000001'
SIZE_MB = 50


def safe_reset(path):
    """删除前校验：目标须在桌面下且目录名含测试标识，否则拒绝删除。"""
    path = os.path.abspath(path)
    desktop = os.path.abspath(os.path.join(os.path.expanduser('~'), 'Desktop'))
    if not path.startswith(desktop + os.sep):
        raise SystemExit('拒绝删除：目标不在桌面下 → %s' % path)
    base = os.path.basename(path).lower()
    if 'test' not in base and '测试' not in base:
        raise SystemExit('拒绝删除：目录名不含测试标识 → %s' % path)
    if os.path.exists(path):
        shutil.rmtree(path)


safe_reset(D)
sub = os.path.join(D, 'projects',
                   CWD.replace(chr(92), '-').replace('/', '-').replace(':', '').strip('-').lower())
os.makedirs(sub, exist_ok=True)

ts = int(datetime.datetime(2026, 9, 29, 10, 0).timestamp() * 1000)
con = sqlite3.connect(os.path.join(D, 'workbuddy.db'))
con.execute('create table sessions(id TEXT,cwd TEXT,title TEXT,custom_title TEXT,'
            'created_at INTEGER,updated_at INTEGER,last_activity_at INTEGER,'
            'model TEXT)')
con.execute('insert into sessions values(?,?,?,?,?,?,?,?)',
            (SID, CWD, '超大单行会话', None, ts, ts, ts, 'test'))
con.commit()
con.close()

# 正常小会话（对照）
small = json.dumps({'type': 'message', 'role': 'user', 'timestamp': ts,
                    'sessionId': SID, 'trim': '小行对照',
                    'content': [{'type': 'input_text', 'text': '正常内容'}]},
                   ensure_ascii=False)
big = 'X' * (SIZE_MB * 1024 * 1024)
bigline = json.dumps({'type': 'message', 'role': 'user', 'timestamp': ts,
                      'sessionId': SID,
                      'content': [{'type': 'input_text', 'text': big}]},
                     ensure_ascii=False)
p = os.path.join(sub, SID + '.jsonl')
with open(p, 'w', encoding='utf-8') as f:
    f.write(small + '\n')
    f.write(bigline + '\n')

print('测试数据：%s' % p)
print('  文件大小：%.1f MB（含单行 %.0f MB）' % (os.path.getsize(p) / 1048576, SIZE_MB))

env = dict(os.environ)
env['PYTHONIOENCODING'] = 'utf-8'


def run(label, args, timeout=180):
    t0 = time.perf_counter()
    try:
        r = subprocess.run([PY, SKILL, '--home', D] + args, capture_output=True,
                           env=env, timeout=timeout)
        dt = time.perf_counter() - t0
        out = r.stdout.decode('utf-8', errors='replace')
        err = r.stderr.decode('utf-8', errors='replace')
        print('%-34s rc=%d  耗时 %6.2fs  输出 %d 字节' % (label, r.returncode, dt, len(out)))
        if r.returncode != 0:
            tail = (err.strip().splitlines() or [''])[-1]
            print('     错误：%s' % tail[:160])
        return dt, r.returncode
    except subprocess.TimeoutExpired:
        dt = time.perf_counter() - t0
        print('%-34s 超时（>%ds）' % (label, timeout))
        return dt, -9


print('\n--- 实测 ---')
run('列表模式（只读索引）', ['--date', '2026-09-29', '--list'])
run('正文模式（需读该超大文件）', ['--date', '2026-09-29', '--id', 'fade0001'])
run('关键词模式（逐份读全文）', ['--date', '2026-09-29', '--keyword', '正常内容', '--list'])
run('all-turns（读全文并渲染）', ['--date', '2026-09-29', '--id', 'fade0001', '--all-turns'])

print('\n结论判据：')
print('  · 耗时是否随单行大小爆炸（正常应 <2s）')
print('  · 是否因内存不足崩溃（rc=137 / MemoryError）')
print('  · 输出是否被超大内容撑爆（正常不应输出 50MB 原文）')
