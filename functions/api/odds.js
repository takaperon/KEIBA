// 更新ボタン用：その場の単勝オッズを返す（地方＝netkeiba のオッズAPI、中央＝JRA公式）。
// 鍵を持つ端末からの署名つきリクエストだけ受け付ける（公開鍵で確認。秘密の値は置かない）。
const PUB = 'MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAuomsLOeecVhMsJSUByYIb/4dMQhuwic+LLmdmUNRlwiiMT8wE8V1Uy7Z6fUUm1wFTl6gLZVo/5oE5WgpX77b0zxBiM9yoCn/Ehr5tk1dkicvZlwI+DFMKuXYtYNZx9eJJOYdLMfkSScid/TEnRx8gCyI1ONwRrrwS7hSQm4+K+0+iAgY0AYKVJ137+RaVah76DMlnB9GK8JeB6GzBkOyY/4kJrgbutnZjPG0fhM+vAV8rqUX7DKja8i/f0N1LVvAkHiTZ20dAEFvhIY1toPjAbwg7/BS0WKzuWFw2Et1dNGY7yEsDUEJDZG2g0zOSij+76Ttk1P3yTUc632Ib+v+SYRupm4CTSQe+p1FNfRVEags004pISuXSYzV/RwXCY3dZooR+MGYluS3jSQxMZYG0RiZ64dc7P8IuEGoKpnAZcTpMGZMkyujwBozZT3DRGeLF2CRv+C0OyA+lCURXWGQ4yiUwodfn3gANRReNLRXSkG7v3ihIBi+qli7mrd5BYrNAgMBAAE=';
const UA = 'Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)';
const b2u = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
async function verify(msg, sig) {
  const key = await crypto.subtle.importKey('spki', b2u(PUB), { name: 'RSA-PSS', hash: 'SHA-256' }, false, ['verify']);
  return crypto.subtle.verify({ name: 'RSA-PSS', saltLength: 32 }, key, b2u(sig), new TextEncoder().encode(msg));
}
const J = 'https://www.jra.go.jp/JRADB/';
async function jpost(access, cname) {
  const r = await fetch(J + access, { method: 'POST', headers: { 'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'cname=' + cname });
  return new TextDecoder('shift_jis').decode(await r.arrayBuffer());
}
const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
export async function onRequestGet({ request }) {
  const u = new URL(request.url);
  const kind = u.searchParams.get('kind'), id = u.searchParams.get('id') || '', ts = +u.searchParams.get('ts'), sig = u.searchParams.get('sig') || '';
  if (!kind || !ts || Math.abs(Date.now() / 1000 - ts) > 300) return json({ error: 'expired' }, 401);
  try { if (!(await verify(kind + '|' + id + '|' + ts, sig))) return json({ error: 'bad signature' }, 401); } catch (e) { return json({ error: 'bad signature' }, 401); }
  const at = new Date(Date.now() + 9 * 3600e3).toISOString().slice(11, 19);
  if (kind === 'nar') {
    if (!/^\d{12}$/.test(id)) return json({ error: 'id' }, 400);
    const r = await fetch('https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id=' + id + '&type=1&action=update', { headers: { 'User-Agent': UA } });
    const j = await r.json();
    const odds = {};
    for (const [k, v] of Object.entries(j.ary_odds || {})) odds[+k] = [parseFloat(v.Odds) || null, parseInt(v.Ninki) || null];
    return json({ at, status: j.odds_status, odds });
  }
  if (kind === 'jra') {
    // id = 場コード(2)+R(2)+日付(8)  例 081120261115
    const m = id.match(/^(\d{2})(\d{2})(\d{8})$/); if (!m) return json({ error: 'id' }, 400);
    const top = await jpost('accessO.html', 'pw15oli00/6D');
    const lists = [...new Set(top.match(/pw15orl[0-9A-Za-z]+\/[0-9A-F]{2}/g) || [])].filter(c => c.includes(m[3]));
    for (const c of lists) {
      const h = await jpost('accessO.html', c);
      const cs = [...new Set(h.match(/pw151ou[0-9A-Za-z]+\/[0-9A-F]{2}/g) || [])];
      const hit = cs.find(x => { const y = x.match(/^pw151ou\w{2}(\d{2})\d{8}(\d{2})(\d{8})/); return y && y[1] === m[1] && +y[2] === +m[2] && y[3] === m[3]; });
      if (!hit) continue;
      const p = await jpost('accessO.html', hit);
      const odds = {};
      for (const tr of p.split('<tr').slice(1)) {
        const n = tr.match(/<td class="num">(\d+)<\/td>/), t = tr.match(/<td class="odds_tan">([\d.]+)<\/td>/);
        if (n && t) odds[+n[1]] = [parseFloat(t[1]), null];
      }
      const order = Object.entries(odds).sort((a, b) => a[1][0] - b[1][0]); order.forEach(([k], i) => { odds[k][1] = i + 1; });
      return json({ at, status: 'jra', odds });
    }
    return json({ error: 'not found' }, 404);
  }
  return json({ error: 'kind' }, 400);
}
