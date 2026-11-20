"""PM-1b：印の付け方を厳しくしたらどうなるか（検証期間で選び、テスト期間で確認）。
元：PM-1/PM-2：血統の狙い目印は効くか（地方）。集めた途中の血統データ（約1.4万頭）で検証する。

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



from keiba import ped_mark as PMK
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

PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)


def fit(cs, y, d=df):
    tr, va = d[d.split == 'train'], d[d.split == 'valid']
    return lgb.train(PARAMS, lgb.Dataset(tr[cs], tr[y]), 3000, valid_sets=[lgb.Dataset(va[cs], va[y])], callbacks=[lgb.early_stopping(100, verbose=False)])


m3 = fit(cols, 'top3')
df['p3'] = m3.predict(df[cols], num_iteration=m3.best_iteration)

RACE = {r['id']: r for r in races}
hid = {(r['id'], h.get('num')): h.get('horse_id') for r in races for h in r['runners']}
# 学習期間の条件別成績（ped_mark と同じ数え方）。n・率・平均を持っておき、閾値ごとに選び直す
import collections
cnt = collections.defaultdict(lambda: [0, 0]); base = collections.defaultdict(lambda: [0, 0])
for r in races:
    if r['date'] >= TRAIN_END:
        continue
    c = PMK.conds(r['place'], r.get('surface'), r.get('distance'), r.get('going'))
    for h in r['runners']:
        if not h.get('pos') and not h.get('pos_text'):
            continue
        t3 = 1 if h.get('pos') and h['pos'] <= 3 else 0
        for a, v in c.items():
            b = base[(a, v)]; b[0] += 1; b[1] += t3
        p = ped.get(h.get('horse_id') or '')
        if p:
            for who, nm in (('父', p[0]), ('母父', p[2])):
                if nm:
                    for a, v in c.items():
                        x = cnt[(who, nm, a, v)]; x[0] += 1; x[1] += t3
ev = df[(df.split != 'train')].copy()
ev['hid'] = [hid.get((a, b)) for a, b in zip(ev.race, ev.num)]
ev = ev[[bool(ped.get(h or '')) for h in ev.hid]].copy()
ev['cond'] = [PMK.conds(RACE[a]['place'], RACE[a].get('surface'), RACE[a].get('distance'), RACE[a].get('going')) for a in ev.race]
ev['sire'] = [ped[h][0] for h in ev.hid]; ev['dams'] = [ped[h][2] for h in ev.hid]
pay = {}
for r in races:
    for p in (r.get('payouts') or {}).get('複勝') or []:
        try:
            pay[(r['id'], int(p['combo']))] = p['yen']
        except Exception:  # noqa
            pass
ev['fuku'] = [pay.get((a, int(b)), 0) if t else 0 for a, b, t in zip(ev.race, ev.num, ev.top3)]
P(f'評価する馬：検証 {int((ev.split == "valid").sum())}・テスト {int((ev.split == "test").sum())}（血統が分かる馬）')


def score(nmin, ratio, k, need2):
    good = {}
    for key, (n, t) in cnt.items():
        bn, bt = base[(key[2], key[3])]; br = bt / bn if bn else 0
        if n >= nmin and (t + k * br) / (n + k) >= br * ratio:
            good[key] = 1
    s_n = [sum(('父', s, a, v) in good for a, v in c.items()) for s, c in zip(ev.sire, ev.cond)]
    m_n = [sum(('母父', m, a, v) in good for a, v in c.items()) for m, c in zip(ev.dams, ev.cond)]
    th = 2 if need2 else 1
    mk = [2 if (a >= th and b >= th) else 1 if (a >= th or b >= th) else 0 for a, b in zip(s_n, m_n)]
    return np.array(mk)


P('\n規則ごとの結果。上積み＝実際の3着内率 − HORSE指数の見込み（同じ馬の平均）。人気差＝同じ人気帯の無印との3着内率の差の平均')
P('  規則                                    | 検証: 印率  ◎率  ◎上積み ○上積み 無印上積み | テスト: ◎n   ◎3着内 ◎上積み ◎人気差 ◎複回 | ○上積み')
rows_ = []
for nmin in (30, 60, 100):
    for ratio in (1.2, 1.3, 1.5):
        for need2 in (False, True):
            mk = score(nmin, ratio, 50, need2)
            ev['mk'] = mk
            out = {}
            for sp in ('valid', 'test'):
                x = ev[ev.split == sp]
                o = {}
                for v in (2, 1, 0):
                    g = x[x.mk == v]
                    o[v] = (len(g), g.top3.mean() if len(g) else np.nan, (g.top3 - g.p3).mean() if len(g) else np.nan, g.fuku.sum() / len(g) if len(g) else np.nan)
                # 同じ人気帯の無印との差
                diffs = []
                for lo, hi in ((1, 1), (2, 3), (4, 6), (7, 9), (10, 99)):
                    gg = x[(x['pop'] >= lo) & (x['pop'] <= hi)]
                    a2, z = gg[gg.mk == 2], gg[gg.mk == 0]
                    if len(a2) > 20 and len(z) > 20:
                        diffs.append((len(a2), a2.top3.mean() - z.top3.mean()))
                o['popdiff'] = sum(n * d for n, d in diffs) / sum(n for n, _ in diffs) if diffs else np.nan
                o['share'] = (x.mk >= 1).mean(); o['share2'] = (x.mk == 2).mean()
                out[sp] = o
            v_, t_ = out['valid'], out['test']
            nm = f'n≥{nmin} 平均×{ratio} {"2条件以上" if need2 else "1条件以上"}'
            rows_.append((v_[2][2], nm))
            P(f'  {nm:<26} | {v_["share"]:5.0%} {v_["share2"]:5.0%} {v_[2][2]:+6.1%} {v_[1][2]:+6.1%} {v_[0][2]:+6.1%} | {t_[2][0]:>6} {t_[2][1]:6.1%} {t_[2][2]:+6.1%} {t_["popdiff"]:+6.1%} {t_[2][3]:4.0f}% | {t_[1][2]:+6.1%}')
P('\n検証期間の ◎上積みが大きい順：' + ' / '.join(f'{nm}（{u:+.1%}）' for u, nm in sorted(rows_, reverse=True)[:4]))
