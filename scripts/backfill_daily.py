"""デイリー うま屋のスピード指数（SP）と本紙の印を、中央の過去レース（jradata）について集める。
3秒間隔・1回の上限ページ数あり・403/429/503 で止める。保存：dailydata/races.jsonl.gz（キャッシュだけ。リポジトリには置かない）"""
import argparse, gzip, json, os, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import daily

ap = argparse.ArgumentParser()
ap.add_argument('--jra', default='jradata'); ap.add_argument('--out', default='dailydata')
ap.add_argument('--since', default='20250901'); ap.add_argument('--interval', type=float, default=3.0)
ap.add_argument('--max-pages', type=int, default=2400); ap.add_argument('--max-minutes', type=float, default=150)
a = ap.parse_args()
T0 = time.time(); os.makedirs(a.out, exist_ok=True)
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
F = f'{a.out}/races.jsonl.gz'
have = set()
if os.path.exists(F):
    with gzip.open(F, 'rt') as f:
        for l in f:
            have.add(json.loads(l)['id'])
ids = []
for fn in sorted(os.listdir(f'{a.jra}/races')):
    for l in open(f'{a.jra}/races/{fn}'):
        r = json.loads(l)
        if r['date'] >= a.since and r.get('kai') and r.get('day'):
            ids.append((r['date'], f"{r['date'][:4]}{r['place']}{r['kai']:02d}{r['day']:02d}{r['rno']:02d}"))
ids = sorted(set(ids), reverse=True)
todo = [x for x in ids if x[1] not in have]
print(f'対象 {len(ids)} 取得済み {len(have)} 残り {len(todo)}', flush=True)
n = err = 0; last = 0.0; refused = False
with gzip.open(F, 'at') as f:
    for d, rid in todo:
        if n >= a.max_pages or time.time() - T0 > a.max_minutes * 60:
            break
        w = a.interval - (time.time() - last)
        if w > 0:
            time.sleep(w)
        last = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(daily.url(rid), headers={'User-Agent': UA}), timeout=40) as r:
                p = daily.parse(r.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 503):
                print('先方に断られたので止める', e.code, rid, flush=True); refused = True; break
            err += 1; continue
        except Exception as e:  # noqa
            err += 1; print('ERR', rid, e, flush=True); continue
        n += 1
        f.write(json.dumps({'id': rid, 'date': d, 'page_date': p['date'], 'rows': p['rows']}, ensure_ascii=False) + '\n')
        if n % 200 == 0:
            f.flush(); print(n, rid, flush=True)
print(f'取得 {n} エラー {err} 残り {len(todo) - n}', flush=True)
json.dump({'have': len(have) + n, 'left': len(todo) - n, 'errors': err, 'fetched': n, 'refused': refused}, open(f'{a.out}/status.json', 'w'))
