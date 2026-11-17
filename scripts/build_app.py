"""app-data の暗号化データを秘密鍵で開けて、アプリの HTML を作る。使い方: build_app.py app.sealed 秘密鍵.pem 出力.html"""
import json, os, subprocess, sys, tempfile
sealed, key, dst = sys.argv[1:4]
t = tempfile.mkdtemp()
subprocess.run(['tar', '-xf', sealed, '-C', t], check=True)
k = [f for f in os.listdir(t) if f.endswith('.key')][0]; dd = [f for f in os.listdir(t) if f.endswith('.data')][0]
subprocess.run(['openssl', 'pkeyutl', '-decrypt', '-inkey', key, '-in', f'{t}/{k}', '-out', f'{t}/k'], check=True)
subprocess.run(['openssl', 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-in', f'{t}/{dd}', '-pass', f'file:{t}/k', '-out', f'{t}/app.json'], check=True)
data = json.load(open(f'{t}/app.json'))
html = open(os.path.join(os.path.dirname(__file__), 'app_template.html')).read().replace('/*DATA*/null', json.dumps(data, ensure_ascii=False))
open(dst, 'w').write(html)
print({m: len(v) for m, v in data['modes'].items()}, data['notes'].keys())
