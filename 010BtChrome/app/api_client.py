from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

import requests

from app.config import (
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    RETRY_DELAY,
    RETRY_STATUSES,
)

logger = logging.getLogger(__name__)


class BitBrowserAPIError(Exception):
    pass


class BitBrowserAPI:
    """比特浏览器本地 HTTP API 客户端"""

    def __init__(self, base_url: str = ""):
        self._base_url = base_url.rstrip("/")
        self._timeout = REQUEST_TIMEOUT
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/json"
        self._last_call = 0.0
        self._min_interval = 0.6  # 比特浏览器有频率限制，保持 600ms 间隔

    @property
    def base_url(self) -> str:
        return self._base_url

    def configure(self, url: str, timeout: int | None = None):
        self._base_url = url.rstrip("/")
        if timeout is not None:
            self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _post(self, endpoint: str, data: dict | None = None) -> dict:
        if not self._base_url:
            raise BitBrowserAPIError("请先配置 API 地址")
        url = f"{self._base_url}{endpoint}"
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                # 频率控制：确保请求间隔不小于 _min_interval
                with self._lock:
                    elapsed = time.time() - self._last_call
                    if elapsed < self._min_interval:
                        time.sleep(self._min_interval - elapsed)
                    resp = self._session.post(
                        url, json=data or {}, timeout=self._timeout
                    )
                    self._last_call = time.time()
                if resp.status_code in RETRY_STATUSES:
                    wait = RETRY_DELAY * (2**attempt)
                    logger.warning(
                        "retry %d/%d after %ds (status %d)",
                        attempt + 1,
                        MAX_RETRIES,
                        wait,
                        resp.status_code,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                try:
                    body: dict = resp.json()
                except ValueError:
                    raise BitBrowserAPIError("API 返回了非 JSON 响应")
                # 即使 200 也要检查业务错误
                if not body.get("success", False):
                    raise BitBrowserAPIError(
                        body.get("msg", "未知 API 错误")
                    )
                return body.get("data", {})
            except requests.RequestException as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (2**attempt)
                    logger.warning(
                        "retry %d/%d after %ds (error: %s)",
                        attempt + 1,
                        MAX_RETRIES,
                        wait,
                        e,
                    )
                    time.sleep(wait)
                else:
                    raise BitBrowserAPIError(str(e)) from e
            except BitBrowserAPIError:
                raise  # 业务错误直接透传，不重试也不包装
            except Exception as e:
                raise BitBrowserAPIError(str(e)) from e
        raise BitBrowserAPIError(str(last_error))

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> bool:
        """检测本地服务是否连通"""
        try:
            self._post("/health")
            return True
        except BitBrowserAPIError:
            return False

    # ------------------------------------------------------------------
    # Group
    # ------------------------------------------------------------------

    def group_list(self, page: int = 0, page_size: int = 100) -> dict:
        return self._post("/group/list", {"page": page, "pageSize": page_size})

    def group_add(self, name: str, sort_num: int = 0) -> dict:
        return self._post("/group/add", {"groupName": name, "sortNum": sort_num})

    def group_edit(self, id: str, name: str, sort_num: int = 0) -> dict:
        return self._post(
            "/group/edit", {"id": id, "groupName": name, "sortNum": sort_num}
        )

    def group_delete(self, id: str) -> dict:
        return self._post("/group/delete", {"id": id})

    def group_detail(self, id: str) -> dict:
        return self._post("/group/detail", {"id": id})

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------

    def browser_update(self, params: dict) -> dict:
        return self._post("/browser/update", params)

    def browser_open(
        self,
        id: str,
        args: list[str] | None = None,
        queue: bool | None = None,
        ignore_default_urls: bool | None = None,
        new_page_url: str | None = None,
    ) -> dict:
        data: dict[str, Any] = {"id": id}
        if args:
            data["args"] = args
        if queue is not None:
            data["queue"] = queue
        if ignore_default_urls is not None:
            data["ignoreDefaultUrls"] = ignore_default_urls
        if new_page_url:
            data["newPageUrl"] = new_page_url
        return self._post("/browser/open", data)

    def browser_close(self, id: str) -> dict:
        return self._post("/browser/close", {"id": id})

    def browser_delete(self, id: str) -> dict:
        return self._post("/browser/delete", {"id": id})

    def browser_detail(self, id: str) -> dict:
        return self._post("/browser/detail", {"id": id})

    def browser_list(
        self,
        page: int = 0,
        page_size: int = 20,
        group_id: str | None = None,
        name: str | None = None,
        remark: str | None = None,
        seq: int | None = None,
        min_seq: int | None = None,
        max_seq: int | None = None,
        sort: str | None = None,
        owned_by_me: bool | None = None,
        opened: bool | None = None,
    ) -> dict:
        data: dict[str, Any] = {"page": page, "pageSize": page_size}
        if group_id:
            data["groupId"] = group_id
        if name:
            data["name"] = name
        if remark:
            data["remark"] = remark
        if seq is not None:
            data["seq"] = seq
        if min_seq is not None:
            data["minSeq"] = min_seq
        if max_seq is not None:
            data["maxSeq"] = max_seq
        if sort:
            data["sort"] = sort
        if owned_by_me is not None:
            data["ownedByMe"] = owned_by_me
        if opened is not None:
            data["opened"] = opened
        return self._post("/browser/list", data)

    def browser_batch_group(self, group_id: str, browser_ids: list[str]) -> dict:
        return self._post(
            "/browser/group/update", {"groupId": group_id, "browserIds": browser_ids}
        )

    def browser_batch_proxy(self, ids: list[str], proxy: dict) -> dict:
        data: dict[str, Any] = {"ids": ids, **proxy}
        return self._post("/browser/proxy/update", data)

    def browser_batch_remark(self, browser_ids: list[str], remark: str) -> dict:
        return self._post(
            "/browser/remark/update", {"browserIds": browser_ids, "remark": remark}
        )

    def browser_close_by_seqs(self, seqs: list[int]) -> dict:
        return self._post("/browser/close/byseqs", {"seqs": seqs})

    def browser_update_partial(self, ids: list[str], fields: dict) -> dict:
        data: dict[str, Any] = {"ids": ids, **fields}
        return self._post("/browser/update/partial", data)

    def browser_pids(self, ids: list[str]) -> dict:
        return self._post("/browser/pids", {"ids": ids})

    def browser_pids_all(self) -> dict:
        """获取所有活跃窗口 PID"""
        return self._post("/browser/pids/all")

    def browser_pids_alive(self, ids: list[str]) -> dict:
        return self._post("/browser/pids/alive", {"ids": ids})

    def browser_delete_ids(self, ids: list[str]) -> dict:
        return self._post("/browser/delete/ids", {"ids": ids})

    def browser_close_all(self) -> dict:
        """关闭所有窗口"""
        return self._post("/browser/close/all")

    def browser_closing_reset(self, id: str) -> dict:
        """重置窗口关闭状态（窗口异常关闭后卡在"打开中/关闭中"时使用）"""
        return self._post("/browser/closing/reset", {"id": id})

    def browser_ports(self) -> dict:
        """获取所有窗口的调试端口"""
        return self._post("/browser/ports")

    def browser_fingerprint_random(self, browser_id: str) -> dict:
        """获取随机指纹"""
        return self._post("/browser/fingerprint/random", {"browserId": browser_id})

    # ------------------------------------------------------------------
    # Window Layout
    # ------------------------------------------------------------------

    def window_bounds(self, layout: dict) -> dict:
        return self._post("/windowbounds", layout)

    def window_bounds_flexable(self, seqlist: list[int] | None = None) -> dict:
        """一键自适应排列窗口"""
        data: dict[str, Any] = {}
        if seqlist:
            data["seqlist"] = seqlist
        return self._post("/windowbounds/flexable", data)

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def cache_clear(self, ids: list[str]) -> dict:
        """清理指定窗口的本地和服务端缓存"""
        return self._post("/cache/clear", {"ids": ids})

    def cache_clear_except_extensions(self, ids: list[str]) -> dict:
        """清理缓存（保留扩展数据）"""
        return self._post("/cache/clear/exceptExtensions", {"ids": ids})

    # ------------------------------------------------------------------
    # Cookies
    # ------------------------------------------------------------------

    def browser_cookies_set(self, browser_id: str, cookies: list[dict]) -> dict:
        """设置窗口的实时 Cookie"""
        return self._post(
            "/browser/cookies/set", {"browserId": browser_id, "cookies": cookies}
        )

    def browser_cookies_get(self, browser_id: str) -> dict:
        """获取窗口的实时 Cookie"""
        return self._post("/browser/cookies/get", {"browserId": browser_id})

    def browser_cookies_clear(self, browser_id: str, save_synced: bool = True) -> dict:
        """清空窗口 Cookie"""
        return self._post(
            "/browser/cookies/clear",
            {"browserId": browser_id, "saveSynced": save_synced},
        )

    def browser_cookies_format(self, cookie: Any, hostname: str) -> dict:
        """格式化 Cookie 数据"""
        return self._post(
            "/browser/cookies/format", {"cookie": cookie, "hostname": hostname}
        )

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def browser_tag_list(self) -> dict:
        """获取标签列表"""
        return self._post("/browserTag/list")

    def browser_tag_create(self, tag_name: str, tag_color: str) -> dict:
        """创建标签"""
        return self._post(
            "/browserTag/create", {"tagName": tag_name, "tagColor": tag_color}
        )

    def browser_tag_update(self, id: str, tag_name: str, tag_color: str) -> dict:
        """修改标签"""
        return self._post(
            "/browserTag/update",
            {"id": id, "tagName": tag_name, "tagColor": tag_color},
        )

    def browser_tag_delete(self, ids: list[str]) -> dict:
        """删除标签（支持批量）"""
        return self._post("/browserTag/delete", {"ids": ids})

    def browser_tag_update_relation(
        self, browser_id: str, add_tag_ids: list[str], remove_tag_ids: list[str]
    ) -> dict:
        """更新窗口的标签绑定关系"""
        return self._post(
            "/browserTag/updateRelation",
            {
                "browserId": browser_id,
                "addTagIds": add_tag_ids,
                "removeTagIds": remove_tag_ids,
            },
        )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def check_agent(
        self,
        host: str,
        port: int,
        proxy_type: str,
        proxy_user_name: str = "",
        proxy_password: str = "",
        ip_check_service: str = "ip123in",
        check_exists: int = 0,
    ) -> dict:
        """检测代理连通性"""
        return self._post(
            "/checkagent",
            {
                "host": host,
                "port": port,
                "proxyType": proxy_type,
                "proxyUserName": proxy_user_name,
                "proxyPassword": proxy_password,
                "ipCheckService": ip_check_service,
                "checkExists": check_exists,
            },
        )

    def all_displays(self) -> dict:
        """获取显示器列表"""
        return self._post("/alldisplays")
