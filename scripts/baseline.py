"""N4: ベタ買い回収率の基準。人気順・単勝オッズ帯・芝ダ・クラス別に、単勝と複勝を全頭100円ずつ買った場合。

注意：オッズ帯は最終オッズで切っている（締切前に同じ帯で買えるとは限らない）。基準として見るだけ。
"""
import argparse, glob, json, collections

BANDS = [(1, 2), (2, 3), (3, 5), (5, 7), (7, 10), (10, 15), (15, 20), (20, 30), (30, 50), (50, 100), (100, 10000)]


def band(o):
    for lo, hi in BANDS:
        if lo <= o < hi:
            return f'{lo}-{hi if hi < 10000 else ""}'
    return None


def load(data):
    seen = {}
    for fn in sorted(glob.glob(f'{data}/races/*.jsonl')):
        for line in open(fn):
            r = json.loads(line)
            seen[r['id']] = r
    return list(seen.values())


def pay_map(r, kind):
    return {ln['combo']: ln['yen'] for ln in r['payouts'].get(kind, []) if ln.get('yen')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    races = load(a.data)
    agg = collections.defaultdict(lambda: [0, 0.0, 0, 0.0, 0])  # 単勝:点数,払戻 複勝:点数,払戻, 的中(単)
    n_ok = 0
    for r in races:
        od = r.get('odds') or {}
        if not od:
            continue
        n_ok += 1
        tan, fuku = pay_map(r, '単勝'), pay_map(r, '複勝')
        surf = r.get('surface') or '?'
        cls = '障害' if surf == '障' else ('新馬未勝利' if any(x in (r.get('cls') or '') for x in ('新馬', '未勝利')) else
                                         ('1-3勝' if '勝クラス' in (r.get('cls') or '') else 'OP以上'))
        for h in r['runners']:
            if h['num'] is None or h['pos_text'] in ('取消', '除外'):
                continue
            o = od.get(str(h['num'])) or od.get(h['num'])
            if not o or not o.get('tan'):
                continue
            keys = [('全体', ''), ('人気', h['pop'] if h['pop'] and h['pop'] <= 12 else '13+'),
                    ('単勝オッズ帯', band(o['tan'])), ('芝ダ×オッズ帯', f"{surf} {band(o['tan'])}"),
                    ('クラス×オッズ帯', f"{cls} {band(o['tan'])}")]
            t = tan.get(str(h['num']), 0)
            f = fuku.get(str(h['num']), 0)
            for k in keys:
                g = agg[k]
                g[0] += 1; g[1] += t; g[2] += 1; g[3] += f; g[4] += 1 if t else 0
    rows = []
    for (cat, key), (nt, pt, nf, pf, hit) in agg.items():
        rows.append({'cat': cat, 'key': str(key), 'n': nt, 'win_hit': round(hit / nt, 4),
                     'win_roi': round(pt / (nt * 100), 4), 'place_roi': round(pf / (nf * 100), 4)})
    order = {c: i for i, c in enumerate(['全体', '人気', '単勝オッズ帯', '芝ダ×オッズ帯', 'クラス×オッズ帯'])}
    rows.sort(key=lambda x: (order[x['cat']], x['key'] if x['cat'] != '人気' else f"{x['key']:>3}"))
    res = {'races': len(races), 'races_with_odds': n_ok,
           'dates': [min(r['date'] for r in races), max(r['date'] for r in races)] if races else None, 'rows': rows}
    if a.out:
        json.dump(res, open(a.out, 'w'), ensure_ascii=False, indent=1)
    print(f"races={res['races']} with_odds={n_ok} range={res['dates']}")
    for x in rows:
        print(f"{x['cat']:<10} {x['key']:<14} n={x['n']:>6} 単勝的中={x['win_hit']:.3f} 単勝回収={x['win_roi']:.3f} 複勝回収={x['place_roi']:.3f}")


if __name__ == '__main__':
    main()
