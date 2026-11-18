"""外部指数：水分ボンバーオンライン（nar.k-ba.net）・かよちんの地方競馬予想（kayochinkeiba.com）を読む。
どちらも robots.txt で許可（2026-11-18 確認）。個人利用。データは公開の場所に置かない。"""
import re
from bs4 import BeautifulSoup

NAME2CODE = {'門別': '30', '盛岡': '35', '水沢': '36', '浦和': '42', '船橋': '43', '大井': '44', '川崎': '45',
             '金沢': '46', '笠松': '47', '名古屋': '48', '園田': '50', '姫路': '51', '高知': '54', '佐賀': '55', '帯広': '65'}
KAYO = {'monbetsu': '30', 'morioka': '35', 'mizusawa': '36', 'urawa': '42', 'funabashi': '43', 'ooi': '44', 'kawasaki': '45',
        'kanazawa': '46', 'kasamatsu': '47', 'nagoya': '48', 'sonoda': '50', 'himeji': '51', 'kochi': '54', 'kouchi': '54',
        'saga': '55', 'obihiro': '65'}


def sbo_day(html, day):
    """日付ページ → [(場コード(netkeiba), R, url)]"""
    out = []
    for m in re.finditer(r'href="//nar\.k-ba\.net/(%s)/(\d+)/(\d+)/table\.html" title="(\D+?)(\d+)R予想"' % day, html):
        code = NAME2CODE.get(m.group(4))
        if code and code != '65':
            out.append((code, int(m.group(3)), f'https://nar.k-ba.net/{m.group(1)}/{m.group(2)}/{m.group(3)}/table.html'))
    return out


def _v(td):
    t = td.get_text(strip=True) if td else ''
    m = re.match(r'(\d+)', t)
    return int(m.group(1)) if m else None


def sbo_race(html):
    """{馬番: {kinsou, kyori, baba, avg}}"""
    s = BeautifulSoup(html, 'lxml')
    tb = s.find('table', id='table')
    out = {}
    if not tb:
        return out
    for tr in tb.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) >= 10 and tds[0].get_text(strip=True).isdigit():
            out[int(tds[0].get_text(strip=True))] = {'kinsou': _v(tds[6]), 'kyori': _v(tds[7]), 'baba': _v(tds[8]), 'avg': _v(tds[9])}
    return out


CIRC = {chr(0x2460 + i): i + 1 for i in range(20)}


def kayo_post(html):
    """{R: {馬番: 指数}}（記事冒頭の「1R ⑦ ① … 指 79 74 …」の表）"""
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', html, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', t)
    s = re.sub(r'&nbsp;', ' ', s); s = re.sub(r'\s+', ' ', s)
    out = {}
    for m in re.finditer(r'(\d{1,2})R\s+((?:[①-⑳]\s*)+)指\s+((?:\d{1,3}\s+)+)', s + ' '):
        r = int(m.group(1))
        nums = [CIRC[c] for c in m.group(2) if c in CIRC]
        vals = [int(x) for x in m.group(3).split()]
        if r in out or len(vals) < len(nums):
            continue
        out[r] = dict(zip(nums, vals[:len(nums)]))
    return out


def kayo_url_key(url):
    """https://kayochinkeiba.com/261117kanazawa/ → ('20261117', '46')"""
    m = re.search(r'kayochinkeiba\.com/(\d{6})([a-z]+)/?$', url)
    if not m or m.group(2) not in KAYO:
        return None
    return '20' + m.group(1), KAYO[m.group(2)]


def knavi_url(day, place, rno):
    """競馬ナビ（m-jockey.co.jp/keiba-navi）の地方AI予想。当日分だけ（過去日は 403）。場コードは netkeiba と同じ"""
    return f'https://m-jockey.co.jp/keiba-navi/localrace/ai-all-race-predictions/?ymd={day}&venue={place}&race_num={rno:02d}'


def knavi_race(html):
    """{馬番: ナビ指数}"""
    s = BeautifulSoup(html, 'lxml')
    for tb in s.find_all('table'):
        head = tb.get_text(' ', strip=True)[:200]
        if 'ナビ指数' not in head or '馬番' not in head:
            continue
        out = {}
        for tr in tb.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) >= 5 and tds[1].get_text(strip=True).isdigit():
                v = tds[-1].get_text(strip=True)
                if re.fullmatch(r'-?\d+(\.\d+)?', v):
                    out[int(tds[1].get_text(strip=True))] = float(v)
        return out
    return {}
