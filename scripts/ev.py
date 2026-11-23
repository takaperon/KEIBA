"""EV（2026-11-23 オーナー「やってみます」）：地方の単勝で、指数が人気より高く見ている馬だけ買うと回収率100%を超えるか。

指数の勝率 p（HORSE・合成、レース内で合計1に直す）× 単勝オッズ ＝ 期待値 EV。EV が基準以上の馬だけ買う。
  EV-1 作る：検証期間（2025-08-16〜11-15）で、基準（EVの下限・オッズの上限）を選ぶ。ここだけは確定オッズで選ぶ（作る段階）
  EV-2 確かめる（参考）：テスト期間（2025-11-16〜2026-11-16）で同じ基準。確定オッズで選ぶので締切前には分からない＝参考
  EV-3 確かめる（本番）：締切前オッズの記録がある 2026-11-17〜。発走2分前（無ければ5分前）のオッズで選び、払戻は確定の単勝払戻
勝率は、学習期間〜2025-08-15 で作ったモデルを検証期間で校正（isotonic）。出力は集計値だけ。
使い方：python3 scripts/ev.py nar nardata extdata oddsdata
"""
import gzip, json, os, sys, collections
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '_nar_frame.py')).read())
O = sys.argv[4]
PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)
FWD = '20261117'
df['split2'] = np.where(df.date < TRAIN_END, 'train', np.where(df.date < VALID_END, 'valid', np.where(df.date < FWD, 'test', 'fwd')))
tr, va = df[df.split2 == 'train'], df[df.split2 == 'valid']
for nm, cs in (('h', cols), ('s', cols + ['ext_w', 'ext_have'])):
    m = lgb.train(PARAMS, lgb.Dataset(tr[cs], tr.win), 3000, valid_sets=[lgb.Dataset(va[cs], va.win)], callbacks=[lgb.early_stopping(100, verbose=False)])
    raw = m.predict(df[cs], num_iteration=m.best_iteration)
    iso = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=0.99).fit(raw[df.split2 == 'valid'], df.win[df.split2 == 'valid'])
    p = pd.Series(iso.predict(raw), index=df.index)
    df['p_' + nm] = p / p.groupby(df.race).transform('sum')
# 単勝払戻（100円あたり）
PAYW = {}
for r in races:
    for p in (r.get('payouts') or {}).get('単勝') or []:
        try:
            PAYW[(r['id'], int(p['combo']))] = float(p['yen'])
        except Exception:  # noqa
            pass
df['ret'] = [PAYW.get((a, int(b)), 0.0) if w else 0.0 for a, b, w in zip(df.race, df.num, df.win)]
# 締切前オッズ
SN = {}
d_ = f'{O}/odds'
for fn in sorted(os.listdir(d_)) if os.path.isdir(d_) else []:
    with gzip.open(f'{d_}/{fn}', 'rt') as f:
        for l in f:
            x = json.loads(l)
            SN[(x['race_id'], x['mark'])] = x['win']


def pre(rid, num):
    for mk in (2, 5):
        w = SN.get((rid, mk)) or {}
        v = w.get(f'{int(num):02d}') or w.get(str(int(num)))
        try:
            o = float(v[0])
            if o > 0:
                return o, mk
        except Exception:  # noqa
            pass
    return None, None


df['o_pre'] = [pre(a, b)[0] for a, b in zip(df.race, df.num)]
df = df[df.tan.notna() & (df.tan > 0)]
fw = df[df.split2 == 'fwd']
P(f'締切前オッズの記録：{fw.race.nunique()}レース中 {fw[fw.o_pre.notna()].race.nunique()}レースにあり（{fw.date.min()}〜{fw.date.max()}）')
if len(fw):
    x = fw[fw.o_pre.notna()]
    P(f'  2分前オッズと確定オッズの比（中央値）{np.median(x.tan / x.o_pre):.3f}、確定の方が低い馬 {(x.tan < x.o_pre).mean():.0%}')


def sel(d, pc, oc, evmin, omax):
    ev = d[pc] * d[oc]
    return d[(ev >= evmin) & (d[oc] <= omax)]


def stat(x):
    if not len(x):
        return None
    roi = x.ret.sum() / (100 * len(x)); srt = np.sort(x.ret.values)[::-1]
    rng = np.random.default_rng(1); rs = x.race.values; u = np.unique(rs)
    g = x.groupby('race').ret.agg(['sum', 'size'])
    bs = []
    for _ in range(400):
        i = rng.integers(0, len(g), len(g)); bs.append(g['sum'].values[i].sum() / (100 * g['size'].values[i].sum()))
    mo = x.assign(m=x.date.str[:6]).groupby('m').apply(lambda y: y.ret.sum() / (100 * len(y)), include_groups=False)
    return dict(n=len(x), races=len(u), hit=x.win.mean(), roi=roi, ex1=(x.ret.sum() - srt[0]) / (100 * len(x)), lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5),
                over=int((mo >= 1).sum()), months=len(mo), odds=float(x.tan.median()))


def line(nm, s):
    if not s:
        return f'  {nm:<34} 該当なし'
    return (f'  {nm:<34} {s["n"]:>5}頭 的中 {s["hit"]:5.1%} 回収 {s["roi"]:5.0%}（95%の幅 {s["lo"]:.0%}〜{s["hi"]:.0%}、最高1本除く {s["ex1"]:.0%}）'
            f' 100%超えた月 {s["over"]}/{s["months"]} 単勝の中央値 {s["odds"]:.1f}')


EVS = (1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.2)
OMX = (5, 10, 20, 50, 999)
va, te = df[df.split2 == 'valid'], df[df.split2 == 'test']
P('\n[EV-0] 何も絞らない単勝（全頭100円ずつ）：' + ' / '.join(f'{s} {d.ret.sum() / (100 * len(d)):.0%}' for s, d in (('検証', va), ('テスト', te))))
choice = {}
for pc, pn in (('p_h', 'HORSE'), ('p_s', '合成')):
    P(f'\n[EV-1] {pn}：検証期間（確定オッズ）で EV下限 × オッズ上限 の回収率（買った頭数）')
    best = None
    P('  EV＼上限 ' + ''.join(f'{o:>12}' for o in OMX))
    for e in EVS:
        cells = []
        for o in OMX:
            x = sel(va, pc, 'tan', e, o); r = x.ret.sum() / (100 * len(x)) if len(x) else 0
            cells.append(f'{r:>6.0%}({len(x):>4})')
            if len(x) >= 300 and (best is None or r > best[0]):
                best = (r, e, o)
        P(f'  {e:>6.1f}  ' + ''.join(f'{c:>12}' for c in cells))
    choice[pc] = best
    P(f'  → 検証期間で一番良い基準（300頭以上）：EV {best[1]} 以上・オッズ {best[2]} 倍以下（検証 {best[0]:.0%}）')
P('\n[EV-2] テスト期間（参考：確定オッズで選ぶので締切前には分からない）')
for pc, pn in (('p_h', 'HORSE'), ('p_s', '合成')):
    _, e, o = choice[pc]
    P(line(f'{pn} EV≥{e}・{o}倍以下', stat(sel(te, pc, 'tan', e, o))))
    for e2, o2 in ((1.2, 20), (1.5, 20), (1.2, 999), (1.5, 999)):
        P(line(f'{pn} EV≥{e2}・{o2}倍以下', stat(sel(te, pc, 'tan', e2, o2))))
# テスト期間の跳ねの確認：オッズ帯ごと
P('\n[EV-2b] テスト期間・合成の選んだ基準：オッズ帯ごと')
_, e, o = choice['p_s']
x = sel(te, 'p_s', 'tan', e, o).copy(); x['ob'] = pd.cut(x.tan, [0, 3, 5, 10, 20, 50, 1000])
for b, g in x.groupby('ob', observed=True):
    P(f'  {str(b):<12} {len(g):>5}頭 的中 {g.win.mean():5.1%} 回収 {g.ret.sum() / (100 * len(g)):5.0%}')
P(f'\n[EV-3] 本番：締切前（2分前、無ければ5分前）のオッズで選ぶ（{FWD}〜）')
f2 = fw[fw.o_pre.notna()]
for pc, pn in (('p_h', 'HORSE'), ('p_s', '合成')):
    _, e, o = choice[pc]
    a, b = stat(sel(f2, pc, 'o_pre', e, o)), stat(sel(f2, pc, 'tan', e, o))
    P(line(f'{pn} EV≥{e}・{o}倍以下（2分前で選ぶ）', a))
    P(line(f'{pn} 同じ基準（確定で選ぶ・比べ）', b))
P(f'  何も絞らない単勝（同じ期間）：{f2.ret.sum() / (100 * len(f2)):.0%}（{len(f2)}頭）')

# ---------- EV-4 市場と指数を混ぜた勝率で EV を出す（Benter 型）。重みは検証期間、確かめはテスト期間 ----------
from sklearn.linear_model import LogisticRegression
P('\n[EV-4] 市場の勝率と指数の勝率を混ぜて EV を出す（重みは検証期間で決め、テスト期間で確かめる。どちらも確定オッズ＝参考）')
for d in (df,):
    q = 1 / d.tan; d['p_m'] = q / q.groupby(d.race).transform('sum')
va, te = df[df.split2 == 'valid'], df[df.split2 == 'test']
for pc, pn in (('p_h', 'HORSE'), ('p_s', '合成')):
    X = lambda d: np.c_[np.log(d.p_m.clip(1e-4)), np.log(d[pc].clip(1e-4))]
    lr = LogisticRegression(C=10, max_iter=1000).fit(X(va), va.win)
    for d in (va, te):
        z = lr.decision_function(X(d)); e = pd.Series(np.exp(z), index=d.index)
        d['p_b'] = e / e.groupby(d.race).transform('sum')
    P(f'  {pn}：重み 市場 {lr.coef_[0][0]:+.2f}・指数 {lr.coef_[0][1]:+.2f}')
    for e_, o_ in ((1.05, 10), (1.1, 10), (1.1, 20), (1.2, 20), (1.3, 20), (1.2, 50)):
        a = sel(va, 'p_b', 'tan', e_, o_); b = stat(sel(te, 'p_b', 'tan', e_, o_))
        P(f'    EV≥{e_}・{o_}倍以下：検証 {a.ret.sum() / (100 * max(1, len(a))):.0%}（{len(a)}頭）｜テスト ' + (line('', b).strip() if b else '該当なし'))
