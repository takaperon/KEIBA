"""中央：デイリー うま屋のスピード指数（SP）・本紙の印 を HORSE指数と合わせたら良くなるか（DY ノード）。

HORSE は jra_model と同じ（〜2025-08 で学習、2025-09〜12 で止め時を決める）。
合わせ方は 2025-09〜12（検証期間）でロジスティック回帰の重みを決め、2026年（テスト期間）で確かめる。
先に「過去のページの SP が、そのレースの結果を含んだ値に書き換わっていないか」を確かめる（未来の混入チェック）。
出力は集計値だけ。
"""
import gzip, json, os, sys, collections
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score, log_loss
from sklearn.linear_model import LogisticRegression
import importlib.util
sp_ = importlib.util.spec_from_file_location('jm', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jra_model.py'))
JM = importlib.util.module_from_spec(sp_); sp_.loader.exec_module(JM)
P = print
races = JM.load()
nid = {r['id']: f"{r['date'][:4]}{r['place']}{r['kai']:02d}{r['day']:02d}{r['rno']:02d}" for r in races if r.get('kai') and r.get('day')}
DY = {}
with gzip.open('dailydata/races.jsonl.gz', 'rt') as f:
    for l in f:
        x = json.loads(l); DY[x['id']] = {int(k): v for k, v in x['rows'].items()}
P(f'デイリーのページ {len(DY)}レース分（SPのある馬 {sum(1 for v in DY.values() for h in v.values() if h.get("sp") is not None)}頭）')

# ---- 未来の混入チェック：勝った馬の次走ページの SP は、勝ったレースのページの SP より上がっているか ----
P('\n[DY-0] 未来の混入チェック（同じ馬の連続した2走）')
hist = collections.defaultdict(list)
for r in races:
    k = nid.get(r['id'])
    if k not in DY:
        continue
    for h in r['runners']:
        v = DY[k].get(h['num'])
        if h.get('horse_id') and v and v.get('sp') is not None:
            hist[h['horse_id']].append((r['date'], v['sp'], h.get('pos')))
up = collections.Counter(); tot = collections.Counter()
for hid, xs in hist.items():
    xs.sort()
    for (d0, s0, p0), (d1, s1, p1) in zip(xs, xs[1:]):
        g = '前走1着' if p0 == 1 else '前走2-5着' if p0 and p0 <= 5 else '前走6着以下'
        tot[g] += 1; up[g] += s1 != s0
for g in ('前走1着', '前走2-5着', '前走6着以下'):
    if tot[g]:
        P(f'  {g}：次のページで SP が変わった割合 {up[g] / tot[g]:.1%}（{tot[g]}組）')
P('  （ページの SP がレース前の値なら、勝った後は変わる割合が高くなるはず。どの組もほぼ0%なら、レース後に書き換わっている疑い）')

# ---- HORSE ----
df, _vt, _wj, base0 = JM.frame(races, JM.TRAIN_END)
df['mkt'] = 1 / df.tan; df['mkt'] = df.mkt / df.groupby('race').mkt.transform('sum')
df = df[df.field >= 5].copy()
df['split'] = np.where(df.date < JM.TRAIN_END, 'train', np.where(df.date < JM.VALID_END, 'valid', 'test'))
tr, va = df[df.split == 'train'], df[df.split == 'valid']
m = lgb.train(JM.PARAMS, lgb.Dataset(tr[base0], tr.top3), 3000, valid_sets=[lgb.Dataset(va[base0], va.top3)], callbacks=[lgb.early_stopping(100, verbose=False)])
df['p_h'] = m.predict(df[base0], num_iteration=m.best_iteration)
df['sp'] = [((DY.get(nid.get(a)) or {}).get(b) or {}).get('sp') for a, b in zip(df.race, df.num)]
df['mk'] = [((DY.get(nid.get(a)) or {}).get(b) or {}).get('mark') for a, b in zip(df.race, df.num)]
df['has_page'] = [nid.get(a) in DY for a in df.race]
d = df[(df.split != 'train') & df.has_page].copy()
d['sp'] = pd.to_numeric(d.sp, errors='coerce')
g = d.groupby('race').sp
d['sp_z'] = ((d.sp - g.transform('mean')) / g.transform('std').replace(0, np.nan)).fillna(-1.5)  # 指数なし（初出走など）は下の方に置く
d['sp_na'] = d.sp.isna().astype(int)
MK = {'◎': 4, '○': 3, '▲': 2, '△': 1, '☆': 1, '注': 1}
d['mk_s'] = d.mk.map(lambda x: MK.get(x or '', 0))
for c in ('mk1', 'mk2', 'mk3', 'mk4'):
    d[c] = (d.mk_s == int(c[-1])).astype(int)
d['lh'] = np.log(np.clip(d.p_h, 1e-4, 1 - 1e-4) / (1 - np.clip(d.p_h, 1e-4, 1 - 1e-4)))
va, te = d[d.split == 'valid'], d[d.split == 'test'].copy()
P(f'\n検証期間 {va.race.nunique()}レース（重みを決める） ／ テスト期間 {te.race.nunique()}レース {len(te)}頭（確かめる）')
P(f'  SP のある馬の割合：テスト {1 - te.sp_na.mean():.1%}')


def ev(nm, p):
    P(f'  {nm:<26} 3着以内 AUC {roc_auc_score(te.top3, p):.4f}  logloss {log_loss(te.top3, np.clip(p, 1e-6, 1 - 1e-6)):.4f}  1着 AUC {roc_auc_score(te.win, p):.4f}')


P('\n[DY-1] テスト期間（2026年）')
ev('HORSE（今のアプリ）', te.p_h)
ev('デイリーSP だけ', te.sp_z)
ev('本紙の印 だけ', te.mk_s + te.sp_z * 0.01)
ev('市場（確定単勝オッズ）', te.mkt)
res = {}
for nm, cols in (('HORSE＋SP', ['lh', 'sp_z', 'sp_na']), ('HORSE＋印', ['lh', 'mk1', 'mk2', 'mk3', 'mk4']), ('HORSE＋SP＋印', ['lh', 'sp_z', 'sp_na', 'mk1', 'mk2', 'mk3', 'mk4'])):
    lr = LogisticRegression(C=1.0, max_iter=1000).fit(va[cols], va.top3)
    p = lr.predict_proba(te[cols])[:, 1]; te['p_' + nm] = p; res[nm] = p
    ev(nm, p); P('      重み：' + '  '.join(f'{c} {w:+.2f}' for c, w in zip(cols, lr.coef_[0])))
lr = LogisticRegression(C=1.0, max_iter=1000).fit(va[['lh']], va.top3)
te['p_h2'] = lr.predict_proba(te[['lh']])[:, 1]
ev('（比べ）HORSE を同じ期間で校正しただけ', te.p_h2)

best = max(res, key=lambda k: roc_auc_score(te.top3, res[k]))
P(f'\n[DY-2] 偏りの確認（{best} − HORSE校正、3着以内 logloss の差。マイナスなら良くなった）')
te['month'] = te.date.str[:6]; w = 0
for mo, g in te.groupby('month'):
    a = log_loss(g.top3, g['p_' + best], labels=[0, 1]) - log_loss(g.top3, g.p_h2, labels=[0, 1]); w += a < 0
    P(f'  {mo} n={len(g):>5}  {a:+.4f}')
P(f'  良くなった月 {w}/{te.month.nunique()}')
te['sf'] = [x for x in te.race.map({r['id']: r.get('surface') for r in races})]
for s, g in te.groupby('sf'):
    P(f'  {s} n={len(g)}  logloss {log_loss(g.top3, g.p_h2):.4f} → {log_loss(g.top3, g["p_" + best]):.4f}')

P('\n[DY-3] レース内1位の馬（テスト期間）')
for col, nm in (('p_h', 'HORSE1位'), ('sp_z', 'SP1位'), ('p_' + best, best + ' 1位'), ('mkt', '1番人気')):
    x = te.sort_values(col, ascending=False).groupby('race').head(1)
    P(f'  {nm:<16} {len(x)}頭 勝率 {x.win.mean():.1%} 3着内 {x.top3.mean():.1%} 単勝回収 {(x.tan * x.win).sum() / len(x):.0%} 平均人気 {x["pop"].mean():.1f}')
x = te[te.mk == '◎']
P(f'  本紙◎             {len(x)}頭 勝率 {x.win.mean():.1%} 3着内 {x.top3.mean():.1%} 単勝回収 {(x.tan * x.win).sum() / max(1, len(x)):.0%} 平均人気 {x["pop"].mean():.1f}')
# HORSE と SP が割れたとき
te['rh'] = te.groupby('race').p_h.rank(ascending=False); te['rs'] = te.groupby('race').sp_z.rank(ascending=False)
for nm, x in (('HORSE1位・SP4位以下', te[(te.rh == 1) & (te.rs >= 4)]), ('SP1位・HORSE4位以下', te[(te.rs == 1) & (te.rh >= 4)])):
    if len(x):
        P(f'  {nm:<16} {len(x)}頭 3着内 {x.top3.mean():.1%} 単勝回収 {(x.tan * x.win).sum() / len(x):.0%} 平均人気 {x["pop"].mean():.1f}')
