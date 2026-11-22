#!/bin/bash
# デイリー馬屋のスピード指数：robots.txt と、過去のレースのページが見られるか（指数の表だけ書き出す）
set -u
O=$1; mkdir -p $O
pip install -q beautifulsoup4 lxml >/dev/null 2>&1
curl -s -A 'Mozilla/5.0 (compatible; KEIBA-personal/0.1)' https://www.daily.co.jp/robots.txt > $O/daily_robots.txt
for id in 202608041110 202608050601 202605050301 202506030501 202509020812 202408010101; do
  curl -s -A 'Mozilla/5.0 (compatible; KEIBA-personal/0.1)' "https://www.daily.co.jp/umaya/race/shutsuba.shtml?race_id=$id" -o p.html -w "$id %{http_code} %{size_download}\n" >> $O/codes.txt
  python3 - "$id" >> $O/daily.txt <<'P'
import sys, re
from bs4 import BeautifulSoup
s = BeautifulSoup(open('p.html', encoding='utf-8', errors='replace').read(), 'lxml')
print('=====', sys.argv[1], (s.title.get_text(strip=True) if s.title else '')[:80])
t = s.get_text('\n', strip=True)
m = re.search(r'20\d\d/\d+/\d+\([^)]*\)[^\n]{0,40}', t); print('  日付:', m.group(0) if m else '-')
for tb in s.find_all('table'):
    if 'SP' in tb.get_text(' ', strip=True)[:300] or '指数' in tb.get_text(' ', strip=True)[:300]:
        hdr = [x.get_text(' ', strip=True)[:12] for x in tb.find_all('tr')[0].find_all(['th', 'td'])]
        print('  表の見出し:', hdr)
        for tr in tb.find_all('tr')[1:4]:
            print('  T:', ' | '.join(x.get_text(' ', strip=True)[:14] for x in tr.find_all(['td', 'th'])))
        break
P
  sleep 5
done
