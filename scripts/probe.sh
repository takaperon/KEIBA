#!/bin/bash
# N1/N2: JRA公式の各ページの中身確認（少数・3秒間隔）
set -u
out=$1; mkdir -p $out/f
UA='Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
J=https://www.jra.go.jp
p() { sleep 3; curl -sSL -A "$UA" -m 30 -o "$out/f/$1" -w "%{http_code} %{size_download} $2 $3\n" --data "cname=$3" "$J/JRADB/$2" >> $out/status.txt 2>>$out/err.txt; }
fix() { for f in "$@"; do iconv -f CP932 -t UTF-8 "$f" > "${f%.html}.u8.html" 2>/dev/null || cp "$f" "${f%.html}.u8.html"; grep -oE "pw[0-9a-z]+/[0-9A-F]{2}" "$f" | sort -u > "${f%.html}.cnames.txt"; done; }
# 1段目
p srl.html accessS.html pw01srl10082026050320261114/50
p sde.html accessS.html pw01sde1008202605031120261114/B7
p skl202410.html accessS.html pw01skl10202410/92
p orl.html accessO.html pw15orl00082026050420261115/15
fix $out/f/*.html
# 2段目：オッズ一覧と過去月ページのリンクを種類ごとに1つずつ（最大10件）
n=0
for base in orl skl202410; do
  a=accessO.html; [ $base = skl202410 ] && a=accessS.html
  for c in $(cat $out/f/$base.cnames.txt); do
    pre=${c:0:6}
    case $pre in pw01dl|pw01hl|pw01id|pw01sk|pw01sl|pw03tr|pw15ol|pw17hd|pw15or) continue;; esac
    grep -qx "$base$pre" $out/seen.txt 2>/dev/null && continue
    echo "$base$pre" >> $out/seen.txt
    n=$((n+1)); [ $n -gt 10 ] && break 2
    p "2_$(echo $c | tr / _).html" $a $c
  done
done
fix $out/f/2_*.html
exit 0
