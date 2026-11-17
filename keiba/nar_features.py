"""地方：各出走馬の「そのレースより前」のデータだけから評価要素を作る（未来の情報は混ぜない）。

指示書の14項目のうち、データにあるものだけを作る。無いもの（調教・血統・水分量・外部指数）は作らない＝欠損。
オッズ・人気はここでは使わない（評価要素に入れない）。
"""
import re, math, collections

GOING = {'良': 0, '稍重': 1, '重': 2, '不良': 3}


def tsec(t):
    if not t:
        return None
    m = re.match(r'(?:(\d+):)?(\d+)\.(\d)', t)
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10


def class_level(name):
    n = name or ''
    if re.search(r'重賞|JpnⅠ|JpnⅡ|JpnⅢ|SP|S[123]|記念|賞典|グランプリ|ダービー|オークス|杯', n) and not re.search(r'[ABC]\d', n):
        return 10
    m = re.search(r'(?:^|[^A-Za-z])([ABC])\s*(\d)?(?![A-Za-z])', n)
    if not m:
        return None
    base = {'A': 8, 'B': 5, 'C': 1}[m.group(1)]
    sub = int(m.group(2)) if m.group(2) else 1
    return base + max(0, 3 - sub) if m.group(1) != 'C' else base + max(0, 4 - sub)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def build_standards(races, until):
    """基準タイム（場×距離×馬場）。until より前（学習期間）のデータだけで作る。"""
    acc = collections.defaultdict(list)
    for r in races:
        if r['date'] >= until:
            break
        g = GOING.get(r.get('going'))
        for h in r['runners']:
            t = tsec(h.get('time'))
            if t and h.get('pos'):
                acc[(r['place'], r.get('distance'), g)].append(t)
                acc[(r['place'], r.get('distance'), None)].append(t)
    std = {}
    for k, v in acc.items():
        if len(v) >= 60:
            v.sort()
            std[k] = v[len(v) // 2]
    return std


def raw_figure(r, h, std):
    t = tsec(h.get('time'))
    if not t or not r.get('distance'):
        return None
    s = std.get((r['place'], r['distance'], GOING.get(r.get('going')))) or std.get((r['place'], r['distance'], None))
    if not s:
        return None
    return (s - t) / (r['distance'] / 1000)


VARIANT = {}


def build_variants(races, std):
    """その日・その場の全完走馬の生指数の中央値＝その日の馬場の速さ。過去走の指数を作るときだけ使う（当日の予測には使わない）"""
    acc = collections.defaultdict(list)
    for r in races:
        for h in r['runners']:
            if h.get('pos'):
                f = raw_figure(r, h, std)
                if f is not None:
                    acc[(r['date'], r['place'])].append(f)
    VARIANT.clear()
    for k, v in acc.items():
        if len(v) >= 20:
            v.sort(); VARIANT[k] = v[len(v) // 2]


def figure(r, h, std):
    """走破タイムの指数：基準より1kmあたり何秒速いか（大きいほど良い）。日ごとの馬場差を引く"""
    f = raw_figure(r, h, std)
    if f is None:
        return None
    return f - VARIANT.get((r['date'], r['place']), 0.0)


GROUPS = {
    'G1_基礎能力': ['fig_best', 'fig_mean5', 'beaten_mean5', 'pospct_mean5', 'opp_mean5', 'fig_top2of5'],
    'G2_直近調子': ['fig_last', 'fig_trend', 'pospct_last', 'days_since', 'n_runs'],
    'G3_距離適性': ['dist_fit', 'dist_diff_last', 'dist_runs'],
    'G4_コース適性': ['venue_fit', 'venue_runs'],
    'G5_馬場適性': ['going_fit', 'going_runs'],
    'G6_枠順': ['num', 'num_pct', 'waku'],
    'G7_展開': ['front_cnt', 'style_x_front'],
    'G8_脚質': ['corner1_pct', 'corner_last_pct', 'gain_mean', 'last3f_rel_mean'],
    'G9_厩舎': ['tr_top3', 'tr_win', 'tr_runs'],
    'G12_馬体重': ['hw', 'hw_diff', 'hw_vs_mean'],
    'G13_条件変化': ['venue_changed', 'class_now', 'class_diff', 'first_in_data'],
    'G14_当日要素': ['kg', 'kg_diff', 'field', 'age', 'sex', 'going_now', 'dist_now'],
}
MISSING_GROUPS = {'G10_調教・追い切り': 'データに無い', 'G11_血統': '結果ページに父・母父が無い',
                  'G5の水分量(%)': '馬場状態（良〜不良）のみで含水率は無い', '外部指数（水分ボンバー・かよちん等）': 'データに無い'}


def build(races, std):
    """races は日付順。各出走馬に特徴量 dict を返す（rows）。"""
    hist = collections.defaultdict(list)
    tr = collections.defaultdict(lambda: [0, 0, 0])
    rows = []
    for r in races:
        field = len([h for h in r['runners'] if h.get('pos_text') not in ('取', '除')])
        g_now = GOING.get(r.get('going'))
        cls = class_level(r.get('race_name'))
        # 展開：今回のメンバーのうち、過去の1角位置が前（上位25%）だった馬の数
        fronts = 0
        for h in r['runners']:
            hs = hist.get(h.get('horse_id'), [])
            c1 = mean([x['c1'] for x in hs[-5:]])
            if c1 is not None and c1 <= 0.25:
                fronts += 1
        pre = [mean([x['fig'] for x in hist.get(h.get('horse_id'), [])[-5:]]) for h in r['runners']]
        opp = mean(pre)
        res_win = None
        for h in r['runners']:
            if h.get('pos') == 1:
                res_win = tsec(h.get('time'))
        l3 = sorted(h['last3f'] for h in r['runners'] if h.get('last3f'))
        l3med = l3[len(l3) // 2] if l3 else None
        for h in r['runners']:
            if h.get('pos_text') in ('取', '除'):
                continue
            hid = h.get('horse_id')
            hs = hist.get(hid, [])
            last5 = hs[-5:]
            f = {}
            figs = [x['fig'] for x in last5]
            f['n_runs'] = len(hs)
            f['first_in_data'] = 1 if not hs else 0
            f['fig_best'] = max([x for x in figs if x is not None], default=None)
            f['fig_mean5'] = mean(figs)
            f['beaten_mean5'] = mean([x['beaten'] for x in last5])
            f['opp_mean5'] = mean([x.get('opp') for x in last5])
            fs = sorted([x for x in figs if x is not None], reverse=True)
            f['fig_top2of5'] = mean(fs[:2]) if fs else None
            f['pospct_mean5'] = mean([x['pospct'] for x in last5])
            f['fig_last'] = hs[-1]['fig'] if hs else None
            f['fig_trend'] = (hs[-1]['fig'] - f['fig_mean5']) if hs and hs[-1]['fig'] is not None and f['fig_mean5'] is not None else None
            f['pospct_last'] = hs[-1]['pospct'] if hs else None
            f['days_since'] = (days(r['date']) - days(hs[-1]['date'])) if hs else None
            allm = mean([x['fig'] for x in hs])
            near = [x['fig'] for x in hs if x['dist'] and r.get('distance') and abs(x['dist'] - r['distance']) <= 100]
            f['dist_fit'] = (mean(near) - allm) if near and allm is not None and mean(near) is not None else None
            f['dist_runs'] = len(near)
            f['dist_diff_last'] = (r['distance'] - hs[-1]['dist']) if hs and hs[-1]['dist'] and r.get('distance') else None
            sv = [x['fig'] for x in hs if x['place'] == r['place']]
            f['venue_fit'] = (mean(sv) - allm) if sv and allm is not None and mean(sv) is not None else None
            f['venue_runs'] = len(sv)
            gg = (g_now or 0) >= 2
            sg = [x['fig'] for x in hs if x['going'] is not None and (x['going'] >= 2) == gg]
            f['going_fit'] = (mean(sg) - allm) if sg and allm is not None and mean(sg) is not None else None
            f['going_runs'] = len(sg)
            f['num'] = h.get('num')
            f['num_pct'] = h['num'] / field if h.get('num') and field else None
            f['waku'] = int(h['waku']) if str(h.get('waku') or '').isdigit() else None
            f['corner1_pct'] = mean([x['c1'] for x in last5])
            f['corner_last_pct'] = mean([x['cl'] for x in last5])
            f['gain_mean'] = mean([x['gain'] for x in last5])
            f['last3f_rel_mean'] = mean([x['l3rel'] for x in last5])
            f['front_cnt'] = fronts
            f['style_x_front'] = (f['corner1_pct'] * fronts) if f['corner1_pct'] is not None else None
            t = tr[trainer_key(h.get('trainer'))]
            f['tr_runs'] = t[0]
            f['tr_top3'] = (t[2] + 0.25 * 20) / (t[0] + 20)
            f['tr_win'] = (t[1] + 0.09 * 20) / (t[0] + 20)
            f['hw'] = h.get('hw')
            f['hw_diff'] = h.get('hw_diff')
            hwm = mean([x['hw'] for x in hs])
            f['hw_vs_mean'] = (h['hw'] - hwm) if h.get('hw') and hwm else None
            f['venue_changed'] = (1 if hs[-1]['place'] != r['place'] else 0) if hs else None
            f['class_now'] = cls
            f['class_diff'] = (cls - hs[-1]['cls']) if hs and cls is not None and hs[-1]['cls'] is not None else None
            f['kg'] = h.get('kg')
            f['kg_diff'] = (h['kg'] - hs[-1]['kg']) if hs and h.get('kg') and hs[-1]['kg'] else None
            f['field'] = field
            m = re.match(r'(\D)(\d+)', h.get('sexage') or '')
            f['sex'] = {'牡': 0, '牝': 1, 'セ': 2}.get(m.group(1)) if m else None
            f['age'] = int(m.group(2)) if m else None
            f['going_now'] = g_now
            f['dist_now'] = r.get('distance')
            rows.append({'race': r['id'], 'date': r['date'], 'place': r['place_name'], 'num': h.get('num'),
                         'pos': h.get('pos'), 'tan': h.get('tan'), 'pop': h.get('pop'), 'f': f})
        # レース後に履歴を更新（次のレースから使う）
        for h in r['runners']:
            if h.get('pos_text') in ('取', '除'):
                continue
            hid = h.get('horse_id')
            t = tsec(h.get('time'))
            cs = h.get('corners') or []
            hist[hid].append({
                'date': r['date'], 'place': r['place'], 'dist': r.get('distance'), 'going': g_now,
                'fig': figure(r, h, std), 'pos': h.get('pos'),
                'pospct': (h['pos'] - 1) / max(1, field - 1) if h.get('pos') else 1.0,
                'beaten': (t - res_win) if t and res_win else None,
                'c1': (cs[0] - 1) / max(1, field - 1) if cs else None,
                'cl': (cs[-1] - 1) / max(1, field - 1) if cs else None,
                'gain': ((cs[-1] - h['pos']) / max(1, field - 1)) if cs and h.get('pos') else None,
                'l3rel': (h['last3f'] - l3med) if h.get('last3f') and l3med else None,
                'hw': h.get('hw'), 'kg': h.get('kg'), 'cls': cls, 'opp': opp})
            t2 = tr[trainer_key(h.get('trainer'))]
            t2[0] += 1
            if h.get('pos') == 1:
                t2[1] += 1
            if h.get('pos') and h['pos'] <= 3:
                t2[2] += 1
    return rows


def trainer_key(t):
    t = re.sub(r'\[.*?\]|（.*?）|\(.*?\)', ' ', t or '').split()
    return t[-1] if t else None


_D = {}


def days(ds):
    if ds not in _D:
        import datetime
        _D[ds] = datetime.date(int(ds[:4]), int(ds[4:6]), int(ds[6:])).toordinal()
    return _D[ds]
