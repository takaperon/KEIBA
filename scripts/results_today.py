"""今日の確定済みレース結果（通過順・上り）を取得。馬場の傾向（前残り/差し）を見る用。"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import jra
from scripts.backfill import Fetcher
f = Fetcher(60, 1.0)
top = f.get('accessS.html', 'pw01sli00/AF')
lists = jra.cnames(top, 'pw01srl')
date = max(c[-11:-3] for c in lists)
out = []
for c in [c for c in lists if c[-11:-3] == date]:
    h = f.get('accessS.html', c)
    for r in jra.cnames(h, 'pw01sde'):
        if r[-11:-3] == date:
            try:
                d = jra.parse_result(f.get('accessS.html', r))
                if d['runners'] and d['runners'][0]['pos']:
                    out.append(dict(jra.race_key(r), **d))
            except Exception as e:
                print('ERR', r, e)
os.makedirs('out', exist_ok=True)
json.dump(out, open('out/results_today.json', 'w'), ensure_ascii=False)
print(len(out))
