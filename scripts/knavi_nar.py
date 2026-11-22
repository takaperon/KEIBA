"""KN：地方の外部指数に競馬ナビを混ぜてよいか（2026-11-22 オーナー「地方はナビだけ検証が必要」）。
競馬ナビは過去日が取れないので、collect_nar_odds が 11/18 から発走前に記録した分（oddsdata/knavi）だけで比べる。
比べるもの：水分ボンバー・かよちん・競馬ナビ それぞれ単独、今の表示（3つの平均）、ナビを抜いた平均（2つ）、市場。
指数はレース内偏差値にしてから平均（アプリと同じ）。出力は集計値だけ。
使い方：python3 scripts/knavi_nar.py nardata oddsdata extdata
"""
import gzip, json, os, sys, collections
import numpy as np
from sklearn.metrics import roc_auc_score
D, O, E = sys.argv[1:4]
P = print
res = {}
for fn in sorted(os.listdir(f'{D}/races')):
    with gzip.open(f'{D}/races/{fn}', 'rt') as f:
        for l in f:
            r = json.loads(l)
            if r['date'] >= '20261118':
                res[r['id']] = r
kn = {}
for fn in sorted(os.listdir(f'{O}/knavi')) if os.path.isdir(f'{O}/knavi') else []:
    with gzip.open(f'{O}/knavi/{fn}', 'rt') as f:
        for l in f:
            x = json.loads(l)
            if x.get('idx'):
                kn[x['race_id']] = {int(k): v for k, v in x['idx'].items()}
ext = collections.defaultdict(dict)
for kind in ('sbo', 'kayo'):
    d = f'{E}/{kind}'
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        with gzip.open(f'{d}/{fn}', 'rt') as f:
            for l in f:
                x = json.loads(l)
                if x['date'] >= '20261118':
                    ext[(x['date'], x['place'], int(x['rno']))][kind] = {int(k): (vv.get('avg') if isinstance(vv, dict) else vv) for k, vv in x['idx'].items()}
P(f'競馬ナビの記録 {len(kn)}レース、結果のあるレース（11/18〜）{len(res)}')


def z(d, nums):
    xs = [d.get(n) for n in nums if d.get(n) is not None]
    if len(xs) < 3:
        return {}
    m, s = np.mean(xs), np.std(xs) or 1
    return {n: 50 + 10 * (d[n] - m) / s for n in nums if d.get(n) is not None}


rows = []; days = collections.Counter()
for rid, k in kn.items():
    r = res.get(rid)
    if not r:
        continue
    H = [h for h in r['runners'] if h.get('pos') and h.get('tan')]
    if len(H) < 5:
        continue
    nums = [h['num'] for h in H]
    e = ext.get((r['date'], r['place'], r['rno'])) or {}
    zk, zs, zy = z(k, nums), z(e.get('sbo') or {}, nums), z(e.get('kayo') or {}, nums)
    if not zk:
        continue
    days[r['date']] += 1
    inv = sum(1 / h['tan'] for h in H)
    for h in H:
        n = h['num']
        a3 = [v for v in (zs.get(n), zy.get(n), zk.get(n)) if v is not None]
        a2 = [v for v in (zs.get(n), zy.get(n)) if v is not None]
        rows.append(dict(race=rid, date=r['date'], place=r.get('place_name') or r['place'], t3=int(h['pos'] <= 3), w=int(h['pos'] == 1), tan=h['tan'], pop=h.get('pop'),
                         kn=zk.get(n, 40.0), sb=zs.get(n), ky=zy.get(n), avg3=np.mean(a3) if a3 else 40.0, avg2=np.mean(a2) if a2 else None,
                         mkt=1 / h['tan'] / inv, raw=k.get(n)))
P(f'比べられたレース {sum(days.values())}（{len(rows)}頭） ' + ' '.join(f'{d}:{n}R' for d, n in sorted(days.items())))
if len(rows) < 300:
    P('まだ少ない'); sys.exit()
import pandas as pd
df = pd.DataFrame(rows)
both = df[df.avg2.notna() & df.sb.notna() & df.ky.notna()]
P(f'\n[KN-1] 3つともそろった馬だけで（{both.date.nunique()}日 {len(both)}頭）AUC 3着以内 / 1着')
for c, nm in (('kn', '競馬ナビ単独'), ('sb', '水分ボンバー単独'), ('ky', 'かよちん単独'), ('avg3', '今の表示（3つの平均）'), ('avg2', 'ナビを抜いた平均（2つ）'), ('mkt', '市場（確定単勝）')):
    P(f'  {nm:<18} {roc_auc_score(both.t3, both[c]):.3f} / {roc_auc_score(both.w, both[c]):.3f}')
P('\n[KN-2] 日ごと・場ごと（3着以内 AUC：ナビ単独 / 3つの平均 / 2つの平均）')
for key in ('date', 'place'):
    for v, g in both.groupby(key):
        if len(g) > 80 and g.t3.nunique() > 1:
            P(f'  {v:<9} n={len(g):>4}  {roc_auc_score(g.t3, g.kn):.3f} / {roc_auc_score(g.t3, g.avg3):.3f} / {roc_auc_score(g.t3, g.avg2):.3f}')
P('\n[KN-3] ナビ指数の向き（生の値と単勝オッズの順位相関、レースごとの平均。マイナス＝指数が高いほど人気）と、1位の馬の成績')
from scipy.stats import spearmanr
P(f"  順位相関 {np.nanmean([spearmanr(g.raw, g.tan)[0] for _, g in both.groupby('race')]):+.2f}")
for c, nm in (('kn', 'ナビ1位'), ('avg2', '2つの平均1位'), ('avg3', '3つの平均1位'), ('mkt', '1番人気')):
    x = both.sort_values(c, ascending=False).groupby('race').head(1)
    P(f'  {nm:<12} {len(x)}頭 勝率 {x.w.mean():.1%} 3着内 {x.t3.mean():.1%} 単勝回収 {(x.tan * x.w).sum() / len(x):.0%} 平均人気 {x["pop"].mean():.1f}')
