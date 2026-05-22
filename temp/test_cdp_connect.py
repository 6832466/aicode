"""Test CDP WebSocket connection and then run full generate_image flow."""
import sys
import os

# Add project to path
sys.path.insert(0, r"E:\AiCode\005flow2api")

# Fix Windows encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from gemini_cdp import GeminiCDPClient

print("=" * 60)
print("Test 1: check_connection()")
print("=" * 60)

client = GeminiCDPClient()
print(f"Resolved CDP URL: {client._cdp_url}")

ok, msg = client.check_connection()
print(f"Result: {'PASS' if ok else 'FAIL'} — {msg}")

if ok:
    print()
    print("=" * 60)
    print("Test 2: generate_image('一只可爱的猫', model='3.5 Flash')")
    print("=" * 60)

    result = client.generate_image(
        prompt="画一只非常可爱的小猫，高清写实风格，毛发清晰可见",
        model="3.5 Flash",
    )

    print()
    print("=" * 60)
    print("Test 2 Results:")
    print("=" * 60)
    print(f"Success: {result.success}")
    print(f"Error: {result.error_message or 'None'}")
    if result.image_data:
        print(f"Image size: {len(result.image_data):,} bytes ({len(result.image_data)/1024/1024:.2f} MB)")
        # Save to desktop
        desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        out_path = os.path.join(desktop, "test_cat_cdp.png")
        with open(out_path, "wb") as f:
            f.write(result.image_data)
        print(f"Saved to: {out_path}")
    else:
        print("No image data returned!")

    client.disconnect()
else:
    print()
    print("[SKIP] Cannot run generate_image test — connection failed")
