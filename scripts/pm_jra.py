"""PM（中央）：血統の狙い目印は中央でも効くか。地方と同じ規則（60走以上・全馬平均の1.3倍以上、◎＝父母父とも／○＝片方）。
中央にはまだ検証済みの独自指数が無いので、比べる相手は人気（同じ人気帯の無印）。学習＝〜2025-12-31、テスト＝2026-01-01〜。"""
import json, os, sys, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import ped_mark as PMK
P = print
ped = json.load(open('peddata/ped.json'))
races = {}
for fn in sorted(os.listdir('jradata/races')):
    for l in open(f'jradata/races/{fn}'):
        r = json.loads(l); races[r['id']] = r
races = sorted(races.values(), key=lambda r: (r['date'], r['place'], r['rno']))
for r in races:
    r['going'] = r.get('going_turf') if r.get('surface') == '芝' else (r.get('going_dirt') or r.get('going_turf'))
SPLIT = '20260101'
n_all = sum(1 for r in races for h in r['runners'] if h.get('pos') or h.get('pos_text'))
n_ped = sum(1 for r in races for h in r['runners'] if (h.get('pos') or h.get('pos_text')) and ped.get(h.get('horse_id') or ''))
P(f'中央の出走 {n_all}走のうち血統が分かる {n_ped}走（{n_ped / n_all:.0%}）')
good = PMK.build(races, ped, SPLIT)
P(f'得意条件（学習期間〜2025年）：{len(good)}組')
rows = []
for r in races:
    if r['date'] < SPLIT:
        continue
    pay = {p['combo']: p['yen'] for p in (r.get('payouts') or {}).get('複勝') or []}
    for h in r['runners']:
        if not (h.get('pos') or h.get('pos_text')) or not h.get('pop'):
            continue
        p = ped.get(h.get('horse_id') or '')
        if not p:
            continue
        m, _ = PMK.mark(good, r['place'], r.get('surface'), r.get('distance'), r.get('going'), p[0], p[2], r['place_name'])
        t3 = 1 if h.get('pos') and h['pos'] <= 3 else 0
        rows.append((m, t3, h['pop'], pay.get(str(h['num']), 0) if t3 else 0))
a = np.array(rows)
P(f'テスト期間（2026年）の血統が分かる出走：{len(a)}')
for v, nm in ((2, '◎'), (1, '○'), (0, '無印')):
    x = a[a[:, 0] == v]
    if len(x):
        P(f'  {nm:<3} n={len(x):>6} ({len(x) / len(a):.0%}) 3着内 {x[:, 1].mean():5.1%} 複回 {x[:, 3].sum() / len(x):3.0f}% 平均人気 {x[:, 2].mean():.1f}')
P('同じ人気帯の無印との差（3着内率）')
for lo, hi in ((1, 1), (2, 3), (4, 6), (7, 9), (10, 99)):
    g = a[(a[:, 2] >= lo) & (a[:, 2] <= hi)]
    for v, nm in ((2, '◎'), (1, '○')):
        x, z = g[g[:, 0] == v], g[g[:, 0] == 0]
        if len(x) > 30 and len(z) > 30:
            P(f'  {lo}〜{hi}番人気 {nm} {x[:, 1].mean():5.1%}（n={len(x)}, 複回{x[:, 3].sum() / len(x):3.0f}%） 無印 {z[:, 1].mean():5.1%}（n={len(z)}, 複回{z[:, 3].sum() / len(z):3.0f}%） 差 {x[:, 1].mean() - z[:, 1].mean():+.1%}')
