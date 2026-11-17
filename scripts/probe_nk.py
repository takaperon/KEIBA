"""出馬表ページの見本を暗号化して取る（中身は公開しない）"""
import re, sys, time, urllib.request, os, subprocess
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
def get(u):
    time.sleep(3)
    return urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30).read()
day = time.strftime('%Y%m%d', time.gmtime(time.time() + 9 * 3600))
h = get(f'https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={day}').decode('utf-8', 'replace')
ids = sorted(set(re.findall(r'race_id=(\d{12})', h)))
os.makedirs('/tmp/s', exist_ok=True)
open('/tmp/s/race_list.html', 'wb').write(h.encode())
for rid in [ids[-1], ids[len(ids) // 2]]:
    open(f'/tmp/s/shutuba_{rid}.html', 'wb').write(get(f'https://nar.netkeiba.com/race/shutuba.html?race_id={rid}'))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
