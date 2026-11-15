"""NAR-N3: 地方の過去レース結果（全頭の最終単勝・人気・通過・上り・払戻）を netkeiba から日付をさかのぼって取る。

3秒間隔。取ったデータはこのリポジトリが公開の間はブランチに置かない（Actions のキャッシュにだけ置く）。
ログには件数だけ出し、中身は出さない。
"""
import argparse, datetime, gzip, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import nk

UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
D = 'https://db.netkeiba.com'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--oldest', default='20241115')
    ap.add_argument('--sleep', type=float, default=3.0)
    ap.add_argument('--max-minutes', type=float, default=320)
    ap.add_argument('--skip-banei', action='store_true', default=True)
    a = ap.parse_args()
    os.makedirs(f'{a.data}/races', exist_ok=True)
    sp = f'{a.data}/state.json'
    st = json.load(open(sp)) if os.path.exists(sp) else {'dates_done': [], 'errors': []}
    done_dates = set(st['dates_done'])
    deadline = time.time() + a.max_minutes * 60
    n_req = n_race = 0

    def get(u):
        nonlocal n_req
        n_req += 1
        time.sleep(a.sleep)
        for i in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30) as r:
                    return nk.decode(r.read())
            except Exception as e:  # noqa
                err = e
                if '403' in str(e) or '429' in str(e):
                    raise RuntimeError(f'blocked {e}')  # 拒否されたら即やめる
                time.sleep(10 * (i + 1))
        raise RuntimeError(str(err)[:200])

    def save():
        st['dates_done'] = sorted(done_dates)
        json.dump(st, open(sp, 'w'))

    day = datetime.date.today() - datetime.timedelta(days=1)
    oldest = datetime.datetime.strptime(a.oldest, '%Y%m%d').date()
    stop = None
    try:
        while day >= oldest and time.time() < deadline:
            ds = day.strftime('%Y%m%d')
            day -= datetime.timedelta(days=1)
            if ds in done_dates:
                continue
            ids = [r for r in nk.race_ids(get(f'{D}/race/list/{ds}/'))
                   if r[4:6] in nk.NAR_PLACES and not (a.skip_banei and r[4:6] == '65') and r[:4] + r[6:10] == ds]
            fn = f'{a.data}/races/{ds[:6]}.jsonl.gz'
            have = set()
            if os.path.exists(fn):
                with gzip.open(fn, 'rt') as f:
                    have = {json.loads(l)['id'] for l in f}
            ok = True
            with gzip.open(fn, 'at') as f:
                for rid in ids:
                    if rid in have:
                        continue
                    if time.time() >= deadline:
                        ok = False; break
                    try:
                        d = nk.parse_race(get(f'{D}/race/{rid}/'), rid)
                    except RuntimeError as e:
                        if 'blocked' in str(e):
                            raise
                        st['errors'].append({'id': rid, 'err': str(e)[:120]}); ok = False; continue
                    if d['runners']:
                        f.write(json.dumps(d, ensure_ascii=False) + '\n'); n_race += 1
            if ok:
                done_dates.add(ds)
            save()
    except RuntimeError as e:
        stop = str(e)[:120]
    finally:
        save()
        tot = 0
        for fn in os.listdir(f'{a.data}/races'):
            with gzip.open(f'{a.data}/races/{fn}', 'rt') as f:
                tot += sum(1 for _ in f)
        print(f'requests={n_req} new_races={n_race} total_races={tot} dates_done={len(done_dates)} '
              f'oldest_done={min(done_dates) if done_dates else None} errors={len(st["errors"])} stop={stop}')


if __name__ == '__main__':
    main()
