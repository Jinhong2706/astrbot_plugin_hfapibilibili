import aiohttp
import asyncio
import tempfile
import time
import re
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain

from .config import PluginConfig, HEADERS
from .utils.helpers import (
    check_ffmpeg, find_chinese_font, extract_bvid, extract_avid,
    format_video_info, extract_cover
)
from .core.bilibili_api import BiliAPI
from .core.session_manager import SessionManager
from .core.video_processor import download_and_process_video
from .assets.image_generator import generate_search_image

try:
    from PIL import Image as PILImage
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

@register("astrbot_plugin_hfapibilibili", "Jinhong270", "B站视频下载器", "1.8.0")
class Jinhong270BilibiliPlugin(Star):
    def __init__(self, context: Context, config):
        super().__init__(context)
        self.plugin_config = PluginConfig(config)
        self.has_ffmpeg = check_ffmpeg()

        custom_font = self.plugin_config.custom_font_path
        if custom_font and Path(custom_font).exists():
            self.font_path = Path(custom_font)
            logger.info(f"使用自定义字体: {self.font_path}")
        else:
            self.font_path = find_chinese_font()

        self.enable_search_image = self.plugin_config.enable_search_image
        self.session_mgr = SessionManager()

        if self.plugin_config.cache_dir:
            self.temp_dir = Path(self.plugin_config.cache_dir)
        else:
            self.temp_dir = Path(tempfile.gettempdir()) / "astrbot_plugin_hfapibilibili"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self._session = aiohttp.ClientSession(headers=HEADERS, timeout=aiohttp.ClientTimeout(total=300))
        self.bili_api = BiliAPI(self._session, self.plugin_config.api_base_url)

        self._clean_task = asyncio.create_task(self._clean_temp_files_loop())
        self._session_timeout_task = asyncio.create_task(self._check_session_timeout())

    async def _clean_temp_files_loop(self):
        try:
            while True:
                now = time.time()
                for f in self.temp_dir.iterdir():
                    if f.is_file() and (now - f.stat().st_mtime) > self.plugin_config.temp_retention:
                        f.unlink(missing_ok=True)
                await asyncio.sleep(600)
        except asyncio.CancelledError:
            pass

    async def _check_session_timeout(self):
        try:
            while True:
                await asyncio.sleep(30)
                self.session_mgr.cleanup_expired(timeout_seconds=180)
        except asyncio.CancelledError:
            pass

    async def _resolve_b23_shortlink(self, short_code: str) -> str:
        url = f"https://b23.tv/{short_code}"
        try:
            async with self._session.head(url, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status in (301, 302, 307, 308):
                    location = resp.headers.get("Location", "")
                    if location:
                        bvid = extract_bvid(location)
                        if bvid:
                            return bvid
        except Exception as e:
            logger.error(f"解析短链失败 {short_code}: {e}")
        return ""

    @filter.regex(r'(?i).*(bilibili\.com/video/|BV[a-zA-Z0-9]{10}|b23\.tv|av\d+).*')
    async def handle_bilibili_link(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        bvid = extract_bvid(msg)
        if bvid:
            if not bvid.startswith("BV"):
                resolved = await self._resolve_b23_shortlink(bvid)
                if not resolved:
                    yield event.plain_result("短链解析失败，请稍后重试或使用完整 BV 号。")
                    return
                bvid = resolved
            async for result in download_and_process_video(
                event, bvid, self.bili_api, self._session, self.plugin_config.proxy,
                self.plugin_config.quality, self.has_ffmpeg, self.temp_dir
            ):
                yield result
            return

        avid = extract_avid(msg)
        if avid:
            info_data = await self.bili_api.get_video_info_by_aid(avid)
            if "error" in info_data:
                yield event.plain_result(f"获取视频信息失败: {info_data['error']}")
                return
            bvid = info_data.get("data", {}).get("bvid")
            if bvid:
                async for result in download_and_process_video(
                    event, bvid, self.bili_api, self._session, self.plugin_config.proxy,
                    self.plugin_config.quality, self.has_ffmpeg, self.temp_dir
                ):
                    yield result
            else:
                yield event.plain_result("无法从 AV 号获取 BV 号。")

    @filter.regex(r'^\s*停止点播\s*$', priority=1)
    async def search_stop(self, event: AstrMessageEvent):
        session_key = event.unified_msg_origin
        if self.session_mgr.get(session_key):
            self.session_mgr.delete(session_key)
            yield event.plain_result("已退出点播会话。")
        event.stop_event()

    @filter.regex(r'^(?:b站点播|B站点播)(?:\s+(.+))?$', priority=2)
    async def on_bili_demand(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        m = re.match(r'^(?:b站点播|B站点播)(?:\s+(.+))?$', msg)
        keyword = m.group(1) if m and m.group(1) else None
        if keyword:
            async for result in self._do_search(event, keyword.strip()):
                yield result
        else:
            self.session_mgr.set(event.unified_msg_origin, {"state": "awaiting_keyword"})
            yield event.plain_result("告诉我你想点播的关键词吧～")
        event.stop_event()

    async def _do_search(self, event: AstrMessageEvent, keyword: str):
        data = await self.bili_api.search(keyword, page=1, page_size=self.plugin_config.search_result_count)
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

        videos = videos[:self.plugin_config.search_result_count]

        img_path = None
        if self.enable_search_image and HAS_PILLOW:
            try:
                img_path = await generate_search_image(
                    videos, keyword, self.temp_dir, self.font_path,
                    self._session, self.plugin_config.proxy
                )
            except Exception as e:
                logger.warning(f"生成搜索图片失败: {e}")

        if img_path:
            yield event.image_result(str(img_path))
        else:
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

        self.session_mgr.set(event.unified_msg_origin, {
            "state": "awaiting_selection",
            "videos": videos,
            "timestamp": time.time()
        })

    @filter.regex(r'.*', priority=100)
    async def handle_user_reply(self, event: AstrMessageEvent):
        session_key = event.unified_msg_origin
        session = self.session_mgr.get(session_key)
        if not session:
            return
        msg = event.message_str.strip()
        if session["state"] == "awaiting_keyword":
            self.session_mgr.delete(session_key)
            async for result in self._do_search(event, msg):
                yield result
            return
        if session["state"] == "awaiting_selection":
            if not msg.isdigit():
                return
            idx = int(msg) - 1
            videos = session.get("videos", [])
            if idx < 0 or idx >= len(videos):
                yield event.plain_result("序号无效，请重新输入")
                return
            video = videos[idx]
            bvid = video.get("bvid") or video.get("bvid_str")
            if not bvid:
                yield event.plain_result("获取视频信息失败")
                return
            self.session_mgr.delete(session_key)
            async for result in download_and_process_video(
                event, bvid, self.bili_api, self._session, self.plugin_config.proxy,
                self.plugin_config.quality, self.has_ffmpeg, self.temp_dir
            ):
                yield result

    async def terminate(self):
        if self._session_timeout_task and not self._session_timeout_task.done():
            self._session_timeout_task.cancel()
        if self._clean_task and not self._clean_task.done():
            self._clean_task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("astrbot_plugin_hfapibilibili插件已停止。")