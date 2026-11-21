"""BI（オーナー指示 2026-11-21）：前残り・差し・内枠・外枠の傾向と、開催何日目での変化。

1レースごとの「傾向」を結果だけから数える：
  前残り度 fb = （3着以内の馬の4角位置の平均）−（完走馬全体の4角位置の平均）。位置は 0=先頭 1=最後方。マイナスほど前残り、プラスほど差し
  内枠度   ib = （3着以内の馬の馬番の割合 num/頭数 の平均）−（全体の平均）。マイナスほど内、プラスほど外
BI-1 コースのもともとの傾向（学習期間、場・芝ダ・距離ごと）
BI-2 開催何日目での変化（中央は「4回東京11日」の日、地方は続けて開催した日数で数える）
BI-3 その日の前のレースの傾向が、後のレースでも続くか（テスト期間で相関）。前日の傾向も
BI-4 モデルに入れたとき：今の要素 ＋ 傾向（コース・開催日目・当日の前のレース）× 馬の脚質・馬番 で、テスト期間の 3着以内 logloss / AUC
当日の傾向は「そのレースより前に終わったレース」だけから作る（未来を混ぜない）。出力は集計値だけ。
使い方：python3 scripts/bias.py jra   ／   python3 scripts/bias.py nar nardata
"""
import gzip, json, os, sys, collections, datetime
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score, log_loss
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import nar_features as NF

P = print
MODE = sys.argv[1]


def _d(s):
    return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:]))


if MODE == 'jra':
    import importlib.util
    sp = importlib.util.spec_from_file_location('jm', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jra_model.py'))
    JM = importlib.util.module_from_spec(sp); sp.loader.exec_module(JM)
    races = JM.load()
    TRAIN_END, VALID_END = JM.TRAIN_END, JM.VALID_END
    df, _vt, _wj, cols = JM.frame(races, TRAIN_END)
    for r in races:
        r['meetday'] = r.get('day')
        r['vkey'] = r['place_code']
else:
    D = sys.argv[2]
    TRAIN_END, VALID_END = '20250816', '20251117'
    rs = {}
    for fn in sorted(os.listdir(f'{D}/races')):
        with gzip.open(f'{D}/races/{fn}', 'rt') as f:
            for l in f:
                r = json.loads(l)
                if r['place'] != '65':
                    rs[r['id']] = r
    races = sorted(rs.values(), key=lambda r: (r['date'], r.get('post_time') or '', r['place'], r['rno']))
    std = NF.build_standards(races, TRAIN_END)
    NF.build_variants(races, std)
    rows = NF.build(races, std)
    df = pd.DataFrame([dict(x['f'], race=x['race'], date=x['date'], num=x['num'], pos=x['pos'], tan=x['tan'], pop=x['pop']) for x in rows])
    from keiba import venue_level as VL
    vf, _, _ = VL.build(races, std, TRAIN_END)
    vl_cols = VL.attach(df, races, vf)
    REL = ['fig_best', 'fig_mean5', 'beaten_mean5', 'pospct_mean5', 'fig_last', 'pospct_last', 'dist_fit', 'venue_fit', 'going_fit',
           'corner1_pct', 'last3f_rel_mean', 'tr_top3', 'hw', 'kg']
    for c in REL:
        g = df.groupby('race')[c]
        df[c + '_z'] = (df[c] - g.transform('mean')) / g.transform('std').replace(0, np.nan)
    KEEP = ['G1_基礎能力', 'G2_直近調子', 'G3_距離適性', 'G4_コース適性', 'G8_脚質', 'G9_厩舎', 'G12_馬体重', 'G13_条件変化', 'G14_当日要素']
    cols = ['field'] + sorted({c for g in KEEP for c in NF.GROUPS[g] + [x + '_z' for x in NF.GROUPS[g] if x in REL] if c != 'field'}) + vl_cols
    df['top3'] = ((df.pos >= 1) & (df.pos <= 3)).astype(int); df['win'] = (df.pos == 1).astype(int)
    # 開催何日目：その場で続けて開催した日数（前の開催日から3日以上あいたら1日目に戻す）
    dates = collections.defaultdict(set)
    for r in races:
        dates[r['place']].add(r['date'])
    md = {}
    for pl, ds in dates.items():
        prev = None; n = 0
        for d in sorted(ds):
            n = n + 1 if prev and (_d(d) - _d(prev)).days <= 2 else 1
            md[(pl, d)] = n; prev = d
    for r in races:
        r['meetday'] = md[(r['place'], r['date'])]
        r['vkey'] = r['place']
NAME = {r['place']: (r.get('place_name') or r['place']) + (r.get('surface', '') if MODE == 'jra' else '') for r in races}


# ---------- 1レースごとの傾向 ----------
def race_bias(r):
    fin = [h for h in r['runners'] if h.get('pos') and h.get('corners') and h.get('num')]
    n = len(fin)
    if n < 6:
        return None
    cl = {h['num']: (h['corners'][-1] - 1) / max(1, n - 1) for h in fin}
    npc = {h['num']: (h['num'] - 1) / max(1, n - 1) for h in fin}
    top = [h['num'] for h in fin if h['pos'] <= 3]
    if len(top) < 3:
        return None
    return (np.mean([cl[k] for k in top]) - np.mean(list(cl.values())), np.mean([npc[k] for k in top]) - np.mean(list(npc.values())))


B = {}
for r in races:
    b = race_bias(r)
    if b:
        B[r['id']] = b
P(f'{MODE}：{len(races)}レース（傾向が数えられたレース {len(B)}）{races[0]["date"]}〜{races[-1]["date"]}')
P('  前残り度 fb：マイナスほど前残り・プラスほど差し。内枠度 ib：マイナスほど内枠・プラスほど外枠（どちらも3着以内の馬 − 全体）')
tr_r = [r for r in races if r['date'] < TRAIN_END and r['id'] in B]
fb_all = np.mean([B[r['id']][0] for r in tr_r]); ib_all = np.mean([B[r['id']][1] for r in tr_r])
P(f'  学習期間の平均：fb {fb_all:+.3f}  ib {ib_all:+.3f}（レース数 {len(tr_r)}）')

# ---------- BI-1 コースの傾向 ----------
P('\n[BI-1] コースのもともとの傾向（学習期間、40レース以上、場・距離ごと）')
C = collections.defaultdict(list)
for r in tr_r:
    C[(r['place'], r.get('distance'))].append(B[r['id']])
CB = {}
for k, v in sorted(C.items(), key=lambda x: (NAME.get(x[0][0], ''), x[0][1] or 0)):
    a = np.array(v)
    CB[k] = (a[:, 0].sum() / (len(a) + 30) + fb_all * 30 / (len(a) + 30), a[:, 1].sum() / (len(a) + 30) + ib_all * 30 / (len(a) + 30), len(a))
    if len(a) >= 40:
        se0 = a[:, 0].std() / np.sqrt(len(a)); se1 = a[:, 1].std() / np.sqrt(len(a))
        tag = []
        if a[:, 0].mean() - fb_all < -2 * se0: tag.append('前残り')
        if a[:, 0].mean() - fb_all > 2 * se0: tag.append('差し')
        if a[:, 1].mean() - ib_all < -2 * se1: tag.append('内枠')
        if a[:, 1].mean() - ib_all > 2 * se1: tag.append('外枠')
        P(f'  {NAME.get(k[0], k[0]):<6}{k[1]}m n={len(a):>4}  fb {a[:, 0].mean():+.3f}  ib {a[:, 1].mean():+.3f}  {"・".join(tag)}')
# 学習期間の傾向がテスト期間でも同じか
te_r = [r for r in races if r['date'] >= VALID_END and r['id'] in B]
T = collections.defaultdict(list)
for r in te_r:
    T[(r['place'], r.get('distance'))].append(B[r['id']])
ks = [k for k in CB if CB[k][2] >= 40 and len(T.get(k, [])) >= 20]
if len(ks) > 5:
    for j, nm in ((0, 'fb'), (1, 'ib')):
        x = [CB[k][j] for k in ks]; y = [np.mean([v[j] for v in T[k]]) for k in ks]
        P(f'  コースの傾向は続くか（{nm}、学習期間の値とテスト期間の値の相関、{len(ks)}コース）：{np.corrcoef(x, y)[0, 1]:+.2f}')

# ---------- BI-2 開催何日目 ----------
P('\n[BI-2] 開催何日目での変化（学習期間＋検証期間、全場まとめと場ごと）')
band = (lambda d: '1-2日' if d <= 2 else '3-4日' if d <= 4 else '5-6日' if d <= 6 else '7-8日' if d <= 8 else '9日〜') if MODE == 'jra' else \
       (lambda d: f'{d}日目' if d <= 5 else '6日目〜')
M = collections.defaultdict(list)
for r in races:
    if r['date'] < VALID_END and r['id'] in B and r.get('meetday'):
        M[('全体', band(r['meetday']))].append(B[r['id']])
        M[(r['place'], band(r['meetday']))].append(B[r['id']])
for pl in ['全体'] + sorted({k[0] for k in M if k[0] != '全体'}):
    xs = sorted((k[1], v) for k, v in M.items() if k[0] == pl)
    if sum(len(v) for _, v in xs) < 200:
        continue
    P(f'  {NAME.get(pl, pl):<6} ' + '  '.join(f'{b}(n{len(v)}) fb{np.mean([x[0] for x in v]):+.3f} ib{np.mean([x[1] for x in v]):+.3f}' for b, v in xs if len(v) >= 20))

# ---------- 当日の前のレース・前日の傾向（そのレースより前だけ） ----------
bykey = collections.defaultdict(list)  # (date, place) -> [(post_time, rno, id)]
for r in races:
    bykey[(r['date'], r['place'])].append(r)
SD = {}
prevday = {}
lastday = {}
for (d, pl), rs in sorted(bykey.items()):
    rs = sorted(rs, key=lambda r: r['rno'])
    for i, r in enumerate(rs):
        pr = [B[x['id']] for x in rs[:i] if x['id'] in B]
        SD[r['id']] = (np.mean([p[0] for p in pr]) if pr else None, np.mean([p[1] for p in pr]) if pr else None, len(pr))
    allb = [B[x['id']] for x in rs if x['id'] in B]
    if pl in lastday:
        for r in rs:
            prevday[r['id']] = lastday[pl]
    if allb:
        lastday[pl] = (np.mean([p[0] for p in allb]), np.mean([p[1] for p in allb]), len(allb))

P('\n[BI-3] その日の前のレースの傾向は、後のレースでも続くか（テスト期間。相関が0なら続かない）')
for nmin in (1, 2, 3, 5):
    xs = [(SD[r['id']], B[r['id']]) for r in te_r if SD[r['id']][2] >= nmin]
    if len(xs) > 200:
        c0 = np.corrcoef([a[0] for a, _ in xs], [b[0] for _, b in xs])[0, 1]
        c1 = np.corrcoef([a[1] for a, _ in xs], [b[1] for _, b in xs])[0, 1]
        P(f'  前のレース{nmin}以上（n={len(xs)}）：前残り度の相関 {c0:+.3f}  内枠度の相関 {c1:+.3f}')
xs = [(prevday[r['id']], B[r['id']]) for r in te_r if r['id'] in prevday]
if len(xs) > 200:
    P(f'  前の開催日の傾向（n={len(xs)}）：前残り度 {np.corrcoef([a[0] for a, _ in xs], [b[0] for _, b in xs])[0, 1]:+.3f}  '
      f'内枠度 {np.corrcoef([a[1] for a, _ in xs], [b[1] for _, b in xs])[0, 1]:+.3f}')
xs = [(CB.get((r['place'], r.get('distance'))), B[r['id']]) for r in te_r if CB.get((r['place'], r.get('distance')))]
P(f'  （比べ）コースのもともとの傾向（n={len(xs)}）：前残り度 {np.corrcoef([a[0] for a, _ in xs], [b[0] for _, b in xs])[0, 1]:+.3f}  '
  f'内枠度 {np.corrcoef([a[1] for a, _ in xs], [b[1] for _, b in xs])[0, 1]:+.3f}')
# 前のレースの傾向が強く出た日だけ
xs = [(SD[r['id']], B[r['id']]) for r in te_r if SD[r['id']][2] >= 3]
if xs:
    a = np.array([[s[0], s[1], b[0], b[1]] for s, b in xs])
    q = np.quantile(a[:, 0], [.2, .8]); q1 = np.quantile(a[:, 1], [.2, .8])
    P(f'  前のレースが前残りだった（下位20%）後のレース：fb {a[a[:, 0] <= q[0], 2].mean():+.3f}  差しだった（上位20%）後：fb {a[a[:, 0] >= q[1], 2].mean():+.3f}  全体 {a[:, 2].mean():+.3f}')
    P(f'  前のレースが内枠だった（下位20%）後のレース：ib {a[a[:, 1] <= q1[0], 3].mean():+.3f}  外枠だった（上位20%）後：ib {a[a[:, 1] >= q1[1], 3].mean():+.3f}  全体 {a[:, 3].mean():+.3f}')

# ---------- BI-4 モデル ----------
RD = {r['id']: r for r in races}
def put(name, fn):
    df[name] = pd.to_numeric(pd.Series([fn(RD[x]) for x in df.race], index=df.index), errors='coerce')
put('c_fb', lambda r: (CB.get((r['place'], r.get('distance'))) or (None,))[0])
put('c_ib', lambda r: (CB.get((r['place'], r.get('distance'))) or (None, None))[1])
put('meetday', lambda r: r.get('meetday'))
put('sd_fb', lambda r: SD[r['id']][0]); put('sd_ib', lambda r: SD[r['id']][1]); put('sd_n', lambda r: SD[r['id']][2])
put('pd_fb', lambda r: (prevday.get(r['id']) or (None,))[0]); put('pd_ib', lambda r: (prevday.get(r['id']) or (None, None))[1])
# 当日の傾向は少ないレースだと当てにならないので縮める（前のレース数 n、k=3）
df['sd_fb_s'] = df.sd_fb * df.sd_n / (df.sd_n + 3); df['sd_ib_s'] = df.sd_ib * df.sd_n / (df.sd_n + 3)
sty = df['corner_last_pct'] - 0.5; gate = df['num_pct'] - 0.5
for a in ('c_fb', 'sd_fb_s', 'pd_fb'):
    df[a + '_x'] = df[a] * sty
for a in ('c_ib', 'sd_ib_s', 'pd_ib'):
    df[a + '_x'] = df[a] * gate
df['md_x_gate'] = df.meetday * gate; df['md_x_sty'] = df.meetday * sty
extra = {
    'コースの傾向': ['c_fb', 'c_ib', 'c_fb_x', 'c_ib_x'],
    '＋開催日目': ['c_fb', 'c_ib', 'c_fb_x', 'c_ib_x', 'meetday', 'md_x_gate', 'md_x_sty'],
    '＋当日の前のレース': ['c_fb', 'c_ib', 'c_fb_x', 'c_ib_x', 'meetday', 'md_x_gate', 'md_x_sty', 'sd_fb_s', 'sd_ib_s', 'sd_n', 'sd_fb_s_x', 'sd_ib_s_x'],
    '＋前の開催日': ['c_fb', 'c_ib', 'c_fb_x', 'c_ib_x', 'meetday', 'md_x_gate', 'md_x_sty', 'sd_fb_s', 'sd_ib_s', 'sd_n', 'sd_fb_s_x', 'sd_ib_s_x', 'pd_fb', 'pd_ib', 'pd_fb_x', 'pd_ib_x'],
}
for c in ('num_pct', 'corner_last_pct'):
    if c not in cols:
        cols = cols + [c]
d2 = df[df.field >= 5].copy()
d2['split'] = np.where(d2.date < TRAIN_END, 'train', np.where(d2.date < VALID_END, 'valid', 'test'))
PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)
tr, va, te = d2[d2.split == 'train'], d2[d2.split == 'valid'], d2[d2.split == 'test'].copy()
P(f'\n[BI-4] モデルに入れたとき（テスト期間 {te.date.min()}〜 {te.race.nunique()}レース {len(te)}頭、3着以内）')
res = {}
for nm, cc in [('今のHORSE', cols)] + [(k, cols + v) for k, v in extra.items()]:
    m = lgb.train(PARAMS, lgb.Dataset(tr[cc], tr.top3), 3000, valid_sets=[lgb.Dataset(va[cc], va.top3)], callbacks=[lgb.early_stopping(100, verbose=False)])
    p = np.clip(m.predict(te[cc], num_iteration=m.best_iteration), 1e-6, 1 - 1e-6); te['p_' + nm] = p; res[nm] = p
    imp = dict(zip(cc, m.feature_importance('gain'))); tot = sum(imp.values())
    ex = '  '.join(f'{k} {imp[k] / tot:.1%}' for k in extra.get(nm, []) if imp.get(k, 0) / tot >= 0.003)
    P(f'  {nm:<12} AUC {roc_auc_score(te.top3, p):.4f}  logloss {log_loss(te.top3, p):.4f}  {("効いた要素：" + ex) if ex else ""}')
best = min(extra, key=lambda k: log_loss(te.top3, res[k]))
P(f'\n[BI-4] 偏りの確認（{best} vs 今のHORSE、logloss の差。マイナスなら良くなった）')
te['month'] = te.date.str[:6]; w = 0
for mo, g in te.groupby('month'):
    a = log_loss(g.top3, g['p_' + best], labels=[0, 1]) - log_loss(g.top3, g['p_今のHORSE'], labels=[0, 1]); w += a < 0
    P(f'  {mo} n={len(g):>5}  {a:+.4f}')
P(f'  良くなった月 {w}/{te.month.nunique()}')
te['vk'] = [RD[x]['vkey'] for x in te.race]; w = n = 0
for pl, g in te.groupby('vk'):
    if len(g) > 800:
        a = log_loss(g.top3, g['p_' + best], labels=[0, 1]) - log_loss(g.top3, g['p_今のHORSE'], labels=[0, 1]); w += a < 0; n += 1
        P(f'  {pl} n={len(g):>5}  {a:+.4f}')
P(f'  良くなった場 {w}/{n}')
# 当日の傾向がはっきりした日だけ
x = te[te.sd_n >= 3]
if len(x) > 1000:
    for nm in ('＋当日の前のレース', '＋前の開催日'):
        P(f'  前のレース3以上のレースだけ（n={len(x)}）{nm}：logloss の差 {log_loss(x.top3, x["p_" + nm]) - log_loss(x.top3, x["p_今のHORSE"]):+.4f}')

# ---------- BI-5 なぜ指数が良くならないか ----------
P('\n[BI-5] 傾向が出た日に、前に行きそうな馬（過去の4角位置が前1/3）は今のHORSEの予想より多く3着に来ているか（テスト期間）')
cur = {}
for r in races:
    fin = [h for h in r['runners'] if h.get('pos') and h.get('corners')]
    for h in fin:
        cur[(r['id'], h.get('num'))] = (h['corners'][-1] - 1) / max(1, len(fin) - 1)
te['cl_today'] = [cur.get((a, b)) for a, b in zip(te.race, te.num)]
x = te[te.cl_today.notna() & te.corner_last_pct.notna()]
P(f'  過去の4角位置と今回の4角位置の相関：{np.corrcoef(x.corner_last_pct, x.cl_today)[0, 1]:+.2f}（低いほど「前に行く馬」を当てにくい）')
te['sty3'] = pd.cut(te.corner_last_pct, [-1, 1 / 3, 2 / 3, 2], labels=['前', '中', '後'])
te['gate3'] = pd.cut(te.num_pct, [-1, 1 / 3, 2 / 3, 2], labels=['内', '中', '外'])
for key, lab, grp in (('sd_fb_s', '当日の前のレース', 'sty3'), ('pd_fb', '前の開催日', 'sty3'), ('c_fb', 'コース', 'sty3'),
                      ('sd_ib_s', '当日の前のレース', 'gate3'), ('pd_ib', '前の開催日', 'gate3'), ('c_ib', 'コース', 'gate3')):
    y = te[te[key].notna()]
    if key.startswith('sd'):
        y = y[y.sd_n >= 3]
    q = y[key].quantile([.2, .8]).values
    for nm, g in (('前残り/内枠が強い日（下位20%）', y[y[key] <= q[0]]), ('差し/外枠が強い日（上位20%）', y[y[key] >= q[1]])):
        s = '  '.join(f'{k}：実際{gg.top3.mean():.1%} 予想{gg["p_今のHORSE"].mean():.1%}' for k, gg in g.groupby(grp, observed=True))
        P(f'  {lab}・{nm}  {s}')

# ---------- BI-6 中央：開幕週（前の開催から間があいた初日・2日目）は前残り・内枠か ----------
if MODE == 'jra':
    P('\n[BI-6] 中央の開幕週（その場で4週間以上あいてからの開催の1〜2日目）の傾向。全期間。±は標準誤差')
    ds = collections.defaultdict(set)
    for r in races:
        ds[r['place_code']].add(r['date'])
    start = {}
    for r in races:
        if r.get('day') == 1:
            start[(r['place_code'], r['date'][:4], r.get('kai'))] = r['date']
    def gap(r):
        s = start.get((r['place_code'], r['date'][:4], r.get('kai')))
        if not s:
            return None
        prev = [d for d in ds[r['place_code']] if d < s]
        return (_d(s) - _d(max(prev))).days if prev else None
    G = {}
    for r in races:
        g = gap(r); dy = r.get('day') or 0
        if g is None:
            G[r['id']] = None
        elif g >= 28:
            G[r['id']] = '開幕週(1-2日)' if dy <= 2 else '開幕2週目(3-4日)' if dy <= 4 else '5日〜'
        else:
            G[r['id']] = '続けての開催(1-2日)' if dy <= 2 else '続けての開催(3日〜)'
    for sf in ('芝', 'ダ'):
        A = collections.defaultdict(list)
        for r in races:
            if r['id'] in B and G.get(r['id']) and r['surface'] == sf:
                A[G[r['id']]].append(B[r['id']])
        for k in ('開幕週(1-2日)', '開幕2週目(3-4日)', '5日〜', '続けての開催(1-2日)', '続けての開催(3日〜)'):
            a = np.array(A.get(k, []))
            if len(a) >= 30:
                P(f'  {sf} {k:<14} n={len(a):>4}  fb {a[:, 0].mean():+.3f}±{a[:, 0].std() / np.sqrt(len(a)):.3f}  ib {a[:, 1].mean():+.3f}±{a[:, 1].std() / np.sqrt(len(a)):.3f}')
    # 場ごと（芝・開幕週 vs その他）
    P('  場ごとの芝（開幕週 vs それ以外）')
    for pc in sorted({r['place_code'] for r in races}):
        a = np.array([B[r['id']] for r in races if r['place_code'] == pc and r['surface'] == '芝' and r['id'] in B and G.get(r['id']) == '開幕週(1-2日)'])
        b = np.array([B[r['id']] for r in races if r['place_code'] == pc and r['surface'] == '芝' and r['id'] in B and G.get(r['id']) and G[r['id']] != '開幕週(1-2日)'])
        if len(a) >= 15 and len(b) >= 30:
            P(f'  {NAME.get(pc + "芝", pc)} 開幕週 n={len(a):>3} fb {a[:, 0].mean():+.3f} ib {a[:, 1].mean():+.3f}  ／ それ以外 n={len(b):>3} fb {b[:, 0].mean():+.3f} ib {b[:, 1].mean():+.3f}')
    # 指数とのずれ（テスト期間）
    te['op'] = [G.get(x) for x in te.race]; te['sf'] = [RD[x]['surface'] for x in te.race]
    P('  テスト期間・芝：開幕週かどうかで、脚質・枠ごとの3着内率（実際／今のHORSEの予想）')
    for k in ('開幕週(1-2日)', '5日〜', '続けての開催(3日〜)'):
        y = te[(te.op == k) & (te.sf == '芝')]
        if len(y) > 300:
            s1 = '  '.join(f'{a}：{g.top3.mean():.1%}/{g["p_今のHORSE"].mean():.1%}' for a, g in y.groupby('sty3', observed=True))
            s2 = '  '.join(f'{a}：{g.top3.mean():.1%}/{g["p_今のHORSE"].mean():.1%}' for a, g in y.groupby('gate3', observed=True))
            P(f'  {k} n={len(y)}  脚質 {s1}  ｜ 枠 {s2}')
