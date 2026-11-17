#!/bin/bash
# 公開リポジトリに置くデータを暗号化する（公開鍵で封をする。秘密鍵はリポジトリに無い）
# 使い方: seal.sh 入力ファイル 出力ファイル(.sealed)
set -e
k=$(mktemp); openssl rand -hex 32 > $k
openssl pkeyutl -encrypt -pubin -inkey "$(dirname $0)/../keiba/app_pub.pem" -in $k -out "$2.key"
openssl enc -aes-256-cbc -pbkdf2 -salt -in "$1" -out "$2.data" -pass file:$k
tar -C "$(dirname $2)" -cf "$2" "$(basename $2).key" "$(basename $2).data"; rm -f "$2.key" "$2.data" $k
