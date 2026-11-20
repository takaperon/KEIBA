"""VT（オーナー指示 2026-11-20）：競馬場ごとの距離別の時計の違いを指数に入れると予測が良くなるか。

今の指数（fig）は「その場・距離・馬場の基準タイム（全完走馬の中央値）より 1km あたり何秒速いか」。
場の中でのものさしなので、場ごとの“レベル差”（例：盛岡の0と水沢の0が同じ強さか）は入っていない。

VT-1 基準タイムの場ごとの違い（同じ距離での比較。例：盛岡と水沢）
VT-2 場のレベル差の推定：続けて別の場を走った馬（転厩・遠征）の指数の差から、場ごとの補正値を最小二乗で求める（学習期間だけ）
     → 共通指数 figu = fig + 補正(場)
VT-3 場を移った次の1走の着順に対する予測力（生の時計／場の中の指数／共通指数）
VT-4 「この時計ならここでは上位」：今回の場・クラス・距離帯で3着以内に来た馬の共通指数の中央値（学習期間）との差
VT-5 モデル比較：今の要素 ＋ 新要素 で、テスト期間の 3着以内・1着 の logloss / AUC（全体・場替わりの馬だけ）
出力は集計値だけ。期間は v2 と同じ：学習〜2025-08-15、検証〜2025-11-16、テスト 2025-11-17〜
"""
import gzip, json, os, sys, collections
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score, log_loss
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import nar_features as NF

D = sys.argv[1]
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
NAME = {r['place']: r['place_name'] for r in races}
std = NF.build_standards(races, TRAIN_END)
NF.build_variants(races, std)

# ---------- VT-1 ----------
P('[VT-1] 基準タイム（学習期間・全完走馬の中央値、馬場問わず）')
by_d = collections.defaultdict(dict)
for (pl, d, g), v in std.items():
    if g is None and pl in NAME:
        by_d[d][pl] = v
for d in sorted(by_d):
    if len(by_d[d]) >= 2:
        xs = sorted(by_d[d].items(), key=lambda x: x[1])
        P(f'  {d}m: ' + '  '.join(f'{NAME[p]} {v // 60:.0f}:{v % 60:04.1f}' for p, v in xs))
for d in (1300, 1400, 1600, 1800, 2000):
    a, b = by_d.get(d, {}).get('35'), by_d.get(d, {}).get('36')
    if a and b:
        P(f'  盛岡と水沢 {d}m：水沢 − 盛岡 = {b - a:+.1f}秒')

# ---------- 全走の指数 ----------
runs = collections.defaultdict(list)  # horse_id -> [(date, place, fig, cls, dist, pos, field)]
for r in races:
    cls = NF.class_level(r.get('race_name'))
    field = sum(1 for h in r['runners'] if h.get('pos'))
    for h in r['runners']:
        if not h.get('pos') or not h.get('horse_id'):
            continue
        f = NF.figure(r, h, std)
        if f is not None:
            runs[h['horse_id']].append((r['date'], r['place'], f, cls, r.get('distance'), h['pos'], field, r['id']))

# ---------- VT-2 場のレベル差 ----------
pairs = []
for hid, rs in runs.items():
    for a, b in zip(rs, rs[1:]):
        if b[0] >= TRAIN_END:
            break
        if a[1] != b[1]:
            import datetime as dt
            gap = (dt.date(int(b[0][:4]), int(b[0][4:6]), int(b[0][6:])) - dt.date(int(a[0][:4]), int(a[0][4:6]), int(a[0][6:]))).days
            if gap <= 120:
                pairs.append((a[1], b[1], b[2] - a[2]))
places = sorted({p for a, b, _ in pairs for p in (a, b)})
ix = {p: i for i, p in enumerate(places)}
A = np.zeros((len(pairs) + 1, len(places))); y = np.zeros(len(pairs) + 1)
for k, (a, b, d) in enumerate(pairs):
    A[k, ix[a]] = 1; A[k, ix[b]] = -1; y[k] = d  # figB - figA ≈ lvlA - lvlB
anchor = ix.get('44', 0); A[-1, anchor] = 1; y[-1] = 0  # 大井を0
d_clip = np.clip(y[:-1], np.percentile(y[:-1], 1), np.percentile(y[:-1], 99)); y[:-1] = d_clip
LVL = dict(zip(places, np.linalg.lstsq(A, y, rcond=None)[0]))
cnt = collections.Counter(p for a, b, _ in pairs for p in (a, b))
P(f'\n[VT-2] 場のレベル補正（大井=0。1kmあたりの秒。大きいほどその場の0が強い）。使った「場を移った2走」 {len(pairs)}組（学習期間・120日以内）')
for p, v in sorted(LVL.items(), key=lambda x: -x[1]):
    P(f'  {NAME.get(p, p):<4} {v:+.2f}  （{cnt[p]}組）')

# ---------- 特徴量（各馬の過去走だけで作る） ----------
# 「ここで上位に来る水準」：学習期間、場×クラス×距離帯 の3着以内の共通指数の中央値
def dband(d):
    return 0 if not d else (1 if d <= 1200 else 2 if d <= 1500 else 3 if d <= 1800 else 4)
need = collections.defaultdict(list)
for hid, rs in runs.items():
    for x in rs:
        if x[0] < TRAIN_END and x[5] <= 3:
            need[(x[1], x[3], dband(x[4]))].append(x[2] + LVL.get(x[1], 0))
NEED = {k: float(np.median(v)) for k, v in need.items() if len(v) >= 30}
needp = collections.defaultdict(list)
for k, v in NEED.items():
    needp[(k[0], k[2])].append(v)

new = {}
for hid, rs in runs.items():
    for i, x in enumerate(rs):
        prev = rs[max(0, i - 5):i]
        if not prev:
            continue
        fu = [p[2] + LVL.get(p[1], 0) for p in prev]
        raw = [p[2] + 0 for p in prev]
        best_u = max(fu); mean_u = float(np.mean(fu)); top2u = float(np.mean(sorted(fu, reverse=True)[:2]))
        nd = NEED.get((x[1], x[3], dband(x[4])))
        if nd is None and needp.get((x[1], dband(x[4]))):
            nd = float(np.median(needp[(x[1], dband(x[4]))]))
        same = [p[2] for p in prev if p[1] == x[1]]
        new[(x[7], hid)] = {
            'figu_best': best_u, 'figu_mean5': mean_u, 'figu_top2': top2u, 'figu_last': fu[-1],
            'figu_vs_need': (top2u - nd) if nd is not None else None,
            'lvl_from': LVL.get(prev[-1][1], 0) - LVL.get(x[1], 0),  # 前走の場と今回の場のレベル差
            'fig_last_raw_place_moved': (1 if prev[-1][1] != x[1] else 0),
        }

# 生の時計（場の補正なし、1kmあたり秒）：比べるため
raw_t = {}
for r in races:
    for h in r['runners']:
        t = NF.tsec(h.get('time'))
        if t and r.get('distance') and h.get('pos'):
            raw_t[(r['id'], h.get('horse_id'))] = t / (r['distance'] / 1000)

# ---------- 基本の要素（v2と同じ作り） ----------
rows = NF.build(races, std)
df = pd.DataFrame([dict(x['f'], race=x['race'], date=x['date'], place=x['place'], num=x['num'], pos=x['pos'], horse_id=x.get('horse_id')) for x in rows])
if df['horse_id'].isna().all():
    hid_map = {(r['id'], h.get('num')): h.get('horse_id') for r in races for h in r['runners']}
    df['horse_id'] = [hid_map.get((a, b)) for a, b in zip(df.race, df.num)]
df = df[df['field'] >= 5].copy()
df['top3'] = ((df['pos'] >= 1) & (df['pos'] <= 3)).astype(int)
df['win'] = (df['pos'] == 1).astype(int)
NEWC = ['figu_best', 'figu_mean5', 'figu_top2', 'figu_last', 'figu_vs_need', 'lvl_from']
for c in NEWC:
    df[c] = [new.get((a, b), {}).get(c) for a, b in zip(df.race, df.horse_id)]
df = df.astype({c: float for c in NEWC})
REL = ['fig_best', 'fig_mean5', 'beaten_mean5', 'pospct_mean5', 'fig_last', 'pospct_last', 'dist_fit', 'venue_fit', 'going_fit',
       'corner1_pct', 'last3f_rel_mean', 'tr_top3', 'hw', 'kg', 'figu_best', 'figu_mean5', 'figu_top2', 'figu_last', 'figu_vs_need']
for c in REL:
    g = df.groupby('race')[c]
    df[c + '_z'] = (df[c] - g.transform('mean')) / g.transform('std').replace(0, np.nan)
df['split'] = np.where(df['date'] < TRAIN_END, 'train', np.where(df['date'] < VALID_END, 'valid', 'test'))

# ---------- VT-3 場を移った次の1走 ----------
P('\n[VT-3] 前走と違う場で走った馬（テスト期間）：レース内での順位づけの当たり具合（AUC。3着以内）')
mv = df[(df.split == 'test') & (df.venue_changed == 1)].copy()
mv['rawt_prev'] = np.nan
last_raw = {}
for hid, rs in runs.items():
    for i, x in enumerate(rs):
        if i:
            p = rs[i - 1]
            last_raw[(x[7], hid)] = raw_t.get((p[7], hid))
mv['rawt_prev'] = [-(last_raw.get((a, b)) or np.nan) for a, b in zip(mv.race, mv.horse_id)]
for c, nm in (('rawt_prev', '前走の生の時計（1kmあたり、速いほど良い）'), ('fig_last', '前走の場の中の指数（今の方式）'), ('figu_last', '前走の共通指数（場のレベル補正つき）'),
              ('fig_mean5', '近5走の場の中の指数の平均'), ('figu_mean5', '近5走の共通指数の平均'), ('figu_vs_need', '共通指数−今回の場・クラスで3着内に来る水準')):
    x = mv[[c, 'top3', 'race']].dropna()
    if len(x) > 100 and x.top3.nunique() == 2:
        P(f'  {nm:<34} AUC={roc_auc_score(x.top3, x[c]):.3f}  n={len(x)}')

# ---------- VT-5 モデル比較 ----------
PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)
base_cols = ['field'] + sorted({c for v in NF.GROUPS.values() for c in v if c != 'field'} | {c + '_z' for v in NF.GROUPS.values() for c in v if c in REL})
base_cols = [c for c in base_cols if c in df.columns]
new_cols = base_cols + [c for c in NEWC if c in df.columns] + [c + '_z' for c in NEWC if c + '_z' in df.columns]


def run(cols, yname):
    tr, va, te = df[df.split == 'train'], df[df.split == 'valid'], df[df.split == 'test']
    m = lgb.train(PARAMS, lgb.Dataset(tr[cols], tr[yname]), 3000, valid_sets=[lgb.Dataset(va[cols], va[yname])],
                  callbacks=[lgb.early_stopping(100, verbose=False)])
    p = np.clip(m.predict(te[cols], num_iteration=m.best_iteration), 1e-6, 1 - 1e-6)
    out = {'all': (log_loss(te[yname], p), roc_auc_score(te[yname], p))}
    mm = (te.venue_changed == 1).values
    out['moved'] = (log_loss(te[yname][mm], p[mm]), roc_auc_score(te[yname][mm], p[mm]))
    imp = dict(zip(cols, m.feature_importance('gain')))
    out['pred'] = p
    return out, imp


PRED = {}
P('\n[VT-5] モデル比較（テスト期間 2025-11-17〜。学習〜2025-08-15・検証で打ち切り）')
for yname, nm in (('top3', '3着以内'), ('win', '1着')):
    b, _ = run(base_cols, yname); n, imp = run(new_cols, yname)
    PRED[yname] = (b['pred'], n['pred'])
    for k, lab in (('all', '全頭'), ('moved', '前走と違う場')):
        P(f'  {nm} {lab:<7} 今の要素 logloss={b[k][0]:.4f} AUC={b[k][1]:.3f} → ＋場のレベル差 logloss={n[k][0]:.4f} AUC={n[k][1]:.3f}  （logloss {n[k][0] - b[k][0]:+.4f}）')
    tot = sum(imp.values())
    P('    新要素の重要度（全体に占める割合）: ' + '  '.join(f'{c} {imp.get(c, 0) / tot:.1%}' for c in NEWC + [c + '_z' for c in NEWC if c + '_z' in imp]))
n_te = int((df.split == 'test').sum()); n_mv = int(((df.split == 'test') & (df.venue_changed == 1)).sum())
P(f'  テスト頭数 {n_te}（うち前走と違う場 {n_mv}）')

# ---------- VT-6 偏りの確認：場ごと・月ごと（前走と違う場の馬、3着以内） ----------
te = df[df.split == 'test'].copy()
te['pb'], te['pn'] = PRED['top3']
P('\n[VT-6] 前走と違う場の馬：今回の場ごとの logloss の改善（3着以内、マイナスほど良くなった）')
x = te[te.venue_changed == 1]
for pl, g in sorted(x.groupby('place'), key=lambda kv: -len(kv[1])):
    if len(g) >= 300:
        P(f'  {pl:<4} n={len(g):>5}  {log_loss(g.top3, g.pn, labels=[0, 1]) - log_loss(g.top3, g.pb, labels=[0, 1]):+.4f}')
P('  月ごと:')
for mo, g in x.groupby(x.date.str[:6]):
    P(f'  {mo} n={len(g):>5}  {log_loss(g.top3, g.pn, labels=[0, 1]) - log_loss(g.top3, g.pb, labels=[0, 1]):+.4f}')
P('  前走の場のレベル差（今回の場から見て、前走の場が強い/弱い）ごと:')
for lo, hi, nm in ((-9, -0.3, '前走の場が弱い（0.3秒/km以上）'), (-0.3, 0.3, '同じくらい'), (0.3, 9, '前走の場が強い（0.3秒/km以上）')):
    g = x[(x.lvl_from > lo) & (x.lvl_from <= hi)]
    if len(g) > 100:
        P(f'  {nm:<22} n={len(g):>5}  {log_loss(g.top3, g.pn, labels=[0, 1]) - log_loss(g.top3, g.pb, labels=[0, 1]):+.4f}  実際の3着内率 {g.top3.mean():.1%}')
