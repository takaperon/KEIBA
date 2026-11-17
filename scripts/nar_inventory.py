"""NAR-M1：データの構造・項目・期間・欠損の棚卸し（集計値だけ）"""
import gzip, json, os, sys, collections, re
d = sys.argv[1]
races = {}
for fn in sorted(os.listdir(f'{d}/races')):
    with gzip.open(f'{d}/races/{fn}', 'rt') as f:
        for l in f:
            r = json.loads(l); races[r['id']] = r
R = sorted(races.values(), key=lambda r: (r['date'], r['place'], r['rno']))
print(f'レース数={len(R)} 期間={R[0]["date"]}〜{R[-1]["date"]}')
c = collections.Counter((r['date'][:4], r['place_name']) for r in R)
print('年×場:', dict(sorted(c.items())))
print('レース項目の例:', sorted(R[-1].keys()))
print('出走馬項目の例:', sorted(R[-1]['runners'][0].keys()))
n = 0; miss = collections.Counter()
for r in R:
    for h in r['runners']:
        n += 1
        for k, v in h.items():
            if v in (None, '', []):
                miss[k] += 1
print(f'延べ出走={n}  欠損率:', {k: f'{v / n:.1%}' for k, v in sorted(miss.items(), key=lambda t: -t[1])})
print('着順なし(pos=None)の内訳:', collections.Counter(h['pos_text'] for r in R for h in r['runners'] if h['pos'] is None).most_common(10))
print('馬場:', collections.Counter(r.get('going') for r in R).most_common(), ' 芝ダ:', collections.Counter(r.get('surface') for r in R))
print('距離:', sorted(collections.Counter(r.get('distance') for r in R).items(), key=lambda t: (t[0] or 0)))
print('頭数:', sorted(collections.Counter(len(r['runners']) for r in R).items()))
cls = collections.Counter()
for r in R:
    nm = r.get('race_name') or ''
    k = re.sub(r'[0-9０-９]+', '#', nm)[:8]
    cls[k] += 1
print('レース名(先頭8字・数字#)上位:', cls.most_common(40))
# 各出走馬が、そのレース時点で何走分の過去データを持つか
hist = collections.defaultdict(int); depth = collections.Counter()
for r in R:
    for h in r['runners']:
        k = h.get('horse_id')
        depth[min(hist[k], 10) if k else 'idなし'] += 1
        if k: hist[k] += 1
print('レース時点の過去走数(データ内):', sorted(depth.items(), key=lambda t: str(t[0]).zfill(3)))
print('馬の数=', len(hist), ' 騎手の数=', len({h.get('jockey_id') for r in R for h in r['runners']}), ' 調教師の数=', len({h.get('trainer') for r in R for h in r['runners']}))
print('タイムの形式例:', [h.get('time') for h in R[-1]['runners'][:3]], ' 着差の例:', collections.Counter(h.get('margin') for r in R[-200:] for h in r['runners']).most_common(12))
print('払戻の券種:', collections.Counter(k for r in R for k in r['payouts']).most_common())
print('meta例:', R[-1].get('meta'))
