"""新馬戦の能力検査（能検）タイムの取得元確認：netkeiba 出馬表・馬ページ、楽天競馬 出馬表（暗号化して取る）"""
import sys, time, urllib.request, os, subprocess, re, datetime
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
st = []
def get(u, wait=3):
    time.sleep(wait)
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30)
        b = r.read(); st.append(f'{r.status} {len(b)} {u}'); return b
    except Exception as e:
        st.append(f'ERR {e} {u}'); return b''
os.makedirs('/tmp/s', exist_ok=True)
today = datetime.date.today()
found = []
for k in range(0, 12):
    d = (today - datetime.timedelta(days=k)).strftime('%Y%m%d')
    h = get(f'https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={d}').decode('utf-8', 'replace')
    for m in re.finditer(r'race_id=(\d{12})[^>]*>(.*?)</a>', h, re.S):
        txt = re.sub(r'<[^>]+>', ' ', m.group(2))
        if '新馬' in txt or 'ﾌﾚｯｼｭ' in txt or 'フレッシュ' in txt:
            found.append((d, m.group(1), re.sub(r'\s+', ' ', txt)[:60]))
    if len(found) >= 3:
        break
open('/tmp/s/found.txt', 'w').write('\n'.join(map(str, found)))
seen = set()
for d, rid, txt in found[:2]:
    if rid in seen: continue
    seen.add(rid)
    sh = get(f'https://nar.netkeiba.com/race/shutuba.html?race_id={rid}')
    open(f'/tmp/s/shutuba_{rid}.html', 'wb').write(sh)
    hid = re.search(rb'/horse/(\w+)', sh)
    if hid:
        h2 = hid.group(1).decode()
        open(f'/tmp/s/dbhorse_{h2}.html', 'wb').write(get(f'https://db.netkeiba.com/horse/{h2}/'))
        open(f'/tmp/s/narhorse_{h2}.html', 'wb').write(get(f'https://nar.netkeiba.com/horse/{h2}'))
# 楽天：その日の一覧から新馬のレースを探して出馬表を1つ（60秒間隔）
if found:
    d = found[0][0]
    lst = get(f'https://keiba.rakuten.co.jp/race_card/list/RACEID/{d}0000000000', 61).decode('utf-8', 'replace')
    open('/tmp/s/rakuten_list.html', 'w').write(lst)
    ids = sorted(set(re.findall(r'race_card/list/RACEID/(%s\d{8}00)' % d, lst)))
    open('/tmp/s/rakuten_ids.txt', 'w').write('\n'.join(ids))
    for rid in ids[:1]:
        v = get(f'https://keiba.rakuten.co.jp/race_card/list/RACEID/{rid}', 61).decode('utf-8', 'replace')
        open('/tmp/s/rakuten_venue.html', 'w').write(v)
        rs = sorted(set(re.findall(r'race_card/list/RACEID/(%s\d{10})' % d, v)) - {rid})
        for r2 in rs:
            pass
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
