"""父・母父の地方ダートでの馬場別成績（過去データ＋集めた血統）。暗号化して置く"""
import gzip, json, os, sys, subprocess
sires = sys.argv[1].split(','); dams = sys.argv[2].split(',')
ped = json.load(open('peddata/ped.json'))
G = {'良': '良', '稍': '稍重', '稍重': '稍重', '重': '重', '不': '不良', '不良': '不良'}
st = {}
def add(k, g, pos, win, plc):
    x = st.setdefault(k, {}).setdefault(g, [0, 0, 0, 0, 0])
    x[0] += 1; x[1] += pos == 1; x[2] += bool(pos) and pos <= 3; x[3] += win; x[4] += plc
for fn in sorted(os.listdir('nardata/races')):
    with gzip.open('nardata/races/' + fn, 'rt') as f:
        for l in f:
            r = json.loads(l)
            if r.get('surface') != 'ダ' or r['place'] == '65':
                continue
            g = G.get(r.get('going'))
            if not g:
                continue
            pay = r.get('payouts') or {}
            win = {p['combo']: p['yen'] for p in pay.get('単勝') or []}; plc = {p['combo']: p['yen'] for p in pay.get('複勝') or []}
            for h in r['runners']:
                p = ped.get(h.get('horse_id') or '')
                if not p:
                    continue
                pt = h.get('pos_text') or ''
                if h.get('pos') is None and any(c in pt for c in '取除消'):
                    continue
                pos = h.get('pos') or 0; n = str(h.get('num'))
                w = win.get(n, 0) if pos == 1 else 0; q = plc.get(n, 0) if pos and pos <= 3 else 0
                if p[0] in sires: add('父 ' + p[0], g, pos, w, q)
                if p[2] in dams: add('母父 ' + p[2], g, pos, w, q)
out = {'ped_horses': len(ped), 'stats': st}
os.makedirs('fo', exist_ok=True); json.dump(out, open('fo/sg.json', 'w'), ensure_ascii=False)
subprocess.run('bash scripts/seal.sh fo/sg.json fo/sg.sealed', shell=True, check=True)
