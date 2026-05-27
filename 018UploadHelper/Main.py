"""当前项目入口 —— 内置凭证，直接调用"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloudflare_kv import CloudflareKV

# 全局实例
kv = CloudflareKV()

if __name__ == "__main__":
    print("命名空间:", [ns["title"] for ns in kv.list_namespaces()])
    print("键列表:", [k["name"] for k in kv.list_keys()["keys"]])
