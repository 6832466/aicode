"""Debug: save SSE stream to file to inspect."""
import json
import requests

base = "http://localhost:8000"
headers = {
    "Authorization": "Bearer han1234",
    "Content-Type": "application/json",
}
payload = {
    "model": "gemini-3.1-flash-image-square-2k",
    "messages": [{"role": "user", "content": "a cat"}],
    "stream": True,
}

resp = requests.post(
    f"{base}/v1/chat/completions",
    headers=headers,
    json=payload,
    timeout=120,
    stream=True,
)
print(f"Status: {resp.status_code}")

# Collect all data
raw_lines = []
data_events = []
for line in resp.iter_lines(decode_unicode=True):
    raw_lines.append(line)
    if line.startswith("data: "):
        data_str = line[6:].strip()
        if data_str != "[DONE]":
            try:
                data_events.append(json.loads(data_str))
            except json.JSONDecodeError:
                pass

# Write raw to file
with open(r"e:\AiCode\005flow2api\sse_debug.txt", "w", encoding="utf-8") as f:
    for i, line in enumerate(raw_lines):
        f.write(f"[{i}] {line}\n")

# Analyze data events
print(f"Total lines: {len(raw_lines)}")
print(f"Data events: {len(data_events)}")
for i, evt in enumerate(data_events):
    choices = evt.get("choices", [])
    for c in choices:
        delta = c.get("delta", {})
        content = delta.get("content", "")
        if content:
            print(f"Event [{i}] content: {repr(content[:200])}")
        if c.get("finish_reason"):
            print(f"Event [{i}] finish_reason: {c['finish_reason']}")

print("\nDone. Raw data saved to sse_debug.txt")
