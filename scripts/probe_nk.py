"""外部指数：水分ボンバーの過去ページの残り具合と表の形、かよちんの記事一覧（sitemap）"""
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
S = 'https://nar.k-ba.net'
for name, u in [('sbo_today_list.html', f'{S}/20261118/20/list.html'), ('sbo_today_r1.html', f'{S}/20261118/20/1/table.html'),
                ('sbo_1117.html', f'{S}/20261117/'), ('sbo_20260501.html', f'{S}/20260501/'), ('sbo_20250520.html', f'{S}/20250520/'),
                ('sbo_20241120.html', f'{S}/20241120/'), ('kayo_sitemap.rss', 'https://kayochinkeiba.com/sitemap.rss'),
                ('kayo_sitemap_xml.xml', 'https://kayochinkeiba.com/sitemap.xml'), ('kayo_cat.html', 'https://kayochinkeiba.com/category/chihou/')]:
    open('/tmp/s/' + name, 'wb').write(get(u))
t = open('/tmp/s/sbo_20250520.html', 'rb').read().decode('utf-8', 'replace')
m = re.search(r'//nar\.k-ba\.net/(20250520/\d+/\d+/table\.html)', t)
if m:
    open('/tmp/s/sbo_old_race.html', 'wb').write(get(f'{S}/{m.group(1)}'))
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
