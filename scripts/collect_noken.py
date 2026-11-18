"""能力検査の結果を各主催者の公式ページから集める（keiba/noken.py で読む）。

保存先：nokendata/noken.jsonl（1行1頭）と nokendata/seen.json（読み終えたページ。読めた頭数も）。
Actions のキャッシュに置く。同じページは2回取らない（最新の一覧ページだけは毎回見る）。
状況（件数だけ）は nokendata/status.json に出す。
"""
import json, os, re, subprocess, sys, time, urllib.request, urllib.parse, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import noken as N

UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
D = sys.argv[1] if len(sys.argv) > 1 else 'nokendata'
os.makedirs(D, exist_ok=True)
SEEN = f'{D}/seen.json'
seen = json.load(open(SEEN)) if os.path.exists(SEEN) else {}
recs = []
if os.path.exists(f'{D}/noken.jsonl'):
    recs = [json.loads(l) for l in open(f'{D}/noken.jsonl')]
st = {'errors': [], 'new_pages': {}, 'zero_pages': []}
_last = [0.0]


def get(u):
    w = 3.0 - (time.time() - _last[0])
    if w > 0:
        time.sleep(w)
    _last[0] = time.time()
    with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=40) as r:
        return r.read()


def html(u):
    return get(u).decode('utf-8', 'replace')


def pdftext(u):
    with tempfile.NamedTemporaryFile(suffix='.pdf') as f:
        f.write(get(u)); f.flush()
        return subprocess.run(['pdftotext', '-layout', f.name, '-'], capture_output=True, text=True).stdout


def take(src, u, fn):
    """1ページ分を読む。読めた頭数を seen に記録。0頭なら zero_pages に出す"""
    if u in seen:
        return
    try:
        rs = fn()
    except Exception as e:  # noqa
        st['errors'].append(f'{src} {u} {str(e)[:80]}'); return
    for r in rs:
        r['src'] = src; r['url'] = u
    recs.extend(rs)
    seen[u] = len(rs)
    st['new_pages'][src] = st['new_pages'].get(src, 0) + 1
    if not rs:
        st['zero_pages'].append(f'{src} {u}')


def safe(src, f):
    try:
        f()
    except Exception as e:  # noqa
        st['errors'].append(f'{src} list {str(e)[:100]}')


def iwate():
    t = html('https://www.iwatekeiba.or.jp/race-data/noken/')
    for u in dict.fromkeys(re.findall(r'href="(https?://www\.iwatekeiba\.or\.jp/news/(\d{6})e)"', t)):
        url, ymd = u
        take('岩手', url, lambda: N.iwate(html(url), '20' + ymd))


def hyogo():
    ids = set()
    for p in (1, 2, 3, 4):
        t = html('https://www.sonoda-himeji.jp/data/ability/' + (f'?p={p}' if p > 1 else ''))
        got = set(re.findall(r'/data/ability/detail/(\d+)', t))
        if not got:
            break
        ids |= got
    for i in sorted(ids, key=int):
        u = f'https://www.sonoda-himeji.jp/data/ability/detail/{i}'
        take('兵庫', u, lambda: N.hyogo(html(u)))


def saga():
    t = html('https://www.sagakeiba.net/raceinfo/exam/')
    links = sorted(set(re.findall(r'https://www\.sagakeiba\.net/raceinfo/exam/exam\d{6}/', t)))
    newest = max(links) if links else None
    for u in links:
        if u == newest:
            seen.pop(u, None)  # 最新回は更新されることがあるので毎回読み直す
            recs[:] = [r for r in recs if r.get('url') != u]
        take('佐賀', u, lambda: N.saga(html(u)))


def nagoya():
    t = html('https://www.nagoyakeiba.com/info/program/capability/index.html')
    for u in re.findall(r'<a href="([^"]+\.pdf)"[^>]*>[^<]*能力審査結果', t):
        take('名古屋', u, lambda: N.nagoya(pdftext(u)))


def kasamatsu():
    t = html('https://www.kasamatsu-keiba.com/ability')
    for p in dict.fromkeys(re.findall(r'(/resources/pdfs/ability/\d{4}/\d+_\w+\.pdf)', t)):
        u = 'https://www.kasamatsu-keiba.com' + p
        take('笠松', u, lambda: N.kasamatsu(pdftext(u)))


def kochi():
    posts = []
    for p in (1, 2):
        t = html('https://www.keiba.or.jp/?cat=42' + (f'&paged={p}' if p > 1 else ''))
        posts += re.findall(r'href="(https://www\.keiba\.or\.jp/\?p=\d+)"[^>]*>\s*\d{4}年\d+月\d+日\s*能力検査', t)
    for pu in dict.fromkeys(posts):
        if pu in seen:
            continue
        try:
            t = html(pu)
        except Exception as e:  # noqa
            st['errors'].append(f'高知 {pu} {str(e)[:80]}'); continue
        pdfs = [x for x in dict.fromkeys(re.findall(r'href="(https://www\.keiba\.or\.jp/wp/wp-content/uploads/\d{4}/\d{2}/[0-9a-f]+\.pdf)"', t))]
        n0 = len(recs)
        for u in pdfs:
            take('高知', u, lambda: N.kochi(pdftext(u)))
        seen[pu] = len(recs) - n0
        if not pdfs:
            st['zero_pages'].append(f'高知 {pu} (PDFなし)')


for name, f in (('岩手', iwate), ('兵庫', hyogo), ('佐賀', saga), ('名古屋', nagoya), ('笠松', kasamatsu), ('高知', kochi)):
    safe(name, f)

# 同じ馬・同じ日・同じ時計の重複を除く
uniq = {}
for r in recs:
    uniq[(r['src'], r['date'], r.get('race'), r['horse'], r.get('time'))] = r
recs = sorted(uniq.values(), key=lambda r: (r['src'], r['date'] or '', r.get('race') or 0))
with open(f'{D}/noken.jsonl', 'w') as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
json.dump(seen, open(SEEN, 'w'), ensure_ascii=False)
by = {}
for r in recs:
    b = by.setdefault(r['src'], {'horses': 0, 'with_time': 0, 'dates': set()})
    b['horses'] += 1; b['with_time'] += r.get('sec') is not None; b['dates'].add(r['date'])
st['by_src'] = {k: {'horses': v['horses'], 'with_time': v['with_time'], 'days': len(v['dates']),
                    'first': min(d for d in v['dates'] if d), 'last': max(d for d in v['dates'] if d)} for k, v in by.items()}
json.dump(st, open(f'{D}/status.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps(st, ensure_ascii=False, indent=1))
