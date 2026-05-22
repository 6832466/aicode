"""Clean end-to-end test of generate_image()."""
import sys, os
sys.path.insert(0, r"E:\AiCode\005flow2api")
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from gemini_cdp import GeminiCDPClient

print("=" * 50)
print("Gemini CDP End-to-End Test")
print("=" * 50)

client = GeminiCDPClient()
print(f"CDP URL: {client._cdp_url}")

# Step 1: Check connection
ok, msg = client.check_connection()
print(f"Connection: {'OK' if ok else 'FAIL'} — {msg}")
if not ok:
    print("Cannot proceed without connection.")
    sys.exit(1)

# Step 2: Generate image
print("\n--- Generating cat image with 3.5 Flash ---")
result = client.generate_image(
    prompt="画一只非常可爱的英短蓝猫，高清写实风格",
    model="3.5 Flash",
)

print(f"\n--- Results ---")
print(f"Success: {result.success}")
print(f"Error: {result.error_message or 'None'}")
print(f"Prompt: {result.prompt}")

if result.image_data:
    size = len(result.image_data)
    print(f"Image: {size:,} bytes ({size/1024/1024:.2f} MB)")
    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    path = os.path.join(desktop, "gemini_cat_test.png")
    with open(path, "wb") as f:
        f.write(result.image_data)
    print(f"Saved: {path}")
else:
    print("NO IMAGE DATA RETURNED!")

client.disconnect()
print("\nDone.")
