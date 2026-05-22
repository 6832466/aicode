"""
剧集全集视频下载器
用法:
  python hgDown.py <分享链接>                   -- 从分享链接下载
  python hgDown.py search <关键词>               -- 搜索短剧并选择下载
  python hgDown.py series <series_id>            -- 直接从剧集ID下载
"""

import re
import json
import logging
import sys
import time as _time
import urllib.parse
import requests
from pathlib import Path

# HongguoDatabase 仅在搜索模式使用，懒加载避免依赖问题

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

SCRIPT_DIR = Path(__file__).parent
TEMPLATE_FILE = SCRIPT_DIR / ".hongguo_template.json"


def extract_ssr_data(html: str) -> dict | None:
    """从 HTML 中提取 window._ROUTER_DATA (通过括号匹配)"""
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


def parse_page_data(router_data: dict) -> tuple[dict | None, str]:
    """从 ROUTER_DATA 中提取 pageData"""
    loader = router_data.get("loaderData", {})
    for page_type in ("video-animation-share_page", "video-list-share-ssr_page"):
        try:
            return loader[page_type]["pageData"], page_type
        except (KeyError, TypeError):
            continue
    return None, ""


def get_page_path(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.path


def build_episode_url(base_params: dict, vid: str, page_path: str) -> str:
    zlink_parsed = urllib.parse.urlparse(base_params["zlink"])
    zlink_query = urllib.parse.parse_qs(zlink_parsed.query)
    scheme_params_str = zlink_query.get("schemeParams", [""])[0]
    scheme_params = json.loads(scheme_params_str)
    scheme_params["vid"] = vid
    scheme_params["share_toast_vid"] = vid
    raw_scheme = json.dumps(scheme_params, separators=(",", ":"))
    zlink_query["schemeParams"] = [raw_scheme]
    new_zlink_query = urllib.parse.urlencode(zlink_query, doseq=True)
    new_zlink = urllib.parse.urlunparse(zlink_parsed._replace(query=new_zlink_query))

    report_str = base_params.get("report_params", "")
    if report_str:
        report = json.loads(report_str)
        report["content_id"] = vid
        new_report = json.dumps(report, separators=(",", ":"))
    else:
        new_report = ""

    params = {
        k: v for k, v in base_params.items()
        if k not in ("zlink", "report_params")
    }
    params["zlink"] = new_zlink
    params["report_params"] = new_report
    query = urllib.parse.urlencode(params)
    return f"https://novelquickapp.com{page_path}?{query}"


def parse_base_params(initial_url: str) -> dict:
    parsed = urllib.parse.urlparse(initial_url)
    return dict(urllib.parse.parse_qsl(parsed.query))


def sanitize_filename(name: str) -> str:
    illegal = r'[<>:"/\\|?*]'
    return re.sub(illegal, "_", name)


def download_video(url: str, filepath: Path, max_retries: int = 3) -> bool:
    if filepath.exists():
        print(f"  已存在，跳过: {filepath.name}")
        return True

    headers = {**HEADERS, "Referer": "https://novelquickapp.com/"}

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=120)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            if total > 0 and abs(downloaded - total) > 100:
                print(f"  警告: 预期 {total} 字节, 实际 {downloaded} 字节")
            return True
        except Exception as e:
            if attempt < max_retries:
                wait = attempt * 2
                print(f"  重试 {attempt}/{max_retries}: {e}, {wait}s 后重试...")
                _time.sleep(wait)
            else:
                print(f"  下载失败: {e}")
                if filepath.exists():
                    filepath.unlink()
    return False


# ---- Template params management ----

def save_template_params(params: dict) -> None:
    try:
        TEMPLATE_FILE.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, json.JSONEncodeError):
        logger.exception("保存模板参数失败")


def load_template_params() -> dict | None:
    try:
        if TEMPLATE_FILE.exists():
            return json.loads(TEMPLATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("加载模板参数失败")
    return None


# ---- Search & download ----

def download_from_series_id(series_id: str, session: requests.Session, max_episodes: int = 0) -> bool:
    """使用模板参数从 series_id 下载全剧
    max_episodes: 限制下载集数, 0=全部
    """
    template = load_template_params()
    if not template:
        print("错误: 没有保存的模板参数，请先使用分享链接下载一次")
        return False

    base_params = dict(template)
    page_path = base_params.pop("_page_path", "/hongguo/ug/pages/video-animation-share")

    # Step 1: 从 detail 页面获取 vid_list 和元数据
    print(f"[1/4] 获取剧集信息...")
    detail_url = f"https://novelquickapp.com/detail?series_id={series_id}"
    resp = session.get(detail_url, allow_redirects=True, timeout=30)
    ssr = extract_ssr_data(resp.text)
    if not ssr:
        print("错误: 无法获取剧集详情")
        return False

    sd = ssr["loaderData"]["detail_page"]["seriesDetail"]
    title = sd["series_name"]
    vid_list = sd["vid_list"]
    total = len(vid_list)

    print(f"  剧名: {title}")
    print(f"  类别: {' '.join(sd.get('tags', [])[:5])}")
    print(f"  简介: {sd.get('series_intro', '')[:80]}...")
    print(f"  共 {total} 集")

    safe_title = sanitize_filename(title)
    output_dir = SCRIPT_DIR / safe_title
    output_dir.mkdir(exist_ok=True)

    # Step 2: 用第一个 vid 构造分享页 URL, 获取 chapter_ids 和第一个 play_url
    print(f"\n[2/4] 获取播放地址...")
    first_vid = vid_list[0]

    zlink_parsed = urllib.parse.urlparse(base_params["zlink"])
    zlink_query = urllib.parse.parse_qs(zlink_parsed.query)
    scheme_str = zlink_query.get("schemeParams", [""])[0]
    scheme = json.loads(scheme_str)
    scheme["vid"] = first_vid
    scheme["share_toast_vid"] = first_vid
    scheme["video_id"] = series_id
    new_scheme = json.dumps(scheme, separators=(",", ":"))
    zlink_query["schemeParams"] = [new_scheme]
    base_params["zlink"] = urllib.parse.urlunparse(
        zlink_parsed._replace(query=urllib.parse.urlencode(zlink_query, doseq=True))
    )

    report_str = base_params.get("report_params", "")
    if report_str:
        report = json.loads(report_str)
        report["content_id"] = first_vid
        base_params["report_params"] = json.dumps(report, separators=(",", ":"))

    first_url = f"https://novelquickapp.com{page_path}?{urllib.parse.urlencode(base_params)}"
    resp = session.get(first_url, allow_redirects=True, timeout=30)
    ssr = extract_ssr_data(resp.text)
    if not ssr:
        print("错误: 无法获取分享页数据")
        return False

    page_data, _pt = parse_page_data(ssr)
    if not page_data:
        print("错误: 无法解析 pageData")
        return False

    chapter_ids = page_data.get("chapter_ids", vid_list)
    if max_episodes > 0:
        chapter_ids = chapter_ids[:max_episodes]
        total = len(chapter_ids)
    play_urls = {}
    if page_data["series_data"].get("play_url"):
        play_urls[1] = page_data["series_data"]["play_url"]
        print(f"  第 01/{total} 集 [OK]")

    # Step 3: 获取其余剧集的播放地址
    for idx, vid in enumerate(chapter_ids, 1):
        if idx in play_urls:
            continue
        episode_url = build_episode_url(base_params, vid, page_path)
        try:
            ep_resp = session.get(episode_url, allow_redirects=True, timeout=30)
            ep_ssr = extract_ssr_data(ep_resp.text)
            if ep_ssr:
                ep_data, _pt = parse_page_data(ep_ssr)
                if ep_data and ep_data["series_data"].get("play_url"):
                    play_urls[idx] = ep_data["series_data"]["play_url"]
                    print(f"  第 {idx:02d}/{total} 集 [OK]")
                else:
                    print(f"  第 {idx:02d}/{total} 集 [NO URL]")
            else:
                print(f"  第 {idx:02d}/{total} 集 [PARSE ERR]")
        except Exception as e:
            print(f"  第 {idx:02d}/{total} 集 [FAIL]: {e}")
        _time.sleep(1)

    print(f"\n  共获取 {len(play_urls)}/{total} 个播放地址")

    if not play_urls:
        print("错误: 没有获取到任何播放地址")
        return False

    # Step 4: 下载所有视频
    print(f"\n[3/4] 开始下载视频...")
    success = 0
    for idx in sorted(play_urls.keys()):
        url = play_urls[idx]
        filename = f"{safe_title}_第{idx:02d}集.mp4"
        filepath = output_dir / filename
        print(f"  [{idx:02d}/{total}] {filename}")
        if download_video(url, filepath):
            success += 1

    # Step 5: 保存元数据
    print(f"\n[4/4] 保存元数据...")
    meta = {
        "title": title,
        "category": " ".join(sd.get("tags", [])),
        "intro": sd.get("series_intro", ""),
        "total_episodes": total,
        "downloaded": success,
        "episodes": {
            str(idx): {
                "vid": chapter_ids[idx - 1] if idx <= len(chapter_ids) else "",
                "url": play_urls.get(idx, ""),
                "file": f"{safe_title}_第{idx:02d}集.mp4"
            }
            for idx in range(1, total + 1)
        }
    }
    meta_path = output_dir / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  已保存: {meta_path}")

    print(f"\n完成! 成功下载 {success}/{total} 集到 {output_dir}/")
    return True


def cmd_search(db: "HongguoDatabase", keyword: str):
    """搜索短剧并选择下载"""
    results = db.search(keyword, limit=30)
    if not results:
        print(f"未找到与 \"{keyword}\" 相关的短剧")
        return

    print(f"\n搜索 \"{keyword}\" 找到 {len(results)} 部短剧:\n")
    print(f"{'#':<4} {'剧名':<30} {'集数':<8} {'标签'}")
    print("-" * 80)
    for i, s in enumerate(results, 1):
        tags_str = " ".join(s.tags[:4])
        print(f"{i:<4} {s.series_name:<30} {s.episode_count:<8} {tags_str}")
        if s.series_intro:
            print(f"     {s.series_intro[:60]}")

    while True:
        try:
            choice = input(f"\n输入序号下载 (1-{len(results)}), 或 q 退出: ").strip()
            if choice.lower() == "q":
                return
            idx = int(choice)
            if 1 <= idx <= len(results):
                break
            print(f"请输入 1-{len(results)} 之间的数字")
        except ValueError:
            print("请输入有效数字")

    series = results[idx - 1]
    print(f"\n开始下载: {series.series_name}")

    session = requests.Session()
    session.headers.update(HEADERS)
    download_from_series_id(series.series_id, session)


# ---- Main ----

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg1 = sys.argv[1].strip()

    # 搜索模式
    if arg1 == "search":
        if len(sys.argv) < 3:
            print("用法: python hgDown.py search <关键词>")
            sys.exit(1)
        keyword = sys.argv[2]
        from search import HongguoDatabase
        db = HongguoDatabase()
        db.load_from_homepage()
        cmd_search(db, keyword)
        return

    # 解析 --limit 参数
    limit = 0
    args = sys.argv[1:]
    if "--limit" in args:
        idx = args.index("--limit")
        if idx + 1 < len(args):
            limit = int(args[idx + 1])
            args.pop(idx)  # remove --limit
            args.pop(idx)  # remove value
    arg1 = args[0] if args else ""

    # Series ID 直接下载
    if arg1 == "series":
        if len(args) < 2:
            print("用法: python hgDown.py series <series_id> [--limit N]")
            sys.exit(1)
        series_id = args[1]
        session = requests.Session()
        session.headers.update(HEADERS)
        download_from_series_id(series_id, session, max_episodes=limit)
        return

    # 分享链接模式
    share_url = arg1
    print(f"[1/4] 访问分享链接获取短剧信息...")
    print(f"  URL: {share_url}")

    session = requests.Session()
    session.headers.update(HEADERS)

    resp = session.get(share_url, allow_redirects=True, timeout=30)
    final_url = resp.url
    print(f"  重定向到: {final_url}")

    base_params = parse_base_params(final_url)
    page_path = get_page_path(final_url)

    # 保存模板参数
    template = dict(base_params)
    template["_page_path"] = page_path
    save_template_params(template)
    print(f"  已保存模板参数到 {TEMPLATE_FILE.name}")

    ssr_data = extract_ssr_data(resp.text)
    if not ssr_data:
        print("错误: 无法从页面中提取 SSR 数据")
        sys.exit(1)

    page_data, page_type = parse_page_data(ssr_data)
    if not page_data:
        print("错误: 无法解析 pageData")
        sys.exit(1)

    print(f"  页面类型: {page_type}")

    series = page_data["series_data"]
    title = series["title"]
    chapter_ids = page_data["chapter_ids"]
    total = len(chapter_ids)

    print(f"\n  剧名: {title}")
    print(f"  类别: {series.get('category', '')}")
    print(f"  简介: {series.get('series_intro', '')[:80]}...")
    print(f"  热度: {series.get('popularity', 0) / 10000:.1f}万")
    print(f"  共 {total} 集")

    safe_title = sanitize_filename(title)
    output_dir = SCRIPT_DIR / safe_title
    output_dir.mkdir(exist_ok=True)
    print(f"\n  下载目录: {output_dir}")

    print(f"\n[2/4] 获取各集播放地址...")
    play_urls = {}

    if page_data["series_data"].get("play_url"):
        play_urls[1] = page_data["series_data"]["play_url"]
        print(f"  第 01/{total} 集 [OK] (来自首页)")

    for idx, vid in enumerate(chapter_ids, 1):
        if idx in play_urls:
            continue
        episode_url = build_episode_url(base_params, vid, page_path)
        try:
            ep_resp = session.get(episode_url, allow_redirects=True, timeout=30)
            ep_ssr = extract_ssr_data(ep_resp.text)
            if ep_ssr:
                ep_data, _pt = parse_page_data(ep_ssr)
                if ep_data and ep_data["series_data"].get("play_url"):
                    play_urls[idx] = ep_data["series_data"]["play_url"]
                    print(f"  第 {idx:02d}/{total} 集 [OK]")
                else:
                    print(f"  第 {idx:02d}/{total} 集 [NO URL]")
            else:
                print(f"  第 {idx:02d}/{total} 集 [PARSE ERR]")
        except Exception as e:
            print(f"  第 {idx:02d}/{total} 集 [FAIL]: {e}")
        _time.sleep(1)

    print(f"\n  共获取 {len(play_urls)}/{total} 个播放地址")

    if not play_urls:
        print("错误: 没有获取到任何播放地址")
        sys.exit(1)

    print(f"\n[3/4] 开始下载视频...")
    success = 0
    for idx in sorted(play_urls.keys()):
        url = play_urls[idx]
        filename = f"{safe_title}_第{idx:02d}集.mp4"
        filepath = output_dir / filename
        print(f"  [{idx:02d}/{total}] {filename}")
        if download_video(url, filepath):
            success += 1

    print(f"\n[4/4] 保存元数据...")
    meta = {
        "title": title,
        "category": series.get("category", ""),
        "intro": series.get("series_intro", ""),
        "total_episodes": total,
        "downloaded": success,
        "episodes": {
            str(idx): {
                "vid": chapter_ids[idx - 1],
                "url": play_urls.get(idx, ""),
                "file": f"{safe_title}_第{idx:02d}集.mp4"
            }
            for idx in range(1, total + 1)
        }
    }
    meta_path = output_dir / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  已保存: {meta_path}")

    print(f"\n完成! 成功下载 {success}/{total} 集到 {output_dir}/")


if __name__ == "__main__":
    main()
