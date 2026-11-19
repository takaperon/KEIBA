"""血統（父・母・母父）の過去分を集める。

過去データ（地方：nardata、中央：jradata）のレースを新しい順に見て、まだ血統の分からない馬がいるレースだけ
netkeiba の馬柱ページ（1ページで出走全頭の父・母・母父が分かる）を3秒間隔で取る。
あわせて (場, 芝ダ, 距離) → 右/左/直線 も記録する（地方の過去データには回りの向きが無いため）。
保存：peddata/ped.json {horse_id: [父, 母, 母父]}、peddata/course.json {"場コード|芝ダ|距離": 向き}、peddata/state.json
"""
import argparse, gzip, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import nk

ap = argparse.ArgumentParser()
ap.add_argument('--nar', default='nardata')
ap.add_argument('--jra', default='jradata')
ap.add_argument('--out', default='peddata')
ap.add_argument('--max-minutes', type=float, default=300)
a = ap.parse_args()
T0 = time.time()
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
os.makedirs(a.out, exist_ok=True)
ld = lambda f, d: json.load(open(f'{a.out}/{f}')) if os.path.exists(f'{a.out}/{f}') else d
ped, course, state = ld('ped.json', {}), ld('course.json', {}), ld('state.json', {'fetched': 0, 'errors': 0, 'empty': []})  # empty＝取得済みのレースID
empty = set(state.get('empty', []))
_last = [0.0]


def get(u):
    w = 3.0 - (time.time() - _last[0])
    if w > 0:
        time.sleep(w)
    _last[0] = time.time()
    with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=40) as r:
        return r.read().decode('utf-8', 'replace')


races = []  # (kind, netkeiba race_id, place, surface, distance, [(horse_id, name)])
for fn in sorted(os.listdir(f'{a.nar}/races')):
    with gzip.open(f'{a.nar}/races/{fn}', 'rt') as f:
        for l in f:
            r = json.loads(l)
            races.append(('nar', r['id'], r['place'], r.get('surface'), r.get('distance'), r['date'],
                          [(h.get('horse_id'), h['horse']) for h in r['runners']]))
for fn in sorted(os.listdir(f'{a.jra}/races')):
    for l in open(f'{a.jra}/races/{fn}'):
        r = json.loads(l)
        nid = f"{r['date'][:4]}{r['place']}{r['kai']:02d}{r['day']:02d}{r['rno']:02d}"
        races.append(('jra', nid, 'J' + r['place'], r.get('surface'), r.get('distance'), r['date'],
                      [(h.get('horse_id'), h['horse']) for h in r['runners']]))
races.sort(key=lambda x: x[5], reverse=True)
need_h = {hid for x in races for hid, _ in x[6] if hid} - set(ped)
print('races', len(races), 'horses', len({hid for x in races for hid, _ in x[6] if hid}), 'missing', len(need_h), flush=True)


def fetch(x):
    kind, rid = x[0], x[1]
    host = 'nar.netkeiba.com' if kind == 'nar' else 'race.netkeiba.com'
    try:
        t = get(f'https://{host}/race/shutuba_past.html?race_id={rid}')
    except Exception as e:  # noqa
        state['errors'] += 1; print('ERR', rid, str(e)[:80], flush=True); return
    state['fetched'] += 1
    p = nk.parse_pedigree(t)
    byname = {n: v for n, v in p.items()}
    got = 0
    for hid, name in x[6]:
        v = None
        for vv in p.values():
            if hid and vv.get('horse_id') == hid:
                v = vv; break
        v = v or byname.get(name)
        if v and hid and (v['sire'] or v['damsire']):
            ped[hid] = [v['sire'], v['dam'], v['damsire']]; got += 1
    empty.add(rid)  # 一度取ったレースは取り直さない（載っていない馬がいても）
    cd = nk.parse_course_dir(t)
    if cd and cd[2]:
        course[f'{x[2]}|{cd[0]}|{cd[1]}'] = cd[2]


def save():
    state['empty'] = sorted(empty)
    for f, d in (('ped.json', ped), ('course.json', course), ('state.json', state)):
        json.dump(d, open(f'{a.out}/{f}.tmp', 'w'), ensure_ascii=False)
        os.replace(f'{a.out}/{f}.tmp', f'{a.out}/{f}')


done = False
for x in races:
    if time.time() - T0 > a.max_minutes * 60:
        break
    if x[1] in empty:
        continue
    if any(hid and hid not in ped for hid, _ in x[6]):
        fetch(x)
        if state['fetched'] % 200 == 0:
            print(state['fetched'], 'pages', len(ped), 'horses', flush=True)
            save()  # 途中で止められても集めた分が残るように
else:
    done = True
# 回りの向きが分からない (場, 芝ダ, 距離) は1レースずつ取る
if done:
    seen = set()
    for x in races:
        if time.time() - T0 > a.max_minutes * 60:
            done = False; break
        k = (x[2], x[3], x[4])
        if k in seen or not x[3] or not x[4] or x[0] != 'nar':
            continue
        seen.add(k)
        if f'{x[2]}|{x[3]}|{x[4]}' not in course and x[1] not in empty:
            fetch(x)
state['empty'] = sorted(empty)
state['horses'] = len(ped); state['courses'] = len(course)
state['missing_after'] = len({hid for x in races for hid, _ in x[6] if hid} - set(ped))
for f, d in (('ped.json', ped), ('course.json', course), ('state.json', state)):
    json.dump(d, open(f'{a.out}/{f}', 'w'), ensure_ascii=False)
if done:
    open(f'{a.out}/DONE', 'w').write('1')
elif os.path.exists(f'{a.out}/DONE'):
    os.remove(f'{a.out}/DONE')
print('done' if done else 'partial', {k: v for k, v in state.items() if k != 'empty'}, flush=True)
