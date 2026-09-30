# -*- coding: utf-8 -*-
"""workbuddy会话查找 —— 跨会话读取本机 WorkBuddy 历史任务与对话内容。

只读操作：读 workbuddy.db 会话索引 + projects/*.jsonl 对话全文。

用法：
    python scan.py                          # 今天的任务（裸跑仅为 CLI 兼容）
    python scan.py --date 2026-09-28        # 指定某天
    python scan.py --days 3                 # 最近 3 天
    python scan.py --all                    # 全部时间（与 --date/--days 互斥）
    python scan.py --cwd 数据流水线          # 按工作目录过滤
    python scan.py --keyword 脱敏            # 关键词过滤
    python scan.py --list                   # 只列会话（带编号）
    python scan.py --index 3                # 按编号精确命中单个任务
    python scan.py --id a1b2c3d4            # 按会话 ID 前缀精确命中（未给日期时全局检索）
    python scan.py --title 脱敏              # 按标题精确命中（未给日期时全局检索）
    python scan.py --include-deleted        # 包含已删除的会话（默认只保留未删除）
    python scan.py --index 3 --all-turns    # 导出该任务全部回复轮次
    python scan.py --html                   # 输出 HTML 到桌面
    python scan.py --full                   # 结论不截断
"""
import argparse
import datetime
import html as html_mod
import json
import os
import re
import sqlite3
import sys

# 数据根目录：默认 ~/.workbuddy，可用 --home 覆盖（供隔离测试）
HOME = os.path.expanduser('~') + '/.workbuddy'
DB = HOME + '/workbuddy.db'
PROJ = HOME + '/projects'
DESKTOP = os.path.join(os.path.expanduser('~'), 'Desktop')

MAX_TS = 2 ** 63 - 1      # 全时间窗上界（--all / id·title 全局检索用）
COMPACT_AT = 200          # 列表超过此行数切换紧凑格式（省略目录列，保全量输出）


def set_home(path):
    """重设数据根目录（--home 用）。返回是否成功。"""
    global HOME, DB, PROJ
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        return False, '目录不存在：%s' % path
    if not os.path.exists(os.path.join(path, 'workbuddy.db')):
        return False, '目录下找不到 workbuddy.db：%s' % path
    HOME = path
    DB = os.path.join(path, 'workbuddy.db')
    PROJ = os.path.join(path, 'projects')
    return True, HOME

SKIP_PREFIX = (
    '<teammate-message', '<task-notification', '<cb_summary',
    'You are now in Agent mode', 'Please continue with the conversation',
    'Please continue', '<command-name>', '<local-command',
)


def encode_cwd(p):
    p = p.replace(chr(92), '-').replace('/', '-').replace(':', '')
    return p.strip('-').lower()


def hhmm(ts_ms, with_date=False):
    if not ts_ms:
        return ''
    d = datetime.datetime.fromtimestamp(ts_ms / 1000)
    return d.strftime('%m-%d %H:%M') if with_date else d.strftime('%H:%M')


def text_of(content):
    parts = []
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get('type') in ('text', 'input_text', 'output_text'):
                parts.append(b.get('text') or '')
    return '\n'.join(parts)


def clean(t):
    if not t:
        return ''
    t = re.sub(r'<system-reminder[\s\S]*?</system-reminder>', '', t)
    t = re.sub(r'</?user_query>', '', t)
    t = re.sub(r'<image_local_path>[\s\S]*?</image_local_path>', ' [附图]', t)
    t = re.sub(r'<[a-z_\-]+ data-role=[^>]*>[\s\S]*', '', t)
    t = re.sub(r'\[(?:工具|tool):[^\]]*\]', '', t)
    return ' '.join(t.split()).strip()


def collect(sess, lo_ms, hi_ms, keyword=None):
    """读单个会话 jsonl，返回需求列表、最后结论、全部回复轮次。"""
    jl = os.path.join(PROJ, encode_cwd(sess['cwd'] or ''), sess['id'] + '.jsonl')
    if not os.path.exists(jl):
        return None
    users, last_asst, turns = [], None, []
    seen = set()
    for ln in open(jl, encoding='utf-8', errors='replace'):
        try:
            o = json.loads(ln)
        except Exception:
            continue
        ts = o.get('timestamp')
        if ts and not (lo_ms <= ts < hi_ms):
            continue
        if o.get('type') != 'message':
            continue
        role = o.get('role')
        c = clean(text_of(o.get('content')))
        if role == 'user':
            if not c or c.startswith(SKIP_PREFIX):
                continue
            if c in seen:
                continue
            seen.add(c)
            users.append((ts, c))
        elif role == 'assistant' and c:
            last_asst = (ts, c)
            turns.append((ts, c))
    if keyword:
        kw = keyword.lower()
        users = [u for u in users if kw in u[1].lower()
                 or kw in (sess['custom_title'] or sess['title'] or '').lower()]
        if not users and kw not in (sess['custom_title'] or sess['title'] or '').lower():
            return None
    if not users and not last_asst:
        return None
    return {'users': users, 'asst': last_asst, 'turns': turns}


def main():
    ap = argparse.ArgumentParser(
        description='workbuddy会话查找 —— 跨会话检索本机 WorkBuddy 历史任务')
    ap.add_argument('--date', help='日期 YYYY-MM-DD，默认今天')
    ap.add_argument('--days', type=int, default=None,
                    help='最近 N 天（含指定日或今天）；--days 0 等价 1 天；与 --all 互斥')
    ap.add_argument('--all', action='store_true',
                    help='全部时间（忽略日期窗口）；默认仍过滤已删除会话')
    ap.add_argument('--cwd', help='按工作目录关键词过滤')
    ap.add_argument('--keyword', help='按关键词过滤')
    ap.add_argument('--list', action='store_true', help='只列会话不读正文（带编号）')
    ap.add_argument('--index', type=int, help='按 --list 的编号精确命中单个任务')
    ap.add_argument('--id', help='按会话 ID 前缀精确命中（如 a1b2c3d4；未给日期时全局检索）')
    ap.add_argument('--title', help='按标题精确/模糊匹配单个任务（未给日期时全局检索）')
    ap.add_argument('--include-deleted', action='store_true',
                    help='包含已删除的会话（默认只保留 deleted_at 为空的）')
    ap.add_argument('--all-turns', action='store_true',
                    help='输出该会话全部轮次的 AI 回复（默认只出最后一条结论）')
    ap.add_argument('--html', action='store_true', help='输出 HTML 到桌面')
    ap.add_argument('--full', action='store_true', help='结论不截断')
    ap.add_argument('--out', help='自定义输出路径（--html 时生效）')
    ap.add_argument('--home', help='数据根目录，默认 ~/.workbuddy（隔离测试用）')
    args = ap.parse_args()

    if args.home:
        ok, msg = set_home(args.home)
        if not ok:
            sys.exit(msg)

    if not os.path.exists(DB):
        sys.exit('找不到会话索引库：%s\n'
                 '若数据不在默认位置，用 --home <目录> 指定（该目录需含 workbuddy.db）'
                 % DB)

    if args.all and (args.date is not None or args.days is not None):
        sys.exit('--all 与 --date/--days 只能选其一：--all 表示全部时间，无需再给日期窗口')
    if args.date:
        try:
            d0 = datetime.datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            sys.exit('日期格式不正确：%s\n应为 YYYY-MM-DD，例如 2026-09-29'
                     % args.date)
    else:
        d0 = datetime.date.today()
    # --days N = 从 d0 往前回溯 N 天（含 d0）；None（未给）与 0 都等价 1 天
    ndays = max(args.days or 1, 1)
    d_start = d0 - datetime.timedelta(days=ndays - 1)
    d_end = d0

    if args.all:
        lo, hi = 0, MAX_TS
    else:
        lo = datetime.datetime.combine(d_start, datetime.time(0, 0)).timestamp() * 1000
        hi = datetime.datetime.combine(d_end + datetime.timedelta(days=1),
                                       datetime.time(0, 0)).timestamp() * 1000

    # --id/--title 未显式限定时间窗时默认全局检索（修掉"精确命中只查当天"的坑）；
    # --index 例外：它绑定当次 --list 的编号，复跑必须带同样的范围参数
    if (args.id or args.title) and not args.all \
            and args.date is None and args.days is None:
        lo, hi = 0, MAX_TS
    full = (lo == 0 and hi >= MAX_TS)

    con = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
    con.row_factory = sqlite3.Row
    cols = [r[1] for r in con.execute('pragma table_info(sessions)')]
    conds, params = [], []
    # 双侧区间：会话的最后活跃时间必须落在 [lo, hi) 内，否则跨天会话会串进别的日期
    if not full:
        conds.append('coalesce(last_activity_at,updated_at) >= ?')
        conds.append('coalesce(last_activity_at,updated_at) <  ?')
        params += [lo, hi]
    # 默认过滤已删除会话（deleted_at 非空）；列不存在时（老版本库/测试库）不拼该条件
    if 'deleted_at' in cols and not args.include_deleted:
        conds.append('deleted_at is null')
    sql = ('select id,cwd,title,custom_title,created_at,last_activity_at,model '
           'from sessions')
    if conds:
        sql += ' where ' + ' and '.join(conds)
    sql += ' order by coalesce(last_activity_at,updated_at) desc'
    rows = con.execute(sql, params).fetchall()

    if args.cwd:
        rows = [r for r in rows if args.cwd.lower() in (r['cwd'] or '').lower()]

    # 关键词过滤：标题命中 或 落在区间内的用户消息含关键词
    if args.keyword:
        kw = args.keyword.lower()
        keep = []
        for r in rows:
            t = (r['custom_title'] or r['title'] or '').lower()
            if kw in t:
                keep.append(r)
                continue
            got = collect(r, lo, hi, None)
            if got and any(kw in x[1].lower() for x in got['users']):
                keep.append(r)
        rows = keep

    # 精确命中：--id / --index / --title
    precise = bool(args.id) or args.index is not None or bool(args.title)
    if args.id:
        pre = args.id.lower()
        rows = [r for r in rows if r['id'].lower().startswith(pre)]
        if not rows:
            sys.exit('未找到会话 ID 前缀为 %s 的任务' % args.id)
    if args.index is not None:
        if args.index < 1 or args.index > len(rows):
            sys.exit('编号 %d 超出范围（当前共 %d 个任务，用 --list 查看编号）'
                     % (args.index, len(rows)))
        rows = [(args.index, rows[args.index - 1])]
    else:
        rows = [(i, r) for i, r in enumerate(rows, 1)]
    if args.title:
        kw = args.title.lower()
        hit = [(i, r) for i, r in rows
               if kw in (r['custom_title'] or r['title'] or '').lower()]
        if not hit:
            sys.exit('未找到标题包含「%s」的任务' % args.title)
        rows = hit

    label = ('全部时间' if full
             else (d_start.strftime('%Y-%m-%d') if ndays == 1
                   else '%s ~ %s' % (d_start, d_end)))
    print('=' * 74)
    print('WorkBuddy 会话查找 | %s' % label)
    print('=' * 74)

    if args.list:
        compact = len(rows) > COMPACT_AT
        for i, r in rows:
            t = r['custom_title'] or r['title'] or '(无标题)'
            if compact:
                print('%2d. [%s] %s' % (i, r['id'][:8], t[:32]))
            else:
                print('%2d. [%s] %-32s | %s' % (
                    i, r['id'][:8], t[:32], r['cwd']))
        print('\n共 %d 个会话' % len(rows))
        if compact:
            print('（结果较多，已切换紧凑格式：省略目录列；完整目录/正文用 --index N 查看）')
        else:
            print('提示：用 --index N 直取第 N 个任务的完整内容')
        return

    if full and not precise and len(rows) > 50:
        print('警告：全时间窗 + 正文模式将读取 %d 个会话全文（实测约 20 秒级）；'
              '建议改用 --list 浏览编号，或加 --keyword/--cwd 收窄' % len(rows),
              file=sys.stderr)

    cards = []
    need_full = bool(precise) or args.all_turns
    for i, r in rows:
        got = collect(r, lo, hi, args.keyword)
        if not got:
            continue
        if need_full:
            got = collect(r, lo, hi, None) or {'users': [], 'asst': None, 'turns': []}
        cards.append({'i': i, 's': r, 'u': got['users'], 'a': got['asst'],
                      'turns': got.get('turns', []) if args.all_turns else []})

    if not cards:
        print('\n该时间段没有可读的任务记录。')
        return

    for c in cards:
        i, r, u, a = c['i'], c['s'], c['u'], c['a']
        title = r['custom_title'] or r['title'] or '(无标题)'
        if precise:
            print('\n' + '=' * 74)
            print('精确命中  #%d  %s' % (i, title))
            print('=' * 74)
        else:
            print('\n## %d. %s' % (i, title))
        print('   会话 ID  %s' % r['id'])
        print('   时间     %s — %s' % (hhmm(r['created_at'], True),
                                       hhmm(r['last_activity_at'], True)))
        print('   目录     %s' % r['cwd'])
        print('   模型     %s' % r['model'])
        print('\n   需求（%d 条）:' % len(u))
        for ts, x in u:
            lim = 100000 if (args.full or precise) else 200
            print('     [%s] %s' % (hhmm(ts), x[:lim]))
        if args.all_turns and c.get('turns'):
            print('\n   全部回复（%d 轮）:' % len(c['turns']))
            for n, (ts, x) in enumerate(c['turns'], 1):
                cap = 100000 if args.full else 3000
                print('\n   --- 第 %d 轮 [%s] ---' % (n, hhmm(ts)))
                for line in x[:cap].splitlines():
                    print('     ' + line)
        elif a:
            cap = 100000 if (args.full or precise) else 1500
            print('\n   最终结论:')
            for line in a[1][:cap].splitlines():
                print('     ' + line)

    print('\n' + '-' * 74)
    print('共 %d 个任务会话' % len(cards))

    if args.html:
        if full:
            fname = '任务清单_全部.html'
        elif ndays == 1:
            fname = '任务清单_%s.html' % d_start.strftime('%Y%m%d')
        else:
            fname = '任务清单_%s_%s.html' % (d_start.strftime('%Y%m%d'),
                                            d_end.strftime('%Y%m%d'))
        out = args.out or os.path.join(DESKTOP, fname)
        write_html(out, cards, label)
        print('HTML 报告：%s' % out)


def write_html(out, cards, label):
    blocks = ''
    for i, c in enumerate(cards, 1):
        r, u, a = c['s'], c['u'], c['a']
        title = r['custom_title'] or r['title'] or '(无标题)'
        items = ''.join(
            '<li><span class="tm">%s</span><span class="q">%s</span></li>'
            % (hhmm(ts), html_mod.escape(x)) for ts, x in u[:30])
        concl = ''
        if a:
            concl = ('<div class="concl"><div class="cl">最终结论 · %s</div><p>%s</p></div>'
                     % (hhmm(a[0]), html_mod.escape(a[1][:1500])))
        blocks += '''
    <div class="card">
      <div class="hd"><span class="idx">%d</span><h2>%s</h2></div>
      <div class="meta"><span>会话 <code>%s</code></span><span>%s — %s</span><span>%s</span></div>
      <div class="path">%s</div>
      <div class="sec">需求（%d 条）</div>
      <ul class="qs">%s</ul>%s
    </div>''' % (
            i, html_mod.escape(title), r['id'][:8],
            hhmm(r['created_at'], True), hhmm(r['last_activity_at'], True),
            html_mod.escape(str(r['model'] or '')), html_mod.escape(r['cwd'] or ''),
            len(u), items, concl)

    doc = '''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>任务清单 %s</title><style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#1f2329;line-height:1.65;padding:32px 20px}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:23px;font-weight:600;margin-bottom:6px}
.sub{color:#646a73;font-size:13px;margin-bottom:8px}
.note{background:#eef4ff;border-left:3px solid #3370ff;padding:10px 14px;border-radius:6px;font-size:13px;color:#33508c;margin:14px 0 26px}
.card{background:#fff;border:1px solid #e4e6eb;border-radius:12px;padding:20px 22px;margin-bottom:16px}
.hd{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.idx{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%%;background:#3370ff;color:#fff;font-size:13px;font-weight:600;flex:none}
h2{font-size:16px;font-weight:600}
.meta{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:#8a9099;margin-bottom:6px}
code{background:#f2f3f5;padding:1px 5px;border-radius:4px;font-size:11.5px;color:#4e5969}
.path{font-size:12px;color:#646a73;background:#fafbfc;border:1px dashed #e4e6eb;border-radius:6px;padding:6px 10px;margin-bottom:12px;word-break:break-all}
.sec{font-size:12.5px;font-weight:600;color:#3370ff;margin:14px 0 8px}
ul.qs{list-style:none}
ul.qs li{display:flex;gap:10px;padding:5px 0;border-bottom:1px solid #f2f3f5;font-size:13.5px}
ul.qs li:last-child{border:none}
.tm{color:#a0a5ad;font-size:12px;flex:none;width:42px;font-variant-numeric:tabular-nums}
.q{color:#1f2329;word-break:break-word}
.concl{margin-top:14px;background:#f7fbf8;border-left:3px solid #23a55a;border-radius:6px;padding:12px 14px}
.cl{font-size:12.5px;font-weight:600;color:#1a7f45;margin-bottom:6px}
.concl p{font-size:13px;color:#3d4451;white-space:pre-wrap;word-break:break-word}
footer{text-align:center;color:#a0a5ad;font-size:12px;margin-top:28px}
</style></head><body><div class="wrap">
<h1>任务清单 · %s</h1>
<div class="sub">共 %d 个任务会话 · 数据来自本地会话索引与对话全文</div>
<div class="note"><b>这些内容一直在你电脑里。</b>索引在 <code>~/.workbuddy/workbuddy.db</code>，对话全文在 <code>~/.workbuddy/projects/&lt;工作目录&gt;/&lt;会话ID&gt;.jsonl</code>，每个会话一个文件，明文可读。</div>
%s<footer>WorkBuddy · workbuddy会话查找</footer></div></body></html>''' % (
        label, label, len(cards), blocks)
    open(out, 'w', encoding='utf-8').write(doc)
    return out


if __name__ == '__main__':
    main()
