#!/bin/bash
# NAR-N1d: 楽天競馬の各レースページ（出馬表・単複オッズ・結果）と過去日付の確認。60秒間隔・最大8ページ
set -u
out=$1; mkdir -p $out/f
UA='Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
R=https://keiba.rakuten.co.jp
g() { curl -sSL -A "$UA" -m 30 -o "$out/f/$1" -w "%{http_code} %{size_download} $2\n" "$2" >> $out/status.txt 2>>$out/err.txt; sleep 61; }
lk() { grep -oE 'href="[^"]*"' "$1" | sed 's/href="//;s/"$//;s/&amp;/\&/g;s/?l-id=.*//' | sort -u; }
g card.html $R/race_card/list/RACEID/202611153230130510
g odds.html $R/odds/tanfuku/RACEID/202611153230130510
g perf_list.html $R/race_performance/list/RACEID/202611143230130400
u=$(lk $out/f/perf_list.html | grep -E 'race_performance/list/RACEID/[0-9]{16}(0[1-9]|1[0-2])$' | head -1)
[ -n "$u" ] && g perf_race.html "$u"
echo "$u" > $out/perf_race_url.txt
id=${u##*/}
[ -n "$id" ] && g odds_past.html $R/odds/tanfuku/RACEID/$id
g old_list.html $R/race_performance/list/RACEID/202411140000000000
u2=$(lk $out/f/old_list.html | grep -E 'race_performance/list/RACEID/20241114[0-9]{8}00$' | head -1)
echo "$u2" > $out/old_url.txt
[ -n "$u2" ] && g old_venue.html "$u2"
for f in $out/f/*.html; do lk $f > ${f%.html}.links.txt; done
exit 0
