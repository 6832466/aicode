"""Single clean run — generate cat image to desktop."""
import sys, os
sys.path.insert(0, r"E:\AiCode\005flow2api")
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from gemini_cdp import GeminiCDPClient

client = GeminiCDPClient()
print("连接中...")
ok, msg = client.check_connection()
print(f"连接: {msg}")

if ok:
    print("生成图片中...")
    result = client.generate_image(
        prompt="画一只非常可爱的英短蓝猫，高清写实风格，毛发清晰可见",
        model="3.5 Flash",
    )

    print(f"结果: {'成功' if result.success else '失败'}")
    if result.error_message:
        print(f"错误: {result.error_message}")
    if result.image_data:
        desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
        path = os.path.join(desktop, "gemini_cat.png")
        with open(path, "wb") as f:
            f.write(result.image_data)
        print(f"图片: {len(result.image_data):,} bytes -> {path}")

    client.disconnect()
    print("完成。")
