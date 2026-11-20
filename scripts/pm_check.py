"""PM-1/PM-2：血統の狙い目印は効くか（地方）。集めた途中の血統データ（約1.4万頭）で検証する。

印の規則（学習期間＝〜2025-08-15 のデータだけで作る）：
  父・母父それぞれについて、条件（①芝ダ×距離帯 ②芝ダ×馬場[良稍/重不良] ③競馬場）ごとの3着内率を
  「同じ条件の全馬平均」に向けて縮める（k=50走ぶん）。n≥30 かつ 縮めた後の率 ≥ 平均×1.2 なら「得意条件」。
  今回のレースの条件で、父も母父も得意＝◎、片方＝○、なし＝無印。
検証（テスト期間 2025-11-17〜、血統が分かる馬だけ）：
  PM-2a 印ごとの実際の3着内率・1着率・回収率
  PM-2b HORSE指数（オッズ不使用モデルの3着内確率）が同じくらいの馬どうしで比べても、印のある馬は多く来ているか
  PM-2c 人気が同じくらいの馬どうしで比べても上積みがあるか
  PM-2d 印をモデルの要素に足したときの logloss
"""
import gzip, json, os, sys, collections
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score, log_loss
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import nar_features as NF, venue_level as VL

D = sys.argv[1]
TRAIN_END, VALID_END = '20250816', '20251117'
P = print
ped = json.load(open('peddata/ped.json'))
races = {}
for fn in sorted(os.listdir(f'{D}/races')):
    with gzip.open(f'{D}/races/{fn}', 'rt') as f:
        for l in f:
            r = json.loads(l)
            if r['place'] != '65':
                races[r['id']] = r
races = sorted(races.values(), key=lambda r: (r['date'], r['post_time'] or '', r['place'], r['rno']))


def band(d):
    return 0 if not d else (1 if d <= 1000 else 2 if d <= 1300 else 3 if d <= 1600 else 4 if d <= 1900 else 5)


def conds(r):
    s = r.get('surface') or '?'
    g = '重' if (r.get('going') or '') in ('重', '不', '不良') else '良'
    return {'dist': f"{s}{band(r.get('distance'))}", 'going': f'{s}{g}', 'venue': r['place']}


# ---- 学習期間の条件別成績 ----
cnt = collections.defaultdict(lambda: [0, 0])      # (who, name, aspect, cond) -> [n, top3]
base = collections.defaultdict(lambda: [0, 0])     # (aspect, cond) -> [n, top3]
n_runs = n_ped = 0
for r in races:
    if r['date'] >= TRAIN_END:
        break
    c = conds(r)
    for h in r['runners']:
        if not h.get('pos') and not h.get('pos_text'):
            continue
        t3 = 1 if h.get('pos') and h['pos'] <= 3 else 0
        n_runs += 1
        for a, v in c.items():
            b = base[(a, v)]; b[0] += 1; b[1] += t3
        pd_ = ped.get(h.get('horse_id') or '')
        if not pd_:
            continue
        n_ped += 1
        for who, nm in (('父', pd_[0]), ('母父', pd_[2])):
            if not nm:
                continue
            for a, v in c.items():
                x = cnt[(who, nm, a, v)]; x[0] += 1; x[1] += t3
P(f'学習期間：{n_runs}走のうち血統が分かる {n_ped}走（{n_ped / n_runs:.0%}）。血統データ {len(ped)}頭分（収集途中）')
K = 50
GOOD = {}
for (who, nm, a, v), (n, t) in cnt.items():
    bn, bt = base[(a, v)]
    br = bt / bn if bn else 0
    sr = (t + K * br) / (n + K)
    if n >= 30 and sr >= br * 1.2:
        GOOD[(who, nm, a, v)] = (n, t / n, br)
P(f'得意条件として印の元になる組：{len(GOOD)}（父 {sum(1 for k in GOOD if k[0] == "父")}・母父 {sum(1 for k in GOOD if k[0] == "母父")}）')

# ---- HORSE指数（v3と同じ作り） ----
std = NF.build_standards(races, TRAIN_END)
NF.build_variants(races, std)
rows = NF.build(races, std)
df = pd.DataFrame([dict(x['f'], race=x['race'], date=x['date'], num=x['num'], pos=x['pos'], tan=x['tan'], pop=x['pop']) for x in rows])
feats, _, _ = VL.build(races, std, TRAIN_END)
vl_cols = VL.attach(df, races, feats)
df = df[df['field'] >= 5].copy()
df['top3'] = ((df.pos >= 1) & (df.pos <= 3)).astype(int); df['win'] = (df.pos == 1).astype(int)
REL = ['fig_best', 'fig_mean5', 'beaten_mean5', 'pospct_mean5', 'fig_last', 'pospct_last', 'dist_fit', 'venue_fit', 'going_fit',
       'corner1_pct', 'last3f_rel_mean', 'tr_top3', 'hw', 'kg']
for c in REL:
    g = df.groupby('race')[c]
    df[c + '_z'] = (df[c] - g.transform('mean')) / g.transform('std').replace(0, np.nan)
KEEP = ['G1_基礎能力', 'G2_直近調子', 'G3_距離適性', 'G4_コース適性', 'G8_脚質', 'G9_厩舎', 'G12_馬体重', 'G13_条件変化', 'G14_当日要素']
cols = ['field'] + sorted({c for g in KEEP for c in NF.GROUPS[g] + [x + '_z' for x in NF.GROUPS[g] if x in REL] if c != 'field'}) + vl_cols
df['split'] = np.where(df.date < TRAIN_END, 'train', np.where(df.date < VALID_END, 'valid', 'test'))

# 印
RACE = {r['id']: r for r in races}
hid = {(r['id'], h.get('num')): h.get('horse_id') for r in races for h in r['runners']}
mk, why = [], []
for rid, num in zip(df.race, df.num):
    pd_ = ped.get(hid.get((rid, num)) or '')
    if not pd_:
        mk.append(np.nan); why.append(''); continue
    c = conds(RACE[rid])
    s_ok = [a for a, v in c.items() if (('父', pd_[0], a, v) in GOOD)]
    m_ok = [a for a, v in c.items() if (('母父', pd_[2], a, v) in GOOD)]
    mk.append(2 if s_ok and m_ok else (1 if s_ok or m_ok else 0)); why.append(','.join(['父' + x for x in s_ok] + ['母父' + x for x in m_ok]))
df['pm'] = mk; df['pm_why'] = why

PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)


def fit(cs, y, d=df):
    tr, va = d[d.split == 'train'], d[d.split == 'valid']
    return lgb.train(PARAMS, lgb.Dataset(tr[cs], tr[y]), 3000, valid_sets=[lgb.Dataset(va[cs], va[y])], callbacks=[lgb.early_stopping(100, verbose=False)])


m3 = fit(cols, 'top3')
df['p3'] = m3.predict(df[cols], num_iteration=m3.best_iteration)
pay = {}
for r in races:
    for p in (r.get('payouts') or {}).get('複勝') or []:
        try:
            pay[(r['id'], int(p['combo']))] = p['yen']
        except Exception:  # noqa
            pass
te = df[(df.split == 'test') & df.pm.notna()].copy()
te['fuku'] = [pay.get((a, int(b)), 0) if t else 0 for a, b, t in zip(te.race, te.num, te.top3)]
te['tany'] = np.where(te.win == 1, te.tan * 100, 0)
P(f'\nテスト期間で血統が分かる馬：{len(te)}頭（テスト全体の {len(te) / (df.split == "test").sum():.0%}）')

P('\n[PM-2a] 印ごとの実際の成績（テスト期間）')
for v, nm in ((2, '◎（父・母父とも得意条件）'), (1, '○（どちらか）'), (0, '無印')):
    x = te[te.pm == v]
    if len(x):
        P(f'  {nm:<18} n={len(x):>6} 3着内 {x.top3.mean():5.1%} 1着 {x.win.mean():5.1%}  HORSEの見込み3着内 {x.p3.mean():5.1%}  単回 {x.tany.sum() / len(x):3.0f}% 複回 {x.fuku.sum() / len(x):3.0f}%  平均人気 {x["pop"].mean():.1f}')

P('\n[PM-2b] HORSE指数の見込み（3着内確率）が同じくらいの馬どうし：実際の3着内率（印あり／無印）')
te['pb'] = pd.cut(te.p3, [0, .1, .2, .3, .45, .6, 1])
for b, g in te.groupby('pb', observed=True):
    a, z = g[g.pm >= 1], g[g.pm == 0]
    if len(a) > 50 and len(z) > 50:
        P(f'  見込み {str(b):<12} 印あり {a.top3.mean():5.1%}（n={len(a)}）  無印 {z.top3.mean():5.1%}（n={len(z)}）  差 {a.top3.mean() - z.top3.mean():+.1%}')

P('\n[PM-2c] 人気が同じくらいの馬どうし')
for lo, hi in ((1, 1), (2, 3), (4, 6), (7, 9), (10, 99)):
    g = te[(te['pop'] >= lo) & (te['pop'] <= hi)]
    a, z = g[g.pm >= 1], g[g.pm == 0]
    if len(a) > 50 and len(z) > 50:
        P(f'  {lo}〜{hi}番人気  印あり 3着内 {a.top3.mean():5.1%} 複回 {a.fuku.sum() / len(a):3.0f}%（n={len(a)}）  無印 {z.top3.mean():5.1%} 複回 {z.fuku.sum() / len(z):3.0f}%（n={len(z)}）')

P('\n[PM-2d] 印をモデルの要素に足すと（血統が分かる馬だけ、テスト期間）')
d2 = df[df.pm.notna()].copy()
for cs, nm in ((cols, 'HORSE（今）'), (cols + ['pm'], 'HORSE＋血統の印')):
    m = fit(cs, 'top3', d2)
    t2 = d2[d2.split == 'test']
    p = np.clip(m.predict(t2[cs], num_iteration=m.best_iteration), 1e-6, 1 - 1e-6)
    P(f'  {nm:<14} logloss={log_loss(t2.top3, p):.4f} AUC={roc_auc_score(t2.top3, p):.3f}')
P('\n印の理由の内訳（テスト期間・印ありの馬）：')
c = collections.Counter(w for ws in te[te.pm >= 1].pm_why for w in ws.split(',') if w)
P('  ' + '  '.join(f'{k} {v}' for k, v in c.most_common()))
