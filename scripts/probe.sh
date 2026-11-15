#!/bin/bash
# N1: JRA公式から取れるかの確認（少数・3秒間隔）
set -u
out=$1; mkdir -p $out/f
UA='Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
J=https://www.jra.go.jp
g() { sleep 3; curl -sSL -A "$UA" -m 30 -o "$out/f/$1" -w "%{http_code} %{content_type} %{size_download} $2\n" "$2" >> $out/status.txt 2>>$out/err.txt; }
p() { sleep 3; curl -sSL -A "$UA" -m 30 -o "$out/f/$1" -w "%{http_code} %{content_type} %{size_download} $2 $3\n" --data "cname=$3" "$J/JRADB/$2" >> $out/status.txt 2>>$out/err.txt; }
g robots.txt $J/robots.txt
p d_top.html accessD.html pw01dli00/F3
p s_top.html accessS.html pw01sli00/AF
p o_top.html accessO.html pw15oli00/6D
p s_past.html accessS.html pw01skl00999999/B3
# 文字コードを UTF-8 に変換したコピーと、ページ内の cname を抜き出す
for f in $out/f/*.html; do
  iconv -f CP932 -t UTF-8 "$f" > "${f%.html}.u8.html" 2>/dev/null || cp "$f" "${f%.html}.u8.html"
  grep -oE "pw[0-9a-z]+/[0-9A-F]{2}" "$f" | sort -u > "${f%.html}.cnames.txt"
done
# 2段目：見つかった cname を種類ごとに1つずつたどる（最大8件）
n=0
for f in $out/f/*.cnames.txt; do
  base=$(basename $f .cnames.txt)
  for c in $(head -40 $f); do
    pre=${c:0:5}
    case "$base" in d_*) a=accessD.html;; s_*) a=accessS.html;; o_*) a=accessO.html;; *) continue;; esac
    grep -q "^$pre" $out/seen.txt 2>/dev/null && continue
    echo $pre >> $out/seen.txt
    n=$((n+1)); [ $n -gt 8 ] && break 2
    p "2_${base}_$(echo $c | tr / _).html" $a $c
  done
done
for f in $out/f/2_*.html; do
  [ -f "$f" ] || continue
  iconv -f CP932 -t UTF-8 "$f" > "${f%.html}.u8.html" 2>/dev/null || cp "$f" "${f%.html}.u8.html"
  grep -oE "pw[0-9a-z]+/[0-9A-F]{2}" "$f" | sort -u > "${f%.html}.cnames.txt"
done
exit 0
