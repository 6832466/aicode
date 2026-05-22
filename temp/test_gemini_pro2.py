"""Test gemini-2.5-pro text — fix double-encoding."""
import sys, json, os, re
sys.path.insert(0, r'E:\AiCode\005flow2api')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from config import cfg
import requests

cookie = cfg.api_session_cookie.value
uid = cfg.api_user_id.value or '13679'

if not cookie:
    print('No session cookie. Need login first.')
    sys.exit(1)

headers = {
    'Content-Type': 'application/json',
    'Cookie': f'session={cookie}',
    'new-api-user': uid,
}

payload = {
    'model': 'gemini-2.5-pro',
    'messages': [{'role': 'user', 'content': '用中文简要解释什么是量子纠缠，100字以内。'}],
    'stream': True,
}

resp = requests.post(
    'https://bj.nfai.lol/pg/chat/completions',
    headers=headers,
    json=payload,
    timeout=120,
    stream=True,
)

print(f'HTTP {resp.status_code}')

old_parts = []
fixed_parts = []

for line in resp.iter_lines(decode_unicode=True):
    if not line or not line.startswith('data: '):
        continue
    data_str = line[6:].strip()
    if data_str == '[DONE]':
        break
    try:
        data = json.loads(data_str)
        if 'error' in data:
            print(f'SSE Error: {data["error"]}')
            break
        for c in data.get('choices', []):
            delta = c.get('delta', {})
            content = delta.get('content', '')
            if content:
                old_parts.append(content)
                try:
                    fixed = content.encode('latin-1').decode('utf-8')
                except (UnicodeDecodeError, UnicodeEncodeError):
                    fixed = content
                fixed_parts.append(fixed)
    except json.JSONDecodeError:
        pass

old = ''.join(old_parts)
fixed = ''.join(fixed_parts)

print(f'\nRaw content ({len(old)} chars):')
print(old)
print(f'\nFixed content ({len(fixed)} chars):')
print(fixed)

# Also test: what happens with non-streaming?
print(f'\n{"="*50}')
print('Test 2: non-streaming (stream: false)')
payload2 = {
    'model': 'gemini-2.5-pro',
    'messages': [{'role': 'user', 'content': '你好，请用一句话介绍你自己。'}],
    'stream': False,
}

resp2 = requests.post(
    'https://bj.nfai.lol/pg/chat/completions',
    headers=headers,
    json=payload2,
    timeout=120,
)

print(f'HTTP {resp2.status_code}')
print(f'Content-Type: {resp2.headers.get("Content-Type", "")}')
body = resp2.text
print(f'Body ({len(body)} chars):')
print(body[:1000])
