"""Test-only child process used to simulate a slow or failed Lens GUI."""
import base64
import json
from pathlib import Path
import sys
import time

mode = sys.argv[1]
if mode == 'fatal':
    print(json.dumps(dict(type='fatal', error='Profilo Lens già in uso.')), flush=True)
    sys.exit(1)
print('startup diagnostic (not protocol)', flush=True)
print(json.dumps(dict(type='ready')), flush=True)
init = json.loads(sys.stdin.readline())
image = base64.b64decode(init['image'])
for line in sys.stdin:
    message = json.loads(line)
    if message['type'] == 'close':
        break
    token, question = message['id'], message['question']
    print(json.dumps(dict(type='status', id=token, text='Attendo consenso…')), flush=True)
    if question == 'block':
        while not Path(mode).exists():
            time.sleep(.02)
    print(json.dumps(dict(type='result', id=token,
                         result=dict(ok=True, text=f'{question}:{len(image)}', links=[]))), flush=True)
