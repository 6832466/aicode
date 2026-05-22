"""
剧集 搜索 & 排行榜模块
数据来源: 剧集首页 SSR (504部短剧 + 元数据)
"""

import re
import json
import logging
import urllib.parse
import requests
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("hongguo")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

CACHE_FILE = Path(__file__).parent / ".hongguo_cache.json"


@dataclass
class Series:
    series_id: str
    series_name: str
    series_cover: str
    series_intro: str
    tags: list = field(default_factory=list)
    episode_count: str = ""
    popularity: int = 0
    category: str = ""


class HongguoDatabase:
    """剧集本地数据库"""

    def __init__(self):
        self.series: list[Series] = []
        self.banners: list[Series] = []
        self._tag_index: dict[str, list[int]] = {}

    def load_from_homepage(self, force_refresh: bool = False) -> int:
        """从剧集首页加载短剧数据"""
        if not force_refresh and CACHE_FILE.exists():
            return self._load_cache()

        print("正在从剧集首页获取数据...")
        resp = requests.get(
            "https://novelquickapp.com/",
            headers=HEADERS,
            timeout=30
        )
        html = resp.text

        # 提取 SSR 数据
        ssr = self._extract_ssr(html)
        if not ssr:
            raise RuntimeError("无法提取首页 SSR 数据")

        page = ssr["loaderData"]["page"]
        video_list = page.get("videoList", [])

        if not video_list:
            raise RuntimeError("首页 videoList 为空")

        self.series = []
        for item in video_list:
            s = Series(
                series_id=item.get("series_id", ""),
                series_name=item.get("series_name", ""),
                series_cover=item.get("series_cover", ""),
                series_intro=item.get("series_intro", ""),
                tags=item.get("tags", []),
                episode_count=item.get("episode_right_text", ""),
                popularity=0,
                category="",
            )
            self.series.append(s)

        # 提取 Banner 推荐
        self.banners = []
        for item in page.get("bannerList", []):
            s = Series(
                series_id=item.get("series_id", ""),
                series_name=item.get("series_name", ""),
                series_cover=item.get("series_cover", ""),
                series_intro=item.get("series_intro", ""),
                tags=item.get("tags", []),
                episode_count="",
                popularity=0,
                category="推荐",
            )
            self.banners.append(s)

        self._build_index()
        self._save_cache()
        print(f"已加载 {len(self.series)} 部短剧, {len(self.banners)} 个Banner")
        return len(self.series)

    def search(
        self,
        keyword: str,
        limit: int = 50,
        sort_by: str = "relevance"
    ) -> list[Series]:
        """搜索短剧
        sort_by: relevance | name
        """
        kw = keyword.lower()
        results = []

        for s in self.series:
            score = 0
            name_lower = s.series_name.lower()
            intro_lower = s.series_intro.lower()
            tags_lower = [t.lower() for t in s.tags]

            # 标题精确匹配
            if kw == name_lower:
                score += 100
            # 标题包含
            if kw in name_lower:
                score += 50
            # 标题部分匹配
            for char in kw:
                if char in name_lower:
                    score += 1

            # 标签匹配
            for tag in tags_lower:
                if kw in tag:
                    score += 30
                for char in kw:
                    if char in tag:
                        score += 0.5

            # 简介匹配
            if kw in intro_lower:
                score += 10

            if score > 0:
                results.append((score, s))

        if sort_by == "relevance":
            results.sort(key=lambda x: -x[0])
        elif sort_by == "name":
            results.sort(key=lambda x: x[1].series_name)

        return [s for _, s in results[:limit]]

    def rank(
        self,
        category: Optional[str] = None,
        limit: int = 50,
        sort_by: str = "name"
    ) -> list[Series]:
        """获取排行榜/分类列表
        category: 标签名过滤 (None = 全部)
        sort_by: name | episode | newest
        """
        if category:
            cat_lower = category.lower()
            filtered = [
                s for s in self.series
                if any(cat_lower in t.lower() for t in s.tags)
            ]
        else:
            filtered = list(self.series)

        if sort_by == "name":
            filtered.sort(key=lambda s: s.series_name)
        elif sort_by == "episode":
            def episode_num(s: Series) -> int:
                match = re.search(r"(\d+)集", s.episode_count)
                return int(match.group(1)) if match else 0
            filtered.sort(key=episode_num, reverse=True)
        elif sort_by == "newest":
            filtered.sort(key=lambda s: int(s.series_id), reverse=True)

        return filtered[:limit]

    def categories(self) -> list[tuple[str, int]]:
        """获取所有标签及其数量 (近似榜单)"""
        tag_count: dict[str, int] = {}
        for s in self.series:
            for tag in s.tags:
                tag_count[tag] = tag_count.get(tag, 0) + 1
        return sorted(tag_count.items(), key=lambda x: -x[1])

    def _build_index(self) -> None:
        self._tag_index = {}
        for i, s in enumerate(self.series):
            for tag in s.tags:
                tag_lower = tag.lower()
                if tag_lower not in self._tag_index:
                    self._tag_index[tag_lower] = []
                self._tag_index[tag_lower].append(i)

    def _save_cache(self) -> None:
        try:
            data = {
                "updated": __import__("datetime").datetime.now().isoformat(),
                "count": len(self.series),
                "series": [
                    {
                        "series_id": s.series_id,
                        "series_name": s.series_name,
                        "series_cover": s.series_cover,
                        "series_intro": s.series_intro,
                        "tags": s.tags,
                        "episode_count": s.episode_count,
                    }
                    for s in self.series
                ],
                "banners": [
                    {
                        "series_id": s.series_id,
                        "series_name": s.series_name,
                        "series_cover": s.series_cover,
                        "series_intro": s.series_intro,
                        "tags": s.tags,
                    }
                    for s in self.banners
                ]
            }
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (OSError, json.JSONEncodeError):
            logger.exception("保存缓存文件失败")

    def _load_cache(self) -> int:
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.series = [
                Series(
                    series_id=s["series_id"],
                    series_name=s["series_name"],
                    series_cover=s.get("series_cover", ""),
                    series_intro=s.get("series_intro", ""),
                    tags=s.get("tags", []),
                    episode_count=s.get("episode_count", ""),
                )
                for s in data["series"]
            ]
            self.banners = [
                Series(
                    series_id=s["series_id"],
                    series_name=s["series_name"],
                    series_cover=s.get("series_cover", ""),
                    series_intro=s.get("series_intro", ""),
                    tags=s.get("tags", []),
                    episode_count="",
                    category="推荐",
                )
                for s in data.get("banners", [])
            ]
            self._build_index()
            return len(self.series)
        except (OSError, json.JSONDecodeError, KeyError):
            logger.exception("加载缓存文件失败, 将重新获取")
            return 0

    @staticmethod
    def _extract_ssr(html: str) -> dict | None:
        marker = "window._ROUTER_DATA = "
        start = html.find(marker)
        if start == -1:
            return None
        json_start = html.find("{", start)
        if json_start == -1:
            return None
        depth = 0
        for i in range(json_start, len(html)):
            if html[i] == "{":
                depth += 1
            elif html[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[json_start : i + 1])
                    except json.JSONDecodeError:
                        return None
        return None


# ---- CLI ----

def cmd_search(db: HongguoDatabase, keyword: str, limit: int = 30):
    """搜索短剧"""
    results = db.search(keyword, limit=limit)
    if not results:
        print(f"未找到与 \"{keyword}\" 相关的短剧")
        return

    print(f"\n搜索 \"{keyword}\" 找到 {len(results)} 部短剧:\n")
    print(f"{'序号':<5} {'剧名':<30} {'标签'}")
    print("-" * 80)
    for i, s in enumerate(results, 1):
        tags_str = " ".join(s.tags[:5])
        print(f"{i:<5} {s.series_name:<30} {tags_str}")
        if s.series_intro:
            print(f"      {s.series_intro[:60]}")
        print(f"      集数: {s.episode_count}  |  ID: {s.series_id}")
        print()


def cmd_rank(db: HongguoDatabase, category: str = None, limit: int = 30):
    """显示排行榜"""
    title = f"剧集 - {category or '全部'} (按集数排序)"
    results = db.rank(category=category, limit=limit, sort_by="episode")
    print(f"\n{title}")
    print(f"{'序号':<5} {'剧名':<30} {'集数':<8} {'标签'}")
    print("-" * 80)
    for i, s in enumerate(results, 1):
        tags_str = " ".join(s.tags[:5])
        print(f"{i:<5} {s.series_name:<30} {s.episode_count:<8} {tags_str}")
        print(f"      ID: {s.series_id}")
        print()


def cmd_banners(db: HongguoDatabase):
    """显示首页Banner推荐"""
    print(f"\n剧集 - 首页推荐 (Banner):")
    print(f"{'序号':<5} {'剧名':<30} {'标签'}")
    print("-" * 80)
    for i, s in enumerate(db.banners, 1):
        tags_str = " ".join(s.tags[:5])
        print(f"{i:<5} {s.series_name:<30} {tags_str}")
        if s.series_intro:
            print(f"      {s.series_intro[:60]}")
        print(f"      ID: {s.series_id}")
        print()


def cmd_categories(db: HongguoDatabase, limit: int = 30):
    """显示所有分类标签 (热搜榜/分类榜)"""
    cats = db.categories()
    print(f"\n剧集 分类/标签 Top {limit}:")
    print(f"{'序号':<5} {'标签':<16} {'数量':<8}")
    print("-" * 35)
    for i, (tag, count) in enumerate(cats[:limit], 1):
        bar = "█" * min(count // 10, 30)
        print(f"{i:<5} {tag:<16} {count:<8} {bar}")
    print(f"\n共 {len(cats)} 个标签\n")


if __name__ == "__main__":
    import sys
    db = HongguoDatabase()
    db.load_from_homepage()

    if len(sys.argv) < 2:
        print("用法:")
        print("  python search.py search <关键词>    -- 搜索短剧")
        print("  python search.py rank [标签]       -- 排行榜 (按集数, 可选标签过滤)")
        print("  python search.py banners           -- 首页推荐")
        print("  python search.py categories        -- 所有分类标签 (热搜榜)")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "search":
        kw = sys.argv[2] if len(sys.argv) > 2 else ""
        cmd_search(db, kw)
    elif cmd == "rank":
        cat = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_rank(db, cat)
    elif cmd == "banners":
        cmd_banners(db)
    elif cmd == "categories":
        cmd_categories(db)
    else:
        print(f"未知命令: {cmd}")
