"""競馬ナビ（m-jockey.co.jp/keiba-navi）の AI予想：robots.txt・ページ見本（暗号化して取る）"""
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
B = 'https://m-jockey.co.jp'
for name, u in [('robots.txt', f'{B}/robots.txt'), ('free.html', f'{B}/keiba-navi/localrace/free'),
                ('allrace.html', f'{B}/keiba-navi/localrace/ai-all-race-predictions/')]:
    open('/tmp/s/' + name, 'wb').write(get(u))
h = (open('/tmp/s/free.html', 'rb').read() + open('/tmp/s/allrace.html', 'rb').read()).decode('utf-8', 'replace')
links = sorted(set(re.findall(r'href="([^"]+)"', h)))
open('/tmp/s/links.txt', 'w').write('\n'.join(links))
cand = [l for l in links if re.search(r'localrace/(free|ai)[^"]*\d', l)][:4]
for i, l in enumerate(cand):
    u = l if l.startswith('http') else B + l
    open(f'/tmp/s/page{i}.html', 'wb').write(get(u))
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
