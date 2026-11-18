"""能力検査（能検・能力審査・能力調教試験）の結果を各主催者の公式ページから読む。

取れる主催者：岩手（盛岡・水沢）HTML／兵庫（園田・姫路）HTML／佐賀 HTML／名古屋 PDF／笠松 PDF／高知 PDF。
取れない主催者：南関東（浦和・船橋・大井・川崎。結果は nankankeiba.com で GitHub Actions からは 403）、
              門別（hokkaidokeiba.net が 503）、金沢（公式サイトに結果ページが見当たらない。動画のみ）。
PDF は pdftotext -layout の文字列を受け取る。
"""
import re, unicodedata

# 読み方を直したら上げる（上げた主催者のページは読み直す）
VER = {'岩手': 1, '兵庫': 1, '佐賀': 1, '名古屋': 1, '笠松': 2, '高知': 1}
from bs4 import BeautifulSoup

KANA = r'[ァ-ヴー・ヶヵ゠-ヿ]'


def norm_name(s):
    s = unicodedata.normalize('NFKC', s or '')
    s = re.sub(r'[※＊*\s　()（）]|\(地\)|\(外\)|\[地\]|\[外\]', '', s)
    return s


def tsec(t):
    """'1.35.5' '1:00.3' '1,43.3' '0.53.6' '56.0' → 秒"""
    t = unicodedata.normalize('NFKC', (t or '').strip())
    m = re.fullmatch(r'(\d+)[.:,](\d{2})\.(\d)', t)
    if m:
        return int(m[1]) * 60 + int(m[2]) + int(m[3]) / 10
    m = re.fullmatch(r'(\d{2})\.(\d)', t)
    if m:
        return int(m[1]) + int(m[2]) / 10
    return None


def zen2int(s):
    s = unicodedata.normalize('NFKC', s or '').replace(',', '')
    m = re.search(r'\d+', s)
    return int(m[0]) if m else None


def _rec(**kw):
    kw['horse'] = norm_name(kw.get('horse'))
    kw['sec'] = tsec(kw.get('time'))
    return kw


# ---------- 岩手 ----------
def iwate(html, date):
    s = BeautifulSoup(html, 'lxml')
    out = []
    for tb in s.find_all('table'):
        h = tb.find_previous(string=re.compile(r'(盛岡|水沢)\d+R'))
        if not h:
            continue
        m = re.search(r'(盛岡|水沢)(\d+)R[（(]([^）)]+)[）)]\s*([0-9０-９,，]+)\s*[mｍ]', h)
        if not m:
            continue
        for tr in tb.find_all('tr'):
            c = [x.get_text(' ', strip=True) for x in tr.find_all(['td', 'th'])]
            if len(c) < 8 or not re.search(KANA, c[1]) or c[1] == '出走馬':
                continue
            out.append(_rec(venue=m[1], date=date, race=int(m[2]), kind=m[3], dist=zen2int(m[4]), horse=c[1], sexage=c[2],
                            trainer=c[3], rider=c[4], hw=zen2int(c[5]), time=c[6], rank=None, result=c[7]))
    return out


# ---------- 兵庫 ----------
def hyogo(html):
    s = BeautifulSoup(html, 'lxml')
    t = s.get_text(' ', strip=True)
    m = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})\s*(園田競馬場|姫路競馬場|西脇トレーニングセンター)', t)
    date = f'{m[1]}{int(m[2]):02d}{int(m[3]):02d}' if m else None
    place = {'園田競馬場': '園田', '姫路競馬場': '姫路', '西脇トレーニングセンター': '西脇'}.get(m[4]) if m else None
    out = []
    for tb in s.find_all('table'):
        rows = [[x.get_text(' ', strip=True) for x in tr.find_all(['td', 'th'])] for tr in tb.find_all('tr')]
        if not rows:
            continue
        kind = rows[0][0] if len(rows[0]) == 1 else None
        for c in rows:
            if len(c) >= 6 and re.search(KANA, c[0]) and tsec(c[3]) is not None:
                out.append(_rec(venue=place, date=date, race=None, kind=kind, dist=zen2int(c[2]), horse=c[0], sexage=c[1],
                                trainer=c[5], rider=None, hw=zen2int(c[4]), time=c[3], rank=None,
                                result=c[6] if len(c) > 6 else ('自主参加' if kind == '自主参加' else None)))
    return out


# ---------- 佐賀 ----------
def saga(html):
    s = BeautifulSoup(html, 'lxml')
    t = s.get_text(' ', strip=True)
    m = re.search(r'令和(\d+)年(\d{1,2})月(\d{1,2})日', t)
    date = f'{2018 + int(m[1])}{int(m[2]):02d}{int(m[3]):02d}' if m else None
    import unicodedata as U
    dmap = {zen2int(a): zen2int(b) for a, b in re.findall(r'第([０-９\d]+)競走[^第]{0,40}?([０-９\d][０-９\d,，]{2,5})\s*[mｍ]', t)}
    out = []
    for tb in s.find_all('table'):
        h = tb.find_previous(string=re.compile(r'第[０-９\d]+競走'))
        hh = ''
        if h:  # 「第１競走 サラ系 １，３００m」が複数の要素に分かれていることがあるので後ろもつなぐ
            hh = h.parent.get_text(' ', strip=True) if h.parent else str(h)
        mr = re.search(r'第([０-９\d]+)競走', hh)
        md = re.search(r'([０-９\d][０-９\d,，]*)\s*[mｍ]', hh)
        for tr in tb.find_all('tr'):
            c = [x.get_text(' ', strip=True) for x in tr.find_all(['td', 'th'])]
            if len(c) < 12 or c[0] == '番号' or not re.search(KANA, c[1]):
                continue
            out.append(_rec(venue='佐賀', date=date, race=zen2int(mr[1]) if mr else None, kind='能力検査', dist=dmap.get(zen2int(mr[1])) if mr else None,
                            horse=c[1], sexage=c[2], trainer=c[6], rider=c[4], hw=zen2int(c[10]), time=c[9], rank=zen2int(c[8]),
                            result={'合': '合格', '否': '不合格'}.get(c[11], c[11])))
    return out


TIME = r'(\d[.:]\d{2}\.\d|\d{2}\.\d)'


def _wareki(t):
    m = re.search(r'令和\s*([0-9０-９]+)\s*年\s*([0-9０-９]+)\s*月\s*([0-9０-９]+)\s*日', t)
    return f'{2018 + zen2int(m[1])}{zen2int(m[2]):02d}{zen2int(m[3]):02d}' if m else None


# ---------- 名古屋（PDF） ----------
def nagoya(text):
    y = _wareki(text)
    m = re.search(r'令和\s*([0-9０-９]+)\s*年度', text)
    md = re.search(r'実\s*施\s*日：?\s*([0-9０-９]+)\s*月\s*([0-9０-９]+)\s*日', text)
    date = None
    if m and md:
        fy = 2018 + zen2int(m[1]); mo = zen2int(md[1])
        date = f'{fy + (1 if mo <= 3 else 0)}{mo:02d}{zen2int(md[2]):02d}'
    date = date or y
    dists = sorted({zen2int(x) for x in re.findall(r'([０-９0-9，,]{3,5})\s*[mｍ]', text)} - {None})
    out = []
    rno = 0
    prev_num = 99
    for ln in text.splitlines():
        mm = re.search(r'(?:^|\s)(\d{1,2})\s+(' + KANA + r'{2,})\s+(牡|牝|セ|騸)\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d{3})\s+' + TIME + r'\s+(\d+)\s+(合格|不合格)', ln)
        if not mm:
            continue
        num = int(mm[1])
        if num <= prev_num:
            rno += 1
        prev_num = num
        out.append(_rec(venue='名古屋', date=date, race=rno, kind='能力審査', dist=dists[0] if len(dists) == 1 else None, horse=mm[2],
                        sexage=mm[3] + mm[4], trainer=mm[7], rider=mm[6], hw=int(mm[8]), time=mm[9], rank=int(mm[10]), result=mm[11]))
    # レース番号は行頭の「1  10:15 10:30」で書かれている（真ん中の馬の行）。番号の振り直しで数える
    return out


# ---------- 笠松（PDF） ----------
def kasamatsu(text):
    """2通りの書き方がある：
    ①「 1R      1,400」の行が馬の行と別（2026年度の多く）
    ②「       800     1 オレオス ...」と距離が馬の行の頭にある（2025年度など）"""
    date = _wareki(text)
    races = [(int(a), zen2int(b)) for a, b in re.findall(r'^\s*(\d{1,2})R\s+([0-9,]{3,5})\s*$', text, re.M)]
    out, grp, prev, cur_inline = [], -1, 99, None
    rlines = re.findall(r'^\s*(\d{1,2})R\s*$', text, re.M)  # ②の「 1R」だけの行
    for ln in text.splitlines():
        lead = r'^\s*(?:([0-9]{1,2},[0-9]{3}|[0-9]{3,4})\s+)?(\d{1,2})\s+(' + KANA + r'{2,})\s+'
        mm = re.search(lead + r'(.+?)\s+(\d{3})\s+' + TIME + r'\s+(\d+)\s+(合格|不合格)', ln)
        mn = None if mm else re.search(lead + r'.*?(不合格|取消|中止|除外)', ln)
        m = mm or mn
        if not m:
            continue
        num = int(m[2])
        if num <= prev:
            grp += 1
        prev = num
        if m[1]:
            rr = (int(rlines[grp]) if grp < len(rlines) else grp + 1, zen2int(m[1]))
        else:
            rr = races[grp] if 0 <= grp < len(races) else (None, None)
        if mm:
            out.append(_rec(venue='笠松', date=date, race=rr[0], kind='能力審査', dist=rr[1], horse=mm[3], sexage=None, trainer=None, rider=None,
                            hw=int(mm[5]), time=mm[6], rank=int(mm[7]), result=mm[8]))
        else:
            out.append(_rec(venue='笠松', date=date, race=rr[0], kind='能力審査', dist=rr[1], horse=mn[3], sexage=None, trainer=None, rider=None,
                            hw=None, time=None, rank=None, result=mn[4]))
    return out


# ---------- 高知（PDF） ----------
def kochi(text):
    m = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', text)
    date = f'{m[1]}{int(m[2]):02d}{int(m[3]):02d}' if m else None
    out, rno, dist = [], None, None
    for ln in text.splitlines():
        h = re.search(r'第\s*(\d+)\s*競走.*?(\d{3,4})\s*ｍ', ln)
        if h:
            rno, dist = int(h[1]), int(h[2]); continue
        mm = re.search(r'^\s*(\d{1,2})\s+(' + KANA + r'{2,})\s+\S+\s+(\d+)\s+(.+?)\s+(\d{3})\s+(?:(\d+)\s+' + TIME + r'\s+)?(合|不)\s+' + TIME, ln)
        if not mm:
            continue
        out.append(_rec(venue='高知', date=date, race=rno, kind='能力検査', dist=dist, horse=mm[2], sexage=None, trainer=None, rider=None,
                        hw=int(mm[5]), time=mm[7], rank=int(mm[6]) if mm[6] else None, result='合格' if mm[8] == '合' else '不合格',
                        base=mm[9]))
    return out
