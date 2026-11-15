"""JRA公式サイト（JRADB）のページを読む。取得は scripts/ 側、ここは HTML → dict だけ。"""
import re
from bs4 import BeautifulSoup

PLACES = {'01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
          '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'}
CNAME = re.compile(r"pw[0-9A-Za-z]+/[0-9A-F]{2}")


def decode(raw: bytes) -> str:
    return raw.decode('cp932', errors='replace')


def cnames(html: str, prefix: str):
    """ページ内の cname を順序つき・重複なしで返す"""
    out = []
    for c in CNAME.findall(html):
        if c.startswith(prefix) and c not in out:
            out.append(c)
    return out


def race_key(cname: str):
    """pw01sde10 PP YYYY KK DD RR YYYYMMDD/XX → 'YYYYMMDD-PP-RR' と各要素"""
    m = re.match(r"pw01[sd]de\d\d(\d{2})(\d{4})(\d{2})(\d{2})(\d{2})(\d{8})/", cname)
    if not m:
        return None
    pp, yy, kai, day, rno, date = m.groups()
    return {'id': f"{date}-{pp}-{rno}", 'date': date, 'place': pp, 'place_name': PLACES.get(pp, pp),
            'kai': int(kai), 'day': int(day), 'rno': int(rno)}


def _t(el):
    return el.get_text(' ', strip=True) if el else ''


def _num(s):
    s = (s or '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def _id(el, pat):
    if not el:
        return None
    m = re.search(pat, str(el))
    return m.group(1) if m else None


def parse_header(s):
    h = s.find(class_='race_header')
    d = {}
    if not h:
        return d
    d['date_text'] = _t(h.find(class_='date'))
    m = re.search(r'(\d+)時(\d+)分', _t(h.find(class_='time')))
    d['post_time'] = f"{int(m.group(1)):02d}:{m.group(2)}" if m else None
    baba = h.find(class_='baba')
    d['weather'] = _t(baba.find(class_='weather').find(class_='txt')) if baba and baba.find(class_='weather') else None
    for cls, key in (('turf', 'going_turf'), ('durt', 'going_dirt'), ('dirt', 'going_dirt')):
        li = baba.find(class_=cls) if baba else None
        if li:
            d[key] = _t(li.find(class_='txt'))
    rn = h.find(class_='race_name')
    d['race_name'] = rn.find(string=True, recursive=False).strip() if rn and rn.find(string=True, recursive=False) else _t(rn)
    g = rn.find('img') if rn else None
    d['grade'] = g.get('alt') if g else None
    for cls in ('category', 'class', 'rule', 'weight'):
        d[cls if cls != 'class' else 'cls'] = _t(h.find(class_=f'cell {cls}') or h.select_one(f'.type .{cls}'))
    course = h.select_one('.type .course')
    ct = _t(course)
    m = re.search(r'([\d,]+)\s*メートル', ct)
    d['distance'] = int(m.group(1).replace(',', '')) if m else None
    det = _t(course.find(class_='detail')) if course else ''
    d['course_detail'] = det
    d['surface'] = '芝' if '芝' in det and 'ダート' not in det else ('ダ' if 'ダート' in det else ('障' if '障害' in ct or '障害' in det else None))
    if '障害' in (d.get('category') or '') or '障害' in det:
        d['surface'] = '障'
    return d


def parse_result(html: str) -> dict:
    s = BeautifulSoup(html, 'lxml')
    d = parse_header(s)
    rows = []
    tb = s.find('table', class_='basic')
    for tr in (tb.find('tbody').find_all('tr') if tb and tb.find('tbody') else []):
        g = lambda c: tr.find('td', class_=c)
        hw = _t(g('h_weight'))
        m = re.match(r'(\d+)\s*\(([+\-]?\d+|前計不|計不)?\)?', hw)
        corners = [int(x) for x in re.findall(r'\d+', _t(g('corner')))]
        place = _t(g('place'))
        rows.append({
            'pos': int(place) if place.isdigit() else None, 'pos_text': place,
            'waku': _id(g('waku'), r'waku/(\d+)\.png'),
            'num': int(_t(g('num'))) if _t(g('num')).isdigit() else None,
            'horse': _t(g('horse')), 'horse_id': _id(g('horse'), r'pw01dud\d\d(\d{10})'),
            'sexage': _t(g('age')), 'kg': _num(_t(g('weight'))),
            'jockey': _t(g('jockey')), 'jockey_id': _id(g('jockey'), r'pw04kmk00(\d+)'),
            'time': _t(g('time')) or None, 'margin': _t(g('margin')) or None,
            'corners': corners, 'last3f': _num(_t(g('f_time'))),
            'hw': int(m.group(1)) if m else None,
            'hw_diff': int(m.group(2)) if m and m.group(2) and re.match(r'[+\-]?\d+$', m.group(2)) else None,
            'trainer': _t(g('trainer')), 'trainer_id': _id(g('trainer'), r'pw05cmk00(\d+)'),
            'pop': int(_t(g('pop'))) if _t(g('pop')).isdigit() else None,
        })
    d['runners'] = rows
    pay = {}
    ra = s.find(class_='refund_area')
    for li in (ra.find_all('li') if ra else []):
        dt = li.find('dt')
        if not dt:
            continue
        kind = _t(dt)
        lines = []
        for ln in li.find_all(class_='line'):
            yen = _num(_t(ln.find(class_='yen')).replace('円', ''))
            popm = re.search(r'\d+', _t(ln.find(class_='pop')))
            lines.append({'combo': _t(ln.find(class_='num')), 'yen': yen, 'pop': int(popm.group()) if popm else None})
        if lines:
            pay[kind] = lines
    d['payouts'] = pay
    d['odds_cname'] = next(iter(cnames(html, 'pw151ou')), None)
    return d


def parse_odds(html: str) -> dict:
    """単勝・複勝オッズ（最終 or その時点）"""
    s = BeautifulSoup(html, 'lxml')
    out = {}
    for tb in s.find_all('table'):
        for tr in tb.find_all('tr'):
            num = tr.find('td', class_='num')
            tan = tr.find('td', class_='odds_tan')
            if not (num and tan and _t(num).isdigit()):
                continue
            fk = tr.find('td', class_='odds_fuku')
            out[int(_t(num))] = {
                'tan': _num(_t(tan)),
                'fuku_min': _num(_t(fk.find(class_='min'))) if fk and fk.find(class_='min') else None,
                'fuku_max': _num(_t(fk.find(class_='max'))) if fk and fk.find(class_='max') else None,
            }
    m = re.search(r'複勝（(\d)着払い）', html)
    return {'odds': out, 'fuku_places': int(m.group(1)) if m else None}


def _margin(fin_text, pos):
    m = re.search(r'\(([-\d.]+)\)', fin_text or '')
    if not m:
        return None
    v = float(m.group(1))
    return -v if pos == 1 else v  # 勝ち馬は2着との差をマイナス（＝先着）で


def parse_card(html: str) -> dict:
    """出馬表（単勝オッズ・人気・近4走つき）"""
    s = BeautifulSoup(html, 'lxml')
    d = parse_header(s)
    rows = []
    tb = s.find('table', class_='basic') or s.find('table')
    for tr in (tb.find('tbody').find_all('tr', recursive=False) if tb and tb.find('tbody') else []):
        num = tr.find('td', class_='num')
        if not num or not _t(num).isdigit():
            continue
        hz = tr.find('td', class_='horse')
        jk = tr.find('td', class_='jockey')
        odds = _num(_t(hz.select_one('.odds_line .num'))) if hz else None
        pm = re.search(r'\((\d+)', _t(hz.select_one('.pop_rank'))) if hz else None
        past = []
        for td in tr.find_all('td', class_='past'):
            if not td.find(class_='date'):
                continue
            pl = re.search(r'\d+', _t(td.find(class_='place')))
            mx = re.search(r'\d+', _t(td.select_one('.num .max')))
            dist = _t(td.find(class_='dist'))
            g = td.select_one('.r_class img')
            f3 = re.search(r'3F\s*([\d.]+)', _t(td.find(class_='f3')))
            pos = int(pl.group()) if pl else None
            past.append({'date': _t(td.find(class_='date')), 'rc': _t(td.find(class_='rc')),
                         'name': _t(td.select_one('.race_line .name')), 'grade': g.get('alt') if g else None,
                         'pos': pos, 'field': int(mx.group()) if mx else None,
                         'pop': int(re.search(r'\d+', _t(td.select_one('.num .pop'))).group()) if re.search(r'\d+', _t(td.select_one('.num .pop'))) else None,
                         'dist': dist, 'going': _t(td.find(class_='condition')),
                         'last3f': float(f3.group(1)) if f3 else None,
                         'margin': _margin(_t(td.find(class_='fin')), pos)})
        rows.append({'num': int(_t(num)), 'waku': _id(tr.find('td', class_='waku'), r'waku/(\d+)\.png'),
                     'horse': _t(hz.select_one('.name')) if hz else '',
                     'horse_id': _id(hz, r'pw01dud\d\d(\d{10})'),
                     'odds': odds, 'pop': int(pm.group(1)) if pm else None,
                     'record': _t(hz.select_one('.result')) if hz else '',
                     'sire': _t(hz.select_one('.sire')).replace('父：', '') if hz else '',
                     'trainer': _t(hz.select_one('.trainer a')) if hz else '',
                     'sexage': _t(jk.find(class_='age')) if jk else '',
                     'kg': _num(_t(jk.find(class_='weight')).replace('kg', '')) if jk else None,
                     'jockey': _t(jk.select_one('.jockey a')) if jk else '',
                     'past': past})
    d['runners'] = rows
    return d
