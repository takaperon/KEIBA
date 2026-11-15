#!/bin/bash
# N2: 過去レースのオッズページが残っているか（少数・3秒間隔）
set -u
out=$1; mkdir -p $out/f
UA='Mozilla/5.0 (compatible; KEIBA-personal/0.1; +https://github.com/takaperon)'
J=https://www.jra.go.jp
p() { sleep 3; curl -sSL -A "$UA" -m 30 -o "$out/f/$1" -w "%{http_code} %{size_download} $2 $3\n" --data "cname=$3" "$J/JRADB/$2" >> $out/status.txt 2>>$out/err.txt; }
p o2024.html accessO.html pw151ou1005202404011120241005Z/DE
p o2026.html accessO.html pw151ou1008202605031120261114Z/F9
p otoday.html accessO.html pw151ouS308202605041120261115Z/EF
p horse.html accessU.html pw01dud002024101722/3A
for f in $out/f/*.html; do iconv -f CP932 -t UTF-8 "$f" > "${f%.html}.u8.html" 2>/dev/null || cp "$f" "${f%.html}.u8.html"; grep -oE "pw[0-9A-Za-z]+/[0-9A-F]{2}" "$f" | sort -u > "${f%.html}.cnames.txt"; done
exit 0
