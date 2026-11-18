"""読み取りの確認（場ごと）。結果は件数と一致率だけを出す（データの中身は出さない）。

地方（ばんえい除く13場＋園田/姫路で14場）：
  各場の直近開催日（過去データにある最新日）から最初と最後のレースを選び、
  ・出馬表（nar.netkeiba shutuba）の馬番→馬名が過去データ（db.netkeiba の結果）と一致するか
  ・結果ページ（nar.netkeiba result）の着順・単勝払戻が db.netkeiba と一致するか
  ・単勝オッズAPI が db.netkeiba の確定単勝オッズと一致するか
  ・水分ボンバー（その日・そのレース）・かよちん（その日・その場）で指数が何頭分読めたか
  当日開催中の場は、当日の出馬表・オッズAPI・競馬ナビも読めるか。
中央（10場）：
  過去データ（JRA公式から取ったもの）の各場の最新開催日の1Rと最終Rを、db.netkeiba の同じレースと比べる
  （着順・馬名・タイム・単勝払戻・3連単払戻・確定単勝オッズ）。
"""
import gzip, json, os, re, sys, time, datetime, urllib.request, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import nk, ext

UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
JST = datetime.timezone(datetime.timedelta(hours=9))
today = datetime.datetime.now(JST).strftime('%Y%m%d')
_last = [0.0]


def get(u):
    w = 3.0 - (time.time() - _last[0])
    if w > 0:
        time.sleep(w)
    _last[0] = time.time()
    with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30) as r:
        return r.read()


def T(u):
    return get(u).decode('utf-8', 'replace')


def eqf(a, b, tol=0.05):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


rep = {'nar': {}, 'nar_today': {}, 'jra': {}}
DBG = []  # 食い違いの中身（暗号化して置く）

# ---------- 地方 ----------
D = sys.argv[1]
hist = {}
for fn in sorted(os.listdir(f'{D}/races')):
    with gzip.open(f'{D}/races/{fn}', 'rt') as f:
        for l in f:
            r = json.loads(l); hist[r['id']] = r
byp = {}
for r in hist.values():
    byp.setdefault(r['place'], []).append(r)
pay_missing = {}
for r in hist.values():
    m = pay_missing.setdefault(r['date'][:6], [0, 0]); m[1] += 1; m[0] += not r.get('payouts')
rep['nar_hist_no_payout_by_month'] = pay_missing
sbo_cache, kayo_cache = {}, {}
for code, name in nk.NAR_PLACES.items():
    if code == '65':
        continue
    rs = byp.get(code) or []
    if not rs:
        rep['nar'][name] = {'error': '過去データにこの場のレースがない'}; continue
    last = max(r['date'] for r in rs)
    day = sorted([r for r in rs if r['date'] == last], key=lambda r: r['rno'])
    pick = [day[0], day[-1]] if len(day) > 1 else day
    o = {'date': last, 'races': len(pick), 'shutuba': [0, 0], 'result_pos': [0, 0], 'result_tan': [0, 0], 'odds_api': [0, 0],
         'sbo': [0, 0], 'kayo': [0, 0], 'errors': []}
    for r in pick:
        rid = r['id']
        ref = {h['num']: h for h in r['runners'] if h.get('num')}
        try:
            s = nk.parse_shutuba(T(f'https://nar.netkeiba.com/race/shutuba.html?race_id={rid}'), rid)
            for h in s['runners']:
                o['shutuba'][1] += 1; o['shutuba'][0] += ref.get(h['num'], {}).get('horse') == h['horse']
        except Exception as e:  # noqa
            o['errors'].append('shutuba ' + str(e)[:60])
        try:
            res = nk.parse_nar_result(T(f'https://nar.netkeiba.com/race/result.html?race_id={rid}'))
            for n, h in ref.items():
                o['result_pos'][1] += 1; o['result_pos'][0] += (res['runners'].get(n) or {}).get('pos') == h.get('pos')
            a = [x['yen'] for x in (res['payouts'].get('単勝') or [])]; b = [x['yen'] for x in (r['payouts'].get('単勝') or [])]
            if not b:
                o.setdefault('db_no_payout', 0); o['db_no_payout'] += 1
            o['result_tan'][1] += 1; o['result_tan'][0] += bool(a) and sorted(a) == sorted(b)
            if not (a and sorted(a) == sorted(b)):
                DBG.append({'nar_tan': rid, 'result_page': res['payouts'], 'db': r['payouts']})
        except Exception as e:  # noqa
            o['errors'].append('result ' + str(e)[:60])
        try:
            j = json.loads(get(f'https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id={rid}&type=1&action=update'))
            od = j.get('ary_odds') or {}
            for n, h in ref.items():
                if h.get('tan') is None:
                    continue
                v = (od.get(f'{n:02d}') or od.get(str(n)) or {}).get('Odds')
                o['odds_api'][1] += 1; o['odds_api'][0] += eqf(v, h['tan'])
        except Exception as e:  # noqa
            o['errors'].append('odds ' + str(e)[:60])
        # 水分ボンバー
        try:
            if last not in sbo_cache:
                sbo_cache[last] = {(c, rn): u for c, rn, u in ext.sbo_day(T(f'https://nar.k-ba.net/{last}/'), last)}
            u = sbo_cache[last].get((code, r['rno']))
            o['sbo'][1] += len(ref)
            if u:
                v = ext.sbo_race(T(u))
                o['sbo'][0] += sum(1 for n in ref if (v.get(n) or {}).get('avg') is not None)
                miss = [n for n in ref if (v.get(n) or {}).get('avg') is None]
                if miss:
                    DBG.append({'sbo': rid, 'miss': [(n, ref[n].get('pos_text'), v.get(n)) for n in miss]})
        except Exception as e:  # noqa
            o['errors'].append('sbo ' + str(e)[:60])
        # かよちん
        try:
            if last[:6] not in kayo_cache:
                kayo_cache[last[:6]] = re.findall(r'<loc>([^<]+)</loc>', T(f'https://kayochinkeiba.com/sitemap-posttype-post.{last[:6]}.xml'))
            o['kayo'][1] += len(ref)
            for u in kayo_cache[last[:6]]:
                k = ext.kayo_url_key(u)
                if k and k == (last, code):
                    v = ext.kayo_post(T(u)).get(r['rno']) or {}
                    o['kayo'][0] += sum(1 for n in ref if v.get(n) is not None)
                    break
        except Exception as e:  # noqa
            o['errors'].append('kayo ' + str(e)[:60])
    rep['nar'][name] = o

# 能検：過去データの新馬戦（直近120日）の出走馬が、集めた能検の結果に名前で見つかるか（場ごと）
from keiba.noken import norm_name
NK = {}
if os.path.exists('nokendata/noken.jsonl'):
    for l in open('nokendata/noken.jsonl'):
        x = json.loads(l); NK.setdefault(x['horse'], []).append(x)
cut = (datetime.datetime.now(JST) - datetime.timedelta(days=120)).strftime('%Y%m%d')
rep['noken_shinba'] = {}
for r in hist.values():
    if r['date'] < cut or '新馬' not in (r.get('race_name') or '') or r['place'] == '65':
        continue
    o = rep['noken_shinba'].setdefault(r['place_name'], {'races': 0, 'horses': 0, 'found': 0, 'found_before_race': 0, 'with_time': 0, 'last_race': ''})
    o['races'] += 1; o['last_race'] = max(o['last_race'], r['date'])
    for h in r['runners']:
        o['horses'] += 1
        xs = NK.get(norm_name(h['horse'])) or []
        o['found'] += bool(xs)
        xb = [x for x in xs if (x.get('date') or '') <= r['date']]
        o['found_before_race'] += bool(xb)
        o['with_time'] += any(x.get('sec') for x in xb)

# 2歳の初出走馬（過去データで初めて出てきた2歳馬）で同じことを確認。新馬戦の名前が場ごとに違うため
first = {}
for r in sorted(hist.values(), key=lambda r: (r['date'], r['rno'])):
    for h in r['runners']:
        k = h.get('horse_id') or h['horse']
        if k not in first:
            first[k] = (r, h)
rep['noken_debut2'] = {}
for k, (r, h) in first.items():
    if r['date'] < cut or r['place'] == '65' or not re.search(r'2', h.get('sexage') or ''):
        continue
    o = rep['noken_debut2'].setdefault(r['place_name'], {'horses': 0, 'found_before_race': 0, 'with_time': 0, 'race_names': {}})
    o['horses'] += 1
    xb = [x for x in (NK.get(norm_name(h['horse'])) or []) if (x.get('date') or '') <= r['date']]
    o['found_before_race'] += bool(xb); o['with_time'] += any(x.get('sec') for x in xb)
    nm = re.sub(r'\d+', '#', r.get('race_name') or '')[:12]
    o['race_names'][nm] = o['race_names'].get(nm, 0) + 1
for o in rep['noken_debut2'].values():
    o['race_names'] = dict(sorted(o['race_names'].items(), key=lambda x: -x[1])[:5])

# 当日開催中の場：出馬表・オッズAPI・競馬ナビ
try:
    hl = T(f'https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={today}')
    ids = sorted(set(re.findall(r'race_id=(\d{12})', hl)))
    for code in sorted({i[4:6] for i in ids} - {'65'}):
        rid = [i for i in ids if i[4:6] == code][0]
        o = {'race_id_r': int(rid[10:12])}
        try:
            s = nk.parse_shutuba(T(f'https://nar.netkeiba.com/race/shutuba.html?race_id={rid}'), rid)
            o['shutuba_horses'] = len(s['runners']); o['shutuba_named'] = sum(1 for h in s['runners'] if h['horse'])
        except Exception as e:  # noqa
            o['shutuba_err'] = str(e)[:60]
        try:
            j = json.loads(get(f'https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id={rid}&type=1&action=update'))
            o['odds_n'] = len(j.get('ary_odds') or {}); o['odds_status'] = j.get('odds_status')
        except Exception as e:  # noqa
            o['odds_err'] = str(e)[:60]
        try:
            v = ext.knavi_race(T(ext.knavi_url(today, code, int(rid[10:12]))))
            o['knavi_n'] = len(v)
        except Exception as e:  # noqa
            o['knavi_err'] = str(e)[:60]
        rep['nar_today'][nk.NAR_PLACES.get(code, code)] = o
except Exception as e:  # noqa
    rep['nar_today']['error'] = str(e)[:100]

# ---------- 中央 ----------
J = {}
for fn in sorted(os.listdir('jradata/races')):
    for l in open(f'jradata/races/{fn}'):
        r = json.loads(l); J[r['id']] = r
jp = {}
for r in J.values():
    jp.setdefault(r['place_name'], []).append(r)
for name, rs in sorted(jp.items()):
    last = max(r['date'] for r in rs)
    day = sorted([r for r in rs if r['date'] == last], key=lambda r: r['rno'])
    pick = [day[0], day[-1]]
    o = {'date': last, 'horse': [0, 0], 'pos': [0, 0], 'time': [0, 0], 'tan_odds': [0, 0], 'pay_tan': [0, 0], 'pay_3tan': [0, 0], 'errors': []}
    for r in pick:
        nid = f"{r['date'][:4]}{r['place']}{r['kai']:02d}{r['day']:02d}{r['rno']:02d}"
        try:
            n = nk.parse_race(nk.decode(get(f'https://db.netkeiba.com/race/{nid}/')), nid)
            nb = {h['num']: h for h in n['runners'] if h.get('num')}
            for h in r['runners']:
                x = nb.get(h['num']) or {}
                o['horse'][1] += 1; o['horse'][0] += x.get('horse') == h['horse']
                o['pos'][1] += 1; o['pos'][0] += x.get('pos') == h.get('pos')
                if h.get('time'):
                    o['time'][1] += 1; o['time'][0] += x.get('time') == h['time']
                t = (r.get('odds') or {}).get(str(h['num']), {}).get('tan')
                if t is not None and x.get('tan') is not None:
                    o['tan_odds'][1] += 1; o['tan_odds'][0] += eqf(t, x['tan'])
            for k, key in (('単勝', 'pay_tan'), ('3連単', 'pay_3tan')):
                nkp = {kk.replace('三連', '3連'): vv for kk, vv in n['payouts'].items()}  # netkeiba は「三連単」表記
                a = sorted(p['yen'] for p in (r['payouts'].get(k) or [])); b = sorted(p['yen'] for p in (nkp.get(k) or []))
                o[key][1] += 1; o[key][0] += bool(a) and a == b
                if not (a and a == b):
                    DBG.append({'jra_pay': nid, 'kind': k, 'jra_keys': list(r['payouts']), 'nk_keys': list(n['payouts']), 'jra': a, 'nk': b})
        except Exception as e:  # noqa
            o['errors'].append(nid + ' ' + str(e)[:60])
    rep['jra'][name] = o

os.makedirs('vout', exist_ok=True)
json.dump(rep, open('vout/verify.json', 'w'), ensure_ascii=False, indent=1)
json.dump(DBG, open('vout/debug.json', 'w'), ensure_ascii=False, indent=1)
subprocess.run('bash scripts/seal.sh vout/debug.json vout/debug.sealed', shell=True, check=True)
print(json.dumps(rep, ensure_ascii=False, indent=1))
