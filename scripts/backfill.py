"""N3: 過去のレース結果＋最終単複オッズを、1回あたりのリクエスト上限つきで少しずつ取る。

data/state.json に進捗、data/races/YYYYMM.jsonl に1行1レースで保存する。
途中で止まっても次回は続きから。取れなかったページは errors に記録し、取れたことにしない。
"""
import argparse, json, os, re, sys, time, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import jra

UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
J = 'https://www.jra.go.jp/JRADB/'


class Fetcher:
    def __init__(self, budget, sleep, max_minutes=None):
        self.budget, self.sleep, self.n = budget, sleep, 0
        self.deadline = time.time() + max_minutes * 60 if max_minutes else None

    def ok(self):
        return self.n < self.budget and (self.deadline is None or time.time() < self.deadline)

    def get(self, access, cname):
        self.n += 1
        time.sleep(self.sleep)
        req = urllib.request.Request(J + access, data=urllib.parse.urlencode({'cname': cname}).encode(),
                                     headers={'User-Agent': UA})
        for i in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return jra.decode(r.read())
            except Exception as e:  # noqa
                err = e
                time.sleep(5 * (i + 1))
        raise RuntimeError(f'{cname}: {err}')


def month_list(start, end):
    y, m = int(start[:4]), int(start[4:])
    out = []
    while f'{y}{m:02d}' <= end:
        out.append(f'{y}{m:02d}')
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--start', default='202411')
    ap.add_argument('--end', default=time.strftime('%Y%m'))
    ap.add_argument('--until', default=None, help='この日付(YYYYMMDD)より前のレースだけ')
    ap.add_argument('--budget', type=int, default=2400)
    ap.add_argument('--sleep', type=float, default=1.5)
    ap.add_argument('--max-minutes', type=float, default=None, help='この時間で打ち切って保存（Actions のタイムアウト対策）')
    a = ap.parse_args()
    until = a.until or time.strftime('%Y%m%d')
    os.makedirs(f'{a.data}/races', exist_ok=True)
    sp = f'{a.data}/state.json'
    st = json.load(open(sp)) if os.path.exists(sp) else {}
    st.setdefault('months', {})
    st.setdefault('errors', [])
    f = Fetcher(a.budget, a.sleep, a.max_minutes)

    def save():
        json.dump(st, open(sp, 'w'), ensure_ascii=False, indent=0)

    try:
        if 'objParam' not in st:
            h = f.get('accessS.html', 'pw01skl00999999/B3')
            st['objParam'] = dict(re.findall(r'objParam\["(\d{4})"\]="([0-9A-F]{2})"', h))
            st['cur_month'] = re.search(r'var yearMonth = "(\d{6})"', h).group(1)
        # 新しい月から順に（直近のデータを先にそろえる）
        for ym in reversed(month_list(a.start, a.end)):
            ms = st['months'].setdefault(ym, {'srl': None, 'srl_done': [], 'races': []})
            if not f.ok():
                break
            if ms['srl'] is None or ym >= st.get('cur_month', ''):
                pre = 'pw01skl00' if ym >= st.get('cur_month', '') else 'pw01skl10'
                h = f.get('accessS.html', f"{pre}{ym}/{st['objParam'][ym[2:]]}")
                ms['srl'] = [c for c in jra.cnames(h, 'pw01srl') if c[-11:-5] == ym and c[-11:-3] < until]
            for c in ms['srl']:
                if c in ms['srl_done'] or not f.ok():
                    continue
                try:
                    h = f.get('accessS.html', c)
                except Exception as e:  # noqa
                    st['errors'].append({'cname': c, 'err': str(e)[:200]})
                    continue
                day = c[-11:-3]
                for r in jra.cnames(h, 'pw01sde'):
                    if r[-11:-3] == day and r not in ms['races']:
                        ms['races'].append(r)
                ms['srl_done'].append(c)
            save()
            done = set(ms.get('done', []))
            out = open(f'{a.data}/races/{ym}.jsonl', 'a')
            for r in ms['races']:
                if r in done or not f.ok():
                    continue
                if f.n + 2 > a.budget:
                    break
                k = jra.race_key(r)
                try:
                    d = jra.parse_result(f.get('accessS.html', r))
                    od = jra.parse_odds(f.get('accessO.html', d['odds_cname'])) if d.get('odds_cname') else None
                except Exception as e:  # noqa
                    st['errors'].append({'cname': r, 'err': str(e)[:200]})
                    continue
                rec = dict(k, **d, odds=od['odds'] if od else None, fuku_places=od['fuku_places'] if od else None, cname=r)
                out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                done.add(r)
                ms['done'] = sorted(done)
                if len(done) % 50 == 0:
                    out.flush(); save()
            out.close()
            ms['complete'] = bool(ms['srl']) and len(ms['srl_done']) == len(ms['srl']) and len(done) == len(ms['races'])
            save()
    finally:
        save()
        tot = sum(len(m.get('done', [])) for m in st['months'].values())
        comp = sorted(k for k, m in st['months'].items() if m.get('complete'))
        want = month_list(a.start, a.end)
        if all(st['months'].get(m, {}).get('complete') for m in want):
            open(f'{a.data}/DONE', 'w').write(time.strftime('%Y-%m-%d %H:%M'))
        print(f'requests={f.n} races_total={tot} complete_months={len(comp)} errors={len(st["errors"])}')


if __name__ == '__main__':
    main()
