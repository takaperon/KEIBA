"""NAR-L1：締切前オッズ・調教の取得元の確認（構造だけ。中身は保存しない）"""
import re, sys, time, json, urllib.request
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
out = {}
def get(u, name):
    time.sleep(3)
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30)
        b = r.read()
        m = re.search(rb'charset=["\']?([\w-]+)', b[:3000]); enc = m.group(1).decode() if m else 'utf-8'
        h = b.decode(enc, errors='replace')
        out[name] = {'url': u, 'status': r.status, 'len': len(h), 'ctype': r.headers.get('content-type')}
        return h
    except Exception as e:
        out[name] = {'url': u, 'err': str(e)[:150]}; return ''
day = time.strftime('%Y%m%d', time.gmtime(time.time() + 9 * 3600))
get('https://nar.netkeiba.com/robots.txt', 'nar_robots'); out['nar_robots']['text'] = get('https://nar.netkeiba.com/robots.txt', 'nar_robots2')[:600]
h = get(f'https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={day}', 'race_list')
ids = sorted(set(re.findall(r'race_id=(\d{12})', h)))
out['race_ids_today'] = len(ids); out['race_id_sample'] = ids[:3]
links = sorted(set(re.findall(r'href="([^"]+)"', h)))
out['race_list_link_kinds'] = sorted(set(re.sub(r'\d{6,}', '#', l) for l in links))[:60]
if ids:
    rid = ids[len(ids) // 2]
    for nm, u in [('shutuba', f'https://nar.netkeiba.com/race/shutuba.html?race_id={rid}'),
                  ('odds_b1', f'https://nar.netkeiba.com/odds/index.html?type=b1&race_id={rid}'),
                  ('api_odds1', f'https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id={rid}&type=1&action=update'),
                  ('api_odds5', f'https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id={rid}&type=5&action=update'),
                  ('oikiri', f'https://nar.netkeiba.com/race/oikiri.html?race_id={rid}'),
                  ('keibalab_db', f'https://www.keibalab.jp/db/race/{day}/')]:
        t = get(u, nm)
        info = out[nm]
        info['title'] = (re.search(r'<title>(.*?)</title>', t, re.S).group(1).strip()[:80] if re.search(r'<title>(.*?)</title>', t, re.S) else None)
        info['has_odds_words'] = {w: (w in t) for w in ('単勝', '複勝', 'ワイド', 'オッズ', '発売', '時点', '調教', '追い切り', '評価')}
        if t.lstrip().startswith('{'):
            try:
                j = json.loads(t); info['json_keys'] = list(j.keys())[:20]
                d = j.get('data') or {}
                info['json_data_keys'] = list(d.keys())[:20] if isinstance(d, dict) else type(d).__name__
                info['json_head'] = re.sub(r'\d', '9', t[:300])  # 数字は伏せて形だけ
            except Exception as e:
                info['json_err'] = str(e)[:80]
        info['classes'] = sorted(set(re.findall(r'class="([^"]{3,30})"', t)))[:80]
json.dump(out, open(sys.argv[1], 'w'), ensure_ascii=False, indent=1)
