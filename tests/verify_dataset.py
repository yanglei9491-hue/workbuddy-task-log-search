# -*- coding: utf-8 -*-
"""数据集保真度自检：核对 db 与 jsonl 是否与真值表一致。"""
import json
import os
import sqlite3

OUT = os.path.join(os.path.expanduser('~'), 'Desktop', '测试数据集')


def encode_cwd(p):
    p = p.replace(chr(92), '-').replace('/', '-').replace(':', '')
    return p.strip('-').lower()


truth = json.load(open(os.path.join(OUT, '_ground_truth.json'), encoding='utf-8'))
con = sqlite3.connect('file:%s?mode=ro' % os.path.join(OUT, 'workbuddy.db'), uri=True)

print('真值表条数：%d' % len(truth))

# 1. db 行数与真值表一致
dbn = con.execute('select count(*) from sessions').fetchone()[0]
print('db sessions 行数：%d  %s' % (dbn, 'OK' if dbn == len(truth) else '✗不符'))

# 2. 逐条核对 id/cwd/title/last_activity
err = 0
for t in truth:
    row = con.execute('select id,cwd,title,custom_title,last_activity_at '
                      'from sessions where id=?', (t['id'],)).fetchone()
    if not row:
        print('  ✗ db 缺 %s' % t['id'][:8]); err += 1; continue
    if row[1] != t['cwd'] or row[4] != t['last_activity_at']:
        print('  ✗ 字段不符 %s' % t['id'][:8]); err += 1
print('db 字段核对：%s' % ('全部一致' if err == 0 else '%d 条不符' % err))

# 3. jsonl 存在性与行数
miss, mismatch = 0, 0
for t in truth:
    p = os.path.join(OUT, 'projects', encode_cwd(t['cwd']), t['id'] + '.jsonl')
    if not os.path.exists(p):
        miss += 1; continue
    lines = sum(1 for _ in open(p, encoding='utf-8'))
    # +1 为 session-meta 行
    if lines != t['msg_count'] + 1:
        print('  ✗ 行数不符 %s: jsonl=%d 期望=%d'
              % (t['id'][:8], lines, t['msg_count'] + 1))
        mismatch += 1
print('jsonl 缺失：%d  行数不符：%d' % (miss, mismatch))

# 4. 按日期分布（以 db 的 last_activity_at 为准）
print('\n按 last_activity 日期分布：')
q = con.execute('''select date(last_activity_at/1000,'unixepoch','localtime') d,
                          count(*) from sessions group by d order by d''')
for d, c in q:
    print('  %s : %d' % (d, c))

# 5. 文件总数
tot = sum(len(f) for _, _, f in os.walk(os.path.join(OUT, 'projects')))
print('\nprojects 下 jsonl 文件数：%d' % tot)

# 6. 对抗场景抽样核对
print('\n对抗场景抽样：')
dup = con.execute("select count(*) from sessions where custom_title='重复任务名-数据清洗'").fetchone()[0]
print('  重复标题份数：%d（期望 10）' % dup)
pre = con.execute("select count(*) from sessions where id like 'abcd1234%'").fetchone()[0]
print('  共享前缀 abcd1234 份数：%d（期望 2）' % pre)
big = con.execute("select id from sessions where title='超大会话 5000 条'").fetchone()
if big:
    p = os.path.join(OUT, 'projects', encode_cwd('E:/workspace/perf-stress'),
                     big[0] + '.jsonl')
    n = sum(1 for _ in open(p, encoding='utf-8'))
    print('  压测会话行数：%d（期望 5001）' % n)
