"""デイリースポーツ うま屋の出馬表（スピード指数 SP と本紙の印）。robots.txt で /umaya/ は許可（2026-11-22 確認）。
race_id は netkeiba と同じ12桁（年・場・回・日・R）。"""
import re
from bs4 import BeautifulSoup

MARKS = {'◎': 4, '○': 3, '▲': 2, '△': 1, '☆': 1, '注': 1}


def url(rid):
    return f'https://www.daily.co.jp/umaya/race/shutsuba.shtml?race_id={rid}'


def parse(html):
    """{'date': 'YYYY/M/D', 'rows': {馬番: {'sp': int|None, 'mark': str}}}"""
    s = BeautifulSoup(html, 'lxml')
    t = s.get_text('\n', strip=True)
    m = re.search(r'(20\d\d/\d+/\d+)\(', t)
    out = {'date': m.group(1) if m else None, 'rows': {}}
    for tb in s.find_all('table'):
        trs = tb.find_all('tr')
        if not trs:
            continue
        hdr = [x.get_text('', strip=True) for x in trs[0].find_all(['th', 'td'])]
        if not hdr or not hdr[0].startswith('SP') or '馬番' not in hdr:
            continue
        iu, im = hdr.index('馬番'), (hdr.index('印') if '印' in hdr else None)
        for tr in trs[1:]:
            c = [x.get_text('', strip=True) for x in tr.find_all(['td', 'th'])]
            if len(c) <= iu or not c[iu].isdigit():
                continue
            sp = c[0] if re.fullmatch(r'\d+', c[0] or '') else None
            out['rows'][int(c[iu])] = {'sp': int(sp) if sp else None, 'mark': (c[im] if im is not None and len(c) > im else '')}
        break
    return out
