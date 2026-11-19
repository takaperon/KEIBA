"""血統成績の検索用データを作る（アプリの「血統」欄で使う）。

過去データの各出走（取消・除外は除く）に、父・母父（peddata/ped.json）と条件を付けて列ごとの配列にする。
ブラウザ側で 父・母父・父×母父 で絞り込み、距離・芝ダ・馬場・回り別に集計する。
出力：appout/ped_chiho.json.gz・appout/ped_chuo.json.gz（このあと seal2 で暗号化）
"""
import gzip, json, os, sys

NAR, JRA, PED, OUT = 'nardata', 'jradata', 'peddata', 'appout'
os.makedirs(OUT, exist_ok=True)
ped = json.load(open(f'{PED}/ped.json')) if os.path.exists(f'{PED}/ped.json') else {}
course = json.load(open(f'{PED}/course.json')) if os.path.exists(f'{PED}/course.json') else {}
BANDS = [(1000, '〜1000'), (1300, '1100〜1300'), (1600, '1400〜1600'), (1900, '1700〜1900'), (2200, '2000〜2200'), (99999, '2300〜')]
SURF = {'芝': 0, 'ダ': 1, '障': 2}
GO = {'良': 0, '稍': 1, '稍重': 1, '重': 2, '不': 3, '不良': 3}
TURN = {'右': 0, '左': 1, '直線': 2}


def band(d):
    for i, (mx, _) in enumerate(BANDS):
        if d and d <= mx:
            return i
    return -1


def build(kind, races):
    sires, dams, places = {}, {}, {}
    idx = lambda dct, k: dct.setdefault(k, len(dct))
    C = {k: [] for k in 'smbfgtpwqv'}
    n_all = n_ped = 0
    dates = []
    for r in races:
        surf = SURF.get(r.get('surface'))
        if surf is None:
            continue
        if kind == 'chuo':
            det = r.get('course_detail') or ''
            turn = 2 if '直線' in det else (1 if '左' in det else (0 if '右' in det else 3))
            going = GO.get(r.get('going_turf') if surf == 0 else r.get('going_dirt'), 4)
            place = r['place_name']
        else:
            turn = TURN.get(course.get(f"{r['place']}|{r.get('surface')}|{r.get('distance')}"), 3)
            going = GO.get(r.get('going'), 4)
            place = r['place_name']
        pay = r.get('payouts') or {}
        win = {p['combo']: p['yen'] for p in pay.get('単勝') or [] if p.get('yen')}
        plc = {p['combo']: p['yen'] for p in pay.get('複勝') or [] if p.get('yen')}
        for h in r['runners']:
            pt = h.get('pos_text') or ''
            if h.get('pos') is None and any(x in pt for x in ('取', '除', '消')):
                continue
            n_all += 1
            pd = ped.get(h.get('horse_id') or '')
            if not pd:
                continue
            n_ped += 1
            num = str(h.get('num'))
            pos = h.get('pos') or 0
            C['s'].append(idx(sires, pd[0] or '?')); C['m'].append(idx(dams, pd[2] or '?'))
            C['b'].append(band(r.get('distance'))); C['f'].append(surf); C['g'].append(going); C['t'].append(turn)
            C['p'].append(pos)
            C['w'].append(int(win.get(num, 0) // 10) if pos == 1 else 0)
            C['q'].append(int(plc.get(num, 0) // 10) if pos and pos <= 3 else 0)
            C['v'].append(idx(places, place))
        dates.append(r['date'])
    out = {'v': 1, 'kind': kind, 'sires': list(sires), 'damsires': list(dams), 'places': list(places),
           'bands': [b for _, b in BANDS], 'cols': C, 'from': min(dates) if dates else None, 'to': max(dates) if dates else None,
           'runs_all': n_all, 'runs_with_ped': n_ped}
    with gzip.open(f'{OUT}/ped_{kind}.json.gz', 'wt') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(kind, 'runs', n_all, 'with ped', n_ped, 'sires', len(sires), 'damsires', len(dams))
    return n_all, n_ped


nar = {}
if os.path.isdir(f'{NAR}/races'):
    for fn in sorted(os.listdir(f'{NAR}/races')):
        with gzip.open(f'{NAR}/races/{fn}', 'rt') as f:
            for l in f:
                r = json.loads(l)
                if r['place'] != '65':
                    nar[r['id']] = r
jra = {}
if os.path.isdir(f'{JRA}/races'):
    for fn in sorted(os.listdir(f'{JRA}/races')):
        for l in open(f'{JRA}/races/{fn}'):
            r = json.loads(l); jra[r['id']] = r
st = {'chiho': build('chiho', nar.values()), 'chuo': build('chuo', jra.values())}
json.dump(st, open(f'{OUT}/ped_cov.json', 'w'))
