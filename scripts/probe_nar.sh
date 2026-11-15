#!/bin/bash
# NAR-N1c: 楽天競馬のページ構成の確認。robots.txt の Crawl-Delay 60 に従い60秒間隔・最大9ページ
set -u
out=$1; mkdir -p $out/f
UA='Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
R=https://keiba.rakuten.co.jp
g() { curl -sSL -A "$UA" -m 30 -o "$out/f/$1" -w "%{http_code} %{size_download} $2\n" "$2" >> $out/status.txt 2>>$out/err.txt; sleep 61; }
g top.html $R/
grep -oE 'href="[^"]*"' $out/f/top.html | sed 's/href="//;s/"$//;s/&amp;/\&/g' | grep -E 'race_card|odds|race_performance|RACEID' | sort -u > $out/links1.txt
n=0
for pat in 'race_card/list' 'race_card/detail' 'odds/tanfuku' 'race_performance' 'odds'; do
  u=$(grep -m1 "$pat" $out/links1.txt) || continue
  [ -n "$u" ] || continue
  case "$u" in http*) url=$u;; /*) url=$R$u;; *) url=$R/$u;; esac
  n=$((n+1)); g "1_$n.html" "$url"
done
cat $out/f/1_*.html 2>/dev/null | grep -oE 'href="[^"]*"' | sed 's/href="//;s/"$//;s/&amp;/\&/g' | grep -E 'race_card|odds|race_performance|RACEID|horse' | sort -u > $out/links2.txt
for pat in 'race_card/list/RACEID' 'odds/tanfuku/RACEID' 'race_performance/list/RACEID' 'horse_detail'; do
  u=$(grep -m1 "$pat" $out/links2.txt) || continue
  case "$u" in http*) url=$u;; /*) url=$R$u;; *) url=$R/$u;; esac
  n=$((n+1)); [ $n -gt 9 ] && break; g "2_$n.html" "$url"
done
exit 0
