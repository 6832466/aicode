"""下载引擎 - videodl 解析 + requests 直链下载"""
import os
import time
import requests
import urllib.request
from app.utils.link_utils import detect_platform, source_to_platform
from app.utils.logger import get_logger

_log = get_logger('DownloadEngine')

# 修复快手 DrissionPage 卡死: 反转解析器顺序，优先用 requests
_patched_kuaishou = False

def _patch_kuaishou_parser():
    global _patched_kuaishou
    if _patched_kuaishou:
        return
    try:
        from videodl.modules.sources.kuaishou import KuaishouVideoClient
        _original_parse = KuaishouVideoClient.parsefromurl

        def _patched_parsefromurl(self, url, request_overrides=None):
            # requests 优先，避免 DrissionPage headless Chrome 卡死
            for parser in [self._parsefromurlusingrequests, self._parsefromurlusingdrissionpage]:
                video_infos = parser(url, request_overrides)
                if any(getattr(vi, 'with_valid_download_url', False) for vi in (video_infos or [])):
                    break
            return video_infos

        KuaishouVideoClient.parsefromurl = _patched_parsefromurl
        _patched_kuaishou = True
        _log.info('快手解析器已打补丁: requests 优先')
    except Exception as e:
        _log.warning(f'快手解析器补丁失败: {e}')


def _get_system_proxy() -> dict | None:
    """读取系统代理设置"""
    try:
        proxies = urllib.request.getproxies()
        http_proxy = proxies.get('http') or proxies.get('https')
        if http_proxy:
            return {'http': http_proxy, 'https': http_proxy}
    except Exception:
        pass
    return None


class DownloadEngine:
    """封装 videodl 解析，requests 直链下载"""

    def __init__(self, ffmpeg_path: str = None):
        self._ffmpeg_path = ffmpeg_path
        self._proxy_mode: str = 'system'
        self._proxy_url: str = ''

    def set_proxy(self, mode: str = 'system', url: str = ''):
        self._proxy_mode = mode
        self._proxy_url = url

    def _get_proxies(self) -> dict | None:
        if self._proxy_mode == 'none':
            return None
        if self._proxy_mode == 'custom' and self._proxy_url:
            return {'http': self._proxy_url, 'https': self._proxy_url}
        return _get_system_proxy()

    def parse_video(self, url: str, cookie: str = None) -> dict | None:
        """解析视频链接，返回视频信息字典"""
        try:
            from videodl import videodl
            client = self._create_videodl_client(cookie)
            video_infos = client.parsefromurl(url)

            if not video_infos:
                return None

            info = video_infos[0]
            if info.get('err_msg'):
                _log.warning(f'解析错误: {info.get("err_msg")}')
                return None

            # 使用 videodl 返回的真实 source 确定平台
            videodl_source = str(info.get('source', ''))
            platform = source_to_platform(videodl_source) if videodl_source else (detect_platform(url) or 'unknown')

            download_url = info.get('download_url', '')
            # 处理 YouTube 官方 API 返回的 Stream 对象（有 .url 属性）
            if hasattr(download_url, 'url') and isinstance(download_url.url, str):
                download_url = download_url.url
            # 同样处理音频 URL
            audio_download_url = info.get('audio_download_url', '')
            if hasattr(audio_download_url, 'url') and isinstance(audio_download_url.url, str):
                audio_download_url = audio_download_url.url
            result = {
                'title': info.get('title', '未知标题'),
                'download_url': download_url,
                'audio_download_url': audio_download_url,
                'ext': info.get('ext', 'mp4'),
                'source': videodl_source,
                'platform': platform,
                'author': info.get('author', ''),
                'duration': str(info.get('duration', '')),
                'cover_url': info.get('cover_url', ''),
                'size_estimate': info.get('guess_video_ext_result', {}).get('filesize', 0) or 0,
                'video_id': info.get('identifier', ''),
                'raw_info': dict(info) if hasattr(info, 'items') else {},
                '_headers': dict(info.get('default_download_headers', {}) or {}),
                '_cookies': dict(info.get('default_download_cookies', {}) or {}),
            }
            _log.info(f'解析成功: {result["title"]}')
            return result
        except Exception as e:
            _log.exception(f'解析异常: {url} {e}')
            return None

    def download(self, video_info: dict, save_dir: str, filename: str,
                 progress_callback=None, cookie: str = None) -> str | None:
        """
        直接 HTTP 下载视频文件。
        progress_callback(percent, speed, downloaded_bytes, total_bytes, error)
        返回最终文件路径，失败返回 None。
        """
        url = video_info.get('download_url', '')
        if not url:
            _log.error('下载失败: download_url 为空')
            if progress_callback:
                progress_callback(-1, 0, 0, 0, '下载链接为空')
            return None

        save_path = os.path.join(save_dir, filename)
        from app.utils.file_utils import resolve_filename_conflict
        save_path = resolve_filename_conflict(save_path)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            'Referer': 'https://www.douyin.com/',
        }
        # 合并视频源自带的 headers
        src_headers = video_info.get('_headers', {})
        if src_headers:
            headers.update(src_headers)

        cookies = video_info.get('_cookies', {})
        if cookie:
            for item in cookie.split(';'):
                if '=' in item:
                    k, v = item.strip().split('=', 1)
                    cookies[k] = v

        temp_path = save_path + '.part'
        _log.info(f'开始下载: {os.path.basename(save_path)}')

        try:
            req_kwargs = dict(headers=headers, cookies=cookies,
                            stream=True, timeout=30, verify=False)
            proxies = self._get_proxies()
            if proxies:
                req_kwargs['proxies'] = proxies
            resp = requests.get(url, **req_kwargs)
            resp.raise_for_status()

            total = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            start_time = time.time()
            last_report = start_time

            with open(temp_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 每秒最多报告 4 次进度
                        now = time.time()
                        if progress_callback and (now - last_report >= 0.25):
                            elapsed = now - start_time
                            pct = int(downloaded / total * 100) if total > 0 else 0
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            progress_callback(pct, speed, downloaded, total, None)
                            last_report = now

            # 完成
            if progress_callback:
                progress_callback(100, 0, downloaded, total or downloaded, None)

            os.replace(temp_path, save_path)

            if os.path.exists(save_path):
                size_mb = os.path.getsize(save_path) / (1024 * 1024)
                _log.info(f'下载完成: {os.path.basename(save_path)} ({size_mb:.1f} MB)')
                return save_path
            else:
                _log.error(f'下载后文件不存在: {save_path}')
                if progress_callback:
                    progress_callback(-1, 0, 0, 0, '文件保存失败')
                return None

        except requests.exceptions.RequestException as e:
            _log.exception(f'下载网络异常: {e}')
            if progress_callback:
                progress_callback(-1, 0, 0, 0, f'网络错误: {str(e)[:100]}')
            # 清理临时文件
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            return None
        except Exception as e:
            _log.exception(f'下载异常: {e}')
            if progress_callback:
                progress_callback(-1, 0, 0, 0, str(e)[:100])
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            return None

    def _create_videodl_client(self, cookie: str = None):
        _patch_kuaishou_parser()
        from videodl import videodl
        from videodl.modules import VideoClientBuilder
        kwargs = {'allowed_video_sources': []}  # 空列表 = 使用全部平台

        proxies = self._get_proxies()
        if proxies:
            overrides = {}
            for vc_name in VideoClientBuilder.REGISTERED_MODULES:
                overrides[vc_name] = {'proxies': proxies}
            kwargs['requests_overrides'] = overrides

        client = videodl.VideoClient(**kwargs)

        if cookie:
            try:
                client.setcookie(cookie)
            except Exception:
                pass

        return client
