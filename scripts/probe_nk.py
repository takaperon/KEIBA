"""競馬ナビ：AI予想を読み込む JS と、その呼び出し先（暗号化して取る）"""
import sys, time, urllib.request, urllib.parse, os, subprocess, re
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
st = []
def get(u, data=None):
    time.sleep(3)
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, data=data, headers={'User-Agent': UA, 'Referer': 'https://m-jockey.co.jp/keiba-navi/localrace/free', 'X-Requested-With': 'XMLHttpRequest'}), timeout=30)
        b = r.read(); st.append(f'{r.status} {len(b)} {u} {data[:120] if data else ""}'); return b
    except Exception as e:
        st.append(f'ERR {e} {u} {data[:120] if data else ""}'); return b''
os.makedirs('/tmp/s', exist_ok=True)
js = get('https://m-jockey.co.jp/keiba-navi/wp-content/themes/cocoon-child-master/localraceaiyosou.js')
open('/tmp/s/ai.js', 'wb').write(js)
t = js.decode('utf-8', 'replace')
urls = set(re.findall(r'["\'](https?://[^"\']+|/[^"\']*(?:ajax|api|json|php)[^"\']*)["\']', t))
acts = set(re.findall(r'action["\']?\s*[:=]\s*["\']([\w\-]+)', t))
open('/tmp/s/found.txt', 'w').write('URLS ' + repr(urls) + '\nACTIONS ' + repr(acts))
day = time.strftime('%Y%m%d', time.gmtime(time.time() + 9 * 3600))
for a in list(acts)[:3]:
    for key in ('id', 'race_id', 'data_id'):
        b = get('https://m-jockey.co.jp/keiba-navi/wp-admin/admin-ajax.php', urllib.parse.urlencode({'action': a, key: f'{day}:44:11'}).encode())
        open(f'/tmp/s/ajax_{a}_{key}.txt', 'wb').write(b)
        if len(b) > 200:
            break
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
