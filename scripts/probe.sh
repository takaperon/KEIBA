#!/bin/bash
# 競馬ナビ（中央）のページが、指定した日付・場・レースのものかを確かめる（見出しと指数の表だけ書き出す）
set -u
O=$1; mkdir -p $O
pip install -q beautifulsoup4 lxml >/dev/null 2>&1
for q in "20261122&venue=08&race_num=11" "20261122&venue=05&race_num=11" "20261121&venue=08&race_num=01" "20261122&venue=08&race_num=01"; do
  curl -s -A 'Mozilla/5.0 (compatible; KEIBA-personal/0.1)' "https://m-jockey.co.jp/keiba-navi/jra/ai/?ymd=$q" -o p.html -w "$q %{http_code}\n" >> $O/codes.txt
  python3 - "$q" >> $O/knavi.txt <<'P'
import sys, re
from bs4 import BeautifulSoup
s = BeautifulSoup(open('p.html', encoding='utf-8', errors='replace').read(), 'lxml')
print('=====', sys.argv[1])
t = s.get_text('\n', strip=True)
for l in t.split('\n'):
    if re.search(r'(20\d\d年|\d+月\d+日|\d+R|レース|ステークス|特別|未勝利|新馬|勝クラス)', l) and len(l) < 60:
        print('  H:', l)
for tb in s.find_all('table'):
    h = tb.get_text(' ', strip=True)[:200]
    if 'ナビ指数' in h and '馬番' in h:
        for tr in tb.find_all('tr')[:20]:
            print('  T:', ' | '.join(x.get_text(strip=True) for x in tr.find_all(['td', 'th'])))
        break
P
  sleep 5
done
