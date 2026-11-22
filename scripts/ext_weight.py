"""EW（2026-11-22 オーナー「うん」＝かよちんを重めにした平均の方が良いか確かめる）。
地方の外部指数：水分ボンバー（sbo）とかよちん（kayo）を、レース内偏差値にしてから重みをつけて平均する。
重みは検証期間（2025-08-16〜11-16）で選び、テスト期間（2025-11-17〜）で確かめる。
あわせて、HORSE と合わせるモデル（合成）に、平均1本で入れるか、2サイト別々に入れるかを比べる。出力は集計値だけ。
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



SB, KY = {}, {}
for r in races:
    e = ext.get((r['date'], r['place'], r['rno']))
    if not e:
        continue
    for k, D_ in (('sbo', SB), ('kayo', KY)):
        if e.get(k):
            for n, v in dev(e[k]).items():
                D_[(r['id'], n)] = v
df['sb'] = [SB.get((a, b), np.nan) for a, b in zip(df.race, df.num)]
df['ky'] = [KY.get((a, b), np.nan) for a, b in zip(df.race, df.num)]
df['mkt'] = 1 / df.tan; df['mkt'] = df.mkt / df.groupby('race').mkt.transform('sum')
for s in ('valid', 'test'):
    x = df[df.split == s]
    P(f'{s}：水分ボンバーのある馬 {x.sb.notna().mean():.1%}・かよちん {x.ky.notna().mean():.1%}・両方 {(x.sb.notna() & x.ky.notna()).mean():.1%}（{x.race.nunique()}レース）')


def wavg(x, w):
    a, b = x.sb, x.ky
    return np.where(a.notna() & b.notna(), (1 - w) * a + w * b, np.where(b.notna(), b, a))


P('\n[EW-1] 1サイトずつ（両方ある馬だけ）AUC 3着以内 / 1着')
for s in ('valid', 'test'):
    x = df[(df.split == s) & df.sb.notna() & df.ky.notna() & df.tan.notna()]
    P(f'  {s}：水分ボンバー {roc_auc_score(x.top3, x.sb):.3f} / {roc_auc_score(x.win, x.sb):.3f}   かよちん {roc_auc_score(x.top3, x.ky):.3f} / {roc_auc_score(x.win, x.ky):.3f}   '
      f'市場 {roc_auc_score(x.top3, x.mkt):.3f} / {roc_auc_score(x.win, x.mkt):.3f}')

P('\n[EW-2] かよちんの重み（0＝水分ボンバーだけ、0.5＝今の平均、1＝かよちんだけ）AUC 3着以内 / 1着')
W = (0, .25, .5, .6, .7, .8, .9, 1)
sc = {}
for w in W:
    o = []
    for s in ('valid', 'test'):
        x = df[(df.split == s) & (df.sb.notna() | df.ky.notna())]
        p = wavg(x, w); o.append((roc_auc_score(x.top3, p), roc_auc_score(x.win, p)))
    sc[w] = o[0][0]
    P(f'  重み {w:.2f}：検証 {o[0][0]:.4f} / {o[0][1]:.4f}   テスト {o[1][0]:.4f} / {o[1][1]:.4f}')
wb = max(sc, key=sc.get)
P(f'  検証期間で一番良い重み：{wb}')
# テスト期間の月ごと・場ごと（選んだ重み vs 今の0.5）
x = df[(df.split == 'test') & (df.sb.notna() | df.ky.notna())].copy()
x['pb'] = wavg(x, wb); x['p5'] = wavg(x, .5); x['month'] = x.date.str[:6]
w1 = n1 = 0
for mo, g in x.groupby('month'):
    a, b = roc_auc_score(g.top3, g.pb), roc_auc_score(g.top3, g.p5); w1 += a > b; n1 += 1
P(f'  テスト期間：重み{wb}が今(0.5)より良い月 {w1}/{n1}')
w2 = n2 = 0
for pl, g in x.groupby('place'):
    if len(g) > 2000:
        a, b = roc_auc_score(g.top3, g.pb), roc_auc_score(g.top3, g.p5); w2 += a > b; n2 += 1
P(f'  テスト期間：重み{wb}が今(0.5)より良い場 {w2}/{n2}')

P('\n[EW-3] HORSE と合わせるモデル（合成）：外部を平均1本で入れる vs 2サイト別々（3着以内、テスト期間）')
PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)


def fit(cs, y):
    tr, va = df[df.split == 'train'], df[df.split == 'valid']
    return lgb.train(PARAMS, lgb.Dataset(tr[cs], tr[y]), 3000, valid_sets=[lgb.Dataset(va[cs], va[y])], callbacks=[lgb.early_stopping(100, verbose=False)])


df['ext_z'] = wavg(df, .5); df['ext_have'] = (df.sb.notna() | df.ky.notna()).astype(int)
df['ext_w'] = wavg(df, wb)
df['sb_have'] = df.sb.notna().astype(int); df['ky_have'] = df.ky.notna().astype(int)
mm = (df.split == 'test') & (df.ext_have == 1)
T = df[mm].copy(); T['month'] = T.date.str[:6]
for cs, nm in ((cols, 'HORSE（ext なし）'), (cols + ['ext_z', 'ext_have'], '今の合成（平均0.5）'), (cols + ['ext_w', 'ext_have'], f'合成（重み{wb}）'),
               (cols + ['sb', 'ky', 'sb_have', 'ky_have'], '合成（2サイト別々）')):
    m = fit(cs, 'top3'); p = np.clip(m.predict(T[cs], num_iteration=m.best_iteration), 1e-6, 1 - 1e-6); T['p_' + nm] = p
    P(f'  {nm:<18} logloss={log_loss(T.top3, p):.4f} AUC={roc_auc_score(T.top3, p):.4f}')
for nm in (f'合成（重み{wb}）', '合成（2サイト別々）'):
    w = sum(log_loss(g.top3, g['p_' + nm], labels=[0, 1]) < log_loss(g.top3, g['p_今の合成（平均0.5）'], labels=[0, 1]) for _, g in T.groupby('month'))
    P(f'  {nm} が今の合成より良い月 {w}/{T.month.nunique()}')
for c, nm in (('p_今の合成（平均0.5）', '今の合成1位'), (f'p_合成（2サイト別々）', '2サイト別々1位'), ('mkt', '1番人気')):
    y = T.sort_values(c, ascending=False).groupby('race').head(1)
    P(f'  {nm:<12} {len(y)}頭 勝率 {y.win.mean():.1%} 3着内 {y.top3.mean():.1%} 単勝回収 {(y.tan * y.win).sum() / len(y):.0%}')
