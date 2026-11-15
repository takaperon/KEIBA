"""当日の出馬表 JSON → 1枚の HTML（データ埋め込み）。暫定指数は未検証として表示する。"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba.provisional import score_race

src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src))
races = []
for r in d['races']:
    score_race(r)
    races.append({k: r.get(k) for k in ('place_name', 'rno', 'race_name', 'grade', 'post_time', 'surface', 'distance',
                                         'course_detail', 'going_turf', 'going_dirt', 'weather', 'cls', 'no_past')} | {
        'runners': [{k: h.get(k) for k in ('num', 'waku', 'horse', 'jockey', 'sexage', 'kg', 'odds', 'pop', 'mkt_p',
                                           'ps_idx', 'ps_rank', 'ps_runs', 'gap')} |
                    {'last': [f"{p.get('pos') or '-'}着" for p in (h.get('past') or [])[:4]]} for h in r['runners']]})
data = json.dumps({'date': d['date'], 'fetched_at': d['fetched_at'], 'races': races}, ensure_ascii=False)
html = open(os.path.join(os.path.dirname(__file__), 'page_template.html')).read().replace('/*DATA*/null', data)
open(dst, 'w').write(html)
print('ok', len(races))
