from __future__ import annotations

from dataclasses import dataclass

_STATUS_MAP: dict[int, str] = {
    0: "closed",
    1: "opening",
    2: "open",
    3: "closing",
    4: "error",
}


def _parse_status(raw) -> str:
    if isinstance(raw, str):
        return raw.lower()
    if isinstance(raw, int):
        return _STATUS_MAP.get(raw, "unknown")
    return "unknown"


@dataclass
class GroupItem:
    id: str
    name: str
    sort: int = 0


@dataclass
class BrowserItem:
    id: str
    name: str
    seq: int = 0
    group_id: str = ""
    group_name: str = ""
    platform: str = ""
    remark: str = ""
    proxy_method: int = 2
    proxy_type: str = "noproxy"
    status: str = "closed"
    ws_url: str = ""
    http_url: str = ""
    driver_path: str = ""
    core_version: str = ""

    @classmethod
    def from_api_dict(cls, d: dict) -> BrowserItem:
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            seq=d.get("seq", 0),
            group_id=d.get("groupId", ""),
            group_name=d.get("groupName", ""),
            platform=d.get("platform", ""),
            remark=d.get("remark", ""),
            proxy_method=d.get("proxyMethod", 2),
            proxy_type=d.get("proxyType", "noproxy"),
            core_version=d.get("coreVersion", ""),
            status=_parse_status(d.get("status")),
        )
