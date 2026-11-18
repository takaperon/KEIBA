"""楽天競馬の新馬戦 出馬表に能検タイムが載っているか（60秒間隔・2ページ、暗号化して取る）"""
import sys, time, urllib.request, os, subprocess
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
st = []
def get(u):
    time.sleep(61)
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30)
        b = r.read(); st.append(f'{r.status} {len(b)} {u}'); return b
    except Exception as e:
        st.append(f'ERR {e} {u}'); return b''
os.makedirs('/tmp/s', exist_ok=True)
open('/tmp/s/rk_card.html', 'wb').write(get('https://keiba.rakuten.co.jp/race_card/list/RACEID/202611172015120203'))
open('/tmp/s/rk_perf.html', 'wb').write(get('https://keiba.rakuten.co.jp/race_performance/list/RACEID/202611172015120203'))
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
