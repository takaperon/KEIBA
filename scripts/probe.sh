#!/bin/bash
# ばんえい（帯広）：db.netkeiba の結果ページと nar.netkeiba の出馬表が今のパーサで読めるか（BN-0）
set -u
O=$1; mkdir -p $O
pip install -q beautifulsoup4 lxml >/dev/null 2>&1
UA='Mozilla/5.0 (compatible; KEIBA-personal/0.1)'
curl -s -A "$UA" "https://db.netkeiba.com/race/list/20261123/" -o list.html -w "list %{http_code}\n" >> $O/codes.txt; sleep 3
curl -s -A "$UA" "https://db.netkeiba.com/race/202665112310/" -o r.html -w "race %{http_code}\n" >> $O/codes.txt; sleep 3
curl -s -A "$UA" "https://nar.netkeiba.com/race/shutuba.html?race_id=202665112810" -o s.html -w "shutuba %{http_code}\n" >> $O/codes.txt; sleep 3
curl -s -A "$UA" "https://nar.netkeiba.com/race/result.html?race_id=202665112310" -o nr.html -w "nar_result %{http_code}\n" >> $O/codes.txt
python3 - > $O/banei.txt <<'P'
import sys, json, re
sys.path.insert(0, '.')
from keiba import nk
from bs4 import BeautifulSoup
L = nk.decode(open('list.html', 'rb').read()); ids = [i for i in nk.race_ids(L) if i[4:6] == '65']
print('11/23 のばんえいのレースID', len(ids), ids[:3])
h = nk.decode(open('r.html', 'rb').read())
r = nk.parse_race(h, '202665112310')
print('== parse_race', {k: v for k, v in r.items() if k not in ('runners', 'payouts', 'corner_text')})
print('払戻の券種', list((r.get('payouts') or {}).keys()))
for x in r['runners'][:4]:
    print('  ', x)
t = BeautifulSoup(h, 'lxml').get_text(' ', strip=True)
for k in ('水分', '馬場', 'ダ', '200m', '障害'):
    i = t.find(k); print('  文中', k, t[max(0, i - 40):i + 60] if i >= 0 else '-')
s = nk.decode(open('s.html', 'rb').read())
x = nk.parse_shutuba(s, '202665112810')
print('== parse_shutuba', {k: v for k, v in x.items() if k not in ('runners',)})
for y in x['runners'][:3]:
    print('  ', y)
t2 = BeautifulSoup(s, 'lxml').get_text(' ', strip=True)
i = t2.find('水分'); print('  出馬表の水分', t2[max(0, i - 60):i + 40] if i >= 0 else '-')
P
