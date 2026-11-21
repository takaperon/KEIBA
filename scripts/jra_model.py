"""中央版 HORSE指数（N5/N6、オーナー指示 2026-11-21「すぐに。検証もね」）。

地方の HORSE指数 v3 と同じ作り（keiba/nar_features.build：走破タイム指数・距離/コース/馬場適性・脚質・厩舎・馬体重・条件変化・当日要素）を
中央の結果データ（JRA公式から取った 2024-11〜）に当てはめる。中央向けの違い：
  ・場は「場コード＋芝ダ」で分ける（同じ距離でも芝とダートで時計が違うため）
  ・クラスは 新馬0 未勝利1 1勝2 2勝3 3勝4 OP/L5 G3 6 G2 7 G1 8
  ・騎手の成績（それより前のレースだけ、縮小推定）を足した版も作って比べる
期間：学習〜2025-08-31、検証 2025-09-01〜2025-12-31（打ち切り用）、テスト 2026-01-01〜
比べるもの：暫定指数（今アプリに出ているもの）／モデル（オッズ不使用）／モデル＋騎手／市場（確定単勝オッズ）
出力は集計値だけ。
"""
import json, os, re, sys, collections
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score, log_loss
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import nar_features as NF

TRAIN_END, VALID_END = '20250901', '20260101'
P = print
GR = {'GⅠ': 8, 'JpnⅠ': 8, 'GⅡ': 7, 'JpnⅡ': 7, 'GⅢ': 6, 'JpnⅢ': 6}


def jclass(r):
    if r.get('grade') in GR:
        return GR[r['grade']]
    c = (r.get('cls') or '') + ' ' + (r.get('race_name') or '')
    if '新馬' in c: return 0
    if '未勝利' in c: return 1
    if '1勝' in c or '500万' in c: return 2
    if '2勝' in c or '1000万' in c: return 3
    if '3勝' in c or '1600万' in c: return 4
    if re.search(r'オープン|OP|\(L\)|リステッド', c): return 5
    return None


def load(d='jradata/races'):
    rs = {}
    for fn in sorted(os.listdir(d)):
        for l in open(f'{d}/{fn}'):
            r = json.loads(l); rs[r['id']] = r
    out = []
    for r in rs.values():
        if r.get('surface') not in ('芝', 'ダ'):
            continue  # 障害は除く
        r = dict(r)
        r['place_code'] = r['place']
        r['place'] = r['place'] + r['surface']
        r['going'] = r.get('going_turf') if r['surface'] == '芝' else (r.get('going_dirt') or r.get('going_turf'))
        c = jclass(r)
        r['race_name'] = f'CLS:{c}' if c is not None else ''
        odds = r.get('odds') or {}
        for h in r['runners']:
            h['tan'] = (odds.get(str(h.get('num'))) or {}).get('tan')
            if h.get('pos') is None and h.get('pos_text') and any(x in h['pos_text'] for x in ('取', '除')):
                h['pos_text'] = '取'
        out.append(r)
    return sorted(out, key=lambda r: (r['date'], r.get('post_time') or '', r['place'], r['rno']))


NF.class_level = lambda s: int(s.split(':')[1]) if s and s.startswith('CLS:') else None


def jkey(h):
    """騎手の名前（減量記号▲△☆◇★と空白を除く。出馬表に騎手IDが無いので名前で合わせる）"""
    return re.sub(r'[▲△☆◇★\s　]', '', h.get('jockey') or '') or None


def jockey_feats(races):
    """騎手の成績（それより前のレースだけ）。全体・同じ場芝ダ。縮小推定"""
    J = collections.defaultdict(lambda: [0, 0, 0]); JV = collections.defaultdict(lambda: [0, 0, 0])
    out = {}
    for r in races:
        for h in r['runners']:
            k = jkey(h)
            a, b = J[k], JV[(k, r['place'])]
            out[(r['id'], h.get('num'))] = {'jk_top3': (a[2] + 0.25 * 30) / (a[0] + 30), 'jk_win': (a[1] + 0.08 * 30) / (a[0] + 30), 'jk_runs': a[0],
                                           'jkv_top3': (b[2] + 0.25 * 20) / (b[0] + 20)}
        for h in r['runners']:
            if h.get('pos_text') == '取' or h.get('pos') is None and not h.get('pos_text'):
                continue
            k = jkey(h)
            for x in (J[k], JV[(k, r['place'])]):
                x[0] += 1; x[1] += h.get('pos') == 1; x[2] += bool(h.get('pos')) and h['pos'] <= 3
    return out


def provisional(races):
    """今アプリに出ている暫定指数と同じ考え方：近4走の（クラス値 − 勝ち馬との差[秒]）の重み付き平均"""
    W = [1.0, 0.75, 0.55, 0.4]
    LV = {0: -0.8, 1: -0.7, 2: -0.3, 3: 0.0, 4: 0.25, 5: 0.45, 6: 0.6, 7: 0.75, 8: 1.0}
    hist = collections.defaultdict(list); out = {}
    for r in races:
        cl = LV.get(NF.class_level(r['race_name']), 0.3)
        win_t = next((NF.tsec(h.get('time')) for h in r['runners'] if h.get('pos') == 1), None)
        for h in r['runners']:
            ps = hist.get(h.get('horse_id'), [])[-4:][::-1]
            num = den = 0
            for w, (c, m) in zip(W, ps):
                num += w * (c - m); den += w
            out[(r['id'], h.get('num'))] = num / den if den else None
        for h in r['runners']:
            if h.get('pos_text') == '取':
                continue
            t = NF.tsec(h.get('time'))
            m = (t - win_t) if (t and win_t) else 2.0
            hist[h.get('horse_id')].append((cl, max(-1.0, min(3.0, m))))
    return out


REL = ['fig_best', 'fig_mean5', 'beaten_mean5', 'pospct_mean5', 'fig_last', 'pospct_last', 'dist_fit', 'venue_fit', 'going_fit',
       'corner1_pct', 'last3f_rel_mean', 'tr_top3', 'hw', 'kg', 'jk_top3', 'jk_win', 'jkv_top3']
KEEP = ['G1_基礎能力', 'G2_直近調子', 'G3_距離適性', 'G4_コース適性', 'G5_馬場適性', 'G6_枠順', 'G7_展開', 'G8_脚質', 'G9_厩舎', 'G12_馬体重', 'G13_条件変化', 'G14_当日要素']
JK = ['jk_top3', 'jk_win', 'jk_runs', 'jkv_top3']
PARAMS = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)


def frame(races, until):
    std = NF.build_standards(races, until)
    NF.build_variants(races, std)
    rows = NF.build(races, std)
    df = pd.DataFrame([dict(x['f'], race=x['race'], date=x['date'], num=x['num'], pos=x['pos'], tan=x['tan'], pop=x['pop']) for x in rows])
    jf = jockey_feats(races)
    for c in JK:
        df[c] = [jf.get((a, b), {}).get(c) for a, b in zip(df.race, df.num)]
    for c in REL:
        g = df.groupby('race')[c]
        df[c + '_z'] = (df[c] - g.transform('mean')) / g.transform('std').replace(0, np.nan)
    df['top3'] = ((df.pos >= 1) & (df.pos <= 3)).astype(int); df['win'] = (df.pos == 1).astype(int)
    base = ['field'] + sorted({c for g in KEEP for c in NF.GROUPS[g] + [x + '_z' for x in NF.GROUPS[g] if x in REL] if c != 'field'})
    withj = base + JK + [c + '_z' for c in JK if c + '_z' in df.columns]
    # 場のレベル差（VT、地方と同じ keiba/venue_level。場は「場コード＋芝ダ」、until より前だけで作る）
    from keiba import venue_level as VL
    vf, LVL, _ = VL.build(races, std, until, anchor='05芝')
    vt = base + VL.attach(df, races, vf)
    frame.LVL = LVL
    KN = [g for g in KEEP if g not in ('G5_馬場適性', 'G6_枠順', 'G7_展開')]
    frame.nar_same = ['field'] + sorted({c for g in KN for c in NF.GROUPS[g] + [x + '_z' for x in NF.GROUPS[g] if x in REL] if c != 'field'})
    return df, vt, withj, base


if __name__ == '__main__':
    races = load()
    P(f'中央（平地）{len(races)}レース {races[0]["date"]}〜{races[-1]["date"]}')
    df, base, withj, base0 = frame(races, TRAIN_END)
    pv = provisional(races)
    df['prov'] = [pv.get((a, b)) for a, b in zip(df.race, df.num)]
    df['mkt'] = 1 / df.tan; df['mkt'] = df.mkt / df.groupby('race').mkt.transform('sum')
    df = df[df.field >= 5].copy()
    df['split'] = np.where(df.date < TRAIN_END, 'train', np.where(df.date < VALID_END, 'valid', 'test'))
    for s in ('train', 'valid', 'test'):
        x = df[df.split == s]; P(f'  {s}: {x.race.nunique()}レース {len(x)}頭')

    def fit(cols, y):
        tr, va = df[df.split == 'train'], df[df.split == 'valid']
        return lgb.train(PARAMS, lgb.Dataset(tr[cols], tr[y]), 3000, valid_sets=[lgb.Dataset(va[cols], va[y])], callbacks=[lgb.early_stopping(100, verbose=False)])

    te = df[df.split == 'test'].copy()
    P('\n[N6] テスト期間（2026年）の当たり具合')
    P('  　　　　　　　　　　　　 3着以内 AUC / logloss　　1着 AUC / logloss')
    for nm, col in (('暫定指数（今のアプリ）', 'prov'), ('市場（確定単勝オッズ）', 'mkt')):
        x = te[te[col].notna()]
        P(f'  {nm:<20} {roc_auc_score(x.top3, x[col]):.3f}{"":<12} {roc_auc_score(x.win, x[col]):.3f}  （n={len(x)}）')
    preds = {}
    for cols, nm in ((frame.nar_same, 'HORSE（地方と同じ要素）'), (base0, 'HORSE（場の差なし）'), (base, 'HORSE＋場の差(VT)')):
        o = []
        for y in ('top3', 'win'):
            m = fit(cols, y); p = np.clip(m.predict(te[cols], num_iteration=m.best_iteration), 1e-6, 1 - 1e-6)
            o.append((roc_auc_score(te[y], p), log_loss(te[y], p))); preds[(nm, y)] = p
            if y == 'top3':
                imp = dict(zip(cols, m.feature_importance('gain')))
        P(f'  {nm:<20} {o[0][0]:.3f} / {o[0][1]:.4f}      {o[1][0]:.3f} / {o[1][1]:.4f}')
    tot = sum(imp.values()); top = sorted(imp.items(), key=lambda x: -x[1])[:12]
    P('    重要な要素（VT版）：' + '  '.join(f'{k} {v / tot:.0%}' for k, v in top))
    P('  場の補正 LVL（05芝=0、+は時計の割に強い場）：' + '  '.join(f'{k} {v:+.2f}' for k, v in sorted(frame.LVL.items(), key=lambda x: -x[1])))
    # 1位に推した馬の成績
    te['p_b'] = preds[('HORSE（場の差なし）', 'top3')]; te['p_j'] = preds[('HORSE＋場の差(VT)', 'top3')]
    te['tany'] = np.where(te.win == 1, te.tan * 100, 0)
    P('\n[N6] レース内1位の馬（テスト期間）')
    for col, nm in (('prov', '暫定指数1位'), ('p_b', 'HORSE1位'), ('p_j', 'HORSE+VT 1位'), ('mkt', '1番人気')):
        x = te[te[col].notna()]
        top = x.loc[x.groupby('race')[col].idxmax()]
        P(f'  {nm:<14} {len(top)}頭 勝率 {top.win.mean():5.1%} 3着内 {top.top3.mean():5.1%} 単勝回収 {top.tany.sum() / len(top):3.0f}%  平均人気 {top["pop"].mean():.1f}')
    # 偏りの確認：月ごと・場を移った馬・場ごと（VT版 vs 場の差なし）
    P('\n[VT] 偏りの確認（3着以内 AUC：VT版 vs 場の差なし）')
    te['month'] = te.date.str[:6]
    w = 0
    for mo, g in te.groupby('month'):
        a, b = roc_auc_score(g.top3, g.p_j), roc_auc_score(g.top3, g.p_b); w += a > b
        P(f'  {mo} n={len(g):>5}  VT {a:.3f}  なし {b:.3f}')
    P(f'  VT が良い月 {w}/{te.month.nunique()}')
    mv = te[te.lvl_from.notna() & (te.lvl_from.abs() > 1e-9)]
    st = te[te.lvl_from.notna() & (te.lvl_from.abs() <= 1e-9)]
    for nm, g in (('前走と違う場（芝ダ替わり含む）', mv), ('前走と同じ場', st)):
        if len(g) > 100:
            P(f'  {nm:<18} n={len(g):>5}  AUC VT {roc_auc_score(g.top3, g.p_j):.3f} なし {roc_auc_score(g.top3, g.p_b):.3f}  '
              f'logloss VT {log_loss(g.top3, np.clip(g.p_j, 1e-6, 1)):.4f} なし {log_loss(g.top3, np.clip(g.p_b, 1e-6, 1)):.4f}')
    te['pl'] = te.race.str.split('-').str[1]
    w = 0; n = 0
    for pl, g in te.groupby('pl'):
        if g.top3.nunique() > 1 and len(g) > 500:
            a, b = roc_auc_score(g.top3, g.p_j), roc_auc_score(g.top3, g.p_b); w += a > b; n += 1
    P(f'  VT が良い場 {w}/{n}')
