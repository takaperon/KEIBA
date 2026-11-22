"""中央：外部指数（競馬ナビ）と HORSE指数を合わせたら良くなるか（前向きの検証）。
app_data が毎回 knavidata/jra/{日付}.jsonl に、その日のナビ指数と HORSE指数（その日より前だけで学習）を残す。
結果は jradata（JRA公式の成績）から。出力は集計値だけ。
"""
import json, os, sys, glob
import numpy as np
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import importlib.util
sp = importlib.util.spec_from_file_location('jm', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jra_model.py'))
JM = importlib.util.module_from_spec(sp); sp.loader.exec_module(JM)
res = {}
for r in JM.load():
    res[(r['date'], r['place_code'], r['rno'])] = {h['num']: h.get('pos') for h in r['runners']}
rows = []; days = {}
for fn in sorted(glob.glob('knavidata/jra/*.jsonl')):
    for l in open(fn):
        x = json.loads(l)
        pos = res.get((x['date'], x['place'], x['rno']))
        hs = {int(k): v for k, v in (x.get('horse') or {}).items()}
        nv = {int(k): v for k, v in x['idx'].items()}
        if not pos or not hs:
            continue
        H = [n for n in nv if n in hs and pos.get(n)]
        if len(H) < 5:
            continue
        z = lambda v: (np.array(v, float) - np.mean(v)) / (np.std(v) or 1)
        a, b = z([hs[n] for n in H]), z([nv[n] for n in H])
        days[x['date']] = days.get(x['date'], 0) + 1
        for n, p, q in zip(H, a, b):
            rows.append((x['date'], int(pos[n] <= 3), int(pos[n] == 1), p, q))
print(f'記録のある日：{len(days)}日 {sum(days.values())}レース {len(rows)}頭  ' + ' '.join(f'{k}:{v}R' for k, v in sorted(days.items())))
if len(rows) < 100:
    print('まだ少ないので判断しない'); sys.exit()
X = np.array([r[1:] for r in rows], float)
print('3着以内 AUC（レース内の偏差で比べる）')
for w in (0, .1, .2, .3, .5, 1):
    s = (1 - w) * X[:, 2] + w * X[:, 3]
    print(f'  ナビの重み {w:.1f}：3着以内 {roc_auc_score(X[:, 0], s):.3f}  1着 {roc_auc_score(X[:, 1], s):.3f}')
print('日ごと（HORSE単独 / ナビ単独 / 半々）')
for d in sorted(days):
    m = np.array([r[0] == d for r in rows]); Y = X[m]
    if Y[:, 0].sum() and len(Y) > 30:
        print(f'  {d} {days[d]}R  {roc_auc_score(Y[:, 0], Y[:, 2]):.3f} / {roc_auc_score(Y[:, 0], Y[:, 3]):.3f} / {roc_auc_score(Y[:, 0], Y[:, 2] + Y[:, 3]):.3f}')
