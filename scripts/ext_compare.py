"""EXT-3/4＋オーナーの質問（2026-11-20）「HORSE指数と外部指数で格差がある場合、どっちの方が着順がいい？」

テスト期間（2025-11-17〜）で：
 X-1 単独の当たり具合：HORSE指数（v3、オッズ不使用）／外部指数（水分ボンバー・かよちんをレース内偏差値にして平均）／市場（単勝オッズ）の AUC
 X-2 レース内の順位が食い違う馬：HORSE上位×外部下位、外部上位×HORSE下位 などの実際の1着率・3着内率・単勝/複勝回収率
 X-3 偏差値の差（HORSE − 外部）の帯ごとの実際の3着内率と、市場が見込んでいた3着内率
 X-4 外部指数をモデルの要素に足したときの logloss（検証で打ち切り、テストで確認）
競馬ナビは過去分が取れないので入っていない。出力は集計値だけ。
"""
import gzip, json, os, sys, collections
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score, log_loss
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import nar_features as NF, venue_level as VL

D, E = sys.argv[1], sys.argv[2]
TRAIN_END, VALID_END = '20250816', '20251117'
P = print
races = {}
for fn in sorted(os.listdir(f'{D}/races')):
    with gzip.open(f'{D}/races/{fn}', 'rt') as f:
        for l in f:
            r = json.loads(l)
            if r['place'] != '65':
                races[r['id']] = r
races = sorted(races.values(), key=lambda r: (r['date'], r['post_time'] or '', r['place'], r['rno']))
RACE = {r['id']: r for r in races}
std = NF.build_standards(races, TRAIN_END)
NF.build_variants(races, std)
rows = NF.build(races, std)
df = pd.DataFrame([dict(x['f'], race=x['race'], date=x['date'], place=x['place'], num=x['num'], pos=x['pos'], tan=x['tan'], pop=x['pop']) for x in rows])
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

# ---- 外部指数（過去分） ----
ext = collections.defaultdict(dict)  # (date, place, rno) -> {'sbo': {num: avg}, 'kayo': {num: v}}
for kind in ('sbo', 'kayo'):
    d = f'{E}/{kind}'
    if not os.path.isdir(d):
        continue
    for fn in sorted(os.listdir(d)):
        with gzip.open(f'{d}/{fn}', 'rt') as f:
            for l in f:
                x = json.loads(l)
                v = {int(k): (vv.get('avg') if isinstance(vv, dict) else vv) for k, vv in x['idx'].items()}
                ext[(x['date'], x['place'], int(x['rno']))][kind] = v


def dev(vals):
    xs = [v for v in vals.values() if v is not None]
    if len(xs) < 3:
        return {}
    m = sum(xs) / len(xs); sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** .5 or 1
    return {k: 50 + 10 * (v - m) / sd for k, v in vals.items() if v is not None}


EXTV = {}
cov = collections.Counter()
for r in races:
    e = ext.get((r['date'], r['place'], r['rno']))
    if not e:
        continue
    ds = [dev(e[k]) for k in ('sbo', 'kayo') if e.get(k)]
    cov['races'] += 1
    for h in r['runners']:
        vs = [d[h['num']] for d in ds if h.get('num') in d]
        if vs:
            EXTV[(r['id'], h['num'])] = (sum(vs) / len(vs), len(vs))
df['ext'] = [EXTV.get((a, b), (np.nan, 0))[0] for a, b in zip(df.race, df.num)]
df['ext_n'] = [EXTV.get((a, b), (np.nan, 0))[1] for a, b in zip(df.race, df.num)]
for s in ('train', 'valid', 'test'):
    x = df[df.split == s]
    P(f'外部指数がある出走：{s} {x.ext.notna().mean():.1%}（{int(x.ext.notna().sum())}/{len(x)}）')

# ---- HORSE指数（v3。学習〜2025-08-15、検証で打ち切り） ----
PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)


def fit(cs, y):
    tr, va = df[df.split == 'train'], df[df.split == 'valid']
    return lgb.train(PARAMS, lgb.Dataset(tr[cs], tr[y]), 3000, valid_sets=[lgb.Dataset(va[cs], va[y])], callbacks=[lgb.early_stopping(100, verbose=False)])


m3 = fit(cols, 'top3')
df['p3'] = m3.predict(df[cols], num_iteration=m3.best_iteration)
lt = np.log(df.p3 / (1 - df.p3))
ref = lt[df.split == 'train']
df['horse'] = 50 + 10 * (lt - ref.mean()) / ref.std()
# レース内偏差値（外部とそろえる）
g = df.groupby('race')['horse']
df['horse_d'] = 50 + 10 * (df.horse - g.transform('mean')) / g.transform('std').replace(0, np.nan)
df['mkt'] = 1 / df.tan
df['mkt'] = df.mkt / df.groupby('race').mkt.transform('sum')
te = df[(df.split == 'test') & df.ext.notna() & df.tan.notna()].copy()
te['r_h'] = te.groupby('race').horse.rank(ascending=False, method='first')
te['r_e'] = te.groupby('race').ext.rank(ascending=False, method='first')
te['r_m'] = te.groupby('race').tan.rank(ascending=True, method='first')
pay = {}
for r in races:
    for p in (r.get('payouts') or {}).get('複勝') or []:
        try:
            pay[(r['id'], int(p['combo']))] = p['yen']
        except Exception:  # noqa
            pass
te['fuku'] = [pay.get((a, int(b)), 0) if t else 0 for a, b, t in zip(te.race, te.num, te.top3)]
te['tany'] = np.where(te.win == 1, te.tan * 100, 0)
P(f'\nテスト期間（外部指数と単勝オッズがある出走）：{len(te)}頭・{te.race.nunique()}レース')

P('\n[X-1] 1つずつの当たり具合（AUC、テスト期間）')
for c, nm, sg in (('horse', 'HORSE指数', 1), ('ext', '外部指数（水分ボンバー＋かよちん）', 1), ('mkt', '市場（単勝オッズ）', 1)):
    P(f'  {nm:<26} 3着内 {roc_auc_score(te.top3, sg * te[c]):.3f}  1着 {roc_auc_score(te.win, sg * te[c]):.3f}')
for c, nm in (('r_h', 'HORSE'), ('r_e', '外部'), ('r_m', '人気')):
    x = te[te[c] == 1]
    P(f'  {nm}1位の馬：{len(x)}頭 勝率 {x.win.mean():.1%} 3着内 {x.top3.mean():.1%} 単勝回収 {x.tany.sum() / len(x):.0f}% 複勝回収 {x.fuku.sum() / len(x):.0f}%')


def show(nm, x):
    if len(x) < 50:
        P(f'  {nm:<34} n={len(x):>5}（少ない）'); return
    P(f'  {nm:<34} n={len(x):>5} 勝率 {x.win.mean():5.1%} 3着内 {x.top3.mean():5.1%}（市場の見込み3着内 {np.clip(x.mkt * 3, 0, 1).mean():5.1%}）単回 {x.tany.sum() / len(x):4.0f}% 複回 {x.fuku.sum() / len(x):4.0f}%  平均{x.tan.mean():.1f}倍')


P('\n[X-2] レース内の順位が食い違う馬（テスト期間）')
show('HORSE 1〜2位 × 外部 1〜2位（一致）', te[(te.r_h <= 2) & (te.r_e <= 2)])
show('HORSE 1〜2位 × 外部 5位以下', te[(te.r_h <= 2) & (te.r_e >= 5)])
show('外部 1〜2位 × HORSE 5位以下', te[(te.r_e <= 2) & (te.r_h >= 5)])
show('HORSE 1〜3位 × 外部 4位以下', te[(te.r_h <= 3) & (te.r_e >= 4)])
show('外部 1〜3位 × HORSE 4位以下', te[(te.r_e <= 3) & (te.r_h >= 4)])

P('\n[X-3] 偏差値の差（HORSE − 外部、どちらもレース内偏差値）の帯ごと')
te['gap'] = te.horse_d - te.ext
for lo, hi, nm in ((-99, -15, 'HORSEの方が15以上低い'), (-15, -7, 'HORSEの方が7〜15低い'), (-7, 7, 'ほぼ同じ（差7未満）'), (7, 15, 'HORSEの方が7〜15高い'), (15, 99, 'HORSEの方が15以上高い')):
    show(nm, te[(te.gap > lo) & (te.gap <= hi)])
P('  ※同じ「差」でも、両方高い馬と両方低い馬が混ざるので、平均的な強さ（2つの平均）で分けた内訳：')
te['avg2'] = (te.horse_d + te.ext) / 2
for lo2, hi2, nm2 in ((55, 99, '2つの平均55以上'), (45, 55, '平均45〜55')):
    for lo, hi, nm in ((-99, -7, 'HORSEが低い'), (7, 99, 'HORSEが高い')):
        show(f'{nm2}・{nm}', te[(te.avg2 > lo2) & (te.avg2 <= hi2) & (te.gap > lo) & (te.gap <= hi)])

P('\n[X-4] 外部指数をモデルに足すと（3着以内、テスト期間 logloss・AUC）')
df['ext_z'] = df.ext; df['ext_have'] = df.ext.notna().astype(int)
mm = (df.split == 'test') & df.ext.notna()
for cs, nm in ((cols, 'HORSE（今）'), (cols + ['ext_z', 'ext_have'], 'HORSE＋外部指数')):
    m = fit(cs, 'top3'); p = np.clip(m.predict(df.loc[mm, cs], num_iteration=m.best_iteration), 1e-6, 1 - 1e-6)
    P(f'  {nm:<16} logloss={log_loss(df.loc[mm, "top3"], p):.4f} AUC={roc_auc_score(df.loc[mm, "top3"], p):.3f}')
P('  参考：検証期間までの外部指数のある割合が低いと、モデルが外部指数の使い方を学べない点に注意')
