"""Test deepcopy of VideoInfo"""
import sys
import os
import copy
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CURRENT_DIR, '..', 'eaglepy310', 'Lib', 'site-packages'))

from videodl.modules.utils.data import VideoInfo

desktop = os.path.join(os.path.expanduser("~"), "Desktop")

# Simulate what douyin parser produces
info = VideoInfo(
    source="DouyinVideoClient",
    title="测试标题",
    download_url="https://example.com/video.mp4",
    ext="mp4",
    save_path=os.path.join("videodl_outputs", "DouyinVideoClient", "测试标题.mp4"),
    identifier="test123"
)

print(f"Original save_path: {info.save_path}")

# My override
info.save_path = os.path.join(desktop, "测试标题.mp4")
print(f"After override: {info.save_path}")

# Deep copy (as done in _download)
info_copy = copy.deepcopy(info)
print(f"Deep copy save_path: {info_copy.save_path}")
print(f"Deep copy type: {type(info_copy)}")
