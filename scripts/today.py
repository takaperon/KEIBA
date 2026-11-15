"""今日（または指定日）の出馬表を全レース取得して JSON にする。約40リクエスト・1.5秒間隔。"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import jra
from scripts.backfill import Fetcher

ap = argparse.ArgumentParser()
ap.add_argument('--out', required=True)
ap.add_argument('--date', default=None)
a = ap.parse_args()
f = Fetcher(80, 1.5)
top = f.get('accessD.html', 'pw01dli00/F3')
lists = jra.cnames(top, 'pw01drl')
date = a.date or max(c[-11:-3] for c in lists)
races = []
for c in [c for c in lists if c[-11:-3] == date]:
    h = f.get('accessD.html', c)
    for r in jra.cnames(h, 'pw01dde'):
        if r[-11:-3] == date and r not in [x['cname'] for x in races]:
            races.append({'cname': r})
out = []
for r in races:
    try:
        d = jra.parse_card(f.get('accessD.html', r['cname']))
    except Exception as e:  # noqa
        print('ERR', r['cname'], e); continue
    k = jra.race_key(r['cname'])
    out.append(dict(k, **d, cname=r['cname']))
out.sort(key=lambda x: (x['place'], x['rno']))
os.makedirs(a.out, exist_ok=True)
json.dump({'date': date, 'fetched_at': time.strftime('%Y-%m-%d %H:%M', time.localtime()), 'races': out},
          open(f'{a.out}/{date}.json', 'w'), ensure_ascii=False)
json.dump({'latest': date}, open(f'{a.out}/latest.json', 'w'))
print(f'date={date} races={len(out)} requests={f.n}')
