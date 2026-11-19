"""血統の取得元確認：JRA公式の出馬表（1R分の馬欄HTML）と、nar.netkeiba の馬柱ページ（暗号化）"""
import sys, time, urllib.request, os, subprocess, re, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import jra
from scripts.backfill import Fetcher
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
os.makedirs('/tmp/s', exist_ok=True)
st = []
try:
    f = Fetcher(10, 2)
    top = f.get('accessD.html', 'pw01dli00/F3')
    lists = jra.cnames(top, 'pw01drl')
    st.append('jra lists ' + ' '.join(c[-11:-3] for c in lists))
    if lists:
        h = f.get('accessD.html', lists[0])
        rs = jra.cnames(h, 'pw01dde')
        if rs:
            open('/tmp/s/jra_card.html', 'w').write(f.get('accessD.html', rs[0]))
except Exception as e:
    st.append('jra ERR ' + str(e)[:100])
def get(u):
    time.sleep(3)
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=40).read(); st.append(f'200 {len(b)} {u}'); return b
    except Exception as e:
        st.append(f'ERR {str(e)[:60]} {u}'); return b''
day = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y%m%d')
hl = get(f'https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={day}').decode('utf-8', 'replace')
ids = sorted(set(re.findall(r'race_id=(\d{12})', hl)))
if ids:
    rid = ids[0]
    open('/tmp/s/nar_past.html', 'wb').write(get(f'https://nar.netkeiba.com/race/shutuba_past.html?race_id={rid}'))
    open('/tmp/s/nar_shutuba.html', 'wb').write(get(f'https://nar.netkeiba.com/race/shutuba.html?race_id={rid}'))
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
