import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score, log_loss
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import nar_features as NF, venue_level as VL

D, E = sys.argv[2], sys.argv[3]
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

SB, KY = {}, {}
for r in races:
    e = ext.get((r['date'], r['place'], r['rno']))
    if not e:
        continue
    for k, D2 in (('sbo', SB), ('kayo', KY)):
        if e.get(k):
            for n, v in dev(e[k]).items():
                D2[(r['id'], n)] = v
df['sb'] = [SB.get((a, b), np.nan) for a, b in zip(df.race, df.num)]
df['ky'] = [KY.get((a, b), np.nan) for a, b in zip(df.race, df.num)]
df['ext_w'] = np.where(df.sb.notna() & df.ky.notna(), 0.2 * df.sb + 0.8 * df.ky, np.where(df.ky.notna(), df.ky, df.sb))
df['ext_have'] = (df.sb.notna() | df.ky.notna()).astype(int)
