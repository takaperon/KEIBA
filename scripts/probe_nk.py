"""能力検査 4回目：0頭しか読めなかったページの中身（暗号化して取る）"""
import sys, time, urllib.request, os, subprocess
UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
os.makedirs('/tmp/s', exist_ok=True)
U = ['https://www.sagakeiba.net/raceinfo/exam/exam202601/',
     'https://www.kasamatsu-keiba.com/resources/pdfs/ability/2026/1787877667_d4ddf1e8be9c2c326852.pdf',
     'https://www.kasamatsu-keiba.com/resources/pdfs/ability/2025/1765925933_53dd9398b3db9f4a95fa.pdf',
     'https://www.keiba.or.jp/wp/wp-content/uploads/2026/09/c93a6641274c0752c9fcb2428d2ba24c.pdf']
st = []
for i, u in enumerate(U):
    time.sleep(3)
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=40).read(); st.append(f'200 {len(b)} {u}')
    except Exception as e:
        b = b''; st.append(f'ERR {e} {u}')
    open(f'/tmp/s/z{i}.' + ('pdf' if u.endswith('.pdf') else 'html'), 'wb').write(b)
open('/tmp/s/status.txt', 'w').write('\n'.join(st))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
