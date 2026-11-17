"""NAR-M2〜M6：地方の独自指数（HORSE SCORE・PLACE/PAIR PROBABILITY・FAIR ODDS・EV）の構築とバックテスト。

期間：学習 〜2025-08-15 ／ 検証（要素選択・閾値決め・確率校正）2025-08-16〜2025-11-16 ／ テスト 2025-11-17〜（最後に1回だけ見る）
オッズ・人気は能力評価に使わない。EV の計算と成績の内訳にだけ使う。出力は集計値だけ。
"""
import gzip, json, os, sys, collections, math
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, log_loss
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keiba import nar_features as NF
from baseline import band

D = sys.argv[1]
TRAIN_END, VALID_END = '20250816', '20251117'
P = print

races = {}
for fn in sorted(os.listdir(f'{D}/races')):
    with gzip.open(f'{D}/races/{fn}', 'rt') as f:
        for l in f:
            r = json.loads(l); races[r['id']] = r
races = sorted(races.values(), key=lambda r: (r['date'], r['post_time'] or '', r['place'], r['rno']))
RACE = {r['id']: r for r in races}
std = NF.build_standards(races, TRAIN_END)
NF.build_variants(races, std)
rows = NF.build(races, std)
df = pd.DataFrame([dict(x['f'], race=x['race'], date=x['date'], place=x['place'], num=x['num'], pos=x['pos'], tan=x['tan'], pop=x['pop']) for x in rows])
df['num_'] = df['num']
df = df[df['field'] >= 5].copy()
df['top3'] = ((df['pos'] >= 1) & (df['pos'] <= 3)).astype(int)
df['win'] = (df['pos'] == 1).astype(int)
# レース内の相対値（同じレースの他馬との比較）
REL = ['fig_best', 'fig_mean5', 'beaten_mean5', 'pospct_mean5', 'fig_last', 'pospct_last', 'dist_fit', 'venue_fit', 'going_fit',
       'corner1_pct', 'last3f_rel_mean', 'tr_top3', 'hw', 'kg']
for c in REL:
    g = df.groupby('race')[c]
    df[c + '_z'] = (df[c] - g.transform('mean')) / g.transform('std').replace(0, np.nan)
GROUPS = {k: v + [c + '_z' for c in v if c in REL] for k, v in NF.GROUPS.items()}
split = np.where(df['date'] < TRAIN_END, 'train', np.where(df['date'] < VALID_END, 'valid', 'test'))
df['split'] = split
P(f'出走（5頭以上のレース）: 学習 {sum(split == "train")} / 検証 {sum(split == "valid")} / テスト {sum(split == "test")} 頭')
P('作れなかった要素（欠損扱い）:', NF.MISSING_GROUPS)

PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)


def fit(cols, y='top3', rounds=2000):
    tr, va = df[df.split == 'train'], df[df.split == 'valid']
    m = lgb.train(PARAMS, lgb.Dataset(tr[cols], tr[y]), rounds, valid_sets=[lgb.Dataset(va[cols], va[y])],
                  callbacks=[lgb.early_stopping(100, verbose=False)])
    return m


def ll(m, cols, part, y='top3'):
    x = df[df.split == part]
    p = np.clip(m.predict(x[cols], num_iteration=m.best_iteration), 1e-6, 1 - 1e-6)
    return log_loss(x[y], p), roc_auc_score(x[y], p)


# ---- M3：各要素の単独の予測力と、全体から外したときの悪化（検証期間で判定） ----
BASE = ['field']
mb = fit(BASE)
b_ll, b_auc = ll(mb, BASE, 'valid')
P(f'\n[M3] 3着以内の予測。基準（頭数だけ）検証 logloss={b_ll:.4f} AUC={b_auc:.3f}')
allcols = BASE + sorted({c for v in GROUPS.values() for c in v if c != 'field'})
mfull = fit(allcols)
f_ll, f_auc = ll(mfull, allcols, 'valid')
P(f'全要素 検証 logloss={f_ll:.4f} AUC={f_auc:.3f}')
keep = []
P('要素グループ | 単独で頭数に足したとき logloss改善 / AUC | 全体から外したとき logloss悪化 | 判定')
for g, cols in GROUPS.items():
    cs = BASE + [c for c in cols if c != 'field']
    m1 = fit(cs); s_ll, s_auc = ll(m1, cs, 'valid')
    rest = [c for c in allcols if c not in cols or c == 'field']
    m2 = fit(rest); d_ll, _ = ll(m2, rest, 'valid')
    ok = (b_ll - s_ll) > 0.0005 and (d_ll - f_ll) > 0.0
    if ok:
        keep.append(g)
    P(f'  {g:<10} 単独 {b_ll - s_ll:+.4f} / {s_auc:.3f} | 外すと {d_ll - f_ll:+.4f} | {"採用" if ok else "不採用"}')
cols = BASE + sorted({c for g in keep for c in GROUPS[g] if c != 'field'})
P('採用:', keep)

# ---- M4：HORSE SCORE と PLACE PROBABILITY（校正つき） ----
m_place = fit(cols, 'top3')
m_win = fit(cols, 'win')
for nm, m, y in (('3着以内', m_place, 'top3'), ('1着', m_win, 'win')):
    for part in ('valid', 'test'):
        a, b = ll(m, cols, part, y)
        P(f'[M4] {nm} {part} logloss={a:.4f} AUC={b:.3f}')
df['raw_place'] = m_place.predict(df[cols], num_iteration=m_place.best_iteration)
df['raw_win'] = m_win.predict(df[cols], num_iteration=m_win.best_iteration)
iso_p = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=0.999).fit(df[df.split == 'valid'].raw_place, df[df.split == 'valid'].top3)
iso_w = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=0.999).fit(df[df.split == 'valid'].raw_win, df[df.split == 'valid'].win)
df['p_place'] = iso_p.predict(df.raw_place)
df['p_win'] = iso_w.predict(df.raw_win)
# レース内で合計をそろえる（1着=1頭、3着以内=3頭）
df['p_win'] = df['p_win'] / df.groupby('race')['p_win'].transform('sum')
df['p_place'] = (df['p_place'] / df.groupby('race')['p_place'].transform('sum') * df['field'].clip(upper=3)).clip(upper=0.98)
lg = np.log(df.raw_place / (1 - df.raw_place))
df['horse_score'] = 50 + 10 * (lg - lg[df.split == 'train'].mean()) / lg[df.split == 'train'].std()
te = df[df.split == 'test']
P('\n[M4] テスト期間の確率の当たり具合（予測 vs 実際）')
for lo, hi in ((0, .1), (.1, .2), (.2, .3), (.3, .4), (.4, .5), (.5, .6), (.6, .7), (.7, .8), (.8, 1)):
    x = te[(te.p_place >= lo) & (te.p_place < hi)]
    if len(x):
        P(f'  3着以内 予測{lo:.0%}-{hi:.0%} n={len(x):>6} 予測平均{x.p_place.mean():.1%} 実際{x.top3.mean():.1%}')
for lo, hi in ((0, .05), (.05, .1), (.1, .2), (.2, .3), (.3, .5), (.5, 1)):
    x = te[(te.p_win >= lo) & (te.p_win < hi)]
    if len(x):
        P(f'  1着   予測{lo:.0%}-{hi:.0%} n={len(x):>6} 予測平均{x.p_win.mean():.1%} 実際{x.win.mean():.1%}')
mk = te.copy(); mk['mkt'] = 1 / mk.tan; mk['mkt'] = mk.mkt / mk.groupby('race').mkt.transform('sum')
ok = mk.tan.notna()
P(f'  参考：1着の logloss（テスト）モデル={log_loss(mk[ok].win, mk[ok].p_win.clip(1e-4, .999)):.4f} ／ 市場オッズ={log_loss(mk[ok].win, mk[ok].mkt.clip(1e-4, .999)):.4f}（オッズは能力評価には使っていない。物差しとして比較）')
imp = sorted(zip(cols, m_place.feature_importance('gain')), key=lambda t: -t[1])
tot = sum(v for _, v in imp)
P('[M4] 3着以内モデルの重み（gain の割合）上位:', ', '.join(f'{c} {v / tot:.1%}' for c, v in imp[:20]))

# ---- M5：PAIR PROBABILITY（ワイド）— 1着確率から着順を多数回シミュレーション ----
rng = np.random.default_rng(3)


def pair_probs(g, sims=4000):
    p = g.p_win.values; n = len(p)
    gum = -np.log(-np.log(rng.random((sims, n))))
    order = np.argsort(-(np.log(p + 1e-9) + gum), axis=1)[:, :3]
    top = np.zeros((sims, n), bool)
    np.put_along_axis(top, order, True, axis=1)
    pr = (top[:, :, None] & top[:, None, :]).mean(0)
    return pr, top.mean(0)


# 払戻の見込み（学習期間の実績だけから）：複勝＝単勝オッズ帯別の的中時平均、ワイド＝2頭のオッズ帯の組合せ別の的中時平均
def bandkey(o):
    return band(o) if o and o == o else None


plp = collections.defaultdict(list); wdp = collections.defaultdict(list)
for r in races:
    if r['date'] >= TRAIN_END:
        break
    od = {h['num']: h.get('tan') for h in r['runners']}
    for x in r['payouts'].get('複勝', []):
        if x['combo'].isdigit() and od.get(int(x['combo'])):
            plp[bandkey(od[int(x['combo'])])].append(x['yen'])
    for x in r['payouts'].get('ワイド', []):
        a = [int(v) for v in x['combo'].split('-') if v.isdigit()]
        if len(a) == 2 and od.get(a[0]) and od.get(a[1]):
            k = tuple(sorted((bandkey(od[a[0]]), bandkey(od[a[1]]))))
            wdp[k].append(x['yen'])
EPL = {k: float(np.mean(v)) for k, v in plp.items() if len(v) >= 30}
EWD = {k: float(np.mean(v)) for k, v in wdp.items() if len(v) >= 30}

# ---- M6：バックテスト（閾値は検証期間で決め、テストに1回だけ当てる） ----
def pays(r, kind):
    return {x['combo']: x['yen'] for x in r['payouts'].get(kind, []) if x.get('yen')}


bets = []  # (part, race, kind, key, stake, ret, ev, extra)
for rid, g in df[df.split != 'train'].groupby('race', sort=False):
    r = RACE[rid]; part = g.split.iloc[0]
    g = g.sort_values('num')
    tan, fuku, wide = pays(r, '単勝'), pays(r, '複勝'), pays(r, 'ワイド')
    pr, sim_place = pair_probs(g)
    nums = g.num.astype(int).values
    axis_i = int(np.argmax(g.p_place.values))
    for i, h in enumerate(g.itertuples()):
        if h.tan and h.tan == h.tan:
            bets.append((part, rid, '単勝', str(nums[i]), h.p_win * h.tan, tan.get(str(nums[i]), 0), h))
            e = EPL.get(bandkey(h.tan))
            if e:
                bets.append((part, rid, '複勝', str(nums[i]), h.p_place * e / 100, fuku.get(str(nums[i]), 0), h))
    rowsg = list(g.itertuples())
    a = axis_i; ha = rowsg[a]
    for j in range(len(nums)):
        if j == a:
            continue
        hb = rowsg[j]
        if not (ha.tan == ha.tan and hb.tan == hb.tan and ha.tan and hb.tan):
            continue
        e = EWD.get(tuple(sorted((bandkey(ha.tan), bandkey(hb.tan)))))
        if not e:
            continue
        k = '-'.join(map(str, sorted((nums[a], nums[j]))))
        bets.append((part, rid, 'ワイド', k, pr[a, j] * e / 100, wide.get(k, 0), hb))
B = pd.DataFrame([dict(part=b[0], race=b[1], kind=b[2], key=b[3], ev=b[4], ret=b[5], hit=int(b[5] > 0),
                       pop=b[6].pop, tan=b[6].tan, place=b[6].place, dist=b[6].dist_now, going=b[6].going_now,
                       cls=b[6].class_now, score=b[6].horse_score, p_place=b[6].p_place) for b in bets])
P(f'\n[M6] 払戻見込み表：複勝 {len(EPL)} 帯・ワイド {len(EWD)} 組（学習期間の実績のみ）')
GRID = [0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.2]
chosen = {}
for kind in ('単勝', '複勝', 'ワイド'):
    P(f'\n  {kind}：EV閾値ごとの成績（検証期間 → テスト期間）')
    best = None
    for th in GRID:
        rowv = []
        for part in ('valid', 'test'):
            x = B[(B.part == part) & (B.kind == kind) & (B.ev >= th)]
            if kind == 'ワイド':
                x = x.sort_values('ev', ascending=False).groupby('race').head(3)
            n = len(x); roi = x.ret.sum() / (n * 100) if n else 0
            rowv.append((n, x.hit.mean() if n else 0, roi, x.race.nunique()))
        (vn, vh, vr, vrc), (tn, th_, tr, trc) = rowv
        P(f'    EV≥{th:<4} 検証 {vn:>6}点 的中{vh:5.1%} 回収{vr:6.1%} | テスト {tn:>6}点 {trc:>5}R 的中{th_:5.1%} 回収{tr:6.1%}')
        if vn >= 300 and (best is None or vr > best[1]):
            best = (th, vr)
    chosen[kind] = best[0] if best else None
P('\n  検証期間で選んだ閾値:', chosen)

te_races = df[df.split == 'test'].race.nunique()
for kind, th in chosen.items():
    if th is None:
        continue
    x = B[(B.part == 'test') & (B.kind == kind) & (B.ev >= th)]
    if kind == 'ワイド':
        x = x.sort_values('ev', ascending=False).groupby('race').head(3)
    n = len(x)
    P(f'\n[M6] テスト結果 {kind} EV≥{th}: {n}点 / {x.race.nunique()}R（見送り {te_races - x.race.nunique()}R）'
      f' 的中率{x.hit.mean():.1%} 回収率{x.ret.sum() / (n * 100):.1%} 1Rあたり収支{(x.ret.sum() - n * 100) / max(1, x.race.nunique()):+.0f}円')
    # 偏りの確認：上位3的中を除いた回収率・月別
    top = sorted(x.ret[x.ret > 0], reverse=True)
    P(f'    上位3的中を除いた回収率 {(x.ret.sum() - sum(top[:3])) / (n * 100):.1%}  最大配当 {top[0] if top else 0:.0f}円')
    x = x.assign(month=x.race.str[:6] if False else x.race.map(lambda r: RACE[r]['date'][:6]))
    for nm, key in (('月', 'month'), ('人気', 'pop'), ('オッズ帯', None), ('場', 'place'), ('距離', 'dist'), ('馬場', 'going'), ('クラス', 'cls')):
        k = x[key] if key else x.tan.map(bandkey)
        g = x.groupby(k).agg(n=('ret', 'size'), hit=('hit', 'mean'), ret=('ret', 'sum'))
        g = g[g.n >= 20]
        P(f'    {nm}別: ' + ' / '.join(f'{i} {int(v.n)}点 的中{v.hit:.0%} 回収{v.ret / (v.n * 100):.0%}' for i, v in g.iterrows()))

# 軸馬（HORSE SCORE 1位）の複勝率と、見送りの有効性
t = df[df.split == 'test'].sort_values('p_place', ascending=False).groupby('race').head(1)
fk = {rid: pays(RACE[rid], '複勝') for rid in t.race}
t = t.assign(fuku=[fk[r].get(str(int(n)), 0) for r, n in zip(t.race, t.num)])
P(f'\n[M6] 軸馬（各レースの3着以内確率1位）テスト: {len(t)}R 複勝率{t.top3.mean():.1%} 複勝回収{t.fuku.sum() / (len(t) * 100):.1%} 人気平均{t["pop"].mean():.2f}')
th = chosen.get('複勝')
if th:
    bet_r = set(B[(B.part == 'test') & (B.kind == '複勝') & (B.ev >= th)].race)
    a = t[t.race.isin(bet_r)]; b = t[~t.race.isin(bet_r)]
    P(f'    見送りの有効性（軸馬の複勝回収）: 買ったレース {a.fuku.sum() / max(1, len(a) * 100):.1%}（{len(a)}R） ／ 見送ったレース {b.fuku.sum() / max(1, len(b) * 100):.1%}（{len(b)}R）')
w = B[(B.part == 'test') & (B.kind == 'ワイド')]
P(f'    相手馬の期待値（ワイド、軸×相手の全組）: EV平均 {w.ev.mean():.2f} 実際の回収 {w.ret.sum() / (len(w) * 100):.1%}（{len(w)}点）')
