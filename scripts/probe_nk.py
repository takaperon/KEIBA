"""中央の外部指数の取得元確認：競馬ナビ（JRA 全レースAI予想）の一覧と1レース分（暗号化）"""
import sys, time, urllib.request, urllib.parse, os, subprocess, re
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
os.makedirs('/tmp/s', exist_ok=True)
st = []
def get(u):
    time.sleep(4)
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=40).read(); st.append(f'200 {len(b)} {u}'); return b.decode('utf-8', 'replace')
    except Exception as e:
        st.append(f'ERR {str(e)[:60]} {u}'); return ''
t = get('https://m-jockey.co.jp/keiba-navi/jra/ai'); open('/tmp/s/jra_ai.html', 'w').write(t)
links = sorted(set(re.findall(r'href="([^"]*(?:ai-all-race|jra/ai)[^"]*)"', t)))
open('/tmp/s/links.txt', 'w').write('\n'.join(links))
cand = [l.replace('&#038;', '&') for l in links if 'ymd=' in l][:2]
for i, l in enumerate(cand):
    open(f'/tmp/s/race{i}.html', 'w').write(get(urllib.parse.urljoin('https://m-jockey.co.jp/', l)))
# 過去日は取れるか（地方では403だった）
open('/tmp/s/past.html', 'w').write(get('https://m-jockey.co.jp/keiba-navi/jra/ai/?ymd=20261115&venue=05&race_num=11'))
open('/tmp/s/status.txt', 'w').write('\n'.join(st)); print('\n'.join(st))
sys.path.insert(0, os.getcwd())
from keiba import ext
for i in range(2):
    try:
        print('knavi_race', i, ext.knavi_race(open(f'/tmp/s/race{i}.html').read()))
    except Exception as e:
        print('parse ERR', e)
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
