#!/bin/bash
# NAR-N1: 地方競馬公式（keiba.go.jp）から取れるかの確認（少数・3秒間隔）
set -u
out=$1; mkdir -p $out/f
UA='Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
K=https://www.keiba.go.jp
g() { sleep 3; curl -sSL -A "$UA" -m 30 -o "$out/f/$1" -w "%{http_code} %{size_download} $2\n" "$2" >> $out/status.txt 2>>$out/err.txt; }
g robots.txt $K/robots.txt
g top.html "$K/KeibaWeb/TodayRaceInfo/TodayRaceInfoTop"
# ページ内のリンクを種類ごとに1つずつたどる（最大12件）
grep -oE 'href="[^"]*KeibaWeb/[^"]+"' $out/f/top.html | sed 's/href="//;s/"$//;s/&amp;/\&/g' | sort -u > $out/links1.txt
n=0
while read -r u; do
  t=$(echo "$u" | sed -E 's#.*KeibaWeb/([A-Za-z]+/[A-Za-z]+).*#\1#')
  grep -qx "$t" $out/seen.txt 2>/dev/null && continue; echo "$t" >> $out/seen.txt
  n=$((n+1)); [ $n -gt 12 ] && break
  case "$u" in http*) url=$u;; /*) url=$K$u;; *) url=$K/KeibaWeb/TodayRaceInfo/$u;; esac
  g "1_$(echo $t | tr / _).html" "$url"
done < $out/links1.txt
# 2段目
cat $out/f/1_*.html | grep -oE 'href="[^"]*KeibaWeb/[^"]+"' | sed 's/href="//;s/"$//;s/&amp;/\&/g' | sort -u > $out/links2.txt
n=0
while read -r u; do
  t=$(echo "$u" | sed -E 's#.*KeibaWeb/([A-Za-z]+/[A-Za-z]+).*#\1#')
  grep -qx "$t" $out/seen.txt 2>/dev/null && continue; echo "$t" >> $out/seen.txt
  n=$((n+1)); [ $n -gt 14 ] && break
  case "$u" in http*) url=$u;; /*) url=$K$u;; *) url=$K/KeibaWeb/TodayRaceInfo/$u;; esac
  g "2_$(echo $t | tr / _).html" "$url"
done < $out/links2.txt
exit 0
