#!/bin/bash
# NAR-N1e: ほかの取得元の robots.txt（ページ本体は取らない）。403 だったところはブラウザ相当の UA でも確認
set -u
out=$1; mkdir -p $out/f
UA='Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
BUA='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
for h in db.netkeiba.com race.netkeiba.com www.jbis.or.jp www.keibalab.jp umanity.jp www.oddspark.com www.spat4.jp www.nankankeiba.com www.keiba.go.jp keiba.yahoo.co.jp sports.yahoo.co.jp www.keibabook.co.jp p.keibabook.co.jp; do
  sleep 2; curl -sSL -A "$UA" -m 30 -o "$out/f/$h.txt" -w "%{http_code} %{size_download} $h\n" "https://$h/robots.txt" >> $out/status.txt 2>>$out/err.txt
  c=$(tail -1 $out/status.txt | cut -d' ' -f1)
  if [ "$c" != "200" ]; then sleep 2; curl -sSL -A "$BUA" -m 30 -o "$out/f/$h.b.txt" -w "%{http_code} %{size_download} $h (browser UA)\n" "https://$h/robots.txt" >> $out/status.txt 2>>$out/err.txt; fi
done
# keiba.go.jp の過去の robots.txt（Wayback Machine の記録）
sleep 2; curl -sSL -A "$UA" -m 30 -o $out/f/wayback_cdx.txt "https://web.archive.org/cdx/search/cdx?url=keiba.go.jp/robots.txt&output=txt&collapse=digest" -w "%{http_code} wayback\n" >> $out/status.txt
exit 0
