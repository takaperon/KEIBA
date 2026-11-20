"""血統の狙い目印（PM、2026-11-20 検証：テスト期間で同じHORSE見込みの馬より3着内率が0.5〜2.9ポイント高い。回収率は100%未満）。
父・母父それぞれ、条件（芝ダ×距離帯／芝ダ×馬場[良稍・重不良]／競馬場）ごとの3着内率を同じ条件の全馬平均に向けて縮め（k=50）、
n≥30 かつ 平均×1.2 以上なら得意条件。今回の条件で父・母父とも得意＝◎(2)、片方＝○(1)。"""
import collections

BANDN = {1: '〜1000', 2: '1100〜1300', 3: '1400〜1600', 4: '1700〜1900', 5: '2000〜'}
ASP = {'dist': '距離', 'going': '馬場', 'venue': '競馬場'}


def band(d):
    return 0 if not d else (1 if d <= 1000 else 2 if d <= 1300 else 3 if d <= 1600 else 4 if d <= 1900 else 5)


def conds(place, surface, distance, going):
    s = surface or '?'
    g = '重' if (going or '') in ('重', '不', '不良') else '良'
    return {'dist': f'{s}{band(distance)}', 'going': f'{s}{g}', 'venue': place}


def label(a, v, place_name=None):
    if a == 'dist':
        return f"{'ダ' if v[0] == 'ダ' else v[0]}{BANDN.get(int(v[1:]), '')}"
    if a == 'going':
        return f"{v[0]}・{'重/不良' if v[1] == '重' else '良/稍重'}"
    return place_name or v


def build(races, ped, until, k=50):
    cnt = collections.defaultdict(lambda: [0, 0]); base = collections.defaultdict(lambda: [0, 0])
    for r in races:
        if r['date'] >= until:
            continue
        c = conds(r['place'], r.get('surface'), r.get('distance'), r.get('going'))
        for h in r['runners']:
            if not h.get('pos') and not h.get('pos_text'):
                continue
            t3 = 1 if h.get('pos') and h['pos'] <= 3 else 0
            for a, v in c.items():
                b = base[(a, v)]; b[0] += 1; b[1] += t3
            p = ped.get(h.get('horse_id') or '')
            if not p:
                continue
            for who, nm in (('父', p[0]), ('母父', p[2])):
                if nm:
                    for a, v in c.items():
                        x = cnt[(who, nm, a, v)]; x[0] += 1; x[1] += t3
    good = {}
    for (who, nm, a, v), (n, t) in cnt.items():
        bn, bt = base[(a, v)]
        br = bt / bn if bn else 0
        if n >= 30 and (t + k * br) / (n + k) >= br * 1.2:
            good[(who, nm, a, v)] = (n, t / n, br)
    return good


def mark(good, place, surface, distance, going, sire, damsire, place_name=None):
    c = conds(place, surface, distance, going)
    why, s_ok, m_ok = [], False, False
    for who, nm in (('父', sire), ('母父', damsire)):
        for a, v in c.items():
            g = good.get((who, nm, a, v))
            if g:
                why.append(f'{who} {nm}：{label(a, v, place_name)} 3着内{g[1]:.0%}（全馬平均{g[2]:.0%}・{g[0]}走）')
                s_ok |= who == '父'; m_ok |= who == '母父'
    return (2 if s_ok and m_ok else 1 if (s_ok or m_ok) else 0), why
