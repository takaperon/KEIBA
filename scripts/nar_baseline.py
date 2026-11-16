"""地方 N4：ベタ買い回収率（人気・単勝オッズ帯・競馬場・前半/後半）。出力は集計値だけ。"""
import gzip, json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baseline import band
d = sys.argv[1]
races = {}
for fn in sorted(os.listdir(f'{d}/races')):
    with gzip.open(f'{d}/races/{fn}', 'rt') as f:
        for l in f:
            r = json.loads(l); races[r['id']] = r
races = list(races.values())
dates = sorted(r['date'] for r in races)
mid = dates[len(dates) // 2] if dates else ''
A = collections.defaultdict(lambda: [[0, 0, 0], [0, 0, 0]])
for r in races:
    pm = lambda k: {x['combo']: x['yen'] for x in r['payouts'].get(k, []) if x.get('yen')}
    tan, fuku = pm('単勝'), pm('複勝')
    half = 0 if r['date'] < mid else 1
    for h in r['runners']:
        if not h.get('tan') or h.get('num') is None:
            continue
        keys = [('全体', ''), ('人気', min(h.get('pop') or 99, 10)), ('単勝帯', band(h['tan'])),
                ('場', r['place_name']), ('場×帯', f"{r['place_name']} {band(h['tan'])}")]
        for k in keys:
            g = A[k][half]; g[0] += 1; g[1] += tan.get(str(h['num']), 0); g[2] += fuku.get(str(h['num']), 0)
print(f'races={len(races)} range={dates[0] if dates else None}..{dates[-1] if dates else None} split={mid}')
order = ['全体', '人気', '単勝帯', '場', '場×帯']
for k in sorted(A, key=lambda k: (order.index(k[0]), str(k[1]).zfill(3) if k[0] == '人気' else str(k[1]))):
    a, b = A[k]; n = a[0] + b[0]
    if n < 300:
        continue
    f = lambda g, i: f"{g[i] / (g[0] * 100):6.1%}" if g[0] else '   -  '
    print(f"{k[0]:<4} {str(k[1]):<12} n={n:>6} 単{(a[1] + b[1]) / n / 100:6.1%} 複{(a[2] + b[2]) / n / 100:6.1%} | 前半 単{f(a, 1)} 複{f(a, 2)} | 後半 単{f(b, 1)} 複{f(b, 2)}")
