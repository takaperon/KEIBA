"""場のレベル差（VT、2026-11-20 検証済み）。

今の指数 fig は「その場・距離・馬場の基準タイムより1kmあたり何秒速いか」で、場の中のものさし。
場の“0”の強さは場ごとに違うので、続けて別の場を走った馬の指数の差から場ごとの補正（LVL）を求め、
共通指数 figu = fig + LVL[場] にする。さらに「今回の場・クラス・距離帯で3着以内に来た馬の共通指数の中央値」との差を出す。
LVL と水準は until より前のデータだけで作る（未来を混ぜない）。
"""
import collections, datetime
import numpy as np
from keiba import nar_features as NF

NEWC = ['figu_best', 'figu_mean5', 'figu_top2', 'figu_last', 'figu_vs_need', 'lvl_from']
REL_NEW = ['figu_best', 'figu_mean5', 'figu_top2', 'figu_last', 'figu_vs_need']


def _d(s):
    return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:]))


def dband(d):
    return 0 if not d else (1 if d <= 1200 else 2 if d <= 1500 else 3 if d <= 1800 else 4)


def build(races, std, until, anchor='44'):
    """races は日付順（当日分を含んでよい。当日分は pos が無いので履歴には入らない）。
    戻り値：({(race_id, horse_id): {新要素}}, LVL, NEED)"""
    runs = collections.defaultdict(list)
    for r in races:
        cls = NF.class_level(r.get('race_name'))
        for h in r['runners']:
            if h.get('pos') and h.get('horse_id'):
                f = NF.figure(r, h, std)
                if f is not None:
                    runs[h['horse_id']].append((r['date'], r['place'], f, cls, r.get('distance'), h['pos']))
    # 場のレベル差（until より前の「場を移った2走」・120日以内）
    pairs = []
    for rs in runs.values():
        for a, b in zip(rs, rs[1:]):
            if b[0] >= until:
                break
            if a[1] != b[1] and (_d(b[0]) - _d(a[0])).days <= 120:
                pairs.append((a[1], b[1], b[2] - a[2]))
    places = sorted({p for a, b, _ in pairs for p in (a, b)})
    LVL = {}
    if pairs:
        ix = {p: i for i, p in enumerate(places)}
        A = np.zeros((len(pairs) + 1, len(places))); y = np.zeros(len(pairs) + 1)
        for k, (a, b, d) in enumerate(pairs):
            A[k, ix[a]] = 1; A[k, ix[b]] = -1; y[k] = d
        A[-1, ix.get(anchor, 0)] = 1
        y[:-1] = np.clip(y[:-1], np.percentile(y[:-1], 1), np.percentile(y[:-1], 99))
        LVL = dict(zip(places, np.linalg.lstsq(A, y, rcond=None)[0]))
    need = collections.defaultdict(list)
    for rs in runs.values():
        for x in rs:
            if x[0] < until and x[5] <= 3:
                need[(x[1], x[3], dband(x[4]))].append(x[2] + LVL.get(x[1], 0))
    NEED = {k: float(np.median(v)) for k, v in need.items() if len(v) >= 30}
    needp = collections.defaultdict(list)
    for k, v in NEED.items():
        needp[(k[0], k[2])].append(v)
    # 各出走（当日分も）に、それより前の走だけで要素を作る
    out = {}
    seen = collections.defaultdict(list)
    for r in races:
        cls = NF.class_level(r.get('race_name'))
        for h in r['runners']:
            hid = h.get('horse_id')
            prev = seen.get(hid, [])[-5:] if hid else []
            if not prev:
                continue
            fu = [p[2] + LVL.get(p[1], 0) for p in prev]
            top2 = float(np.mean(sorted(fu, reverse=True)[:2]))
            nd = NEED.get((r['place'], cls, dband(r.get('distance'))))
            if nd is None and needp.get((r['place'], dband(r.get('distance')))):
                nd = float(np.median(needp[(r['place'], dband(r.get('distance')))]))
            out[(r['id'], hid)] = {'figu_best': max(fu), 'figu_mean5': float(np.mean(fu)), 'figu_top2': top2, 'figu_last': fu[-1],
                                   'figu_vs_need': (top2 - nd) if nd is not None else None,
                                   'lvl_from': LVL.get(prev[-1][1], 0) - LVL.get(r['place'], 0)}
        for h in r['runners']:
            if h.get('pos') and h.get('horse_id'):
                f = NF.figure(r, h, std)
                if f is not None:
                    seen[h['horse_id']].append((r['date'], r['place'], f))
    return out, LVL, NEED


def attach(df, races, feats):
    """df（race, num 列あり）に新要素とレース内の相対値を足す"""
    import pandas as pd
    hid = {(r['id'], h.get('num')): h.get('horse_id') for r in races for h in r['runners']}
    keys = [(a, hid.get((a, b))) for a, b in zip(df['race'], df['num'])]
    for c in NEWC:
        df[c] = pd.to_numeric(pd.Series([feats.get(k, {}).get(c) for k in keys], index=df.index), errors='coerce')
    for c in REL_NEW:
        g = df.groupby('race')[c]
        df[c + '_z'] = (df[c] - g.transform('mean')) / g.transform('std').replace(0, np.nan)
    return NEWC + [c + '_z' for c in REL_NEW]
