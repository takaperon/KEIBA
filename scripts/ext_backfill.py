"""外部指数の過去分を集める（かよちん → 水分ボンバーの順）。3秒間隔・1回あたり時間上限。途中から再開できる。
出力：{data}/kayo/YYYYMM.jsonl.gz（date, place, rno, idx{馬番:指数}）、{data}/sbo/YYYYMM.jsonl.gz（date, place, rno, idx{馬番:{kinsou,kyori,baba,avg}}）
"""
import argparse, datetime, gzip, json, os, re, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import ext
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
_last = [0.0]


def get(u):
    w = 3.0 - (time.time() - _last[0])
    if w > 0:
        time.sleep(w)
    _last[0] = time.time()
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise RuntimeError(f'blocked {e.code} {u}')
            if e.code == 404:
                return ''
            err = e
        except Exception as e:  # noqa
            err = e
        time.sleep(10 * (i + 1))
    raise RuntimeError(str(err)[:150])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--oldest', default='20241115')
    ap.add_argument('--max-minutes', type=float, default=320)
    a = ap.parse_args()
    deadline = time.time() + a.max_minutes * 60
    for d in ('kayo', 'sbo'):
        os.makedirs(f'{a.data}/{d}', exist_ok=True)
    sp = f'{a.data}/ext_state.json'
    st = json.load(open(sp)) if os.path.exists(sp) else {'kayo_done': [], 'sbo_done_days': [], 'errors': 0}
    kdone, sdone = set(st['kayo_done']), set(st['sbo_done_days'])
    save = lambda: json.dump(dict(st, kayo_done=sorted(kdone), sbo_done_days=sorted(sdone)), open(sp, 'w'))
    stop = None
    nk = ns = 0
    try:
        # かよちん：月別サイトマップ → 記事
        today = datetime.date.today()
        months = []
        y, m = int(a.oldest[:4]), int(a.oldest[4:6])
        while (y, m) <= (today.year, today.month):
            months.append(f'{y}{m:02d}'); m += 1
            if m == 13:
                y, m = y + 1, 1
        for ym in reversed(months):
            if time.time() > deadline:
                break
            sm = get(f'https://kayochinkeiba.com/sitemap-posttype-post.{ym}.xml')
            for u in re.findall(r'<loc>([^<]+)</loc>', sm):
                k = ext.kayo_url_key(u)
                if not k or k[1] == '65' or u in kdone or k[0] < a.oldest or k[0] >= today.strftime('%Y%m%d'):
                    continue
                if time.time() > deadline:
                    break
                idx = ext.kayo_post(get(u))
                with gzip.open(f'{a.data}/kayo/{k[0][:6]}.jsonl.gz', 'at') as f:
                    for r, v in idx.items():
                        f.write(json.dumps({'date': k[0], 'place': k[1], 'rno': r, 'idx': v}) + '\n')
                kdone.add(u); nk += 1
                if nk % 20 == 0:
                    save()
        save()
        # 水分ボンバー：日付ページ → 各レース
        day = today - datetime.timedelta(days=1)
        old = datetime.datetime.strptime(a.oldest, '%Y%m%d').date()
        while day >= old and time.time() < deadline:
            ds = day.strftime('%Y%m%d'); day -= datetime.timedelta(days=1)
            if ds in sdone:
                continue
            races = ext.sbo_day(get(f'https://nar.k-ba.net/{ds}/'), ds)
            ok = True
            recs = []
            for code, rno, u in races:
                if time.time() > deadline:
                    ok = False; break
                idx = ext.sbo_race(get(u))
                if idx:
                    recs.append({'date': ds, 'place': code, 'rno': rno, 'idx': idx})
            if ok:
                with gzip.open(f'{a.data}/sbo/{ds[:6]}.jsonl.gz', 'at') as f:
                    for x in recs:
                        f.write(json.dumps(x) + '\n')
                sdone.add(ds); ns += 1
                save()
    except RuntimeError as e:
        stop = str(e)[:150]
        open(f'{a.data}/EXT_STOPPED', 'w').write(stop)
    finally:
        save()
        all_days = set()
        d = today - datetime.timedelta(days=1)
        while d >= datetime.datetime.strptime(a.oldest, '%Y%m%d').date():
            all_days.add(d.strftime('%Y%m%d')); d -= datetime.timedelta(days=1)
        if all_days <= sdone:
            open(f'{a.data}/EXT_DONE', 'w').write('done')
        print(f'kayo_posts_new={nk} kayo_posts_total={len(kdone)} sbo_days_new={ns} sbo_days_total={len(sdone)} stop={stop}')


if __name__ == '__main__':
    main()
