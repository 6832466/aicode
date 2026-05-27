"""
Cloudflare KV 辅助类 —— 命名空间 + 键值 CRUD + 批量操作
============================================================
纯标准库，无第三方依赖，复制到任意项目即可使用。

用法:
    from cloudflare_kv import CloudflareKV

    kv = CloudflareKV()  # token、account_id、namespace_id 已内置
    kv.put("key", "value")
    print(kv.get("key"))
    kv.delete("key")
"""
import json
import urllib.request
import urllib.error


class CloudflareKV:
    """Cloudflare Workers KV 操作类"""

    BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self, token: str = None, account_id: str = None, namespace_id: str = None):
        self.token = token or "cfut_07vTfbiE1CYQ345tv1pFVhev5mgsnC8WIVBiPFOEcf5d4aa6"
        self.account_id = account_id or "bb6fc248b149891d2620b9193c1ab7d3"
        self.namespace_id = namespace_id or "21d1f25ddf0847d394227150f58b9ba8"

    # ==================== 内部方法 ====================

    def _req(self, method: str, path: str, body: dict | list | str = None):
        """JSON 请求"""
        url = f"{self.BASE}{path}"
        data = None
        if body is not None:
            data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if not isinstance(body, str):
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}

    def _req_raw(self, method: str, path: str, body: str = None):
        """原始文本请求（KV 值接口返回纯文本而非 JSON）"""
        url = f"{self.BASE}{path}"
        data = body.encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.startswith("{") else raw
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    def _use_ns(self, namespace_id: str = None) -> str:
        ns = namespace_id or self.namespace_id
        if not ns:
            raise ValueError("请设置 namespace_id")
        return ns

    # ==================== 命名空间操作 ====================

    def list_namespaces(self) -> list[dict]:
        """列出所有命名空间"""
        return self._req("GET", f"/accounts/{self.account_id}/storage/kv/namespaces").get("result", [])

    def create_namespace(self, title: str) -> dict:
        """创建命名空间，返回 {id, title, ...}"""
        return self._req("POST", f"/accounts/{self.account_id}/storage/kv/namespaces", {"title": title}).get("result", {})

    def delete_namespace(self, namespace_id: str = None) -> bool:
        """删除命名空间"""
        ns = self._use_ns(namespace_id)
        return self._req("DELETE", f"/accounts/{self.account_id}/storage/kv/namespaces/{ns}").get("success", False)

    # ==================== 键值操作 ====================

    def put(self, key: str, value: str, *,
            ttl: int = None,
            expiration: int = None,
            metadata: dict = None,
            namespace_id: str = None) -> bool:
        """
        写入键值 (upsert)

        参数:
            key:        键名 (最长 512 bytes)
            value:      值 (最长 25 MiB)
            ttl:        相对过期秒数 (最小 60)
            expiration: 绝对过期 Unix 时间戳秒 (与 ttl 同时设置时 ttl 优先)
            metadata:   元数据 (最长 1024 bytes)
        """
        ns = self._use_ns(namespace_id)
        path = f"/accounts/{self.account_id}/storage/kv/namespaces/{ns}/values/{key}"

        params = []
        if ttl is not None:
            params.append(f"expiration_ttl={ttl}")
        if expiration is not None:
            params.append(f"expiration={expiration}")
        if params:
            path += "?" + "&".join(params)

        url = f"{self.BASE}{path}"
        req = urllib.request.Request(url, data=value.encode("utf-8"), method="PUT")
        req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
                result = json.loads(text) if (text and text.startswith("{")) else {}
        except urllib.error.HTTPError:
            return False

        success = result.get("success", False) if isinstance(result, dict) else True

        if success and metadata is not None:
            try:
                md = json.dumps(metadata, ensure_ascii=False)
                md_req = urllib.request.Request(
                    f"{self.BASE}/accounts/{self.account_id}/storage/kv/namespaces/{ns}/metadata/{key}",
                    data=md.encode("utf-8"), method="PUT",
                )
                md_req.add_header("Authorization", f"Bearer {self.token}")
                md_req.add_header("Content-Type", "application/json")
                urllib.request.urlopen(md_req, timeout=15)
            except Exception:
                pass

        return success

    def get(self, key: str, namespace_id: str = None) -> str | None:
        """读取键值，不存在返回 None"""
        ns = self._use_ns(namespace_id)
        result = self._req_raw("GET", f"/accounts/{self.account_id}/storage/kv/namespaces/{ns}/values/{key}")
        if isinstance(result, dict):
            return None if not result.get("success", True) else result.get("result")
        return result

    def list_keys(self, prefix: str = None, limit: int = 1000,
                  cursor: str = None, namespace_id: str = None) -> dict:
        """
        列出键，返回 {"keys": [...], "list_complete": bool, "cursor": str|None}

        分页用法:
            result = kv.list_keys(prefix="user:")
            for k in result["keys"]:
                print(k["name"])
            while not result["list_complete"]:
                result = kv.list_keys(prefix="user:", cursor=result["cursor"])
        """
        ns = self._use_ns(namespace_id)
        params = []
        if limit: params.append(f"limit={limit}")
        if prefix: params.append(f"prefix={urllib.request.quote(prefix)}")
        if cursor: params.append(f"cursor={urllib.request.quote(cursor)}")
        path = f"/accounts/{self.account_id}/storage/kv/namespaces/{ns}/keys"
        if params:
            path += "?" + "&".join(params)

        resp = self._req("GET", path)
        info = resp.get("result_info", {})
        return {
            "keys": resp.get("result", []),
            "list_complete": info.get("count", 0) < limit,
            "cursor": info.get("cursor"),
        }

    def delete(self, key: str, namespace_id: str = None) -> bool:
        """删除单个键"""
        ns = self._use_ns(namespace_id)
        return self._req("DELETE", f"/accounts/{self.account_id}/storage/kv/namespaces/{ns}/values/{key}").get("success", False)

    # ==================== 批量操作 ====================

    def bulk_put(self, items: list[dict], namespace_id: str = None) -> bool:
        """
        批量写入 (最多 10,000 条, 总大小 < 100 MB)

        items = [
            {"key": "k1", "value": "v1"},
            {"key": "k2", "value": "v2", "ttl": 300},
            {"key": "k3", "value": "v3", "metadata": {"tag": "x"}},
        ]
        """
        ns = self._use_ns(namespace_id)
        body = []
        for item in items:
            entry = {"key": item["key"], "value": item["value"]}
            if "ttl" in item: entry["expiration_ttl"] = item["ttl"]
            if "metadata" in item: entry["metadata"] = item["metadata"]
            body.append(entry)
        return self._req("PUT", f"/accounts/{self.account_id}/storage/kv/namespaces/{ns}/bulk", body).get("success", False)

    def bulk_delete(self, keys: list[str], namespace_id: str = None) -> bool:
        """批量删除 (最多 10,000 个键)"""
        ns = self._use_ns(namespace_id)
        return self._req("DELETE", f"/accounts/{self.account_id}/storage/kv/namespaces/{ns}/bulk", keys).get("success", False)
