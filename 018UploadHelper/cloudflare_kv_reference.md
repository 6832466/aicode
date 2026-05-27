# Cloudflare KV 参考文档

> 整理日期: 2025-05-25
> 数据来源: Cloudflare 官方文档, deepwiki, PyPI

---

## 1. 概述

Cloudflare Workers KV 是一个全球分布式、最终一致性的键值存储，专为读取密集型工作负载设计。适合存储配置、用户偏好、功能标志、缓存数据等场景。

### 核心特性

| 特性 | 说明 |
|------|------|
| 一致性模型 | 最终一致性（全局可见延迟通常 < 60 秒） |
| 优化方向 | 读多写少（推荐 100:1 以上读写比） |
| 全球分布 | 写入自动同步到 Cloudflare 全球网络 |
| 免费额度 | 10万次读取/天，1千次写入/天，1 GB 存储 |
| TTL 支持 | 支持相对过期时间 (expiration_ttl) 和绝对过期时间 (expiration) |
| 元数据 | 每个键可附带最多 1024 字节 JSON 元数据 |

### 不适合的场景

- 需要强一致性的操作（用 Durable Objects 替代）
- 高频写入（每个键每秒最多 1 次写入）
- 关系型查询（用 D1 数据库替代）

---

## 2. 两种访问方式

| 方式 | 使用场景 | 性能 |
|------|----------|------|
| **Workers Binding API** | Cloudflare Workers 内部 | 快，低延迟 |
| **REST API** | 外部应用 (Python/Node.js 等) | HTTP 开销，速率限制较低 |

---

## 3. Python SDK —— 官方 `cloudflare` 包

### 3.1 安装

```bash
pip install cloudflare
```

### 3.2 初始化客户端

```python
import os
from cloudflare import Cloudflare

client = Cloudflare(
    api_email=os.environ.get("xq78170809@gmail.com"),
    api_key=os.environ.get("cfut_07vTfbiE1CYQ345tv1pFVhev5mgsnC8WIVBiPFOEcf5d4aa6"),
)
# 或使用 AsyncCloudflare 进行异步操作
```

认证方式参考: https://developers.cloudflare.com/fundamentals/api/get-started/create-token/

### 3.3 命名空间管理（Namespace CRUD）

> ⚠️ 一个账户最多 1,000 个命名空间

```python
ACCOUNT_ID = "your_account_id"

# 创建命名空间
namespace = client.kv.namespaces.create(
    account_id=ACCOUNT_ID,
    title="My Namespace"
)
namespace_id = namespace.id  # 保存下来，后续操作需要

# 列出所有命名空间
namespaces = client.kv.namespaces.list(account_id=ACCOUNT_ID)
for ns in namespaces:
    print(ns.id, ns.title)

# 获取单个命名空间
ns = client.kv.namespaces.get(
    namespace_id="namespace_id",
    account_id=ACCOUNT_ID
)

# 更新命名空间标题
client.kv.namespaces.update(
    namespace_id="namespace_id",
    account_id=ACCOUNT_ID,
    title="New Title"
)

# 删除命名空间
client.kv.namespaces.delete(
    namespace_id="namespace_id",
    account_id=ACCOUNT_ID
)
```

### 3.4 键值 CRUD 操作

#### 写入 / 更新 (upsert)

```python
# 基础写入
client.kv.namespaces.values.update(
    key_name="my-key",
    account_id=ACCOUNT_ID,
    namespace_id="namespace_id",
    value="my string value"
)

# 写入 JSON 数据
import json
client.kv.namespaces.values.update(
    key_name="user:123",
    account_id=ACCOUNT_ID,
    namespace_id="namespace_id",
    value=json.dumps({"name": "张三", "role": "admin"}),
    metadata=json.dumps({"version": 1, "updated_by": "api"})
)

# 带 TTL 过期（秒，最小 60）
client.kv.namespaces.values.update(
    key_name="session:abc",
    account_id=ACCOUNT_ID,
    namespace_id="namespace_id",
    value="token_data",
    expiration_ttl=3600  # 1小时后过期
)

# 带绝对过期时间（Unix 时间戳，秒）
import time
client.kv.namespaces.values.update(
    key_name="temp-key",
    account_id=ACCOUNT_ID,
    namespace_id="namespace_id",
    value="temporary",
    expiration=int(time.time()) + 86400  # 24小时后过期
)
```

#### 读取

```python
# 基础读取
response = client.kv.namespaces.values.get(
    key_name="my-key",
    account_id=ACCOUNT_ID,
    namespace_id="namespace_id"
)
value = response.content  # bytes 类型
value_str = value.decode("utf-8")  # 转字符串

# JSON 读取
import json
response = client.kv.namespaces.values.get(
    key_name="user:123",
    account_id=ACCOUNT_ID,
    namespace_id="namespace_id"
)
data = json.loads(response.content)

# 流式读取（大文件）
with client.kv.namespaces.values.with_streaming_response.get(
    key_name="large-file",
    account_id=ACCOUNT_ID,
    namespace_id="namespace_id"
) as response:
    for chunk in response.iter_bytes():
        process(chunk)

# 获取原始响应头（含 expiration 等信息）
raw = client.kv.namespaces.values.with_raw_response.get(
    key_name="my-key",
    account_id=ACCOUNT_ID,
    namespace_id="namespace_id"
)
print(raw.headers.get("expiration"))
```

#### 列出键

```python
# 列出所有键（分页）
# 注意: 需要在 cloudflare-python SDK 中通过 keys 子资源调用
# 当前 SDK 版本可能使用 values.list 或 keys.list
keys_response = client.kv.namespaces.keys.list(
    namespace_id="namespace_id",
    account_id=ACCOUNT_ID,
    prefix="user:",   # 按前缀过滤
    limit=1000,       # 每次最多 1000
    cursor=None       # 分页游标
)

for key_info in keys_response.result:
    print(key_info.name, key_info.expiration, key_info.metadata)
```

#### 删除

```python
# 删除单个键
client.kv.namespaces.values.delete(
    key_name="my-key",
    account_id=ACCOUNT_ID,
    namespace_id="namespace_id"
)
```

### 3.5 批量操作

```python
# 批量写入（最多 10,000 个键，总大小 < 100 MB）
client.kv.namespaces.bulk_update(
    namespace_id="namespace_id",
    account_id=ACCOUNT_ID,
    body=[
        {"key": "key1", "value": "value1"},
        {"key": "key2", "value": "value2", "expiration_ttl": 300},
        {"key": "key3", "value": "value3", "metadata": {"tag": "important"}},
    ]
)

# 批量删除（最多 10,000 个键）
client.kv.namespaces.bulk_delete(
    namespace_id="namespace_id",
    account_id=ACCOUNT_ID,
    body=["key1", "key2", "key3"]
)
```

### 3.6 异步操作

```python
from cloudflare import AsyncCloudflare
import asyncio

async def main():
    client = AsyncCloudflare(
        api_email=os.environ.get("CLOUDFLARE_EMAIL"),
        api_key=os.environ.get("CLOUDFLARE_API_KEY"),
    )

    # 写入
    await client.kv.namespaces.values.update(
        key_name="async-key",
        account_id=ACCOUNT_ID,
        namespace_id="namespace_id",
        value="async value"
    )

    # 读取
    response = await client.kv.namespaces.values.get(
        key_name="async-key",
        account_id=ACCOUNT_ID,
        namespace_id="namespace_id"
    )
    print(response.content)

    # 删除
    await client.kv.namespaces.values.delete(
        key_name="async-key",
        account_id=ACCOUNT_ID,
        namespace_id="namespace_id"
    )

asyncio.run(main())
```

---

## 4. REST API 直接调用

如果不用 SDK，可以直接调用 REST API。

### 基础 URL

```
https://api.cloudflare.com/client/v4
```

### 认证

每个请求需要带以下 Header:

```
Authorization: Bearer <API_TOKEN>
Content-Type: application/json
```

或者用 API Key 方式:

```
X-Auth-Email: <email>
X-Auth-Key: <global_api_key>
```

### REST API 端点列表

| 操作 | 方法 | 端点 |
|------|------|------|
| **写入** | `PUT` | `/accounts/:account_id/storage/kv/namespaces/:namespace_id/values/:key` |
| **读取** | `GET` | `/accounts/:account_id/storage/kv/namespaces/:namespace_id/values/:key` |
| **列出键** | `GET` | `/accounts/:account_id/storage/kv/namespaces/:namespace_id/keys` |
| **删除** | `DELETE` | `/accounts/:account_id/storage/kv/namespaces/:namespace_id/values/:key` |
| **批量写入** | `PUT` | `/accounts/:account_id/storage/kv/namespaces/:namespace_id/bulk` |
| **批量删除** | `DELETE` | `/accounts/:account_id/storage/kv/namespaces/:namespace_id/bulk` |

### Python 原生请求示例

```python
import requests

BASE_URL = "https://api.cloudflare.com/client/v4"
HEADERS = {
    "Authorization": "Bearer YOUR_API_TOKEN",
    "Content-Type": "application/json",
}

ACCOUNT_ID = "your_account_id"
NAMESPACE_ID = "your_namespace_id"

def kv_put(key: str, value: str, ttl: int = None):
    """写入键值"""
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/values/{key}"
    headers = {**HEADERS}
    if ttl:
        headers["expiration_ttl"] = str(ttl)

    # 注意: value 需要以二进制形式通过 URL 参数传递
    # 实际上 REST API 对 value 的编码方式比较特殊
    # 建议使用 SDK 或通过 multipart 上传
    response = requests.put(url, headers=headers, data=value)
    return response.json()

def kv_get(key: str) -> str:
    """读取键值"""
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/values/{key}"
    response = requests.get(url, headers=HEADERS)
    return response.text  # 返回原始字符串

def kv_list(prefix: str = None, limit: int = 1000, cursor: str = None) -> dict:
    """列出键"""
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/keys"
    params = {"limit": limit}
    if prefix:
        params["prefix"] = prefix
    if cursor:
        params["cursor"] = cursor
    response = requests.get(url, headers=HEADERS, params=params)
    return response.json()

def kv_delete(key: str) -> dict:
    """删除键"""
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/values/{key}"
    response = requests.delete(url, headers=HEADERS)
    return response.json()

def kv_bulk_write(items: list[dict]) -> dict:
    """批量写入，items 为 [{"key": "k", "value": "v"}, ...]"""
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/bulk"
    response = requests.put(url, headers=HEADERS, json=items)
    return response.json()

def kv_bulk_delete(keys: list[str]) -> dict:
    """批量删除"""
    url = f"{BASE_URL}/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/bulk"
    response = requests.delete(url, headers=HEADERS, json=keys)
    return response.json()
```

---

## 5. 限制与配额

| 项目 | 免费计划 | 付费计划 |
|------|----------|----------|
| 读取次数/天 | 100,000 | 无限制 |
| 写入次数/天（不同键）| 1,000 | 无限制 |
| 每个键每秒写入次数 | 1 | 1 |
| 每个账户命名空间数 | 1,000 | 1,000 |
| 存储空间/账户 | 1 GB | 无限制 |
| 键名最大长度 | 512 bytes | 512 bytes |
| 值最大大小 | 25 MiB | 25 MiB |
| 元数据最大大小 | 1,024 bytes | 1,024 bytes |
| 最小 cacheTtl | 60 秒 | 60 秒 |
| 每次 Worker 调用操作次数 | 1,000 | 1,000 |
| 批量写入最大键数 | 10,000 | 10,000 |
| 批量写入总请求大小 | < 100 MB | < 100 MB |
| 最小 TTL | 60 秒 | 60 秒 |

---

## 6. 关键注意事项

### 6.1 一致性
- KV 是**最终一致性**的存储，写入后全局可见通常需要 < 60 秒
- 同一个 POP 节点内可以读到自己刚写的数据 (read-your-own-write)
- 不同 POP 节点之间可能有短暂的不一致

### 6.2 写入限制
- **每个键每秒只能写入 1 次**——这是最重要的限制
- 如果需要高频写入同一个键，使用 Durable Objects

### 6.3 键命名建议
- 使用前缀组织键，如 `user:`, `config:`, `cache:`
- 键名大小写敏感
- URL-safe 字符最佳

### 6.4 过期时间
- 最小 TTL 为 60 秒
- `expiration_ttl`（相对时间）和 `expiration`（绝对时间）同时设置时，`expiration_ttl` 优先
- 都不设置则永不过期
- 过期后键不会立即删除，可能在过期后一段时间仍可读取

### 6.5 列出键的限制
- 结果可能不包含最近写入的键（最终一致性）
- 每次最多返回 1,000 条，分页用 `cursor`
- 结果可能包含已删除的键（短时间内）

---

## 7. 第三方 Python 封装（备选）

### workers-kv.py

```bash
pip install workers-kv.py
```

```python
import workers_kv

ns = workers_kv.Namespace(
    account_id="ACCOUNT_ID",
    namespace_id="NAMESPACE_ID",
    api_key="TOKEN"
)

ns.read("key")                          # 读取
ns.write({"k1": "v1", "k2": "v2"})     # 写入（2+ 个键自动走批量）
ns.delete_one("key")                    # 删除单个
ns.delete_many(["k1", "k2"])           # 批量删除
ns.list_keys()                          # 列出所有键
```

### cfkv

```bash
pip install cfkv
```

```python
from cfkv import KVStore

store = KVStore(
    namespace_id="YOUR_NAMESPACE_ID",
    account_id="ACCOUNT_ID",
    api_key="API_KEY"
)

value = store.get("sample_key")         # 读取，不存在返回 None
store.set("sample_key", {"test": True}) # 写入
```

---

## 8. 环境变量配置建议

在项目中使用 `.env` 或环境变量管理凭证:

```env
CLOUDFLARE_EMAIL=your-email@example.com
CLOUDFLARE_API_KEY=your-global-api-key
CLOUDFLARE_API_TOKEN=your-api-token        # 推荐使用 API Token
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_KV_NAMESPACE_ID=your-namespace-id
```

**推荐使用 API Token 而非 Global API Key**，Token 可以设置更细粒度的权限。

---

## 9. 快速检查清单

准备好以下信息即可开始操作:

- [ ] Cloudflare 账户 ID（Dashboard → Workers & Pages → 右侧栏）
- [ ] API Token（具有 Workers KV Storage 权限）
- [ ] 命名空间 ID（已创建或在代码中创建）
- [ ] 已安装 `cloudflare` Python 包

---

## 10. 参考链接

- [Cloudflare Workers KV 官方文档](https://developers.cloudflare.com/kv/)
- [Cloudflare Workers KV REST API](https://developers.cloudflare.com/api/resources/kv/)
- [Cloudflare Python SDK - PyPI](https://pypi.org/project/cloudflare/)
- [Cloudflare API Token 创建](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)
