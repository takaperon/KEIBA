"""各主催者の公式サイトで、能力検査（能検・能力試験）の結果ページを探す。robots.txt とトップ・リンク先（暗号化して取る）"""
import sys, time, urllib.request, urllib.parse, os, subprocess, re, json
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
st = []
def get(u):
    time.sleep(3)
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30)
        b = r.read(); st.append(f'{r.status} {len(b)} {u}'); return b, r.geturl()
    except Exception as e:
        st.append(f'ERR {str(e)[:60]} {u}'); return b'', u
os.makedirs('/tmp/s', exist_ok=True)
SITES = ['https://www.hokkaidokeiba.net/', 'https://www.iwatekeiba.or.jp/', 'https://www.nankankeiba.com/', 'https://www.tokyocitykeiba.com/',
         'https://www.kawasaki-keiba.jp/', 'https://www.urawa-keiba.jp/', 'https://www.funabashi-keiba.com/', 'https://www.kanazawakeiba.com/',
         'https://www.kasamatsu-keiba.com/', 'https://www.nagoyakeiba.com/', 'https://www.sonoda-himeji.jp/', 'https://www.keiba.or.jp/',
         'https://www.sagakeiba.net/', 'https://www.banei-keiba.or.jp/', 'https://www.jbis.or.jp/']
rep = {}
for s in SITES:
    host = urllib.parse.urlparse(s).netloc
    rb, _ = get(s + 'robots.txt')
    top, final = get(s)
    t = top.decode('utf-8', 'replace')
    if 'charset=shift_jis' in t.lower() or 'charset=sjis' in t.lower():
        t = top.decode('cp932', 'replace')
    links = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
        txt = re.sub(r'<[^>]+>|\s+', '', m.group(2))
        if re.search(r'能力|能検|検査|試験|新馬|2歳|２歳', txt):
            links.append((urllib.parse.urljoin(final, m.group(1)), txt[:30]))
    rep[host] = {'robots': rb.decode('utf-8', 'replace')[:800], 'top_len': len(top), 'final': final, 'links': links[:20]}
    for i, (u, txt) in enumerate(links[:3]):
        b, _ = get(u)
        open(f'/tmp/s/{host}_{i}.html', 'wb').write(b)
json.dump(rep, open('/tmp/s/report.json', 'w'), ensure_ascii=False, indent=1)
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
