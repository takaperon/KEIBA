"""netkeiba が今アクセスを受け付けているかの確認（1回ずつだけ）"""
import sys, time, urllib.request, os, subprocess
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
os.makedirs('/tmp/s', exist_ok=True)
st = []
for u in ['https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date=20261120',
          'https://db.netkeiba.com/race/202644111911/',
          'https://race.netkeiba.com/top/race_list_sub.html?kaisai_date=20261122']:
    time.sleep(5)
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30); st.append(f'{r.status} {u}')
    except Exception as e:
        st.append(f'ERR {str(e)[:60]} {u}')
open('/tmp/s/status.txt', 'w').write('\n'.join(st)); print('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
