"""アプリ用データ：当日の中央・地方の出馬表＋指数を作り、暗号化して app-data ブランチへ（scripts/seal.sh）。

地方：nar.netkeiba の当日出馬表と単勝オッズ（API）。指数は v2 と同じ要素・同じ作り方で、
      過去2年分（キャッシュ）全部で学習し、直近60日で確率校正したモデル。オッズは EV にだけ使う。
      v2 はテストで回収率100%を超えなかったので、推奨買い目は出さない（全レース「見送り」）。
中央：JRA公式の当日出馬表（scripts/today.py と同じ）。中央の独自指数は検証前なので、暫定指数（未検証）を表示。
"""
import gzip, json, os, re, sys, time, datetime, urllib.request
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import nk, nar_features as NF, jra, ext
from keiba.provisional import score_race

UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
JST = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(JST)
day = now.strftime('%Y%m%d')
_fix = os.path.join(os.path.dirname(__file__), 'app_day.txt')  # 検証用：過去の日付で作る
if os.path.exists(_fix):
    day = open(_fix).read().strip()
    now = datetime.datetime(int(day[:4]), int(day[4:6]), int(day[6:]), 23, 59, tzinfo=JST)
_last = [0.0]


def get(u, data=None):
    w = 3.0 - (time.time() - _last[0])
    if w > 0:
        time.sleep(w)
    _last[0] = time.time()
    req = urllib.request.Request(u, data=data, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


out = {'date': day, 'built_at': now.strftime('%Y-%m-%d %H:%M'), 'modes': {}, 'notes': {}}

# ---------- 地方 ----------
try:
    D = sys.argv[1]
    hist = {}
    for fn in sorted(os.listdir(f'{D}/races')):
        with gzip.open(f'{D}/races/{fn}', 'rt') as f:
            for l in f:
                r = json.loads(l); hist[r['id']] = r
    hist = sorted(hist.values(), key=lambda r: (r['date'], r['post_time'] or '', r['place'], r['rno']))
    hl = get(f'https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={day}').decode('utf-8', 'replace')
    ids = [i for i in sorted(set(re.findall(r'race_id=(\d{12})', hl))) if i[4:6] != '65']
    today = []
    for rid in ids:
        try:
            r = nk.parse_shutuba(get(f'https://nar.netkeiba.com/race/shutuba.html?race_id={rid}').decode('utf-8', 'replace'), rid)
            j = json.loads(get(f'https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id={rid}&type=1&action=update'))
            od = j.get('ary_odds') or {}
            for h in r['runners']:
                o = od.get(f"{h['num']:02d}") or od.get(str(h['num'])) or {}
                if o.get('Odds') and re.fullmatch(r'\d+(\.\d+)?', str(o['Odds'])) and float(o['Odds']) > 0:
                    h['tan'] = float(o['Odds']); h['pop'] = int(o['Ninki']) if str(o.get('Ninki', '')).isdigit() else h['pop']
            r['odds_status'] = j.get('odds_status')
            today.append(r)
        except Exception as e:  # noqa
            print('ERR', rid, e)
    train_end = '20250816'
    std = NF.build_standards(hist, train_end)
    NF.build_variants(hist, std)
    rows = NF.build(hist + today, std)
    df = pd.DataFrame([dict(x['f'], race=x['race'], date=x['date'], num=x['num'], pos=x['pos'], tan=x['tan'], pop=x['pop']) for x in rows])
    REL = ['fig_best', 'fig_mean5', 'beaten_mean5', 'pospct_mean5', 'fig_last', 'pospct_last', 'dist_fit', 'venue_fit', 'going_fit',
           'corner1_pct', 'last3f_rel_mean', 'tr_top3', 'hw', 'kg']
    for c in REL:
        g = df.groupby('race')[c]
        df[c + '_z'] = (df[c] - g.transform('mean')) / g.transform('std').replace(0, np.nan)
    KEEP = ['G1_基礎能力', 'G2_直近調子', 'G3_距離適性', 'G4_コース適性', 'G8_脚質', 'G9_厩舎', 'G12_馬体重', 'G13_条件変化', 'G14_当日要素']
    cols = ['field'] + sorted({c for g in KEEP for c in NF.GROUPS[g] + [x + '_z' for x in NF.GROUPS[g] if x in REL] if c != 'field'})
    df['top3'] = ((df.pos >= 1) & (df.pos <= 3)).astype(int); df['win'] = (df.pos == 1).astype(int)
    past = df[(df.date < day) & (df.field >= 5)]
    cut = (datetime.date(int(day[:4]), int(day[4:6]), int(day[6:])) - datetime.timedelta(days=60)).strftime('%Y%m%d')
    tr, va = past[past.date < cut], past[past.date >= cut]
    P = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8,
             bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)
    td = df[df.date == day].copy()
    for y, nm in (('top3', 'p_place'), ('win', 'p_win')):
        m = lgb.train(P, lgb.Dataset(tr[cols], tr[y]), 2000, valid_sets=[lgb.Dataset(va[cols], va[y])], callbacks=[lgb.early_stopping(100, verbose=False)])
        iso = IsotonicRegression(out_of_bounds='clip', y_min=1e-4, y_max=0.999).fit(m.predict(va[cols], num_iteration=m.best_iteration), va[y])
        raw = m.predict(td[cols], num_iteration=m.best_iteration)
        td[nm] = iso.predict(raw)
        if y == 'top3':
            lt = lambda p: np.log(np.clip(p, 1e-4, .9999) / (1 - np.clip(p, 1e-4, .9999)))
            ref = lt(m.predict(tr[cols].sample(min(50000, len(tr)), random_state=1), num_iteration=m.best_iteration))
            td['score'] = 50 + 10 * (lt(raw) - ref.mean()) / ref.std()
    td['p_win'] = td.p_win / td.groupby('race').p_win.transform('sum')
    td['p_place'] = (td.p_place / td.groupby('race').p_place.transform('sum') * td.field.clip(upper=3)).clip(upper=.98)
    pred = {(r, int(n)): x for r, n, x in zip(td.race, td.num, td.to_dict('records'))}
    races = []
    for r in today:
        inv = [1 / h['tan'] for h in r['runners'] if h.get('tan')]
        tot = sum(inv) or 1
        rr = {k: r.get(k) for k in ('place_name', 'rno', 'race_name', 'post_time', 'surface', 'distance', 'going', 'weather', 'odds_status')}
        rr['runners'] = []
        for h in r['runners']:
            x = pred.get((r['id'], h['num']), {})
            pw, pp = x.get('p_win'), x.get('p_place')
            rr['runners'].append({'num': h['num'], 'waku': h['waku'], 'horse': h['horse'], 'jockey': h['jockey'], 'sexage': h['sexage'],
                                  'kg': h['kg'], 'hw': h['hw'], 'hw_diff': h['hw_diff'], 'odds': h.get('tan'), 'pop': h.get('pop'),
                                  'cancel': h['pos_text'] == '取',
                                  'mkt_p': round(1 / h['tan'] / tot, 4) if h.get('tan') else None,
                                  'score': round(float(x['score']), 1) if x.get('score') == x.get('score') and x.get('score') is not None else None,
                                  'p_place': round(float(pp), 4) if pp == pp and pp is not None else None,
                                  'p_win': round(float(pw), 4) if pw == pw and pw is not None else None,
                                  'fair': round(1 / pw, 1) if pw else None,
                                  'ev': round(pw * h['tan'], 2) if pw and h.get('tan') else None,
                                  'runs': int(x['n_runs']) if x.get('n_runs') == x.get('n_runs') and x.get('n_runs') is not None else 0})
        rr['verdict'] = '見送り'
        rr['id'] = r['id']
        races.append(rr)
    # 締切前オッズの動き（collect_nar の記録から）
    snaps = {}
    fn = f'oddsdata/odds/{day}.jsonl.gz'
    if os.path.exists(fn):
        with gzip.open(fn, 'rt') as f:
            for l in f:
                x = json.loads(l)
                snaps[(x['race_id'], x['mark'])] = x['win']
    def oo(rid, mk, num):
        w = snaps.get((rid, mk)) or {}
        v = w.get(f'{num:02d}') or w.get(str(num))
        try:
            return float(v[0])
        except Exception:  # noqa
            return None
    for rr in races:
        for h in rr['runners']:
            h['o60'], h['o30'], h['o10'], h['o2'], h['ofinal'] = (oo(rr['id'], m, h['num']) for m in (60, 30, 10, 2, -3))
            h['mv60_2'] = round(h['o2'] / h['o60'] - 1, 3) if h['o2'] and h['o60'] else None
            h['mv10_2'] = round(h['o2'] / h['o10'] - 1, 3) if h['o2'] and h['o10'] else None
            h['mv30_2'] = round(h['o2'] / h['o30'] - 1, 3) if h['o2'] and h['o30'] else None
        rr['has_moves'] = any(h['mv10_2'] is not None for h in rr['runners'])
    # 終わったレースの結果（db.netkeiba の結果ページ）
    for rr in races:
        try:
            pt = rr.get('post_time') or '99:99'
            if now.strftime('%H:%M') < (datetime.datetime.strptime(pt, '%H:%M') + datetime.timedelta(minutes=15)).strftime('%H:%M'):
                continue
            res = nk.parse_nar_result(get(f'https://nar.netkeiba.com/race/result.html?race_id={rr["id"]}').decode('utf-8', 'replace'))
            if not any(h.get('pos') for h in res['runners'].values()):
                continue
            pos = res['runners']
            for h in rr['runners']:
                x = pos.get(h['num']) or {}
                h['pos'] = x.get('pos'); h['pos_text'] = x.get('pos_text'); h['final_tan'] = x.get('tan')
            rr['payouts'] = {k: v for k, v in res['payouts'].items() if k in ('単勝', '複勝', 'ワイド', '馬連', '馬単', '3連複', '3連単')}
        except Exception as e:  # noqa
            print('result ERR', rr['id'], e)
    # 外部指数（水分ボンバー・かよちん）：当日分。検証前なので参考表示のみ
    try:
        sbo = {}
        for code, rno, u in ext.sbo_day(get(f'https://nar.k-ba.net/{day}/').decode('utf-8', 'replace'), day):
            try:
                sbo[(code, rno)] = ext.sbo_race(get(u).decode('utf-8', 'replace'))
            except Exception as e:  # noqa
                print('sbo ERR', u, e)
        kayo = {}
        sm = get(f'https://kayochinkeiba.com/sitemap-posttype-post.{day[:6]}.xml').decode('utf-8', 'replace')
        for u in re.findall(r'<loc>([^<]+)</loc>', sm):
            k = ext.kayo_url_key(u)
            if k and k[0] == day:
                for rno, v in ext.kayo_post(get(u).decode('utf-8', 'replace')).items():
                    kayo[(k[1], rno)] = v
        for rr in races:
            key = (rr['id'][4:6], int(rr['id'][10:12]))
            sb, ky = sbo.get(key) or {}, kayo.get(key) or {}
            for h in rr['runners']:
                a = (sb.get(h['num']) or {}).get('avg'); b = ky.get(h['num'])
                h['ext_sbo'] = a; h['ext_kayo'] = b
                vals = [x for x in (a, b) if x is not None]
                h['ext'] = round(sum(vals) / len(vals), 1) if vals else None
            rr['has_ext'] = any(h.get('ext') is not None for h in rr['runners'])
        out['notes']['chiho_ext'] = f'外部指数：水分ボンバー {len(sbo)}R・かよちん {len(kayo)}R'
    except Exception as e:  # noqa
        out['notes']['chiho_ext'] = '外部指数を取得できず：' + str(e)[:100]
    out['modes']['chiho'] = races
    out['notes']['chiho'] = ('独自指数 v2（オッズ不使用・過去2年で学習）。テスト1年で3着以内AUC0.79・確率の当たり具合は良好だが、'
                             'EV買いの回収率は64〜75%で100%に届かず、モデルと市場がずれた馬は市場どおりの結果だった。'
                             'そのため推奨買い目は出さず全レース「見送り」。EV・適正オッズは参考値。')
except Exception as e:  # noqa
    out['notes']['chiho_error'] = str(e)[:200]
    print('chiho error', e)

# ---------- 中央 ----------
try:
    top = jra.decode(get('https://www.jra.go.jp/JRADB/accessD.html', b'cname=pw01dli00/F3'))
    lists = [c for c in jra.cnames(top, 'pw01drl') if c[-11:-3] == day]
    races = []
    for c in lists:
        h = jra.decode(get('https://www.jra.go.jp/JRADB/accessD.html', ('cname=' + c).encode()))
        for rc in jra.cnames(h, 'pw01dde'):
            if rc[-11:-3] != day:
                continue
            d = jra.parse_card(jra.decode(get('https://www.jra.go.jp/JRADB/accessD.html', ('cname=' + rc).encode())))
            d.update(jra.race_key(rc)); score_race(d)
            races.append({k: d.get(k) for k in ('place_name', 'rno', 'race_name', 'grade', 'post_time', 'surface', 'distance', 'going_turf', 'going_dirt', 'weather')} |
                         {'going': d.get('going_turf') or d.get('going_dirt'), 'verdict': '見送り', 'id': f"{d['place']}{d['rno']:02d}{day}",
                          'runners': [{'num': x['num'], 'waku': x['waku'], 'horse': x['horse'], 'jockey': x['jockey'], 'sexage': x['sexage'],
                                       'kg': x['kg'], 'odds': x['odds'], 'pop': x['pop'], 'mkt_p': x['mkt_p'],
                                       'score': x['ps_idx'], 'p_place': None, 'p_win': None, 'fair': None, 'ev': None,
                                       'runs': len(x.get('past') or []), 'cancel': False} for x in d['runners']]})
    races.sort(key=lambda r: (r['place_name'], r['rno']))
    try:
        st = jra.decode(get('https://www.jra.go.jp/JRADB/accessS.html', b'cname=pw01sli00/AF'))
        for c in [c for c in jra.cnames(st, 'pw01srl') if c[-11:-3] == day]:
            h = jra.decode(get('https://www.jra.go.jp/JRADB/accessS.html', ('cname=' + c).encode()))
            for rc in jra.cnames(h, 'pw01sde'):
                if rc[-11:-3] != day:
                    continue
                k = jra.race_key(rc)
                rr = next((x for x in races if x['place_name'] == k['place_name'] and x['rno'] == k['rno']), None)
                if not rr:
                    continue
                res = jra.parse_result(jra.decode(get('https://www.jra.go.jp/JRADB/accessS.html', ('cname=' + rc).encode())))
                pos = {x['num']: x for x in res['runners']}
                for hh in rr['runners']:
                    x = pos.get(hh['num']) or {}
                    hh['pos'] = x.get('pos'); hh['pos_text'] = x.get('pos_text')
                rr['payouts'] = {k2: v for k2, v in res['payouts'].items() if k2 in ('単勝', '複勝', 'ワイド', '馬連', '馬単', '3連複', '3連単')}
    except Exception as e:  # noqa
        print('jra result ERR', e)
    out['modes']['chuo'] = races
    out['notes']['chuo'] = '中央の独自指数は検証前。表示は暫定指数（近4走の着差×レースの格、未検証）。推奨買い目は出さない。'
except Exception as e:  # noqa
    out['notes']['chuo_error'] = str(e)[:200]
    print('chuo error', e)

os.makedirs('appout', exist_ok=True)
json.dump(out, open('appout/app.json', 'w'), ensure_ascii=False)
print({k: len(v) for k, v in out['modes'].items()}, out['notes'].keys())
