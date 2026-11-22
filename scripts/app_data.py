"""アプリ用データ：当日の中央・地方の出馬表＋指数を作り、暗号化して app-data ブランチへ（scripts/seal.sh）。

地方：nar.netkeiba の当日出馬表と単勝オッズ（API）。指数は v2 と同じ要素・同じ作り方で、
      過去2年分（キャッシュ）全部で学習し、直近60日で確率校正したモデル。オッズは EV にだけ使う。
      v2 はテストで回収率100%を超えなかったので、推奨買い目は出さない（全レース「見送り」）。
中央：JRA公式の当日出馬表（scripts/today.py と同じ）。HORSE指数（中央版、2026-11-21 検証済み）を表示。作れなかったときだけ暫定指数。
"""
import collections, gzip, json, os, re, sys, time, datetime, urllib.request
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
if os.environ.get('APP_DAY') or os.path.exists(_fix):
    day = os.environ.get('APP_DAY') or open(_fix).read().strip()
    now = datetime.datetime(int(day[:4]), int(day[4:6]), int(day[6:]), 23, 59, tzinfo=JST)
NEXT = os.environ.get('APP_NEXT') == '1'  # 翌日の出走表（夜に作る。結果・オッズはまだ無い）
if NEXT:
    day = (now + datetime.timedelta(days=1)).strftime('%Y%m%d')
_last = [0.0]


def get(u, data=None):
    w = 3.0 - (time.time() - _last[0])
    if w > 0:
        time.sleep(w)
    _last[0] = time.time()
    req = urllib.request.Request(u, data=data, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


out = {'date': day, 'built_at': now.strftime('%Y-%m-%d %H:%M'), 'modes': {}, 'notes': {}, 'next': NEXT}

# ---------- 地方 ----------
try:
    D = sys.argv[1]
    hist = {}
    for fn in sorted(os.listdir(f'{D}/races')):
        with gzip.open(f'{D}/races/{fn}', 'rt') as f:
            for l in f:
                r = json.loads(l); hist[r['id']] = r
    hist = sorted((r for r in hist.values() if r['date'] < day), key=lambda r: (r['date'], r['post_time'] or '', r['place'], r['rno']))  # 当日以降は使わない（過去日テスト時も未来を混ぜない）
    hl = get(f'https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={day}').decode('utf-8', 'replace')
    ids = [i for i in sorted(set(re.findall(r'race_id=(\d{12})', hl))) if i[4:6] != '65']
    today = []
    for rid in ids:
        try:
            r = nk.parse_shutuba(get(f'https://nar.netkeiba.com/race/shutuba.html?race_id={rid}').decode('utf-8', 'replace'), rid)
            j = {} if NEXT else json.loads(get(f'https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id={rid}&type=1&action=update'))
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
    # 場のレベル差（VT、2026-11-20 検証：場を移った馬で 3着内 logloss −0.008、全体でも改善）
    from keiba import venue_level as VL
    vl_feats, VLVL, _ = VL.build(hist + today, std, train_end)
    vl_cols = VL.attach(df, hist + today, vl_feats)
    REL = ['fig_best', 'fig_mean5', 'beaten_mean5', 'pospct_mean5', 'fig_last', 'pospct_last', 'dist_fit', 'venue_fit', 'going_fit',
           'corner1_pct', 'last3f_rel_mean', 'tr_top3', 'hw', 'kg']
    for c in REL:
        g = df.groupby('race')[c]
        df[c + '_z'] = (df[c] - g.transform('mean')) / g.transform('std').replace(0, np.nan)
    KEEP = ['G1_基礎能力', 'G2_直近調子', 'G3_距離適性', 'G4_コース適性', 'G8_脚質', 'G9_厩舎', 'G12_馬体重', 'G13_条件変化', 'G14_当日要素']
    cols = ['field'] + sorted({c for g in KEEP for c in NF.GROUPS[g] + [x + '_z' for x in NF.GROUPS[g] if x in REL] if c != 'field'}) + vl_cols
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
    COURSE = json.load(open('peddata/course.json')) if os.path.exists('peddata/course.json') else {}
    # 血統（父・母父）：馬柱ページから1レース1回
    peds = {}
    for r in today:
        try:
            peds[r['id']] = nk.parse_pedigree(get(f"https://nar.netkeiba.com/race/shutuba_past.html?race_id={r['id']}").decode('utf-8', 'replace'))
        except Exception as e:  # noqa
            print('ped ERR', r['id'], e)
    for r in today:
        inv = [1 / h['tan'] for h in r['runners'] if h.get('tan')]
        tot = sum(inv) or 1
        rr = {k: r.get(k) for k in ('place_name', 'rno', 'race_name', 'post_time', 'surface', 'distance', 'going', 'weather', 'odds_status')}
        rr['turn'] = COURSE.get(f"{r['place']}|{r.get('surface')}|{r.get('distance')}")  # 右/左/直線（馬柱ページの表記から集めたもの）
        rr['runners'] = []
        for h in r['runners']:
            x = pred.get((r['id'], h['num']), {})
            pw, pp = x.get('p_win'), x.get('p_place')
            ped = peds.get(r['id'], {}).get(h['horse'], {})
            rr['runners'].append({'num': h['num'], 'waku': h['waku'], 'horse': h['horse'], 'jockey': h['jockey'], 'sexage': h['sexage'],
                                  'sire': ped.get('sire'), 'damsire': ped.get('damsire'),
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
            if NEXT or now.strftime('%H:%M') < (datetime.datetime.strptime(pt, '%H:%M') + datetime.timedelta(minutes=15)).strftime('%H:%M'):
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
        ext_err = []  # サイトごとに失敗を分ける（1つのサイトが落ちても他は出す）
        sbo = {}
        try:
            for code, rno, u in ext.sbo_day(get(f'https://nar.k-ba.net/{day}/').decode('utf-8', 'replace'), day):
                try:
                    sbo[(code, rno)] = ext.sbo_race(get(u).decode('utf-8', 'replace'))
                except Exception as e:  # noqa
                    print('sbo ERR', u, e)
        except Exception as e:  # noqa
            ext_err.append('水分ボンバー：' + str(e)[:60].replace('<', '').replace('>', ''))
        kayo = {}
        try:
            sm = get(f'https://kayochinkeiba.com/sitemap-posttype-post.{day[:6]}.xml').decode('utf-8', 'replace')
            for u in re.findall(r'<loc>([^<]+)</loc>', sm):
                k = ext.kayo_url_key(u)
                if k and k[0] == day:
                    try:
                        for rno, v in ext.kayo_post(get(u).decode('utf-8', 'replace')).items():
                            kayo[(k[1], rno)] = v
                    except Exception as e:  # noqa
                        print('kayo ERR', u, e)
        except Exception as e:  # noqa
            ext_err.append('かよちん：' + str(e)[:60].replace('<', '').replace('>', ''))
        knavi = {}
        kf = f'oddsdata/knavi/{day}.jsonl.gz'
        if os.path.exists(kf):
            with gzip.open(kf, 'rt') as f:
                for l in f:
                    x = json.loads(l); knavi[x['race_id']] = {int(k): v for k, v in x['idx'].items()}
        for rr in races:
            if rr['id'] not in knavi:
                try:
                    knavi[rr['id']] = ext.knavi_race(get(ext.knavi_url(day, rr['id'][4:6], int(rr['id'][10:12]))).decode('utf-8', 'replace'))
                except Exception as e:  # noqa
                    print('knavi ERR', rr['id'], e)
        def dev(vals):  # レース内の偏差値（サイトごとに物差しが違うのでそろえてから平均する）
            xs = [v for v in vals.values() if v is not None]
            if len(xs) < 3:
                return {}
            m = sum(xs) / len(xs); sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** .5 or 1
            return {k: 50 + 10 * (v - m) / sd for k, v in vals.items() if v is not None}
        for rr in races:
            key = (rr['id'][4:6], int(rr['id'][10:12]))
            sb, ky, kn = sbo.get(key) or {}, kayo.get(key) or {}, knavi.get(rr['id']) or {}
            raw = {'sbo': {n: (v or {}).get('avg') for n, v in sb.items()}, 'kayo': dict(ky), 'knavi': dict(kn)}
            devs = {k: dev(v) for k, v in raw.items()}
            for h in rr['runners']:
                h['ext_sbo'] = raw['sbo'].get(h['num']); h['ext_kayo'] = raw['kayo'].get(h['num']); h['ext_knavi'] = raw['knavi'].get(h['num'])
                ds = [devs[k].get(h['num']) for k in devs if devs[k].get(h['num']) is not None]
                h['ext'] = round(sum(ds) / len(ds), 1) if ds else None
                h['ext_n'] = len(ds)
                sk = [devs[k].get(h['num']) for k in ('sbo', 'kayo') if devs[k].get(h['num']) is not None]
                h['_sk'] = sum(sk) / len(sk) if sk else None  # 合成指数用（過去分がある2サイトだけ）
            rr['has_ext'] = any(h.get('ext') is not None for h in rr['runners'])
        out['notes']['chiho_ext'] = f'外部指数：水分ボンバー {len(sbo)}R・かよちん {len(kayo)}R・競馬ナビ {sum(1 for v in knavi.values() if v)}R' + ('（取得できず：' + '／'.join(ext_err) + '）' if ext_err else '')
    except Exception as e:  # noqa
        out['notes']['chiho_ext'] = '外部指数を取得できず：' + str(e)[:100].replace('<', '').replace('>', '')
    # 合成指数：HORSE指数の要素＋外部指数（水分ボンバー・かよちんのレース内偏差値の平均）で学習し直したもの。
    # 2026-11-20 検証：テスト期間の3着以内 AUC 0.794→0.810。外部指数がオッズを使っているかは不明なので HORSE指数とは別の列にする
    try:
        def _dev(vals):
            xs = [v for v in vals.values() if v is not None]
            if len(xs) < 3:
                return {}
            m = sum(xs) / len(xs); sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** .5 or 1
            return {k: 50 + 10 * (v - m) / sd for k, v in vals.items() if v is not None}
        exth = collections.defaultdict(dict)
        for kind in ('sbo', 'kayo'):
            dd = f'extdata/{kind}'
            for fn in sorted(os.listdir(dd)) if os.path.isdir(dd) else []:
                with gzip.open(f'{dd}/{fn}', 'rt') as f:
                    for l in f:
                        x = json.loads(l)
                        exth[(x['date'], x['place'], int(x['rno']))][kind] = {int(k): (vv.get('avg') if isinstance(vv, dict) else vv) for k, vv in x['idx'].items()}
        sk = {}
        for r in hist:
            e = exth.get((r['date'], r['place'], r['rno']))
            if not e:
                continue
            ds = [_dev(e[k]) for k in ('sbo', 'kayo') if e.get(k)]
            for h in r['runners']:
                vs = [d[h['num']] for d in ds if h.get('num') in d]
                if vs:
                    sk[(r['id'], h['num'])] = sum(vs) / len(vs)
        for rr in races:
            for h in rr['runners']:
                if h.get('_sk') is not None:
                    sk[(rr['id'], h['num'])] = h['_sk']
        df['ext_z'] = [sk.get((a, int(b))) if b == b else None for a, b in zip(df.race, df.num)]
        df['ext_z'] = pd.to_numeric(df['ext_z'], errors='coerce'); df['ext_have'] = df.ext_z.notna().astype(int)
        cols2 = cols + ['ext_z', 'ext_have']
        past2 = df[(df.date < day) & (df.field >= 5)]
        tr2, va2 = past2[past2.date < cut], past2[past2.date >= cut]
        td2 = df[df.date == day].copy()
        m2 = lgb.train(P, lgb.Dataset(tr2[cols2], tr2['top3']), 2000, valid_sets=[lgb.Dataset(va2[cols2], va2['top3'])], callbacks=[lgb.early_stopping(100, verbose=False)])
        lt2 = lambda p: np.log(np.clip(p, 1e-4, .9999) / (1 - np.clip(p, 1e-4, .9999)))
        ref2 = lt2(m2.predict(tr2[cols2].sample(min(50000, len(tr2)), random_state=1), num_iteration=m2.best_iteration))
        td2['score2'] = 50 + 10 * (lt2(m2.predict(td2[cols2], num_iteration=m2.best_iteration)) - ref2.mean()) / ref2.std()
        s2 = {(a, int(b)): v for a, b, v in zip(td2.race, td2.num, td2.score2)}
        for rr in races:
            for h in rr['runners']:
                v = s2.get((rr['id'], h['num']))
                h['score2'] = round(float(v), 1) if v is not None and v == v else None
                h.pop('_sk', None)
        out['notes']['chiho_score2'] = f'合成指数：HORSE指数の要素＋外部指数（水分ボンバー・かよちん）で学習（過去の外部指数 {len(sk)}頭分）'
    except Exception as e:  # noqa
        out['notes']['chiho_score2'] = '合成指数を作れず：' + str(e)[:100].replace('<', '').replace('>', '')
        for rr in races:
            for h in rr['runners']:
                h.pop('_sk', None)
    # 血統の狙い目印（PM）：過去データ全部（当日より前）から父・母父の得意条件を作り、今回の条件に当てはめる
    try:
        from keiba import ped_mark as PMK
        pedj = json.load(open('peddata/ped.json')) if os.path.exists('peddata/ped.json') else {}
        if pedj:
            good = PMK.build(hist, pedj, day)
            np_ = 0
            TD = {x['id']: x for x in today}
            for rr in races:
                r = TD.get(rr['id'])
                if not r:
                    continue
                for h in rr['runners']:
                    if h.get('sire') or h.get('damsire'):
                        h['pm'], h['pm_why'] = PMK.mark(good, r['place'], r.get('surface'), r.get('distance'), r.get('going'), h.get('sire'), h.get('damsire'), rr['place_name'])
                        np_ += h['pm'] > 0
            out['notes']['chiho_pm'] = f'血統印：得意条件 {len(good)}組から（血統データ {len(pedj)}頭分・収集途中）。印のある馬 {np_}頭'
    except Exception as e:  # noqa
        out['notes']['chiho_pm'] = '血統印を作れず：' + str(e)[:100].replace('<', '').replace('>', '')
    # 能力検査（新馬・初出走の馬だけ）：collect_noken が集めた公式の結果を馬名で引く
    NOKEN_SRC = {'35': '岩手', '36': '岩手', '50': '兵庫', '51': '兵庫', '55': '佐賀', '48': '名古屋', '47': '笠松', '54': '高知'}
    NOKEN_NONE = {'42': '南関東の能検結果は nankankeiba.com にしかなく、取得用のサーバーから拒否される（403）',
                  '43': '南関東の能検結果は nankankeiba.com にしかなく、取得用のサーバーから拒否される（403）',
                  '44': '南関東の能検結果は nankankeiba.com にしかなく、取得用のサーバーから拒否される（403）',
                  '45': '南関東の能検結果は nankankeiba.com にしかなく、取得用のサーバーから拒否される（403）',
                  '30': 'ホッカイドウ競馬の公式サイトが取得用のサーバーに応答しない（503）',
                  '46': '金沢競馬の公式サイトに能検の結果ページが見当たらない（動画のみ）'}
    nk_idx = {}
    nf = 'nokendata/noken.jsonl'
    if os.path.exists(nf):
        for l in open(nf):
            x = json.loads(l)
            nk_idx.setdefault(x['horse'], []).append(x)
    from keiba.noken import norm_name
    n_need = n_hit = 0
    for rr in races:
        code = rr['id'][4:6]
        # 新馬戦は場ごとに名前が違う（New Beginning・ファーストステップ・○○デビュー等）ので、名前か「ほぼ全頭が初出走」で見分ける
        n0 = sum(1 for h in rr['runners'] if not h.get('runs') and not h.get('cancel'))
        nn = sum(1 for h in rr['runners'] if not h.get('cancel')) or 1
        rr['is_shinba'] = bool(re.search(r'新馬|デビュー|ファーストステップ|New\s*Beginning', rr.get('race_name') or '', re.I)) or n0 / nn >= 0.8
        rr['noken_src'] = NOKEN_SRC.get(code)
        rr['noken_none'] = NOKEN_NONE.get(code)
        for h in rr['runners']:
            if h.get('runs'):
                continue
            hs = [x for x in nk_idx.get(norm_name(h['horse']), []) if (x.get('date') or '') <= day]
            hs.sort(key=lambda x: x.get('date') or '', reverse=True)
            # 新馬戦は全頭。それ以外の初出走（転入馬など）は能検・ゲート検査の記録が見つかったときだけ出す
            if not rr['is_shinba'] and not hs:
                continue
            if rr['is_shinba']:
                n_need += 1; n_hit += bool(hs)
            # 同じ検査の同じ組で何頭中何着か（着順が無い主催者は時計の順）
            for x in hs[:3]:
                grp = [y for v in nk_idx.values() for y in v if y.get('url') == x.get('url') and y.get('race') == x.get('race') and y.get('dist') == x.get('dist') and y.get('kind') == x.get('kind')]
                x['n_grp'] = len(grp)
                if x.get('rank') is None and x.get('sec') is not None:
                    x['rank_t'] = 1 + sum(1 for y in grp if y.get('sec') is not None and y['sec'] < x['sec'])
            h['noken'] = [{k: x.get(k) for k in ('date', 'venue', 'kind', 'dist', 'time', 'rank', 'rank_t', 'n_grp', 'hw', 'result', 'src')} for x in hs[:3]]
            h['noken_need'] = True
    n_all = sum(1 for rr in races for h in rr['runners'])
    n_ped = sum(1 for rr in races for h in rr['runners'] if h.get('sire'))
    out['notes']['chiho_ped'] = f'血統（父・母父）：{n_all}頭中 {n_ped}頭'
    out['notes']['chiho_noken'] = (f'能検：新馬戦の出走馬 {n_need}頭のうち {n_hit}頭の結果あり' if n_need else '能検：今日の新馬戦なし') + f'（収録 {sum(len(v) for v in nk_idx.values())}頭分。南関東・門別・金沢は取得元なし）'
    out['modes']['chiho'] = races
    out['notes']['chiho'] = ('独自指数 v3（オッズ不使用・過去2年で学習。v3で競馬場ごとのレベル差を追加＝前走と違う場の馬の予測が改善）。テスト1年で3着以内AUC0.79・確率の当たり具合は良好だが、'
                             'EV買いの回収率は64〜75%で100%に届かず、モデルと市場がずれた馬は市場どおりの結果だった。'
                             'そのため推奨買い目は出さず全レース「見送り」。EV・適正オッズは参考値。')
except Exception as e:  # noqa
    out['notes']['chiho_error'] = str(e)[:200]
    print('chiho error', e)

# ---------- 中央 ----------
try:
    top = jra.decode(get('https://www.jra.go.jp/JRADB/accessD.html', b'cname=pw01dli00/F3'))
    # 今日が開催日でなければ、出馬表が出ている一番近い開催日（例：金曜なら翌日の土曜）を出す
    alld = sorted({c[-11:-3] for c in jra.cnames(top, 'pw01drl') if c[-11:-3] >= day})
    cday = alld[0] if alld else day
    out['chuo_date'] = cday
    lists = [c for c in jra.cnames(top, 'pw01drl') if c[-11:-3] == cday]
    races = []
    cards = {}
    for c in lists:
        h = jra.decode(get('https://www.jra.go.jp/JRADB/accessD.html', ('cname=' + c).encode()))
        for rc in jra.cnames(h, 'pw01dde'):
            if rc[-11:-3] != cday:
                continue
            d = jra.parse_card(jra.decode(get('https://www.jra.go.jp/JRADB/accessD.html', ('cname=' + rc).encode())))
            d.update(jra.race_key(rc)); score_race(d)
            cards[f"{d['place']}{d['rno']:02d}{cday}"] = d
            races.append({k: d.get(k) for k in ('place_name', 'rno', 'race_name', 'grade', 'post_time', 'surface', 'distance', 'going_turf', 'going_dirt', 'weather')} |
                         {'going': d.get('going_turf') if d.get('surface') == '芝' else (d.get('going_dirt') or d.get('going_turf')),
                          'turn': '直線' if '直線' in (d.get('course_detail') or '') else ('左' if '左' in (d.get('course_detail') or '') else ('右' if '右' in (d.get('course_detail') or '') else None)),
                          'verdict': '見送り', 'id': f"{d['place']}{d['rno']:02d}{cday}",
                          'runners': [{'num': x['num'], 'waku': x['waku'], 'horse': x['horse'], 'jockey': x['jockey'], 'sexage': x['sexage'],
                                       'sire': x.get('sire'), 'damsire': x.get('damsire'),
                                       'kg': x['kg'], 'odds': x['odds'], 'pop': x['pop'], 'mkt_p': x['mkt_p'],
                                       'score': x['ps_idx'], 'p_place': None, 'p_win': None, 'fair': None, 'ev': None,
                                       'runs': len(x.get('past') or []), 'cancel': False} for x in d['runners']]})
    races.sort(key=lambda r: (r['place_name'], r['rno']))
    # 中央版 HORSE指数（2026-11-21 検証：テスト2026年で3着以内AUC 0.781・暫定指数0.642・市場0.820。全月で暫定より上）
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('jm', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jra_model.py'))
        JM = importlib.util.module_from_spec(spec); spec.loader.exec_module(JM)
        histj = [r for r in JM.load() if r['date'] < cday]
        todayj = []
        for rr in races:
            d = cards.get(rr['id'])
            if not d or d.get('surface') not in ('芝', 'ダ'):
                continue
            x = {'id': rr['id'], 'date': cday, 'place_name': rr['place_name'], 'place_code': d['place'], 'place': d['place'] + d['surface'], 'surface': d['surface'],
                 'distance': d.get('distance'), 'going': rr.get('going'), 'grade': d.get('grade'), 'cls': d.get('cls'), 'rno': d['rno'],
                 'post_time': d.get('post_time'), 'race_name': d.get('race_name') or ''}
            c = JM.jclass(x); x['race_name'] = f'CLS:{c}' if c is not None else ''
            x['runners'] = [{'num': h['num'], 'waku': h.get('waku'), 'horse_id': h.get('horse_id'), 'jockey': h.get('jockey'), 'trainer': h.get('trainer'),
                             'kg': h.get('kg'), 'sexage': (h.get('sexage') or '').split('/')[0], 'hw': None, 'pos': None, 'pos_text': ''} for h in d['runners']]
            todayj.append(x)
        if todayj:
            dfj, vtj, withj, basej = JM.frame(histj + todayj, cday)
            past = dfj[(dfj.date < cday) & (dfj.field >= 5)]
            vcut = sorted(past.date.unique())[-int(len(past.date.unique()) * 0.15)]
            trj, vaj = past[past.date < vcut], past[past.date >= vcut]
            mj = lgb.train(JM.PARAMS, lgb.Dataset(trj[basej], trj['top3']), 3000, valid_sets=[lgb.Dataset(vaj[basej], vaj['top3'])], callbacks=[lgb.early_stopping(100, verbose=False)])
            lg = lambda p: np.log(np.clip(p, 1e-4, .9999) / (1 - np.clip(p, 1e-4, .9999)))
            ref = lg(mj.predict(trj[basej].sample(min(40000, len(trj)), random_state=1), num_iteration=mj.best_iteration))
            tdj = dfj[dfj.date == cday].copy()
            pj = mj.predict(tdj[basej], num_iteration=mj.best_iteration)
            tdj['sc'] = 50 + 10 * (lg(pj) - ref.mean()) / ref.std(); tdj['pp'] = pj
            S = {(a, int(b)): (v, q) for a, b, v, q in zip(tdj.race, tdj.num, tdj.sc, tdj.pp)}
            nj = 0
            for rr in races:
                for h in rr['runners']:
                    v = S.get((rr['id'], h['num']))
                    h['score'] = round(float(v[0]), 1) if v else None
                    h['p_place'] = round(float(v[1]), 3) if v else None
                    nj += v is not None
            out['notes']['chuo'] = (f'HORSE指数（中央版・オッズ不使用・騎手の成績は入れていない・地方と同じ作り）。テスト期間2026年で3着以内AUC0.773（今までの暫定指数0.642、市場0.820）。場のレベル差(VT)は中央では効かなかったので入れていない。'
                                    f'回収率では市場を上回っていないので推奨買い目は出さない。{nj}頭に指数')
    except Exception as e:  # noqa
        out['notes']['chuo_error'] = 'HORSE指数（中央）を作れず：' + str(e)[:150].replace('<', '').replace('>', '')
    # 外部指数（中央）：競馬ナビの JRA 全レースAI予想（前日から公開。過去日は 403 なので毎回 knavidata/jra に貯めて後で検証する）
    try:
        from keiba import ext
        kn_n = 0
        os.makedirs('knavidata/jra', exist_ok=True)
        rec = []
        for rr in races:
            u = f"https://m-jockey.co.jp/keiba-navi/jra/ai/?ymd={cday}&venue={rr['id'][:2]}&race_num={rr['rno']:02d}"
            try:
                v = ext.knavi_race(get(u).decode('utf-8', 'replace'))
            except Exception as e:  # noqa
                print('knavi jra ERR', u, e); v = {}
            if not v:
                continue
            kn_n += 1
            rec.append({'date': cday, 'place': rr['id'][:2], 'rno': rr['rno'], 'idx': v,
                        'horse': {h['num']: h.get('score') for h in rr['runners'] if h.get('score') is not None}})  # 後でナビとHORSEを比べるため
            xs = list(v.values()); m = sum(xs) / len(xs); sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** .5 or 1
            for h in rr['runners']:
                if h['num'] in v:
                    h['ext_knavi'] = v[h['num']]
                    h['ext'] = round(50 + 10 * (v[h['num']] - m) / sd, 1)
            rr['has_ext'] = True
        if rec:
            with open(f'knavidata/jra/{cday}.jsonl', 'w') as f:
                for x in rec:
                    f.write(json.dumps(x, ensure_ascii=False) + '\n')
        out['notes']['chuo_ext'] = f'外部指数：競馬ナビ {kn_n}/{len(races)}R（中央はまだ1サイトだけ・効き目は未検証。過去分が取れないので今日から貯めて検証する）'
    except Exception as e:  # noqa
        out['notes']['chuo_ext'] = '外部指数を取得できず：' + str(e)[:100].replace('<', '').replace('>', '')
    # 血統の狙い目印（中央）：2026-11-20 検証で ◎ は同じ人気帯の無印より3着内率 +0.6〜+7.6pt・複回90%、○ はほぼ差なし → ◎ だけ出す
    try:
        from keiba import ped_mark as PMK
        pedj = json.load(open('peddata/ped.json')) if os.path.exists('peddata/ped.json') else {}
        jh = {}
        for fn in sorted(os.listdir('jradata/races')) if os.path.isdir('jradata/races') else []:
            for l in open(f'jradata/races/{fn}'):
                x = json.loads(l)
                x['going'] = x.get('going_turf') if x.get('surface') == '芝' else (x.get('going_dirt') or x.get('going_turf'))
                jh[x['id']] = x
        if pedj and jh:
            jgood = PMK.build(sorted(jh.values(), key=lambda r: r['date']), pedj, cday)
            PLC = {v['place_name']: v['place'] for v in jh.values()}
            nj = 0
            for rr in races:
                for h in rr['runners']:
                    if h.get('sire') or h.get('damsire'):
                        m, why = PMK.mark(jgood, PLC.get(rr['place_name']), rr.get('surface'), rr.get('distance'), rr.get('going'), h.get('sire'), h.get('damsire'), rr['place_name'])
                        h['pm'], h['pm_why'] = (2, why) if m == 2 else (0, [])
                        nj += m == 2
            out['notes']['chuo_pm'] = f'血統印（中央は◎のみ）：得意条件 {len(jgood)}組から。◎ {nj}頭'
    except Exception as e:  # noqa
        out['notes']['chuo_pm'] = '血統印を作れず：' + str(e)[:100].replace('<', '').replace('>', '')
    try:
        if NEXT or cday > now.strftime('%Y%m%d'):
            raise StopIteration  # まだ走っていない日は結果を取りに行かない
        st = jra.decode(get('https://www.jra.go.jp/JRADB/accessS.html', b'cname=pw01sli00/AF'))
        for c in [c for c in jra.cnames(st, 'pw01srl') if c[-11:-3] == cday]:
            h = jra.decode(get('https://www.jra.go.jp/JRADB/accessS.html', ('cname=' + c).encode()))
            for rc in jra.cnames(h, 'pw01sde'):
                if rc[-11:-3] != cday:
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
    except StopIteration:
        pass
    except Exception as e:  # noqa
        print('jra result ERR', e)
    out['modes']['chuo'] = races
    out['notes'].setdefault('chuo', 'HORSE指数（中央版）を作れなかったので、暫定指数（近4走の着差×レースの格、未検証）を表示。推奨買い目は出さない。')
    if any('新馬' in (r.get('race_name') or '') for r in races):
        out['notes']['chuo'] += '<br>新馬戦：中央には地方のような能力検査（時計を計る検査レース）がなく、JRA公式サイトにゲート試験の時計も見当たらないため、能検タイムは出せない。'
except Exception as e:  # noqa
    out['notes']['chuo_error'] = str(e)[:200]
    print('chuo error', e)

os.makedirs('appout', exist_ok=True)
json.dump(out, open('appout/app_next.json' if NEXT else 'appout/app.json', 'w'), ensure_ascii=False)
print({k: len(v) for k, v in out['modes'].items()}, out['notes'].keys())
