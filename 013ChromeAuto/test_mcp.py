"""快速测试 MCP 连接 — 独立脚本"""
import sys
sys.path.insert(0, ".")
from mcp_client import McpClient

c = McpClient()
r = c.initialize()
if "error" in r:
    print("INIT FAIL:", r["error"])
    c.close()
    sys.exit(1)

print("INIT OK")

nav = c.call_tool("chrome_navigate", {"url": "https://www.baidu.com"})
print("NAV:", "OK" if nav.get("success") else nav)

extract = c.call_tool("chrome_javascript", {
    "code": "return document.title"
})
print("TITLE:", extract.get("result", "FAIL"))

c.close()
print("DONE")
