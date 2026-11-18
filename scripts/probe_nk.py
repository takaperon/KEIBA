"""外部指数（水分ボンバーオンライン・かよちんの地方競馬予想）の robots.txt とページ見本（暗号化して取る）"""
import sys, time, urllib.request, os, subprocess, re
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
for name, u in [('sbo_robots.txt', 'https://nar.k-ba.net/robots.txt'), ('sbo_top.html', 'https://nar.k-ba.net/'),
                ('kayo_robots.txt', 'https://kayochinkeiba.com/robots.txt'), ('kayo_1117kanazawa.html', 'https://kayochinkeiba.com/261117kanazawa/'),
                ('kayo_old_241120ooi.html', 'https://kayochinkeiba.com/241120ooi/'), ('kayo_old_250520ooi.html', 'https://kayochinkeiba.com/250520ooi/')]:
    open('/tmp/s/' + name, 'wb').write(get(u))
top = open('/tmp/s/sbo_top.html', 'rb').read().decode('utf-8', 'replace')
links = sorted(set(re.findall(r'href="([^"]+)"', top)))
open('/tmp/s/sbo_top_links.txt', 'w').write('\n'.join(links))
cand = [l for l in links if re.search(r'race|\d{8}', l)][:3]
for i, l in enumerate(cand):
    u = l if l.startswith('http') else 'https://nar.k-ba.net' + ('' if l.startswith('/') else '/') + l
    open(f'/tmp/s/sbo_page{i}.html', 'wb').write(get(u))
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
