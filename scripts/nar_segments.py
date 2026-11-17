"""地方：両期間で100%前後の区分（場×単勝オッズ帯）の中身を分解。偶然か理由があるかを見る。集計値だけ出す。"""
import gzip, json, os, sys, collections, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baseline import band
d = sys.argv[1]
races = {}
for fn in sorted(os.listdir(f'{d}/races')):
    with gzip.open(f'{d}/races/{fn}', 'rt') as f:
        for l in f:
            r = json.loads(l); races[r['id']] = r
races = list(races.values())
SEG = [('川崎', '50-100'), ('笠松', '10-15'), ('盛岡', '20-30'), ('浦和', '30-50')]
rows = collections.defaultdict(list)  # seg -> [(race, horse, win_pay)]
allseg = collections.defaultdict(lambda: [0, 0])
for r in races:
    tan = {x['combo']: x['yen'] for x in r['payouts'].get('単勝', []) if x.get('yen')}
    for h in r['runners']:
        if not h.get('tan') or h.get('num') is None:
            continue
        k = (r['place_name'], band(h['tan']))
        p = tan.get(str(h['num']), 0)
        allseg[k][0] += 1; allseg[k][1] += p
        if k in SEG:
            rows[k].append((r, h, p))
# 多重比較の目安：全区分のうち n>=1000 で単勝回収率>=100% の数
big = [(k, v[1] / v[0] / 100) for k, v in allseg.items() if v[0] >= 1000]
print(f'区分数(n>=1000)={len(big)}  うち単勝100%以上={sum(1 for _, x in big if x >= 1.0)}')
for k in SEG:
    xs = rows[k]; n = len(xs); hits = [p for _, _, p in xs if p]
    roi = sum(hits) / n / 100
    top = sorted(hits, reverse=True)
    print(f'\n== {k[0]} {k[1]}倍  n={n} 的中={len(hits)} 単勝回収={roi:.1%}  上位3的中を除く={sum(top[3:]) / n / 100:.1%}  最大配当={top[0] if top else 0:.0f}円')
    # ブートストラップで回収率の95%区間
    random.seed(1); bs = []
    pays = [p for _, _, p in xs]
    for _ in range(2000):
        s = [pays[random.randrange(n)] for _ in range(n)]; bs.append(sum(s) / n / 100)
    bs.sort(); print(f'  95%区間 {bs[50]:.0%}〜{bs[1950]:.0%}')
    def by(name, f):
        g = collections.defaultdict(lambda: [0, 0, 0])
        for r, h, p in xs:
            kk = f(r, h); g[kk][0] += 1; g[kk][1] += p; g[kk][2] += 1 if p else 0
        print('  ' + name + ': ' + ' / '.join(f'{kk} n={v[0]} 的中{v[2]} {v[1] / v[0] / 100:.0%}' for kk, v in sorted(g.items(), key=lambda t: -t[1][0])[:8]))
    by('四半期', lambda r, h: r['date'][:4] + 'Q' + str((int(r['date'][4:6]) - 1) // 3 + 1))
    by('距離', lambda r, h: r.get('distance'))
    by('人気', lambda r, h: h.get('pop'))
    by('頭数', lambda r, h: ('-8' if len(r['runners']) <= 8 else ('9-11' if len(r['runners']) <= 11 else '12+')))
    by('クラス', lambda r, h: next((c for c in ('A', 'B', 'C', '2歳', '3歳', '重賞', 'OP') if c in (r.get('race_name') or '')), 'その他'))
    by('馬場', lambda r, h: r.get('going'))
    by('前走着順なし判定不可', lambda r, h: 'all')
