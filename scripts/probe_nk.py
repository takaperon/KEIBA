"""血統の過去分：過去レースの馬柱ページが見られるか（地方・中央）。暗号化して置く"""
import sys, time, urllib.request, os, subprocess
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
os.makedirs('/tmp/s', exist_ok=True)
st = []
U = {'nar_2025': 'https://nar.netkeiba.com/race/shutuba_past.html?race_id=202544050101',
     'nar_2026': 'https://nar.netkeiba.com/race/shutuba_past.html?race_id=202654111501',
     'jra_2025': 'https://race.netkeiba.com/race/shutuba_past.html?race_id=202505040101',
     'jra_2026': 'https://race.netkeiba.com/race/shutuba_past.html?race_id=202605041101',
     'nar_robots': 'https://nar.netkeiba.com/robots.txt', 'race_robots': 'https://race.netkeiba.com/robots.txt'}
for k, u in U.items():
    time.sleep(3)
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=40).read(); st.append(f'200 {len(b)} {k}')
    except Exception as e:
        b = b''; st.append(f'ERR {str(e)[:60]} {k}')
    open(f'/tmp/s/{k}.html', 'wb').write(b)
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
