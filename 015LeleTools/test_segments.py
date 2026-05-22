"""测试分段改错别字 — 独立运行，打印详细日志"""
import json, sys, time
sys.path.insert(0, '.')
import requests
from pathlib import Path
from core.text_processor import TextProcessor, get_instruction_prompt
from app.constants import INSTRUCTION_FIX_TYPOS, DEFAULT_SEGMENT_SIZE
from app.config_manager import ConfigManager

config = ConfigManager()
ep = config.get_default_endpoint()
if not ep:
    print("FAIL: 未配置 API 端点")
    sys.exit(1)

text = Path(r"C:\Users\Administrator\Desktop\三婚皆空\三婚皆空.txt").read_text(encoding="utf-8")
print(f"原文: {len(text)} 字符, {text.count(chr(10))} 行")

system_prompt = get_instruction_prompt(INSTRUCTION_FIX_TYPOS)
print(f"提示词长度: {len(system_prompt)} 字符")

segments = TextProcessor.split_into_segments(text, DEFAULT_SEGMENT_SIZE)
print(f"分段数: {len(segments)} (每段 {DEFAULT_SEGMENT_SIZE} 字)")
for i, seg in enumerate(segments):
    print(f"  段{i+1}: {len(seg)} 字符")

TAIL_CHARS = 400
MAX_RETRIES = 2
prev_corrected = ""
last_chunk = ""
failed = []
all_results = []

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {ep.api_key}",
    "Connection": "close",
}

for idx, segment in enumerate(segments):
    if prev_corrected:
        user_content = (
            f"{system_prompt}\n\n"
            f"[上文参考] 前一段修正结果的结尾（请保持一致的错别字修正规则和用词风格）：\n"
            f"---\n{prev_corrected}\n---\n\n"
            f"需要处理的文本如下：\n{segment}"
        )
    else:
        user_content = f"{system_prompt}\n\n需要处理的文本如下：\n{segment}"

    messages = [
        {"role": "system", "content": "你是一个专业的文本处理助手，请严格按照用户提供的规则处理文本。只输出处理结果，不要添加解释或开场白。"},
        {"role": "user", "content": user_content},
    ]

    payload = {
        "model": "deepseek-v4-flash",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 8192,
        "stream": True,
    }
    url = f"{ep.base_url}/v1/chat/completions"

    ok = False
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            resp = requests.post(url, json=payload, timeout=(30, 180), stream=True, headers=headers)
            if resp.status_code in {429, 502, 503, 504}:
                wait = 2 * (attempt + 1)
                print(f"  段{idx+1} attempt{attempt+1}: HTTP {resp.status_code}, {wait}s后重试...")
                resp.close()
                time.sleep(wait)
                continue
            resp.raise_for_status()

            buf = []
            chunk_count = 0
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    if "error" in data:
                        err = data["error"]
                        msg = err if isinstance(err, str) else err.get("message", str(err))
                        raise Exception(f"API error: {msg}")
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        reasoning = delta.get("reasoning_content", "")
                        if content:
                            buf.append(content)
                            chunk_count += 1
                        elif reasoning:
                            buf.append(reasoning)
                            chunk_count += 1
                except json.JSONDecodeError:
                    continue

            elapsed = time.time() - t0
            if buf:
                full = ''.join(buf)
                prev_corrected = full[-TAIL_CHARS:] if len(full) > TAIL_CHARS else full
                all_results.append(full)
                print(f"  段{idx+1}/{len(segments)} OK: {chunk_count} chunks, {len(full)} chars, {elapsed:.1f}s")
                resp.close()
                ok = True
                break
            else:
                print(f"  段{idx+1} attempt{attempt+1}: 空响应, {elapsed:.1f}s")
                resp.close()
                if attempt < MAX_RETRIES - 1:
                    time.sleep(3)
        except Exception as e:
            print(f"  段{idx+1} attempt{attempt+1}: FAIL - {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(3 * (attempt + 1))
            else:
                failed.append(idx + 1)

    if not ok and (idx + 1) not in failed:
        failed.append(idx + 1)
    if idx < len(segments) - 1:
        time.sleep(0.5)

print(f"\n===== 结果 =====")
print(f"成功: {len(all_results)}/{len(segments)} 段")
if failed:
    print(f"失败段: {failed}")
else:
    # 拼接保存
    output_text = '\n'.join(all_results)
    out_path = Path(r"C:\Users\Administrator\Desktop\三婚皆空\三婚皆空_corrected.txt")
    out_path.write_text(output_text, encoding="utf-8")
    print(f"已保存: {out_path} ({len(output_text)} 字符)")
