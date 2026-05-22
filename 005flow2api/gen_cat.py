"""Generate cat image and save to desktop."""
import sys
sys.path.insert(0, r"e:\AiCode\005flow2api")
from api_client import Flow2ApiClient
from utils import build_full_model_name
from pathlib import Path

client = Flow2ApiClient("http://localhost:8000", "han1234", timeout=180)
model = build_full_model_name("gemini-3.1-flash-image", "square", "2k")
print(f"Generating... prompt: 一只猫, model: {model}")
result = client.generate_image("一只猫", model)

if result.success:
    desktop = Path.home() / "Desktop"
    filepath = desktop / "cat.png"
    filepath.write_bytes(result.image_data)
    print(f"OK! Saved to: {filepath} ({len(result.image_data)} bytes)")
else:
    print(f"FAILED: {result.error_message}")
