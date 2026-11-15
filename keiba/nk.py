"""netkeiba（db.netkeiba.com）の地方レース結果ページを読む。個人利用の範囲で使い、公開の場所には置かない。"""
import re
from bs4 import BeautifulSoup

NAR_PLACES = {'30': '門別', '35': '盛岡', '36': '水沢', '42': '浦和', '43': '船橋', '44': '大井', '45': '川崎',
              '46': '金沢', '47': '笠松', '48': '名古屋', '50': '園田', '51': '姫路', '54': '高知', '55': '佐賀',
              '65': '帯広(ば)'}


def decode(raw: bytes) -> str:
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000])
    return raw.decode(m.group(1).decode() if m else 'euc-jp', errors='replace')


def race_ids(html):
    out = []
    for r in re.findall(r'/race/(\d{12})/', html):
        if r not in out:
            out.append(r)
    return out


def _num(s):
    s = (s or '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_race(html: str, rid: str) -> dict:
    s = BeautifulSoup(html, 'lxml')
    d = {'id': rid, 'date': rid[:4] + rid[6:10], 'place': rid[4:6], 'place_name': NAR_PLACES.get(rid[4:6], rid[4:6]),
         'rno': int(rid[10:12])}
    rd = s.find(class_='racedata')
    t = rd.get_text(' ', strip=True) if rd else ''
    h1 = rd.find('h1') if rd else None
    d['race_name'] = h1.get_text(' ', strip=True) if h1 else None
    m = re.search(r'(芝|ダ|障)\s*(右|左|直線)?\s*(?:外|内)?\s*(\d+)m', t)
    d['surface'] = m.group(1) if m else None
    d['distance'] = int(m.group(3)) if m else None
    m = re.search(r'天候\s*:\s*(\S+)', t); d['weather'] = m.group(1) if m else None
    m = re.search(r'(?:ダート|芝)\s*:\s*(\S+)', t); d['going'] = m.group(1) if m else None
    m = re.search(r'発走\s*:\s*(\d+:\d+)', t); d['post_time'] = m.group(1) if m else None
    st = s.find('p', class_='smalltxt')
    d['meta'] = st.get_text(' ', strip=True) if st else None
    rows = []
    tb = s.find('table', class_='race_table_01')
    if tb:
        trs = tb.find_all('tr')
        head = [re.sub(r'\s+', '', c.get_text(' ', strip=True)) for c in trs[0].find_all(['th', 'td'])]
        ix = lambda name: next((i for i, h in enumerate(head) if h.startswith(name)), None)
        I = {k: ix(k) for k in ('着順', '枠番', '馬番', '馬名', '性齢', '斤量', '騎手', 'タイム', '着差', '通過', '上り', '単勝', '人気', '馬体重', '調教師')}
        for tr in trs[1:]:
            c = tr.find_all('td')
            g = lambda k: c[I[k]].get_text(' ', strip=True) if I[k] is not None and I[k] < len(c) else ''
            a = c[I['馬名']].find('a') if I['馬名'] is not None and I['馬名'] < len(c) else None
            hid = re.search(r'/horse/(\w+)', a['href']).group(1) if a and a.get('href') and '/horse/' in a['href'] else None
            jk = c[I['騎手']].find('a') if I['騎手'] is not None and I['騎手'] < len(c) else None
            jid = re.search(r'/jockey/(?:result/recent/)?(\w+)', jk['href']).group(1) if jk and jk.get('href') and '/jockey/' in jk['href'] else None
            hw = re.match(r'(\d+)\(([+\-]?\d+)\)', g('馬体重'))
            pos = g('着順')
            rows.append({'pos': int(pos) if pos.isdigit() else None, 'pos_text': pos,
                         'waku': g('枠番'), 'num': int(g('馬番')) if g('馬番').isdigit() else None,
                         'horse': g('馬名'), 'horse_id': hid, 'sexage': g('性齢'), 'kg': _num(g('斤量')),
                         'jockey': g('騎手'), 'jockey_id': jid, 'time': g('タイム') or None, 'margin': g('着差') or None,
                         'corners': [int(x) for x in re.findall(r'\d+', g('通過'))], 'last3f': _num(g('上り')),
                         'tan': _num(g('単勝')), 'pop': int(g('人気')) if g('人気').isdigit() else None,
                         'hw': int(hw.group(1)) if hw else None, 'hw_diff': int(hw.group(2)) if hw else None,
                         'trainer': g('調教師')})
    d['runners'] = rows
    pay = {}
    for pt in s.find_all('table', class_='pay_table_01'):
        for tr in pt.find_all('tr'):
            th = tr.find('th'); tds = tr.find_all('td')
            if not th or len(tds) < 3:
                continue
            combos = [x for x in tds[0].get_text('|', strip=True).split('|') if x]
            yens = [_num(x) for x in tds[1].get_text('|', strip=True).split('|') if x]
            pops = [x for x in tds[2].get_text('|', strip=True).split('|') if x]
            pay[th.get_text(strip=True)] = [{'combo': c, 'yen': y, 'pop': int(p) if p.isdigit() else None}
                                            for c, y, p in zip(combos, yens, pops + [''] * len(combos))]
    d['payouts'] = pay
    corners = {}
    for t2 in s.find_all('table', class_='result_table_02'):
        for tr in t2.find_all('tr'):
            th, td = tr.find('th'), tr.find('td')
            if th and td and 'コーナー' in th.get_text():
                corners[th.get_text(strip=True)] = td.get_text(strip=True)
    d['corner_text'] = corners
    return d
