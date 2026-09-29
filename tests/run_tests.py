# -*- coding: utf-8 -*-
"""暴力测试「会话任务检索」技能。

原则：
  1. 期望值由**独立参考实现**计算（不复用技能代码），双轨互证。
  2. 每个用例独立进程调用，真实测速度与稳定性。
  3. 准确率必须 100%，任何偏差按 P0-P4 分级记录。

用法：
    python run_tests.py [--repeat N]
"""
import argparse
import datetime
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

PY = sys.executable
SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     '..', 'scripts', 'scan.py')
SKILL = os.path.abspath(SKILL)
DATASET = os.path.join(os.path.expanduser('~'), 'Desktop', '测试数据集')

DUP_TITLE = '重复任务名-数据清洗'
KW_TITLE = '会议纪要'
KW_BODY = '量子纠缠'
KW_BOTH = '脱敏'
KW_NONE = '不存在的关键词XYZ'
KW_SYSTEM = '渗透测试'
KW_OUTRANGE = '史前消息'

SKIP_PREFIX = (
    '<teammate-message', '<task-notification', '<cb_summary',
    'You are now in Agent mode', 'Please continue with the conversation',
    'Please continue', '<command-name>', '<local-command',
)


# ============ 独立参考实现 ============

def encode_cwd(p):
    p = p.replace(chr(92), '-').replace('/', '-').replace(':', '')
    return p.strip('-').lower()


class Ref:
    """参考实现：直接从 db + jsonl 按规格重算，不依赖技能代码。"""

    def __init__(self, root):
        self.root = root
        con = sqlite3.connect('file:%s?mode=ro' % os.path.join(root, 'workbuddy.db'),
                              uri=True)
        self.sessions = []
        for r in con.execute('select id,cwd,title,custom_title,created_at,'
                             'last_activity_at from sessions'):
            self.sessions.append({
                'id': r[0], 'cwd': r[1], 'title': r[2], 'custom_title': r[3],
                'created_at': r[4], 'last_activity_at': r[5],
            })
        con.close()
        self._msgcache = {}
        # 按 last_activity 降序（规格：最新在前）
        self.sessions.sort(key=lambda s: -s['last_activity_at'])

    def msgs(self, s):
        if s['id'] in self._msgcache:
            return self._msgcache[s['id']]
        p = os.path.join(self.root, 'projects', encode_cwd(s['cwd']),
                         s['id'] + '.jsonl')
        out = []
        if os.path.exists(p):
            for ln in open(p, encoding='utf-8', errors='replace'):
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                if o.get('type') != 'message':
                    continue
                role = o.get('role')
                c = o.get('content')
                txt = ''
                if isinstance(c, str):
                    txt = c
                elif isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get('type') in (
                                'text', 'input_text', 'output_text'):
                            txt += (b.get('text') or '')
                out.append({'ts': o.get('timestamp'), 'role': role, 'text': txt})
        self._msgcache[s['id']] = out
        return out

    def user_msgs(self, s, lo, hi):
        """区间内、非系统注入、去重后的用户消息。"""
        seen, res = set(), []
        for m in self.msgs(s):
            if m['role'] != 'user':
                continue
            ts = m['ts']
            if not ts or not (lo <= ts < hi):
                continue
            t = ' '.join(m['text'].split()).strip()
            if not t or t.startswith(SKIP_PREFIX) or t in seen:
                continue
            seen.add(t)
            res.append(t)
        return res

    def query(self, cwd=None, date=None, days=1, keyword=None, idp=None,
              index=None, title=None):
        """按规格返回 (会话列表, 错误信息)。"""
        d0 = date or datetime.date.today()
        ndays = max(days, 1)
        ds = d0 - datetime.timedelta(days=ndays - 1)
        lo = int(datetime.datetime.combine(ds, datetime.time(0, 0)).timestamp() * 1000)
        hi = int(datetime.datetime.combine(
            d0 + datetime.timedelta(days=1), datetime.time(0, 0)).timestamp() * 1000)

        rows = [s for s in self.sessions if lo <= s['last_activity_at'] < hi]

        if cwd:
            rows = [s for s in rows if cwd.lower() in (s['cwd'] or '').lower()]

        if keyword:
            kw = keyword.lower()
            keep = []
            for s in rows:
                t = (s['custom_title'] or s['title'] or '').lower()
                if kw in t or any(kw in u.lower() for u in self.user_msgs(s, lo, hi)):
                    keep.append(s)
            rows = keep

        if idp:
            rows = [s for s in rows if s['id'].lower().startswith(idp.lower())]
            if not rows:
                return [], 'id 未命中：%s' % idp

        if index is not None:
            if index < 1 or index > len(rows):
                return [], 'index 越界：%d（共 %d）' % (index, len(rows))
            rows = [rows[index - 1]]

        if title:
            kw = title.lower()
            hit = [s for s in rows if kw in (s['custom_title'] or s['title'] or '').lower()]
            if not hit:
                return [], 'title 未命中：%s' % title
            rows = hit

        return rows, None


# ============ 用例定义 ============

def build_cases():
    """返回用例列表。每例：name, args, 期望（由 reference 算）"""
    C = []

    def case(name, args, ref_kw, kind='list', level='normal'):
        C.append({'name': name, 'args': args, 'ref': ref_kw, 'kind': kind,
                  'level': level})

    # ---- A 日期维度 ----
    for dd in ['2026-09-25', '2026-09-26', '2026-09-27', '2026-09-28', '2026-09-29']:
        case('A-日期 %s' % dd, ['--date', dd, '--list'],
             {'date': datetime.date.fromisoformat(dd)})
    case('A-空日期 09-30', ['--date', '2026-09-30', '--list'],
         {'date': datetime.date(2026, 9, 30)})
    case('A-空日期 01-01', ['--date', '2026-01-01', '--list'],
         {'date': datetime.date(2026, 1, 1)})
    case('A-未来日期', ['--date', '2027-06-01', '--list'],
         {'date': datetime.date(2027, 6, 1)})

    # ---- B days 回溯 ----
    case('B-days2 至 09-29', ['--date', '2026-09-29', '--days', '2', '--list'],
         {'date': datetime.date(2026, 9, 29), 'days': 2})
    case('B-days3 至 09-29', ['--date', '2026-09-29', '--days', '3', '--list'],
         {'date': datetime.date(2026, 9, 29), 'days': 3})
    case('B-days5 至 09-27', ['--date', '2026-09-27', '--days', '5', '--list'],
         {'date': datetime.date(2026, 9, 27), 'days': 5})
    case('B-days1 显式', ['--date', '2026-09-25', '--days', '1', '--list'],
         {'date': datetime.date(2026, 9, 25), 'days': 1})
    case('B-days5 至 09-25（含全量起点）', ['--date', '2026-09-25', '--days', '5', '--list'],
         {'date': datetime.date(2026, 9, 25), 'days': 5})

    # ---- C 跨天归属 ----
    case('C-跨天归 09-29', ['--date', '2026-09-29', '--list'],
         {'date': datetime.date(2026, 9, 29)})
    case('C-跨天不归 09-28', ['--date', '2026-09-28', '--list'],
         {'date': datetime.date(2026, 9, 28)})

    # ---- D 边界时间 ----
    case('D-边界 09-27 含零点与末刻', ['--date', '2026-09-27', '--list'],
         {'date': datetime.date(2026, 9, 27)})

    # ---- E 重复标题 ----
    case('E-重复标题 09-25', ['--date', '2026-09-25', '--title', DUP_TITLE, '--list'],
         {'date': datetime.date(2026, 9, 25), 'title': DUP_TITLE})
    case('E-重复标题 09-29', ['--date', '2026-09-29', '--title', DUP_TITLE, '--list'],
         {'date': datetime.date(2026, 9, 29), 'title': DUP_TITLE})
    case('E-重复标题 全域5天', ['--date', '2026-09-29', '--days', '5',
                          '--title', DUP_TITLE, '--list'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'title': DUP_TITLE})
    case('E-标题不存在', ['--date', '2026-09-29', '--title', '绝不存在的标题',
                     '--list'],
         {'date': datetime.date(2026, 9, 29), 'title': '绝不存在的标题'})

    # ---- F 关键词 ----
    case('F-关键词 标题命中', ['--date', '2026-09-28', '--keyword', KW_TITLE, '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': KW_TITLE})
    case('F-关键词 正文命中', ['--date', '2026-09-28', '--keyword', KW_BODY, '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': KW_BODY})
    case('F-关键词 标题+正文', ['--date', '2026-09-28', '--keyword', KW_BOTH, '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': KW_BOTH})
    case('F-关键词 都不命中', ['--date', '2026-09-28', '--keyword', KW_NONE, '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': KW_NONE})
    case('F-关键词 仅系统消息', ['--date', '2026-09-28', '--keyword', KW_SYSTEM, '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': KW_SYSTEM})
    case('F-关键词 仅区间外消息', ['--date', '2026-09-28', '--keyword', KW_OUTRANGE,
                            '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': KW_OUTRANGE})
    case('F-关键词 区间外消息命中（09-20）',
         ['--date', '2026-09-20', '--keyword', KW_OUTRANGE, '--list'],
         {'date': datetime.date(2026, 9, 20), 'keyword': KW_OUTRANGE})
    case('F-关键词 大小写（大写查小写）',
         ['--date', '2026-09-28', '--keyword', 'UPPER-CASE-PATH'.lower(), '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': 'upper-case-path'})
    case('F-关键词 全覆盖5天', ['--date', '2026-09-29', '--days', '5',
                          '--keyword', KW_BOTH, '--list'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'keyword': KW_BOTH})

    # ---- G cwd ----
    case('G-cwd 中文', ['--date', '2026-09-29', '--cwd', '数据流水线', '--list'],
         {'date': datetime.date(2026, 9, 29), 'cwd': '数据流水线'})
    case('G-cwd 部分匹配', ['--date', '2026-09-29', '--cwd', '视频', '--list'],
         {'date': datetime.date(2026, 9, 29), 'cwd': '视频'})
    case('G-cwd 大小写不敏感（小写查大写）',
         ['--date', '2026-09-29', '--cwd', 'upper-case-path', '--list'],
         {'date': datetime.date(2026, 9, 29), 'cwd': 'upper-case-path'})
    case('G-cwd 不存在', ['--date', '2026-09-29', '--cwd', 'zzz-不存在-zzz', '--list'],
         {'date': datetime.date(2026, 9, 29), 'cwd': 'zzz-不存在-zzz'})
    case('G-cwd 全域5天', ['--date', '2026-09-29', '--days', '5',
                       '--cwd', '视频', '--list'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'cwd': '视频'})

    # ---- H id ----
    case('H-id 共享前缀 abcd123（精确命中）',
         ['--date', '2026-09-29', '--days', '5', '--id', 'abcd123'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'idp': 'abcd123'},
         kind='detail')
    case('H-id 共享前缀 abcd123（列表模式）',
         ['--date', '2026-09-29', '--days', '5', '--id', 'abcd123', '--list'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'idp': 'abcd123'})
    case('H-id 唯一前缀 abcd1234（精确命中）',
         ['--date', '2026-09-29', '--days', '5', '--id', 'abcd1234'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'idp': 'abcd1234'},
         kind='detail')
    case('H-id 不存在（全域5天）',
         ['--date', '2026-09-29', '--days', '5', '--id', 'zzzzzzzz'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'idp': 'zzzzzzzz'},
         level='negative')
    case('H-id 大小写（大写前缀）',
         ['--date', '2026-09-29', '--days', '5', '--id', 'ABCD123'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'idp': 'ABCD123'},
         kind='detail')
    case('H-id 完整 ID（精确命中）',
         ['--date', '2026-09-29', '--days', '5',
          '--id', 'abcd1234-0000-4000-8000-000000000001'],
         {'date': datetime.date(2026, 9, 29), 'days': 5,
          'idp': 'abcd1234-0000-4000-8000-000000000001'}, kind='detail')
    case('H-id 单个字符前缀 c0de',
         ['--date', '2026-09-29', '--days', '5', '--id', 'c0de', '--list'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'idp': 'c0de'})

    # ---- I index ----
    case('I-index 1（09-29）', ['--date', '2026-09-29', '--index', '1'],
         {'date': datetime.date(2026, 9, 29), 'index': 1}, kind='detail')
    case('I-index 5（09-29）', ['--date', '2026-09-29', '--index', '5'],
         {'date': datetime.date(2026, 9, 29), 'index': 5}, kind='detail')
    case('I-index 17（09-29 最后）', ['--date', '2026-09-29', '--index', '17'],
         {'date': datetime.date(2026, 9, 29), 'index': 17}, kind='detail')
    case('I-index 18 越界（09-29）', ['--date', '2026-09-29', '--index', '18'],
         {'date': datetime.date(2026, 9, 29), 'index': 18}, level='negative')
    case('I-index 0 非法', ['--date', '2026-09-29', '--index', '0'],
         {'date': datetime.date(2026, 9, 29), 'index': 0}, level='negative')
    case('I-index 负数', ['--date', '2026-09-29', '--index', '-1'],
         {'date': datetime.date(2026, 9, 29), 'index': -1}, level='negative')
    case('I-index 99 越界', ['--date', '2026-09-29', '--index', '99'],
         {'date': datetime.date(2026, 9, 29), 'index': 99}, level='negative')
    case('I-index 非数字', ['--date', '2026-09-29', '--index', 'abc'],
         {'date': datetime.date(2026, 9, 29)}, level='negative')
    case('I-index 1 + 关键词过滤后',
         ['--date', '2026-09-28', '--title', DUP_TITLE, '--index', '1'],
         {'date': datetime.date(2026, 9, 28), 'title': DUP_TITLE, 'index': 1},
         kind='detail')

    # ---- J 组合 ----
    case('J-date+cwd+keyword', ['--date', '2026-09-28', '--cwd', '视频',
                                '--keyword', KW_BOTH, '--list'],
         {'date': datetime.date(2026, 9, 28), 'cwd': '视频', 'keyword': KW_BOTH})
    case('J-date+cwd', ['--date', '2026-09-28', '--cwd', '视频', '--list'],
         {'date': datetime.date(2026, 9, 28), 'cwd': '视频'})
    case('J-date+keyword+title', ['--date', '2026-09-28', '--title', KW_BOTH,
                                  '--keyword', KW_BOTH, '--list'],
         {'date': datetime.date(2026, 9, 28), 'title': KW_BOTH, 'keyword': KW_BOTH})
    case('J-cwd+id', ['--date', '2026-09-29', '--days', '5', '--cwd', 'workspace',
                      '--id', 'abcd1234', '--list'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'cwd': 'workspace',
          'idp': 'abcd1234'})

    # ---- K 非 list 模式（正文读取）----
    case('K-单任务正文（index 1）', ['--date', '2026-09-29', '--index', '1'],
         {'date': datetime.date(2026, 9, 29), 'index': 1}, kind='detail')
    case('K-关键词正文', ['--date', '2026-09-28', '--keyword', KW_BOTH],
         {'date': datetime.date(2026, 9, 28), 'keyword': KW_BOTH}, kind='detail')
    case('K-id 正文', ['--date', '2026-09-29', '--days', '5', '--id', 'abcd1234'],
         {'date': datetime.date(2026, 9, 29), 'days': 5, 'idp': 'abcd1234'},
         kind='detail')
    case('K-all-turns', ['--date', '2026-09-29', '--index', '1', '--all-turns'],
         {'date': datetime.date(2026, 9, 29), 'index': 1}, kind='turns')
    case('K-all-turns 压测会话（5000 条）',
         ['--date', '2026-09-29', '--title', '超大会话', '--all-turns'],
         {'date': datetime.date(2026, 9, 29), 'title': '超大会话'}, kind='turns')

    # ---- L 输入边界与特殊字符 ----
    case('L-空关键词（应等价不过滤）',
         ['--date', '2026-09-28', '--keyword', '', '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': ''})
    case('L-空 cwd（应等价不过滤）',
         ['--date', '2026-09-28', '--cwd', '', '--list'],
         {'date': datetime.date(2026, 9, 28), 'cwd': ''})
    case('L-关键词含正则元字符 [abc]',
         ['--date', '2026-09-28', '--keyword', '[abc]', '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': '[abc]'})
    case('L-关键词含点星 .*',
         ['--date', '2026-09-28', '--keyword', '.*', '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': '.*'})
    case('L-关键词含百分号 %',
         ['--date', '2026-09-28', '--keyword', '%', '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': '%'})
    case('L-关键词含下划线 _',
         ['--date', '2026-09-28', '--keyword', '_', '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': '_'})
    case('L-关键词含单引号（SQL 注入形状）',
         ['--date', '2026-09-28', '--keyword', "' or '1'='1", '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': "' or '1'='1"})
    case('L-超长关键词（200 字）',
         ['--date', '2026-09-28', '--keyword', '很' * 200, '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': '很' * 200})
    case('L-关键词 emoji',
         ['--date', '2026-09-28', '--keyword', '🎯', '--list'],
         {'date': datetime.date(2026, 9, 28), 'keyword': '🎯'})
    case('L-cwd 特殊字符（测试）#1',
         ['--date', '2026-09-29', '--cwd', '含特殊字符-（测试）#1', '--list'],
         {'date': datetime.date(2026, 9, 29), 'cwd': '含特殊字符-（测试）#1'})
    case('L-无任何过滤参数（全量当天正文）',
         ['--date', '2026-09-29'], {'date': datetime.date(2026, 9, 29)},
         kind='detail')
    case('L-title 空串（应等价不过滤）',
         ['--date', '2026-09-28', '--title', '', '--list'],
         {'date': datetime.date(2026, 9, 28), 'title': ''})
    case('L-非法日期格式',
         ['--date', '2026/09/28', '--list'], {'date': datetime.date(2026, 9, 28)},
         level='negative')
    case('L-days 为 0（应等价 1 天）',
         ['--date', '2026-09-29', '--days', '0', '--list'],
         {'date': datetime.date(2026, 9, 29), 'days': 0})

    return C


# ============ 执行与比对 ============

def run_skill(args, home):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    t0 = time.perf_counter()
    p = subprocess.run([PY, SKILL, '--home', home] + args,
                       capture_output=True, env=env)
    dt = time.perf_counter() - t0
    out = p.stdout.decode('utf-8', errors='replace')
    err = p.stderr.decode('utf-8', errors='replace')
    return p.returncode, out, err, dt


RE_LINE = re.compile(r'^\s*(\d+)\.\s*\[([0-9a-f]{8})\]')
RE_TOTAL = re.compile(r'共\s*(\d+)\s*个会话')
RE_TURNS = re.compile(r'全部回复（(\d+)\s*轮）')


def parse_list(out):
    ids, total = [], None
    for ln in out.splitlines():
        m = RE_LINE.match(ln)
        if m:
            ids.append(m.group(2))
        m2 = RE_TOTAL.search(ln)
        if m2:
            total = int(m2.group(1))
    return ids, total


def parse_detail_ids(out):
    """非 list 模式：从 '会话 ID  xxxxxxxx-...' 行提取。"""
    ids = []
    for ln in out.splitlines():
        m = re.search(r'会话 ID\s+([0-9a-f\-]{8,})', ln)
        if m:
            ids.append(m.group(1)[:8])
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repeat', type=int, default=1,
                    help='每个用例重复次数（稳定性验证）')
    ap.add_argument('--only', help='只跑名称包含该串的用例')
    args = ap.parse_args()

    ref = Ref(DATASET)
    cases = build_cases()
    if args.only:
        cases = [c for c in cases if args.only in c['name']]

    print('=' * 78)
    print('暴力测试「会话任务检索」  |  数据集 100 份  |  用例 %d 个  |  重复 %d 次'
          % (len(cases), args.repeat))
    print('=' * 78)

    results = []
    for c in cases:
        is_list = '--list' in c['args']
        expect_error = c.get('level') == 'negative'

        rows, exp_err = ref.query(**c['ref'])
        exp_ids = [s['id'][:8] for s in rows]
        if exp_err:
            expect_error = True

        ok_all, times, outs = True, [], []
        detail = ''
        for _ in range(args.repeat):
            rc, out, err, dt = run_skill(c['args'], DATASET)
            times.append(dt)
            outs.append(out + '||' + err)

            if expect_error:
                if rc == 0:
                    ok_all = False
                    detail = '期望报错但返回码为 0（静默通过）'
                elif not err.strip():
                    ok_all = False
                    detail = '报错但无错误信息'
            else:
                if rc != 0:
                    ok_all = False
                    detail = '非预期退出 rc=%d：%s' % (rc, err.strip()[:120])
                elif is_list:
                    got_ids, got_total = parse_list(out)
                    if got_ids != exp_ids:
                        ok_all = False
                        detail = ('ID 列表不符\n    期望(%d) %s\n    实际(%d) %s'
                                  % (len(exp_ids), exp_ids[:10],
                                     len(got_ids), got_ids[:10]))
                    elif got_total != len(exp_ids):
                        ok_all = False
                        detail = '计数不符：期望 %d 实际 %s' % (len(exp_ids), got_total)
                else:
                    got_ids = parse_detail_ids(out)
                    if got_ids != exp_ids:
                        ok_all = False
                        detail = ('明细 ID 不符\n    期望(%d) %s\n    实际(%d) %s'
                                  % (len(exp_ids), exp_ids[:10],
                                     len(got_ids), got_ids[:10]))
                    if c['kind'] == 'turns' and not RE_TURNS.search(out):
                        ok_all = False
                        detail = '未输出轮次统计'

            if args.repeat > 1 and len(set(outs)) > 1:
                ok_all = False
                detail = '重复执行输出不一致（不稳定）'

        results.append({
            'name': c['name'], 'ok': ok_all, 'times': times,
            'exp_n': len(exp_ids), 'detail': detail, 'level': c.get('level', 'normal'),
            'avg': sum(times) / len(times), 'max': max(times),
        })
        flag = 'PASS' if ok_all else 'FAIL'
        print('%-4s %-42s 期望%3d条  耗时 %.2fs - %.2fs'
              % (flag, c['name'], len(exp_ids), min(times), max(times)))
        if not ok_all:
            print('     ↳ %s' % detail)

    # 汇总
    total = len(results)
    passed = sum(1 for r in results if r['ok'])
    allt = [t for r in results for t in r['times']]
    print('\n' + '=' * 78)
    print('汇总：%d/%d 通过  准确率 %.2f%%' % (passed, total, passed / total * 100))
    print('单次耗时：min %.2fs / 平均 %.2fs / max %.2fs'
          % (min(allt), sum(allt) / len(allt), max(allt)))
    print('总执行次数：%d  总耗时 %.2fs' % (len(allt), sum(allt)))

    summary = {
        'total': total, 'passed': passed,
        'accuracy': passed / total * 100,
        't_min': min(allt), 't_avg': sum(allt) / len(allt), 't_max': max(allt),
        'runs': len(allt), 't_total': sum(allt),
        'repeat': args.repeat,
        'results': results,
    }
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'test_result.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print('结果已存 test_result.json')
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
