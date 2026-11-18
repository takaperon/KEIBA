"""能力検査 3回目：一覧ページ→各回の結果の中身（暗号化して取る）。南関・門別は再確認だけ"""
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
# 岩手：一覧→最新2件
t = save('iwate_list.html', 'https://www.iwatekeiba.or.jp/race-data/noken/')
m = re.findall(r'href="(https?://www\.iwatekeiba\.or\.jp/news/\d+e)"', t)
for i, u in enumerate(m[:2]):
    t2 = save(f'iwate_post{i}.html', u)
    for j, p in enumerate(re.findall(r'href="([^"]+\.(?:pdf|xlsx?))"', t2)[:2]):
        open(f'/tmp/s/iwate_post{i}_{j}.' + p.rsplit('.', 1)[1], 'wb').write(get(urllib.parse.urljoin(u, p)))
# 名古屋：最新の結果PDF
t = save('nagoya_cap.html', 'https://www.nagoyakeiba.com/info/program/capability/index.html')
for i, p in enumerate(re.findall(r'<a href="([^"]+\.pdf)"[^>]*>[^<]*能力審査結果', t)[:2]):
    open(f'/tmp/s/nagoya_res{i}.pdf', 'wb').write(get(p))
# 高知：カテゴリ一覧（2ページ目まで）
save('kochi_cat.html', 'https://www.keiba.or.jp/?cat=42')
save('kochi_cat2.html', 'https://www.keiba.or.jp/?cat=42&paged=2')
# 兵庫・笠松・佐賀の一覧（過去分の広がり）
save('hyogo_list.html', 'https://www.sonoda-himeji.jp/data/ability/')
save('hyogo_list5.html', 'https://www.sonoda-himeji.jp/data/ability/?p=5')
save('kasamatsu_list.html', 'https://www.kasamatsu-keiba.com/ability')
save('saga_list.html', 'https://www.sagakeiba.net/raceinfo/exam/')
save('saga_14.html', 'https://www.sagakeiba.net/raceinfo/exam/exam202614/')
# 金沢：投稿サイトマップで能検らしきもの
for n in (1, 2):
    t = save(f'kanazawa_posts{n}.xml', f'https://www.kanazawakeiba.com/wp-sitemap-posts-post-{n}.xml')
t = save('kanazawa_pages.xml', 'https://www.kanazawakeiba.com/wp-sitemap-posts-page-1.xml')
save('kanazawa_top.html', 'https://www.kanazawakeiba.com/')
# ばんえい
save('banei_top.html', 'https://www.banei-keiba.or.jp/')
# 南関（川崎の成績リンク先）・門別：再確認だけ
save('nankan_shiken.html', 'https://www.nankankeiba.com/shiken_list/2026111321.do')
save('hokkaido_top.html', 'https://www.hokkaidokeiba.net/')
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
