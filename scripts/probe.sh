#!/bin/bash
# デイリー馬屋のスピード指数：robots.txt と、過去のレースのページが見られるか（指数の表だけ書き出す）
set -u
O=$1; mkdir -p $O
pip install -q beautifulsoup4 lxml >/dev/null 2>&1
for q in "ymd=20261122&venue=36&race_num=01" "ymd=20261122&venue=54&race_num=01" "ymd=20261122&venue=55&race_num=02"; do
  curl -s -A 'Mozilla/5.0 (compatible; KEIBA-personal/0.1)' "https://m-jockey.co.jp/keiba-navi/localrace/ai-all-race-predictions/?$q" -o p.html -w "$q %{http_code}\n" >> $O/codes.txt
  python3 - "$q" >> $O/knavi_nar.txt <<'P'
import sys, re
from bs4 import BeautifulSoup
s = BeautifulSoup(open('p.html', encoding='utf-8', errors='replace').read(), 'lxml')
print('=====', sys.argv[1])
for i, tb in enumerate(s.find_all('table')):
    h = tb.get_text(' ', strip=True)[:200]
    if 'ナビ指数' in h and '馬番' in h:
        pv = tb.find_previous(string=re.compile(r'(表示例|\d+月\d+日)'))
        print(f'  TABLE {i} 直前:', (pv or '').strip()[:60])
        for tr in tb.find_all('tr')[:5]:
            print('  T:', ' | '.join(x.get_text(strip=True)[:25] for x in tr.find_all(['td', 'th'])))
P
  sleep 5
done
