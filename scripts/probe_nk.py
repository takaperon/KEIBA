"""JRA出馬表の一覧に何日・何場が載っているか（公開情報なので暗号化不要だが形式を合わせる）"""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keiba import jra
from scripts.backfill import Fetcher
f = Fetcher(10, 2)
top = f.get('accessD.html', 'pw01dli00/F3')
out = []
for c in jra.cnames(top, 'pw01drl'):
    out.append('drl ' + c)
    h = f.get('accessD.html', c)
    rs = jra.cnames(h, 'pw01dde')
    out.append(f'   races {len(rs)} ' + ' '.join(sorted({r[-11:-3] for r in rs})) + ' ' + (rs[0] if rs else ''))
print('\n'.join(out))
os.makedirs('/tmp/s', exist_ok=True); open('/tmp/s/status.txt', 'w').write('\n'.join(out))
subprocess.run('tar -C /tmp/s -czf /tmp/sample.tgz .', shell=True, check=True)
subprocess.run(f'bash scripts/seal.sh /tmp/sample.tgz {sys.argv[1]}.sealed', shell=True, check=True)
