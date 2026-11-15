"""暫定指数（未検証）。過去データの検証（N4〜N6）が終わるまでのつなぎ。

近4走の「勝ち馬との着差（秒）」をレースの格で補正して平均する、単純なもの。
回収率で検証していないので、買い目の根拠にはしない（画面にも未検証と出す）。
"""
import re

GRADE = {'GⅠ': 1.0, 'JpnⅠ': 0.9, 'GⅡ': 0.75, 'JpnⅡ': 0.65, 'GⅢ': 0.6, 'JpnⅢ': 0.5}
W = [1.0, 0.75, 0.55, 0.4]


def class_level(p):
    if p.get('grade') in GRADE:
        return GRADE[p['grade']]
    n = p.get('name') or ''
    if re.search(r'OP|オープン|\(L\)|Ｌ|リステッド', n):
        return 0.45
    if '3勝' in n:
        return 0.25
    if '2勝' in n:
        return 0.0
    if '1勝' in n:
        return -0.3
    if '未勝利' in n:
        return -0.7
    if '新馬' in n:
        return -0.8
    if p.get('rc') and not re.search(r'札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉', p['rc']):
        return -0.2  # 地方・海外は不明扱いで少し割り引く
    return 0.3  # 名前から分からない特別戦（多くは条件特別・OP）


def horse_score(past):
    num = den = 0.0
    used = 0
    for w, p in zip(W, past):
        m = p.get('margin')
        if m is None:
            if p.get('pos') is None:
                continue
            m = 2.0  # 着差が読めない（競走中止など）
        m = max(-1.0, min(3.0, m))
        num += w * (class_level(p) - m)
        den += w
        used += 1
    return (num / den if den else None), used


def score_race(race):
    xs = []
    for h in race['runners']:
        s, used = horse_score(h.get('past') or [])
        h['ps'] = s
        h['ps_runs'] = used
        if s is not None:
            xs.append(s)
    if xs:
        mu = sum(xs) / len(xs)
        sd = (sum((x - mu) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
    ranked = sorted([h for h in race['runners'] if h['ps'] is not None], key=lambda h: -h['ps'])
    for i, h in enumerate(ranked):
        h['ps_rank'] = i + 1
        h['ps_idx'] = round(50 + 10 * (h['ps'] - mu) / sd, 1)
    inv = [1 / h['odds'] for h in race['runners'] if h.get('odds')]
    tot = sum(inv) or 1
    for h in race['runners']:
        h['mkt_p'] = round((1 / h['odds']) / tot, 4) if h.get('odds') else None
        h.setdefault('ps_rank', None)
        h.setdefault('ps_idx', None)
        h['gap'] = bool(h['ps_rank'] and h['ps_rank'] <= 3 and h.get('pop') and h['pop'] >= 6)
    race['no_past'] = sum(1 for h in race['runners'] if not h.get('past'))
    return race
