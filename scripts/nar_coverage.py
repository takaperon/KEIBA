"""取れたデータの欠け具合を件数だけで出す（中身は出さない）"""
import gzip, json, os, sys, collections
d = sys.argv[1]; c = collections.Counter(); n = 0
for fn in sorted(os.listdir(f'{d}/races')):
    with gzip.open(f'{d}/races/{fn}', 'rt') as f:
        for l in f:
            r = json.loads(l); n += 1
            for k in ('race_name', 'surface', 'distance', 'going', 'post_time'):
                c[k] += r.get(k) is not None
            c['has_tan'] += any(h.get('tan') for h in r['runners'])
            c['all_tan'] += all(h.get('tan') for h in r['runners'] if h.get('pos'))
            c['has_corners'] += any(h.get('corners') for h in r['runners'])
            c['has_horse_id'] += all(h.get('horse_id') for h in r['runners'])
            c['pay_win'] += '単勝' in r['payouts']
            c['pay_place'] += '複勝' in r['payouts']
            c['pay_trifecta'] += '三連単' in r['payouts']
print('races', n, {k: f'{v}/{n}' for k, v in c.items()})
