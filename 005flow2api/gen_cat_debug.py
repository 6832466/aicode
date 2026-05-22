"""Debug: check what flow2api returns for image generation."""
import json
import requests

base = "http://localhost:8000"
headers = {
    "Authorization": "Bearer han1234",
    "Content-Type": "application/json",
}
model = "gemini-3.1-flash-image-square-2k"
payload = {
    "model": model,
    "messages": [{"role": "user", "content": "a cat"}],
    "stream": True,
}

print("=" * 60)
print("DEBUG: Full SSE stream inspection")
print("=" * 60)

resp = requests.post(
    f"{base}/v1/chat/completions",
    headers=headers,
    json=payload,
    timeout=120,
    stream=True,
)
print(f"Status: {resp.status_code}")
print(f"Headers: {dict(resp.headers)}")

print("\n--- Raw SSE lines ---")
line_count = 0
for line in resp.iter_lines(decode_unicode=True):
    line_count += 1
    print(f"[{line_count}] {line[:300]}")
    if line_count > 50:
        print("... truncated after 50 lines")
        break

print(f"\nTotal lines: {line_count}")
