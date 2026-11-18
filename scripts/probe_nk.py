"""能力検査 2回目：各主催者の結果ページの中身（暗号化して取る）"""
import sys, time, urllib.request, urllib.parse, os, subprocess, re, json
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
st = []
def get(u):
    time.sleep(3)
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=40)
        b = r.read(); st.append(f'{r.status} {len(b)} {u}'); return b
    except Exception as e:
        st.append(f'ERR {str(e)[:60]} {u}'); return b''
os.makedirs('/tmp/s', exist_ok=True)
def save(name, u):
    b = get(u); open('/tmp/s/' + name, 'wb').write(b); return b.decode('utf-8', 'replace')
t = save('iwate_list.html', 'https://www.iwatekeiba.or.jp/race-data/noken/')
m = re.findall(r'href="(https://www\.iwatekeiba\.or\.jp/[^"]*(?:noken|kensa|nouryoku)[^"]*)"', t)
m = [x for x in m if x.rstrip('/') != 'https://www.iwatekeiba.or.jp/race-data/noken']
open('/tmp/s/iwate_links.txt', 'w').write('\n'.join(sorted(set(m))))
if m: save('iwate_post.html', m[0])
save('hyogo_130.html', 'https://www.sonoda-himeji.jp/data/ability/detail/130')
t = save('nagoya_cap.html', 'https://www.nagoyakeiba.com/info/program/capability/index.html')
pdfs = re.findall(r'href="([^"]+\.pdf)"', t)
open('/tmp/s/nagoya_pdfs.txt', 'w').write('\n'.join(pdfs))
cap = [p for p in pdfs if 'capability' in p or 'program' in p]
if cap: open('/tmp/s/nagoya_first.pdf', 'wb').write(get(urllib.parse.urljoin('https://www.nagoyakeiba.com/info/program/capability/', cap[0])))
t = save('kochi_post.html', 'https://www.keiba.or.jp/?p=131216')
dl = re.findall(r'href="([^"]+\.(?:pdf|xlsx?))"', t)
open('/tmp/s/kochi_dl.txt', 'w').write('\n'.join(dl))
if dl: open('/tmp/s/kochi_first.' + dl[0].rsplit('.', 1)[1], 'wb').write(get(dl[0]))
open('/tmp/s/kasamatsu_first.pdf', 'wb').write(get('https://www.kasamatsu-keiba.com/resources/pdfs/ability/2026/1793919472_700c3c2387e779780e0d.pdf'))
t = save('kawasaki.html', 'https://www.kawasaki-keiba.jp/data/training_test/')
js = re.findall(r'src="([^"]+\.js[^"]*)"', t)
open('/tmp/s/kawasaki_js.txt', 'w').write('\n'.join(js))
t = save('urawa_top.html', 'https://www.urawa-keiba.jp/')
open('/tmp/s/urawa_links.txt', 'w').write('\n'.join(sorted(set(re.findall(r'href="([^"]+)"', t)))))
save('fkeiba_robots.txt', 'https://www.f-keiba.com/robots.txt')
t = save('fkeiba_top.html', 'https://www.f-keiba.com/')
open('/tmp/s/fkeiba_links.txt', 'w').write('\n'.join(sorted(set(re.findall(r'href="([^"]+)"', t)))))
t = save('kanazawa_sitemap.xml', 'https://www.kanazawakeiba.com/wp-sitemap.xml')
save('hokkaido_robots.txt', 'https://www.hokkaidokeiba.net/robots.txt')
save('hokkaido_top.html', 'https://www.hokkaidokeiba.net/')
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
