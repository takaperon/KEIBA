"""NAR-N1f: netkeiba の地方レース結果ページの構造だけを確認（中身は保存しない。見出し・class名・1行目のみ）"""
import re, sys, time, urllib.request, json
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
out = {}
def get(u):
    time.sleep(3)
    r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30)
    b = r.read(); enc = 'euc-jp'
    m = re.search(rb'charset=["\']?([\w-]+)', b[:3000])
    if m: enc = m.group(1).decode()
    return r.status, b.decode(enc, errors='replace')
from bs4 import BeautifulSoup
def summarize(name, u):
    try:
        st, h = get(u)
    except Exception as e:
        out[name] = {'url': u, 'err': str(e)}; return None
    s = BeautifulSoup(h, 'lxml')
    links = sorted(set(re.findall(r'/race/(\d{12})/', h)))
    tabs = []
    for t in s.find_all('table')[:6]:
        trs = t.find_all('tr')
        tabs.append({'class': t.get('class'), 'rows': len(trs),
                     'head': [c.get_text(' ', strip=True) for c in trs[0].find_all(['th', 'td'])] if trs else [],
                     'row1': [c.get_text(' ', strip=True)[:20] for c in trs[1].find_all(['th', 'td'])] if len(trs) > 1 else []})
    rd = s.find(class_='racedata') or s.find(class_='data_intro')
    out[name] = {'url': u, 'status': st, 'len': len(h), 'title': s.title.get_text(strip=True) if s.title else '',
                 'race_links': links[:40], 'n_links': len(links), 'tables': tabs,
                 'racedata': rd.get_text(' ', strip=True)[:200] if rd else None}
    return links
D = 'https://db.netkeiba.com'
links = summarize('list_20261114', f'{D}/race/list/20261114/') or []
nar = [l for l in links if 30 <= int(l[4:6]) <= 65]
out['nar_ids'] = nar[:20]
if nar:
    summarize('nar_race', f'{D}/race/{nar[0]}/')
summarize('list_20241114', f'{D}/race/list/20241114/')
summarize('nar_list_alt', 'https://nar.netkeiba.com/top/race_list.html?kaisai_date=20241114')
json.dump(out, open(sys.argv[1], 'w'), ensure_ascii=False, indent=1)
