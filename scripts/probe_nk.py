"""能力検査 5回目：名古屋の過去の能力審査結果PDF。公式ページには最新回しか載らないので、
Internet Archive に残っている公式ページの過去の写しからPDFのURLを集め、PDF自体は公式サイトから取る（暗号化して置く）"""
import sys, time, urllib.request, os, subprocess, re, json
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
os.makedirs('/tmp/s', exist_ok=True)
st = []
def get(u, w=3):
    time.sleep(w)
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=60).read(); st.append(f'200 {len(b)} {u}'); return b
    except Exception as e:
        st.append(f'ERR {str(e)[:80]} {u}'); return b''
cdx = get('http://web.archive.org/cdx/search/cdx?url=nagoyakeiba.com/info/program/capability/index.html&output=json&from=2025&filter=statuscode:200&collapse=digest').decode('utf-8', 'replace')
open('/tmp/s/cdx.json', 'w').write(cdx)
rows = json.loads(cdx)[1:] if cdx.strip().startswith('[') else []
links = {}
for r in rows[:60]:
    ts = r[1]
    t = get(f'http://web.archive.org/web/{ts}id_/https://www.nagoyakeiba.com/info/program/capability/index.html', 4).decode('utf-8', 'replace')
    for u, title in re.findall(r'<a href="(?:https?://web\.archive\.org/web/\d+(?:id_)?/)?(https://www\.nagoyakeiba\.com/info/program/file/[0-9a-f]+\.pdf)"[^>]*>([^<]*能力審査結果[^<]*)', t):
        links[u] = title
json.dump(links, open('/tmp/s/links.json', 'w'), ensure_ascii=False, indent=1)
for i, u in enumerate(list(links)[:3]):
    open(f'/tmp/s/p{i}.pdf', 'wb').write(get(u))
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
