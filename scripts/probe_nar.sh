#!/bin/bash
# NAR-N1b: 代わりの取得元の robots.txt だけを確認（ページ本体は取らない）
set -u
out=$1; mkdir -p $out/f
UA='Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
for h in keiba.rakuten.co.jp www.oddspark.com nar.netkeiba.com www.spat4.jp www.nankankeiba.com www.keiba.go.jp; do
  sleep 2; curl -sSL -A "$UA" -m 30 -o "$out/f/$h.robots.txt" -w "%{http_code} %{size_download} $h\n" "https://$h/robots.txt" >> $out/status.txt 2>>$out/err.txt
done
exit 0
