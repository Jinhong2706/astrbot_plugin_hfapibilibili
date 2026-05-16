import aiohttp
import aiofiles
import asyncio
import tempfile
import time
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Video, Plain, Image

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com"
}

@register("astrbot_plugin_hfapibilibili", "Jinhong270", "B站视频下载器", "1.6.0")
class Jinhong270BilibiliPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        self.temp_retention = config.get("temp_file_retention", 600)
        self.search_result_count = min(config.get("search_result_count", 20), 50)
        self.proxy = config.get("proxy", "")
        self.quality = config.get("quality", "720p")
        cache_dir = config.get("cache_dir", "")
        self.api_base_url = config.get("api_base_url", "https://jinhong270-api.hf.space")

        self.user_sessions: Dict[str, dict] = {}
        self.has_ffmpeg = self._check_ffmpeg()
        self.font_path = self._find_chinese_font()

        if cache_dir:
            self.temp_dir = Path(cache_dir)
        else:
            self.temp_dir = Path(tempfile.gettempdir()) / "astrbot_plugin_hfapibilibili"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._clean_task = asyncio.create_task(self._clean_temp_files_loop())
        self._session_timeout_task = asyncio.create_task(self._check_session_timeout())

        self._session = aiohttp.ClientSession(
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=300)
        )

    @staticmethod
    def _check_ffmpeg() -> bool:
        return shutil.which("ffmpeg") is not None

    @staticmethod
    def _find_chinese_font() -> Optional[Path]:
        _CANDIDATE_FONTS = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/msyhbd.ttc",
        ]
        for font in _CANDIDATE_FONTS:
            p = Path(font)
            if p.exists():
                logger.info(f"使用字体: {p}")
                return p
        logger.warning("未找到中文字体，搜索图片将使用默认字体（中文可能乱码）")
        return None

    async def _clean_temp_files_loop(self):
        try:
            while True:
                now = time.time()
                for f in self.temp_dir.iterdir():
                    if f.is_file() and (now - f.stat().st_mtime) > self.temp_retention:
                        f.unlink(missing_ok=True)
                await asyncio.sleep(600)
        except asyncio.CancelledError:
            pass

    async def _check_session_timeout(self):
        try:
            while True:
                await asyncio.sleep(30)
                now = time.time()
                expired = [
                    key for key, s in self.user_sessions.items()
                    if s.get("state") == "awaiting_selection" and (now - s.get("timestamp", 0) > 180)
                ]
                for key in expired:
                    self.user_sessions.pop(key, None)
        except asyncio.CancelledError:
            pass

    async def _fetch_api(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.api_base_url}{endpoint}"
        try:
            async with self._session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"API请求失败 {endpoint}: {e}")
            return {"error": str(e)}

    async def _get_file_size(self, url: str, headers: dict = None, proxy: str = None) -> int:
        proxy_kwargs = {"proxy": proxy} if proxy else {}
        try:
            async with self._session.head(url, headers=headers or {}, timeout=10, **proxy_kwargs) as resp:
                if resp.status == 200:
                    cl = resp.headers.get("Content-Length")
                    if cl:
                        return int(cl)
            range_headers = {**(headers or {}), "Range": "bytes=0-0"}
            async with self._session.get(url, headers=range_headers, timeout=10, **proxy_kwargs) as resp:
                if resp.status in (200, 206):
                    cr = resp.headers.get("Content-Range")
                    if cr and "/" in cr:
                        return int(cr.split("/")[-1])
                    cl = resp.headers.get("Content-Length")
                    if cl:
                        return int(cl)
        except Exception:
            pass
        return 0

    async def _range_download_file(
        self,
        url: str,
        save_path: Path,
        file_size: int,
        headers: dict = None,
        proxy: str = None,
        chunk_size: int = 2 * 1024 * 1024,
        max_concurrent: int = 16
    ) -> bool:
        if file_size <= 0:
            return False
        num_chunks = (file_size + chunk_size - 1) // chunk_size
        if num_chunks <= 1:
            return False
        logger.info(f"启用 Range 并发下载: {save_path.name}，大小 {file_size//1024//1024} MB，分 {num_chunks} 片，并发 {max_concurrent}")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(save_path, "wb") as f:
                f.truncate(file_size)
        except Exception as e:
            logger.warning(f"预分配文件失败: {e}")
            return False
        semaphore = asyncio.Semaphore(max_concurrent)
        lock = asyncio.Lock()
        failed = False

        async def download_chunk(idx: int):
            nonlocal failed
            async with semaphore:
                start = idx * chunk_size
                end = min(start + chunk_size - 1, file_size - 1)
                range_header = {"Range": f"bytes={start}-{end}"}
                req_headers = {**(headers or {}), **range_header}
                proxy_kwargs = {"proxy": proxy} if proxy else {}
                try:
                    timeout = aiohttp.ClientTimeout(total=60)
                    async with self._session.get(url, headers=req_headers, timeout=timeout, **proxy_kwargs) as resp:
                        if resp.status not in (200, 206):
                            raise Exception(f"HTTP {resp.status}")
                        data = await resp.read()
                        expected = end - start + 1
                        if len(data) != expected:
                            raise Exception(f"分片长度不符: {len(data)} vs {expected}")
                        async with lock:
                            with open(save_path, "r+b") as f:
                                f.seek(start)
                                f.write(data)
                    return True
                except Exception as e:
                    logger.warning(f"分片 {idx} 下载失败: {e}")
                    failed = True
                    return False

        tasks = [download_chunk(i) for i in range(num_chunks)]
        await asyncio.gather(*tasks, return_exceptions=True)

        if failed:
            save_path.unlink(missing_ok=True)
            return False

        if save_path.stat().st_size != file_size:
            logger.warning("Range 下载大小校验失败")
            save_path.unlink(missing_ok=True)
            return False

        logger.info(f"Range 下载成功: {save_path}")
        return True

    async def _download_file(self, url: str, save_path: Path, max_retries=3) -> bool:
        proxy_kwargs = {"proxy": self.proxy} if self.proxy else {}
        headers = HEADERS.copy()

        file_size = await self._get_file_size(url, headers, self.proxy)
        use_range = file_size > 20 * 1024 * 1024

        if file_size > 0:
            dynamic_timeout = min(1800, 300 + (file_size // (10 * 1024 * 1024)) * 10)
        else:
            dynamic_timeout = 600

        total_timeout = aiohttp.ClientTimeout(total=dynamic_timeout, connect=10, sock_read=dynamic_timeout)

        for attempt in range(max_retries):
            if attempt == 0 and use_range:
                logger.info(f"尝试 Range 下载 (size={file_size//1024//1024}MB): {url}")
                success = await self._range_download_file(
                    url, save_path, file_size,
                    headers=headers, proxy=self.proxy
                )
                if success:
                    return True
                logger.warning("Range 下载失败，降级为普通下载")

            try:
                async with self._session.get(url, headers=headers, timeout=total_timeout, **proxy_kwargs) as resp:
                    resp.raise_for_status()
                    if file_size == 0:
                        cl = resp.headers.get("Content-Length")
                        if cl:
                            file_size = int(cl)
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(64 * 1024):
                            f.write(chunk)
                    if file_size > 0 and save_path.stat().st_size != file_size:
                        raise Exception("下载大小与预期不符")
                    logger.info(f"下载成功: {save_path} (size={save_path.stat().st_size} bytes)")
                    return True
            except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
                logger.warning(f"下载失败 (第 {attempt+1}/{max_retries} 次): {e}")
                if save_path.exists():
                    save_path.unlink(missing_ok=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                else:
                    logger.error(f"下载最终失败: {url}")

        return False

    def _format_video_info(self, data: dict) -> str:
        if not data:
            return "获取信息失败"
        if "data" in data:
            data = data["data"]
        if "View" in data:
            data = data["View"]

        title = data.get("title") or data.get("Title") or "未知"
        bvid = data.get("bvid") or data.get("Bvid") or "未知"
        owner = data.get("owner", {})
        if isinstance(owner, dict):
            owner_name = owner.get("name") or owner.get("Name") or "未知"
        else:
            owner_name = "未知"
        stat = data.get("stat") or data.get("Stat") or {}
        view = stat.get("view") or stat.get("View") or "0"
        like = stat.get("like") or stat.get("Like") or "0"
        coin = stat.get("coin") or stat.get("Coin") or "0"
        favorite = stat.get("favorite") or stat.get("Favorite") or "0"
        share = stat.get("share") or stat.get("Share") or "0"
        danmaku = stat.get("danmaku") or stat.get("Danmaku") or "0"
        desc = data.get("desc") or data.get("Desc") or ""
        pubdate = data.get("pubdate") or data.get("Pubdate") or data.get("ctime") or data.get("Ctime") or 0
        if pubdate:
            try:
                pubdate_str = time.strftime("%Y-%m-%d", time.localtime(pubdate))
            except:
                pubdate_str = "未知"
        else:
            pubdate_str = "未知"
        link = f"https://www.bilibili.com/video/{bvid}"

        text = (
            f"视频标题：{title}\n"
            f"UP主：{owner_name}\n"
            f"视频简介：{desc if desc else '无'}\n\n"
            f"点赞👍：{like}    投币🪙：{coin}\n"
            f"收藏🌟：{favorite}    转发➡️：{share}\n"
            f"观看👀：{view}    弹幕💬：{danmaku}\n\n"
            f"原始链接：{link}\n\n"
            f"Plugin by Jinhong270"
        )
        return text

    def _extract_cover(self, data: dict) -> Optional[str]:
        if not data:
            return None
        if "data" in data:
            data = data["data"]
        return data.get("pic") or data.get("Pic") or None

    def _extract_bvid(self, text: str) -> Optional[str]:
        patterns = [
            r'(BV[a-zA-Z0-9]{10})',
            r'bvid=([a-zA-Z0-9]{12})',
            r'video/(BV[a-zA-Z0-9]{10})',
            r'bilibili\.com/video/(BV[a-zA-Z0-9]{10})',
            r'b23\.tv/([a-zA-Z0-9]+)'
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                return match.group(1)
        return None

    def _extract_avid(self, text: str) -> Optional[int]:
        patterns = [
            r'av(\d+)',
            r'aid=(\d+)',
            r'video/av(\d+)',
            r'bilibili\.com/video/av(\d+)',
        ]
        for p in patterns:
            match = re.search(p, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    async def _resolve_b23_shortlink(self, short_code: str) -> Optional[str]:
        url = f"https://b23.tv/{short_code}"
        try:
            async with self._session.head(url, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status in (301, 302, 307, 308):
                    location = resp.headers.get("Location", "")
                    if location:
                        bvid = self._extract_bvid(location)
                        if bvid:
                            return bvid
        except Exception as e:
            logger.error(f"解析短链失败 {short_code}: {e}")
        return None

    def _select_video_stream(self, videos: list, quality: str) -> Optional[str]:
        if not videos:
            return None

        quality_map = {
            "1080p": [80, 112, 74],
            "720p": [64, 66],
            "480p": [32, 33],
            "360p": [16, 17],
        }
        target_ids = quality_map.get(quality, [])

        for v in videos:
            vid = v.get("id") or v.get("stream_id")
            if vid in target_ids:
                url = v.get("baseUrl") or v.get("base_url") or v.get("url")
                if url:
                    logger.info(f"画质匹配 (ID={vid}): {quality}")
                    return url

        width_map = {
            "1080p": 1920,
            "720p": 1280,
            "480p": 854,
            "360p": 640,
        }
        target_width = width_map.get(quality, 0)
        best = None
        best_diff = float('inf')
        for v in videos:
            w = v.get("width") or v.get("codec", {}).get("width", 0)
            if w > 0:
                diff = abs(w - target_width)
                if diff < best_diff:
                    best_diff = diff
                    url = v.get("baseUrl") or v.get("base_url") or v.get("url")
                    if url:
                        best = url
        if best:
            logger.info(f"画质匹配 (宽度≈{target_width}): {quality}")
            return best

        for v in videos:
            url = v.get("baseUrl") or v.get("base_url") or v.get("url")
            if url:
                logger.warning(f"未找到画质 {quality}，使用默认流")
                return url
        return None

    def _extract_best_streams(self, download_data: dict, quality: str = "720p") -> Optional[Tuple[str, Optional[str]]]:
        if not isinstance(download_data, dict):
            return None
        data = download_data.get("data")
        if not isinstance(data, dict):
            return None

        dash = data.get("dash")
        if isinstance(dash, dict):
            videos = dash.get("video")
            audios = dash.get("audio")
            if isinstance(videos, list) and videos:
                video_url = self._select_video_stream(videos, quality)
                audio_url = None
                if isinstance(audios, list) and audios:
                    for a in audios:
                        u = a.get("baseUrl") or a.get("base_url") or a.get("url")
                        if u:
                            audio_url = u
                            break
                if video_url:
                    return (video_url, audio_url)

        durl = data.get("durl")
        if isinstance(durl, list) and durl:
            for item in durl:
                u = item.get("url") or item.get("baseUrl") or item.get("base_url")
                if u:
                    return (u, None)
        return None

    async def _merge_audio_video(self, video_path: Path, audio_path: Path, output_path: Path) -> bool:
        if not self.has_ffmpeg:
            return False
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c", "copy",
            str(output_path)
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error(f"ffmpeg合并失败: {stderr.decode()}")
                return False
            return True
        except Exception as e:
            logger.error(f"ffmpeg调用异常: {e}")
            return False

    async def _process_video_by_bvid(self, event: AstrMessageEvent, bvid: str):
        info_data = await self._fetch_api(f"/bilibili/video/{bvid}")
        if "error" in info_data:
            yield event.plain_result(f"获取视频信息失败: {info_data['error']}")
            return

        cover_url = self._extract_cover(info_data)
        info_text = self._format_video_info(info_data)

        if cover_url:
            chain = [
                Image.fromURL(cover_url),
                Plain(text=info_text)
            ]
            yield event.chain_result(chain)
        else:
            yield event.plain_result(info_text)

        if self.quality == "1080p":
            download_endpoint = f"/bilibili/video/download/1080/{bvid}"
        else:
            download_endpoint = f"/bilibili/video/download/{bvid}"

        download_data = await self._fetch_api(download_endpoint)
        if "error" in download_data:
            yield event.plain_result(f"获取下载链接失败: {download_data['error']}")
            return

        streams = self._extract_best_streams(download_data, self.quality)
        if not streams:
            logger.warning(f"下载链接解析失败，原始响应: {download_data}")
            yield event.plain_result("下载链接解析失败，请联系管理员。")
            return

        video_url, audio_url = streams
        if audio_url and not self.has_ffmpeg:
            yield event.plain_result("当前环境未安装ffmpeg，下载的视频将没有声音。")

        video_title = "bilibili_video"
        raw_data = info_data.get("data") if info_data and "data" in info_data else info_data
        if raw_data:
            video_title = raw_data.get("title", video_title)
        safe_title = re.sub(r'[\\/*?:"<>|]', "", video_title) or "bilibili_video"
        safe_title = safe_title[:50]
        base_path = self.temp_dir / safe_title

        temp_video_path = base_path.with_suffix(".video.mp4")
        temp_audio_path = base_path.with_suffix(".audio.m4s") if audio_url else None
        final_path = base_path.with_suffix(".mp4")

        yield event.plain_result("正在下载视频，请稍候...")

        if audio_url and temp_audio_path:
            video_task = asyncio.create_task(self._download_file(video_url, temp_video_path))
            audio_task = asyncio.create_task(self._download_file(audio_url, temp_audio_path))
            video_success, audio_success = await asyncio.gather(video_task, audio_task)
        else:
            video_success = await self._download_file(video_url, temp_video_path)
            audio_success = True
            temp_audio_path = None

        if not video_success or not temp_video_path.exists():
            yield event.plain_result("视频下载失败。")
            if temp_audio_path and temp_audio_path.exists():
                temp_audio_path.unlink(missing_ok=True)
            return

        if audio_url and temp_audio_path:
            if not audio_success:
                temp_video_path.unlink(missing_ok=True)
                yield event.plain_result("音频下载失败，已取消。")
                return

            merged = await self._merge_audio_video(temp_video_path, temp_audio_path, final_path)
            if not merged:
                temp_video_path.unlink(missing_ok=True)
                if temp_audio_path.exists():
                    temp_audio_path.unlink(missing_ok=True)
                yield event.plain_result("音视频合并失败，请检查ffmpeg。")
                return

            temp_video_path.unlink(missing_ok=True)
            temp_audio_path.unlink(missing_ok=True)
        else:
            final_path = temp_video_path

        try:
            video_node = Video.fromFileSystem(str(final_path))
            await event.send(event.chain_result([video_node]))
            logger.info(f"文件发送成功: {final_path}")
        except Exception as e:
            logger.warning(f"文件发送失败: {e}")
            yield event.plain_result("文件发送失败，请稍后重试。")

    async def _process_video_by_aid(self, event: AstrMessageEvent, aid: int):
        info_data = await self._fetch_api(f"/bilibili/video/avid/{aid}")
        if "error" in info_data:
            yield event.plain_result(f"获取视频信息失败: {info_data['error']}")
            return

        cover_url = self._extract_cover(info_data)
        info_text = self._format_video_info(info_data)

        if cover_url:
            chain = [
                Image.fromURL(cover_url),
                Plain(text=info_text)
            ]
            yield event.chain_result(chain)
        else:
            yield event.plain_result(info_text)

        download_data = await self._fetch_api(f"/bilibili/video/download/avid/{aid}")
        if "error" in download_data:
            yield event.plain_result(f"获取下载链接失败: {download_data['error']}")
            return

        streams = self._extract_best_streams(download_data, self.quality)
        if not streams:
            logger.warning(f"下载链接解析失败，原始响应: {download_data}")
            yield event.plain_result("下载链接解析失败，请联系管理员。")
            return

        video_url, audio_url = streams
        if audio_url and not self.has_ffmpeg:
            yield event.plain_result("当前环境未安装ffmpeg，下载的视频将没有声音。")

        video_title = "bilibili_video"
        raw_data = info_data.get("data") if info_data and "data" in info_data else info_data
        if raw_data:
            video_title = raw_data.get("title", video_title)
        safe_title = re.sub(r'[\\/*?:"<>|]', "", video_title) or "bilibili_video"
        safe_title = safe_title[:50]
        base_path = self.temp_dir / safe_title

        temp_video_path = base_path.with_suffix(".video.mp4")
        temp_audio_path = base_path.with_suffix(".audio.m4s") if audio_url else None
        final_path = base_path.with_suffix(".mp4")

        yield event.plain_result("正在下载视频，请稍候...")

        if audio_url and temp_audio_path:
            video_task = asyncio.create_task(self._download_file(video_url, temp_video_path))
            audio_task = asyncio.create_task(self._download_file(audio_url, temp_audio_path))
            video_success, audio_success = await asyncio.gather(video_task, audio_task)
        else:
            video_success = await self._download_file(video_url, temp_video_path)
            audio_success = True
            temp_audio_path = None

        if not video_success or not temp_video_path.exists():
            yield event.plain_result("视频下载失败。")
            if temp_audio_path and temp_audio_path.exists():
                temp_audio_path.unlink(missing_ok=True)
            return

        if audio_url and temp_audio_path:
            if not audio_success:
                temp_video_path.unlink(missing_ok=True)
                yield event.plain_result("音频下载失败，已取消。")
                return

            merged = await self._merge_audio_video(temp_video_path, temp_audio_path, final_path)
            if not merged:
                temp_video_path.unlink(missing_ok=True)
                if temp_audio_path.exists():
                    temp_audio_path.unlink(missing_ok=True)
                yield event.plain_result("音视频合并失败，请检查ffmpeg。")
                return

            temp_video_path.unlink(missing_ok=True)
            temp_audio_path.unlink(missing_ok=True)
        else:
            final_path = temp_video_path

        try:
            video_node = Video.fromFileSystem(str(final_path))
            await event.send(event.chain_result([video_node]))
            logger.info(f"文件发送成功: {final_path}")
        except Exception as e:
            logger.warning(f"文件发送失败: {e}")
            yield event.plain_result("文件发送失败，请稍后重试。")

    @filter.regex(r'(?i).*(bilibili\.com/video/|BV[a-zA-Z0-9]{10}|b23\.tv|av\d+).*')
    async def handle_bilibili_link(self, event: AstrMessageEvent):
        msg = event.message_str.strip()

        bvid = self._extract_bvid(msg)
        if bvid:
            if not bvid.startswith("BV"):
                resolved = await self._resolve_b23_shortlink(bvid)
                if not resolved:
                    yield event.plain_result("短链解析失败，请稍后重试或使用完整 BV 号。")
                    return
                bvid = resolved
            async for result in self._process_video_by_bvid(event, bvid):
                yield result
            return

        avid = self._extract_avid(msg)
        if avid:
            async for result in self._process_video_by_aid(event, avid):
                yield result
            return

    @filter.command("searchstop", priority=1)
    async def search_stop(self, event: AstrMessageEvent):
        session_key = event.unified_msg_origin
        if session_key in self.user_sessions:
            del self.user_sessions[session_key]
            yield event.plain_result("已退出搜索会话。")
        event.stop_event()

    @filter.command("search")
    async def search_entry(self, event: AstrMessageEvent, keyword: str = None):
        if keyword:
            async for result in self._do_search(event, keyword.strip()):
                yield result
            return

        self.user_sessions[event.unified_msg_origin] = {"state": "awaiting_keyword"}
        yield event.plain_result("告诉我你的关键词吧～")
        event.stop_event()

    async def _do_search(self, event: AstrMessageEvent, keyword: str):
        encoded_keyword = quote(keyword)
        data = await self._fetch_api(f"/bilibili/search/{encoded_keyword}",
                                     params={"page": 1, "page_size": self.search_result_count})
        if "error" in data:
            yield event.plain_result(f"搜索失败: {data['error']}")
            return

        videos = []
        if isinstance(data, dict):
            if "data" in data:
                videos = data["data"].get("result") or data["data"].get("list") or []
            elif "result" in data:
                videos = data["result"]
            elif "list" in data:
                videos = data["list"]
        elif isinstance(data, list):
            videos = data

        if not videos:
            yield event.plain_result(f"未找到关于 '{keyword}' 的视频。")
            return

        videos = videos[:self.search_result_count]

        if HAS_PILLOW:
            try:
                img_path = await self._generate_search_image(videos, keyword)
                if img_path:
                    yield event.image_result(str(img_path))
                else:
                    raise Exception("图片生成返回空路径")
            except Exception as e:
                logger.warning(f"生成搜索图片失败: {e}，回退到文字模式")
                img_path = None
        else:
            img_path = None
            logger.info("Pillow 未安装，使用纯文本搜索结果")

        if not img_path:
            result_lines = []
            for idx, v in enumerate(videos, 1):
                title = v.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", "")
                bvid = v.get("bvid") or v.get("bvid_str") or ""
                author = v.get("author") or v.get("owner", {}).get("name") or "未知"
                duration = v.get("duration") or "未知"
                play = v.get("play") or v.get("stat", {}).get("view") or "0"
                line = f"{idx}. {title}\nBV:{bvid} | UP:{author}\n时长:{duration} | 播放:{play}"
                result_lines.append(line)
            full_result = "\n\n".join(result_lines)
            yield event.plain_result(full_result)

        self.user_sessions[event.unified_msg_origin] = {
            "state": "awaiting_selection",
            "videos": videos,
            "timestamp": time.time()
        }

    async def _generate_search_image(self, videos: list, keyword: str) -> Optional[Path]:
        if not videos:
            return None

        COLS = 5
        WIDTH = 1920
        PADDING = 20
        GAP = 14
        n = len(videos)
        rows = (n + COLS - 1) // COLS

        card_w = (WIDTH - 2 * PADDING - (COLS - 1) * GAP) // COLS
        cover_h = int(card_w * 9 / 16)
        title_font_size = max(13, int(card_w * 0.04))
        info_font_size = max(10, int(card_w * 0.032))
        line_spacing = 4

        text_h = title_font_size * 2 + line_spacing * 2 + info_font_size + 10
        card_h = cover_h + text_h
        img_height = 2 * PADDING + rows * card_h + (rows - 1) * GAP

        if self.font_path:
            try:
                title_font = ImageFont.truetype(str(self.font_path), title_font_size)
                info_font = ImageFont.truetype(str(self.font_path), info_font_size)
            except Exception:
                title_font = ImageFont.load_default()
                info_font = ImageFont.load_default()
        else:
            title_font = ImageFont.load_default()
            info_font = ImageFont.load_default()

        async def download_cover(idx, url):
            if not url:
                return None
            try:
                save_path = self.temp_dir / f"cover_{idx}_{int(time.time()*1000)}.jpg"
                success = await self._download_file(url, save_path)
                return save_path if success else None
            except Exception:
                return None

        tasks = []
        for idx, v in enumerate(videos):
            pic = v.get("pic") or v.get("cover") or ""
            tasks.append(download_cover(idx, pic if pic.startswith("http") else "https:" + pic if pic else ""))

        cover_paths = await asyncio.gather(*tasks)

        img = PILImage.new("RGB", (WIDTH, img_height), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        for i, (video, cover_path) in enumerate(zip(videos, cover_paths)):
            row = i // COLS
            col = i % COLS
            x = PADDING + col * (card_w + GAP)
            y = PADDING + row * (card_h + GAP)

            if cover_path and cover_path.exists():
                try:
                    cover_img = PILImage.open(cover_path).convert("RGB")
                    cover_img = cover_img.resize((card_w, cover_h), PILImage.Resampling.LANCZOS)
                    img.paste(cover_img, (x, y))
                except Exception as e:
                    logger.warning(f"封面处理失败: {e}")
                    draw.rectangle([x, y, x + card_w, y + cover_h], fill=(200, 200, 200))
            else:
                draw.rectangle([x, y, x + card_w, y + cover_h], fill=(200, 200, 200))

            title = video.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", "")
            author = video.get("author") or video.get("owner", {}).get("name") or "未知"
            play = video.get("play") or video.get("stat", {}).get("view") or "0"
            duration = video.get("duration") or "未知"

            title_x = x + 4
            title_y = y + cover_h + 4
            max_title_width = card_w - 8
            draw_temp = ImageDraw.Draw(PILImage.new("RGB", (1, 1)))
            lines = []
            current_line = ""
            for char in title:
                test_line = current_line + char
                w = draw_temp.textlength(test_line, font=title_font)
                if w > max_title_width and current_line:
                    lines.append(current_line)
                    current_line = char
                else:
                    current_line = test_line
            if current_line:
                lines.append(current_line)
            if len(lines) > 2:
                lines = lines[:2]
                if len(lines[1]) >= 2:
                    lines[1] = lines[1][:-2] + "..."
                else:
                    lines[1] += "..."

            for j, line in enumerate(lines):
                self._draw_colored_text(draw, line, (title_x, title_y + j * (title_font_size + line_spacing)), title_font, keyword)

            info_y = y + card_h - info_font_size - 4
            meta = f"{author} · {play}播放 · {duration}"
            draw.text((title_x, info_y), meta, fill=(100, 100, 100), font=info_font)

        timestamp = int(time.time())
        img_filename = f"search_{re.sub(r'[\\/*?:\"<>|]', '_', keyword)}_{timestamp}.png"
        img_path = self.temp_dir / img_filename
        img.save(str(img_path), "PNG")
        logger.info(f"搜索图片已生成: {img_path}")
        return img_path

    def _draw_colored_text(self, draw, text: str, xy: tuple, font, keyword: str):
        if not keyword:
            draw.text(xy, text, fill=(0, 0, 0), font=font)
            return

        parts = re.split(f'({re.escape(keyword)})', text, flags=re.IGNORECASE)
        x, y = xy
        for part in parts:
            if not part:
                continue
            color = (255, 0, 0) if part.lower() == keyword.lower() else (0, 0, 0)
            draw.text((x, y), part, fill=color, font=font)
            x += draw.textlength(part, font=font)

    @filter.regex(r'.*')
    async def handle_user_reply(self, event: AstrMessageEvent):
        session_key = event.unified_msg_origin
        if session_key not in self.user_sessions:
            return

        session = self.user_sessions[session_key]
        msg = event.message_str.strip()

        if session["state"] == "awaiting_keyword":
            del self.user_sessions[session_key]
            async for result in self._do_search(event, msg):
                yield result
            return

        if session["state"] == "awaiting_selection":
            videos = session.get("videos", [])
            if not msg.isdigit():
                return

            idx = int(msg) - 1
            if idx < 0 or idx >= len(videos):
                yield event.plain_result("序号无效，请重新输入")
                return

            video = videos[idx]
            bvid = video.get("bvid") or video.get("bvid_str")
            if not bvid:
                yield event.plain_result("获取视频信息失败")
                return

            del self.user_sessions[session_key]
            async for result in self._process_video_by_bvid(event, bvid):
                yield result

    async def terminate(self):
        if hasattr(self, '_session_timeout_task') and self._session_timeout_task and not self._session_timeout_task.done():
            self._session_timeout_task.cancel()
        if self._clean_task and not self._clean_task.done():
            self._clean_task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("Hugging Face API Bilibili 插件已停止。")