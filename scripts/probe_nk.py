"""競馬ナビ：レースごとのAI予想ページ（当日・過去）の見本（暗号化して取る）"""
import sys, time, urllib.request, os, subprocess
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
st = []
def get(u):
    time.sleep(3)
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30)
        b = r.read(); st.append(f'{r.status} {len(b)} {u}'); return b
    except Exception as e:
        st.append(f'ERR {e} {u}'); return b''
os.makedirs('/tmp/s', exist_ok=True)
B = 'https://m-jockey.co.jp/keiba-navi/localrace/free'
day = time.strftime('%Y%m%d', time.gmtime(time.time() + 9 * 3600))
for name, q in [('today_44_11', f'ymd={day}&venue=44&race_num=11'), ('d1117_44_7', 'ymd=20261117&venue=44&race_num=7'),
                ('d1001_44_7', 'ymd=20261001&venue=44&race_num=7'), ('d250520_44_7', 'ymd=20250520&venue=44&race_num=7')]:
    open(f'/tmp/s/{name}.html', 'wb').write(get(f'{B}?{q}'))
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
