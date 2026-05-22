"""CLI test — generate_image() handles full Chrome lifecycle internally."""
import sys, time, base64
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from gemini_cdp import GeminiCDPClient

REF = r"C:\Users\Administrator\Desktop\654af4e26fc1d5718674634402928e5817fe88cf2d3627-wOn0b2_fw658webp.webp"
PROMPT = "根据下面的描述生成一张比例1:1的人物图片，亚洲面孔，3D国漫风格，不要加分割线，纯白色背景，左边腰部以上正面特写，右边正面全身照，站立姿势，不要文字，不要手中拿的物品，双手自然放下，8头身比，极致的身材比例（8k分辨率，极致细节，大师杰作，高品质。）"
OUTPUT = Path.home() / "Desktop" / "gemini_output_hd.png"

print("=" * 60)
print("Gemini CDP — Full Pipeline (auto browser restart)")
print("=" * 60)

# Load reference image
ref_bytes = Path(REF).read_bytes() if Path(REF).exists() else None
print(f"[1] Reference: {len(ref_bytes)} bytes" if ref_bytes else "[1] No ref image")

# Generate — client handles browser restart internally
print("[2] Generating (includes browser restart)...")
client = GeminiCDPClient(chrome_host="127.0.0.1", chrome_port=9222, timeout=300)
start = time.time()
result = client.generate_image(prompt=PROMPT, model="", reference_image=ref_bytes, image_size="")
elapsed = time.time() - start
print(f"    {elapsed:.1f}s — success={result.success}")

if not result.success:
    print(f"    FAIL: {result.error_message}")
    client.disconnect()
    sys.exit(1)

# Save
OUTPUT.write_bytes(result.image_data)
print(f"[3] Saved: {OUTPUT} ({len(result.image_data)} bytes)")

client.disconnect()
print("=" * 60)
print("DONE")
