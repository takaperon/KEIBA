"""結果ページの見本を暗号化して取る（中身は公開しない）"""
import sys, time, urllib.request, os, subprocess
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
def get(u):
    time.sleep(3)
    try:
        return urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30).read()
    except Exception as e:
        return ('ERR ' + str(e)).encode()
os.makedirs('/tmp/s', exist_ok=True)
rid = '202644111707'
open('/tmp/s/nar_result.html', 'wb').write(get(f'https://nar.netkeiba.com/race/result.html?race_id={rid}'))
open('/tmp/s/db_race.html', 'wb').write(get(f'https://db.netkeiba.com/race/{rid}/'))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
