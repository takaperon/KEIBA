"""RO（2026-11-23 オーナー「どの券種でも回収率100％超えないかな？検証してみて。3連複は上位3頭のうち、血統◎を1頭軸にして相手は5頭」）。

テスト期間（中央 2026-01-01〜、地方 2025-11-17〜）で、指数の順位どおりに買ったときの券種ごとの回収率を出す。
指数：HORSE（オッズ不使用）、合成（HORSE＋外部。重みはテスト期間より前で決める）、参考に人気順（確定オッズの順なので締切前には分からない＝参考のみ）。
血統◎はテスト期間より前のデータだけで作る（アプリと同じ規則）。払戻はJRA公式／netkeibaの確定払戻（100円あたり）。
跳ねの確認：最高払戻を除いた回収率、上位1%の払戻を除いた回収率、月ごとに100%を超えた月の数、レースを選び直して作る95%の幅。
使い方：python3 scripts/roi.py jra   ／   python3 scripts/roi.py nar nardata extdata
"""
import gzip, json, os, sys, re, collections, itertools
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import ped_mark as PMK
P = print
MODE = sys.argv[1]
ped = json.load(open('peddata/ped.json'))
PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)
lg = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))

if MODE == 'jra':
    import importlib.util
    sp_ = importlib.util.spec_from_file_location('jm', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jra_model.py'))
    JM = importlib.util.module_from_spec(sp_); sp_.loader.exec_module(JM)
    races = JM.load()
    TRAIN_END, VALID_END = JM.TRAIN_END, JM.VALID_END
    df, _vt, _wj, cols = JM.frame(races, TRAIN_END)
    df = df[df.field >= 5].copy()
    df['split'] = np.where(df.date < TRAIN_END, 'train', np.where(df.date < VALID_END, 'valid', 'test'))
    pm_place = lambda r: r['place_code']
    # 合成：HORSE＋デイリーSP＋本紙の印（ext_daily と同じ）
    nid = {r['id']: f"{r['date'][:4]}{r['place_code']}{r['kai']:02d}{r['day']:02d}{r['rno']:02d}" for r in races if r.get('kai') and r.get('day')}
    DY = {}
    with gzip.open('dailydata/races.jsonl.gz', 'rt') as f:
        for l in f:
            x = json.loads(l); DY[x['id']] = {int(k): v for k, v in x['rows'].items()}
    tr, va = df[df.split == 'train'], df[df.split == 'valid']
    m = lgb.train(PARAMS, lgb.Dataset(tr[cols], tr.top3), 3000, valid_sets=[lgb.Dataset(va[cols], va.top3)], callbacks=[lgb.early_stopping(100, verbose=False)])
    df['h'] = m.predict(df[cols], num_iteration=m.best_iteration)
    df['sp'] = pd.to_numeric(pd.Series([((DY.get(nid.get(a)) or {}).get(b) or {}).get('sp') for a, b in zip(df.race, df.num)], index=df.index), errors='coerce')
    MK = {'◎': 4, '○': 3, '▲': 2, '△': 1, '☆': 1, '注': 1}
    mk = [MK.get(((DY.get(nid.get(a)) or {}).get(b) or {}).get('mark') or '', 0) for a, b in zip(df.race, df.num)]
    g = df.groupby('race').sp
    df['sp_z'] = ((df.sp - g.transform('mean')) / g.transform('std').replace(0, np.nan)).fillna(-1.5); df['sp_na'] = df.sp.isna().astype(int)
    for k in (1, 2, 3, 4):
        df[f'mk{k}'] = [int(v == k) for v in mk]
    df['lh'] = lg(df.h); df['has'] = [nid.get(a) in DY for a in df.race]
    C2 = ['lh', 'sp_z', 'sp_na', 'mk1', 'mk2', 'mk3', 'mk4']
    v2 = df[(df.split == 'valid') & df.has]
    lr = LogisticRegression(C=1.0, max_iter=1000).fit(v2[C2], v2.top3)
    df['s2'] = np.where(df.has, lr.predict_proba(df[C2])[:, 1], np.nan)
else:
    exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '_nar_frame.py')).read())
    pm_place = lambda r: r['place']
    tr, va = df[df.split == 'train'], df[df.split == 'valid']
    m = lgb.train(PARAMS, lgb.Dataset(tr[cols], tr.top3), 3000, valid_sets=[lgb.Dataset(va[cols], va.top3)], callbacks=[lgb.early_stopping(100, verbose=False)])
    df['h'] = m.predict(df[cols], num_iteration=m.best_iteration)
    c2 = cols + ['ext_w', 'ext_have']
    m2 = lgb.train(PARAMS, lgb.Dataset(tr[c2], tr.top3), 3000, valid_sets=[lgb.Dataset(va[c2], va.top3)], callbacks=[lgb.early_stopping(100, verbose=False)])
    df['s2'] = np.where(df.ext_have == 1, m2.predict(df[c2], num_iteration=m2.best_iteration), np.nan)

RACE = {r['id']: r for r in races}
for r in races:
    if MODE == 'jra':
        r['going_pm'] = r.get('going_turf') if r.get('surface') == '芝' else (r.get('going_dirt') or r.get('going_turf'))
    else:
        r['going_pm'] = r.get('going')
TEST = VALID_END
pmr = [dict(r, place=pm_place(r), going=r['going_pm']) for r in races]
good = PMK.build(pmr, ped, TEST)
hid = {(r['id'], h.get('num')): h.get('horse_id') for r in races for h in r['runners']}
pmv = []
for a, b in zip(df.race, df.num):
    p = ped.get(hid.get((a, b)) or '')
    r = RACE[a]
    pmv.append(PMK.mark(good, pm_place(r), r.get('surface'), r.get('distance'), r['going_pm'], p[0], p[2], r.get('place_name'))[0] if p else 0)
df['pm'] = pmv
df['mkt'] = 1 / df.tan
te = df[df.split == 'test'].copy()


# ---- 払戻 ----
def nums(s):
    return tuple(int(x) for x in re.findall(r'\d+', str(s)))


KIND = {'単勝': '単勝', '複勝': '複勝', 'ワイド': 'ワイド', '馬連': '馬連', '馬単': '馬単', '3連複': '3連複', '三連複': '3連複', '3連単': '3連単', '三連単': '3連単'}
ORD = {'馬単', '3連単'}
PAY = {}
for rid in te.race.unique():
    d = collections.defaultdict(dict)
    for k, v in (RACE[rid].get('payouts') or {}).items():
        kk = KIND.get(k)
        if not kk:
            continue
        for p in v or []:
            c = nums(p.get('combo'))
            if c and p.get('yen'):
                d[kk][c if kk in ORD else tuple(sorted(c))] = d[kk].get(c if kk in ORD else tuple(sorted(c)), 0) + float(p['yen'])
    if d.get('単勝') and d.get('3連複'):
        PAY[rid] = d
te = te[te.race.isin(PAY)]
P(f'{MODE}：テスト期間 {te.date.min()}〜{te.date.max()} {te.race.nunique()}レース（払戻のあるレース）。血統◎ {int((te.pm == 2).sum())}頭（{(te.pm == 2).mean():.1%}）')
P(f'  合成のあるレース {te[te.s2.notna()].race.nunique()}')


def tickets(name, rk, pmk):
    """rk：指数順の馬番リスト、pmk：馬番→血統印。(券種, [組]) を返す。買わないときは None"""
    a = rk
    if name == '単勝1位': return '単勝', [(a[0],)]
    if name == '複勝1位': return '複勝', [(a[0],)]
    if name == 'ワイド1-2': return 'ワイド', [(a[0], a[1])]
    if name == 'ワイド1軸-2〜4': return 'ワイド', [(a[0], x) for x in a[1:4]]
    if name == '馬連1-2': return '馬連', [(a[0], a[1])]
    if name == '馬連1軸-2〜5': return '馬連', [(a[0], x) for x in a[1:5]]
    if name == '馬単1→2': return '馬単', [(a[0], a[1])]
    if name == '3連複1-2-3': return '3連複', [tuple(a[:3])]
    if name == '3連複1軸-2〜6': return '3連複', [(a[0],) + c for c in itertools.combinations(a[1:6], 2)]
    if name == '3連複BOX1〜5': return '3連複', list(itertools.combinations(a[:5], 3))
    if name == '3連単1→2→3': return '3連単', [tuple(a[:3])]
    if name == '3連単1→2〜4→2〜4': return '3連単', [(a[0],) + c for c in itertools.permutations(a[1:4], 2)]
    if name.startswith('3連複 上位3頭の血統◎軸'):
        ax = [x for x in a[:3] if pmk.get(x) == 2]
        if not ax:
            return None
        ax = ax[0]; rest = [x for x in a if x != ax][:5]
        return '3連複', [(ax,) + c for c in itertools.combinations(rest, 2)]
    if name.startswith('複勝 上位3頭の血統◎'):
        ax = [x for x in a[:3] if pmk.get(x) == 2]
        return ('複勝', [(ax[0],)]) if ax else None
    if name.startswith('単勝 上位3頭の血統◎'):
        ax = [x for x in a[:3] if pmk.get(x) == 2]
        return ('単勝', [(ax[0],)]) if ax else None


BETS = ['単勝1位', '複勝1位', 'ワイド1-2', 'ワイド1軸-2〜4', '馬連1-2', '馬連1軸-2〜5', '馬単1→2', '3連複1-2-3', '3連複1軸-2〜6', '3連複BOX1〜5',
        '3連単1→2→3', '3連単1→2〜4→2〜4', '3連複 上位3頭の血統◎軸・相手5頭', '複勝 上位3頭の血統◎', '単勝 上位3頭の血統◎']
G = {rid: g for rid, g in te.groupby('race')}


def run(score, need=None):
    out = {}
    for b in BETS:
        recs = []
        for rid, g in G.items():
            if need is not None and g[need].isna().any():
                continue
            g = g.sort_values(score, ascending=False)
            if len(g) < 6:
                continue
            t = tickets(b, list(g.num.astype(int)), dict(zip(g.num.astype(int), g.pm)))
            if not t:
                continue
            kind, cs = t
            pay = sum(PAY[rid][kind].get(c if kind in ORD else tuple(sorted(c)), 0) for c in cs)
            recs.append((g.date.iloc[0][:6], len(cs) * 100, pay))
        out[b] = recs
    return out


def summary(recs):
    if not recs:
        return None
    a = np.array([(c, p) for _, c, p in recs], float)
    cost, pay = a[:, 0].sum(), a[:, 1].sum()
    hit = (a[:, 1] > 0).mean()
    srt = np.sort(a[:, 1])[::-1]
    k = max(1, int(len(srt) * 0.01))
    ex1 = (pay - srt[0]) / cost; ex1p = (pay - srt[:k].sum()) / cost
    mo = collections.defaultdict(lambda: [0, 0])
    for m, c, p in recs:
        mo[m][0] += c; mo[m][1] += p
    over = sum(1 for v in mo.values() if v[1] >= v[0])
    rng = np.random.default_rng(1); bs = []
    for _ in range(400):
        i = rng.integers(0, len(a), len(a)); bs.append(a[i, 1].sum() / a[i, 0].sum())
    return dict(n=len(a), pts=cost / 100 / len(a), hit=hit, roi=pay / cost, ex1=ex1, ex1p=ex1p, lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5),
                over=over, months=len(mo), maxshare=srt[0] / pay if pay else 0)


RES = {}
for sc, nm, need in (('h', 'HORSE', None), ('s2', '合成', 's2'), ('mkt', '人気順（参考：確定オッズ）', None)):
    R = run(sc, need)
    P(f'\n[RO] {nm} の順に買う（100円ずつ）')
    P(f'  {"買い方":<24}{"レース":>6}{"点/R":>5}{"的中率":>7}{"回収率":>7}  {"95%の幅":<13}{"最高1本除く":>9}{"上位1%除く":>9}{"100%超えた月":>9}')
    for b in BETS:
        s = summary(R[b])
        if not s:
            continue
        RES[(nm, b)] = s
        P(f'  {b:<24}{s["n"]:>6}{s["pts"]:>5.1f}{s["hit"]:>7.1%}{s["roi"]:>7.0%}  {s["lo"]:.0%}〜{s["hi"]:.0%}{"":<4}{s["ex1"]:>8.0%}{s["ex1p"]:>9.0%}{s["over"]:>6}/{s["months"]}')
    if nm == 'HORSE':
        RH = R
    if nm == '合成':
        RS = R
best = sorted(((v['roi'], k) for k, v in RES.items() if not k[0].startswith('人気')), reverse=True)[:5]
P('\n回収率の高い順（人気順を除く）：' + '  '.join(f'{k[0]}・{k[1]} {v:.0%}' for v, k in best))
# 依頼の買い方の月ごと
for nm, R in (('HORSE', RH), ('合成', RS)):
    recs = R['3連複 上位3頭の血統◎軸・相手5頭']
    mo = collections.defaultdict(lambda: [0, 0, 0])
    for m_, c, p in recs:
        mo[m_][0] += c; mo[m_][1] += p; mo[m_][2] += 1
    P(f'\n[RO] 3連複 上位3頭の血統◎軸・相手5頭（{nm}）月ごと：' + '  '.join(f'{k} {v[2]}R {v[1] / v[0]:.0%}' for k, v in sorted(mo.items())))
    big = sorted((p for _, _, p in recs), reverse=True)[:5]
    P(f'  払戻の大きい順（100円あたり）：{", ".join(f"{int(x):,}円" for x in big)}')

# ---- 場ごとの成績（2026-11-24 オーナー「地方で一番成績のいいところはどこ？」）----
from sklearn.metrics import roc_auc_score
PN = {r['id']: (r.get('place_name') or r['place']) for r in races}
te['pn'] = te.race.map(PN)
te['fk'] = [PAY[a]['複勝'].get((int(b),), 0) if t else 0 for a, b, t in zip(te.race, te.num, te.top3)]
te['tw'] = [PAY[a]['単勝'].get((int(b),), 0) if w else 0 for a, b, w in zip(te.race, te.num, te.win)]
P('\n[RO-場] 場ごと（テスト期間）：3着以内AUC、指数1位の 勝率・3着内率・単勝回収・複勝回収（HORSE ｜ 合成 ｜ 1番人気）')
rows = []
for pn, g in te.groupby('pn'):
    if g.race.nunique() < 150:
        continue
    o = [pn, g.race.nunique()]
    for c in ('h', 's2', 'mkt'):
        x = g[g[c].notna()]
        t = x.sort_values(c, ascending=False).groupby('race').head(1)
        o += [roc_auc_score(x.top3, x[c]), t.win.mean(), t.top3.mean(), t.tw.sum() / (100 * len(t)), t.fk.sum() / (100 * len(t))]
    rows.append(o)
rows.sort(key=lambda r: -r[2])
for o in rows:
    P(f'  {o[0]:<5} {o[1]:>5}R  HORSE AUC {o[2]:.3f} 1位 勝{o[3]:5.1%} 3内{o[4]:5.1%} 単{o[5]:4.0%} 複{o[6]:4.0%} ｜ 合成 AUC {o[7]:.3f} 勝{o[8]:5.1%} 3内{o[9]:5.1%} 単{o[10]:4.0%} 複{o[11]:4.0%} ｜ 人気 AUC {o[12]:.3f} 単{o[15]:4.0%} 複{o[16]:4.0%}')
