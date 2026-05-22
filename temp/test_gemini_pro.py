"""Test gemini-2.5-pro text completion."""
import sys, json, os
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

print(f'POST https://bj.nfai.lol/pg/chat/completions')
print(f'Model: gemini-2.5-pro')

resp = requests.post(
    'https://bj.nfai.lol/pg/chat/completions',
    headers=headers,
    json=payload,
    timeout=120,
    stream=True,
)

print(f'HTTP {resp.status_code}')

if resp.status_code != 200:
    print(f'Error body: {resp.text[:500]}')
    sys.exit(1)

content_parts = []
raw_lines = []
for line in resp.iter_lines(decode_unicode=True):
    if not line:
        continue
    raw_lines.append(line)
    if not line.startswith('data: '):
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
            if delta.get('content'):
                content_parts.append(delta['content'])
    except json.JSONDecodeError as e:
        print(f'JSON decode error: {e} for: {data_str[:100]}')

full = ''.join(content_parts)
print(f'Content parts count: {len(content_parts)}')
print(f'Full response length: {len(full)} chars')
print(f'Full response repr: {repr(full)}')
print(f'Response: {full}')

# Also dump all raw lines for debugging
print(f'\n--- Raw SSE lines ({len(raw_lines)}) ---')
for i, l in enumerate(raw_lines):
    print(f'  [{i}] {repr(l)[:200]}')
