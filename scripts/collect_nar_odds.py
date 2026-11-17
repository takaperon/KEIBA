"""NAR-L2：地方の締切前オッズのスナップショットを記録する（市場がまだ織り込めていない「オッズの動き」を取るため）。

各レースについて、発走の 60・45・30・15・10・5・2 分前（60・45分前は 2026-11-18 オーナーの提案で追加）と、発走 3 分後に単勝オッズ（全頭）を記録する。
1 リクエストは小さな JSON で、間隔は最低 3 秒。データは公開の場所に置かない（Actions キャッシュ）。
"""
import argparse, gzip, json, os, re, sys, time, datetime, urllib.request
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
N = 'https://nar.netkeiba.com'
MARKS = [60, 45, 30, 15, 10, 5, 2, -3]  # 発走の何分前（マイナスは発走後）
JST = datetime.timezone(datetime.timedelta(hours=9))
last_req = [0.0]


def get(u):
    w = 3.0 - (time.time() - last_req[0])
    if w > 0:
        time.sleep(w)
    last_req[0] = time.time()
    with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30) as r:
        b = r.read()
    return b.decode('utf-8', errors='replace')


def now():
    return datetime.datetime.now(JST)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--max-minutes', type=float, default=340)
    a = ap.parse_args()
    deadline = time.time() + a.max_minutes * 60
    os.makedirs(f'{a.data}/odds', exist_ok=True)
    day = None; races = {}; done = set(); n_snap = 0; errors = 0; next_list = 0
    while time.time() < deadline:
        t = now()
        d = t.strftime('%Y%m%d')
        if d != day:
            day, races, done = d, {}, set()
            fn = f'{a.data}/odds/{day}.jsonl.gz'
            if os.path.exists(fn):
                with gzip.open(fn, 'rt') as f:
                    for l in f:
                        x = json.loads(l); done.add((x['race_id'], x['mark']))
            next_list = 0
        if time.time() >= next_list:
            try:
                h = get(f'{N}/top/race_list_sub.html?kaisai_date={day}')
                for rid in sorted(set(re.findall(r'race_id=(\d{12})', h))):
                    if rid[4:6] == '65' or rid in races:
                        continue
                    s = get(f'{N}/race/shutuba.html?race_id={rid}')
                    m = re.search(r'(\d{1,2}):(\d{2})\s*発走', s)
                    if m:
                        races[rid] = t.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
            except Exception as e:  # noqa
                errors += 1
            next_list = time.time() + 1800
        # 記録すべきスナップショット
        todo = []
        for rid, post in races.items():
            for mk in MARKS:
                at = post - datetime.timedelta(minutes=mk)
                if (rid, mk) not in done and at <= t < at + datetime.timedelta(minutes=2):
                    todo.append((rid, mk, post))
        for rid, mk, post in todo:
            try:
                j = json.loads(get(f'{N}/api/api_get_nar_odds.html?race_id={rid}&type=1&action=update'))
                rec = {'race_id': rid, 'mark': mk, 'post': post.strftime('%H:%M'), 'at': now().strftime('%H:%M:%S'),
                       'odds_status': j.get('odds_status'),
                       'win': {k: [v.get('Odds'), v.get('Ninki')] for k, v in (j.get('ary_odds') or {}).items()}}
                with gzip.open(f'{a.data}/odds/{day}.jsonl.gz', 'at') as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                done.add((rid, mk)); n_snap += 1
            except Exception:  # noqa
                errors += 1
        # 今日のレースが全部終わったら、翌日の朝まで待つ（ただし max-minutes 内）
        if races and all((rid, MARKS[-1]) in done or races[rid] + datetime.timedelta(minutes=10) < t for rid in races):
            if t.hour >= 21:
                break
        time.sleep(15)
    st = {'day': day, 'races': len(races), 'snapshots_this_run': n_snap, 'errors': errors, 'ended': now().strftime('%Y-%m-%d %H:%M')}
    json.dump(st, open(f'{a.data}/collector_status.json', 'w'))
    print(st)


if __name__ == '__main__':
    main()
