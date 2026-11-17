"""中央の締切前オッズのスナップショットを記録（地方の collect_nar_odds.py と同じ時点）。

JRA公式：各場のオッズ一覧（pw15orl）→ 各レースの単複オッズ（pw151ou…）。cname は売り出し状況で変わるので、
記録のたびに一覧を取り直す。間隔は最低3秒。開催の無い日はすぐ終わる。
"""
import argparse, gzip, json, os, re, sys, time, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import jra
import urllib.request, urllib.parse
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
J = 'https://www.jra.go.jp/JRADB/'
MARKS = [60, 45, 30, 15, 10, 5, 2, -3]
JST = datetime.timezone(datetime.timedelta(hours=9))
_last = [0.0]


def get(access, cname):
    w = 3.0 - (time.time() - _last[0])
    if w > 0:
        time.sleep(w)
    _last[0] = time.time()
    req = urllib.request.Request(J + access, data=urllib.parse.urlencode({'cname': cname}).encode(), headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return jra.decode(r.read())


def now():
    return datetime.datetime.now(JST)


def odds_cnames(day):
    """{(場コード, R): cname}"""
    out = {}
    top = get('accessO.html', 'pw15oli00/6D')
    for c in jra.cnames(top, 'pw15orl'):
        if day not in c:
            continue
        h = get('accessO.html', c)
        for oc in jra.cnames(h, 'pw151ou'):
            m = re.match(r'pw151ou\w{2}(\d{2})\d{4}\d{2}\d{2}(\d{2})(\d{8})', oc)
            if m and m.group(3) == day:
                out[(m.group(1), int(m.group(2)))] = oc
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--max-minutes', type=float, default=340)
    a = ap.parse_args()
    deadline = time.time() + a.max_minutes * 60
    os.makedirs(f'{a.data}/odds', exist_ok=True)
    day = now().strftime('%Y%m%d')
    # 出走表から発走時刻
    top = get('accessD.html', 'pw01dli00/F3')
    races = {}
    for c in [c for c in jra.cnames(top, 'pw01drl') if c[-11:-3] == day]:
        h = get('accessD.html', c)
        for rc in jra.cnames(h, 'pw01dde'):
            if rc[-11:-3] != day:
                continue
            k = jra.race_key(rc)
            pt = jra.parse_header(jra.BeautifulSoup(get('accessD.html', rc), 'lxml')).get('post_time')
            if pt:
                t = now()
                races[(k['place'], k['rno'])] = t.replace(hour=int(pt[:2]), minute=int(pt[3:]), second=0, microsecond=0)
    print('races', len(races))
    if not races:
        json.dump({'day': day, 'races': 0, 'note': '開催なし'}, open(f'{a.data}/collector_status.json', 'w'))
        return
    fn = f'{a.data}/odds/{day}.jsonl.gz'
    done = set()
    if os.path.exists(fn):
        with gzip.open(fn, 'rt') as f:
            for l in f:
                x = json.loads(l); done.add((x['place'], x['rno'], x['mark']))
    n = errors = 0
    while time.time() < deadline:
        t = now()
        todo = [(k, mk) for k, post in races.items() for mk in MARKS
                if (k[0], k[1], mk) not in done and post - datetime.timedelta(minutes=mk) <= t < post - datetime.timedelta(minutes=mk) + datetime.timedelta(minutes=2)]
        if todo:
            try:
                oc = odds_cnames(day)
            except Exception:  # noqa
                errors += 1; oc = {}
            for (pl, rno), mk in todo:
                c = oc.get((pl, rno))
                if not c:
                    continue
                try:
                    o = jra.parse_odds(get('accessO.html', c))
                    rec = {'place': pl, 'rno': rno, 'mark': mk, 'post': races[(pl, rno)].strftime('%H:%M'), 'at': now().strftime('%H:%M:%S'),
                           'win': {str(k): [v.get('tan'), None] for k, v in o['odds'].items()},
                           'place_odds': {str(k): [v.get('fuku_min'), v.get('fuku_max')] for k, v in o['odds'].items()}}
                    with gzip.open(fn, 'at') as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    done.add((pl, rno, mk)); n += 1
                except Exception:  # noqa
                    errors += 1
        if all((k[0], k[1], MARKS[-1]) in done or races[k] + datetime.timedelta(minutes=10) < t for k in races):
            break
        time.sleep(15)
    st = {'day': day, 'races': len(races), 'snapshots_this_run': n, 'errors': errors, 'ended': now().strftime('%Y-%m-%d %H:%M')}
    json.dump(st, open(f'{a.data}/collector_status.json', 'w'))
    print(st)


if __name__ == '__main__':
    main()
