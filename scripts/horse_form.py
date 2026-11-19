"""指定レースの出走馬の近走（過去データから）。暗号化して置く"""
import gzip, json, os, sys, subprocess
names = sys.argv[1].split(',')
H = {}
for fn in sorted(os.listdir('nardata/races')):
    with gzip.open('nardata/races/' + fn, 'rt') as f:
        for l in f:
            r = json.loads(l)
            for h in r['runners']:
                if h['horse'] in names:
                    H.setdefault(h['horse'], {})[r['id']] = (r['date'], r['place_name'], r.get('race_name'), r.get('surface'), r.get('distance'), r.get('going'), len(r['runners']),
                                                     h.get('pos_text'), h.get('pop'), h.get('jockey'), h.get('corners'), h.get('last3f'), h.get('margin'), h.get('time'))
out = {n: sorted(H.get(n, {}).values(), reverse=True)[:5] for n in names}
os.makedirs('fo', exist_ok=True)
json.dump(out, open('fo/form.json', 'w'), ensure_ascii=False)
subprocess.run('bash scripts/seal.sh fo/form.json fo/form.sealed', shell=True, check=True)
