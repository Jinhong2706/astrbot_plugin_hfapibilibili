import asyncio
import re
import os
import json
import aiohttp
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Video, Plain, Image
try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

API_BASE_URL = "https://jinhong270-api.hf.space"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com"
}

DEFAULT_CONFIG = {
    "quality": "720p",
    "cache_dir": "/tmp/astrbot_plugin_hfapibilibili"
}

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

@register("astrbot_plugin_hfapibilibili", "Jinhong270", "B站视频下载插件", "1.5.0")
class BilibiliPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        file_config = self.get_config_from_file()
        context_config = context.get_config() or {}
        config = {**context_config, **file_config}
        
        self.quality = config.get("quality", DEFAULT_CONFIG["quality"])
        cache_dir = config.get("cache_dir", DEFAULT_CONFIG["cache_dir"])
        
        self.api_base_url = API_BASE_URL
        
        if cache_dir:
            self.temp_dir = Path(cache_dir)
        else:
            self.temp_dir = Path(DEFAULT_CONFIG["cache_dir"])
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.user_sessions = {}
        self.font_path = self._find_chinese_font()

    def get_config_from_file(self):
        try:
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            config_dir = os.path.join(plugin_dir, "..", "..", "config")
            config_path = os.path.join(config_dir, "astrbot_plugin_hfapibilibili_config.json")
            config_path = os.path.abspath(config_path)
            
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8-sig") as f:
                    config = json.load(f)
                return config
            else:
                return {}
        except Exception:
            return {}

    def _find_chinese_font(self):
        for font in _CANDIDATE_FONTS:
            p = Path(font)
            if p.exists():
                logger.info(f"使用字体: {p}")
                return p
        logger.warning("未找到中文字体，搜索图片将使用默认字体（中文可能乱码）")
        return None

    async def _generate_search_image(self, videos: list, keyword: str):
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
                except Exception:
                    draw.rectangle([x, y, x + card_w, y + cover_h], fill=(200, 200, 200))
            else:
                draw.rectangle([x, y, x + card_w, y + cover_h], fill=(200, 200, 200))

            title = v.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", "")
            author = v.get("author") or "未知"
            play = v.get("play") or "0"
            duration = v.get("duration") or "未知"

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
        img_filename = f"search_{re.sub(r'[\\/*?:"<>|]', '_', keyword)}_{timestamp}.png"
        img_path = self.temp_dir / img_filename
        img.save(str(img_path), "PNG")
        return img_path

    async def _download_file(self, url: str, save_path: Path) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=None)) as resp:
                    resp.raise_for_status()
                    async with aiofiles.open(save_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(128 * 1024):
                            await f.write(chunk)
            return True
        except Exception:
            return False

    def _draw_colored_text(self, draw, text: str, xy: tuple, font, keyword: str):
        if not keyword:
            draw.text(xy, text, fill=(0, 0, 0), font=font)
            return

        parts = re.split(f"({re.escape(keyword)})", text, flags=re.IGNORECASE)
        x, y = xy
        for part in parts:
            if not part:
                continue
            color = (255, 0, 0) if part.lower() == keyword.lower() else (0, 0, 0)
            draw.text((x, y), part, fill=color, font=font)
            x += draw.textlength(part, font=font)

    async def _fetch_api(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.api_base_url}{endpoint}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    resp.raise_for_status()
                    return await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"API请求失败 {endpoint}: {e}")
            return {"error": str(e)}

    def _extract_bvid(self, text: str) -> Optional[str]:
        patterns = [
            r"(BV[a-zA-Z0-9]{10})",
            r"bvid=([a-zA-Z0-9]{12})",
            r"video/(BV[a-zA-Z0-9]{10})",
            r"bilibili\.com/video/(BV[a-zA-Z0-9]{10})",
            r"b23\.tv/([a-zA-Z0-9]+)"
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                return match.group(1)
        return None

    async def _resolve_b23_shortlink(self, short_code: str) -> Optional[str]:
        url = f"https://b23.tv/{short_code}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status in (301, 302, 307, 308):
                        location = resp.headers.get("Location", "")
                        if location:
                            bvid = self._extract_bvid(location)
                            if bvid:
                                return bvid
        except Exception:
            pass
        return None

    def _format_video_info(self, data: dict) -> str:
        if not data:
            return "获取信息失败"
        if "data" in data:
            data = data["data"]
        
        title = data.get("title") or "未知"
        bvid = data.get("bvid") or "未知"
        owner = data.get("owner", {})
        owner_name = owner.get("name") or "未知"
        stat = data.get("stat") or {}
        view = stat.get("view") or "0"
        like = stat.get("like") or "0"
        
        text = f"标题：{title}\nUP主：{owner_name}\n播放：{view}  点赞：{like}\nBV号：{bvid}"
        return text

    def _extract_cover(self, data: dict) -> Optional[str]:
        if not data:
            return None
        if "data" in data:
            data = data["data"]
        return data.get("pic") or None

    async def _process_video(self, event: AstrMessageEvent, bvid: str):
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
            yield event.plain_result("正在获取1080p视频链接（需要ffmpeg合并）...")
            download_data = await self._fetch_api(f"/bilibili/video/download/1080/{bvid}")
        else:
            yield event.plain_result("正在获取720p视频链接...")
            download_data = await self._fetch_api(f"/bilibili/video/download/{bvid}")

        if "error" in download_data:
            yield event.plain_result(f"获取下载链接失败: {download_data['error']}")
            return

        video_url = download_data.get("data", {}).get("durl", [{}])[0].get("url")
        if not video_url:
            yield event.plain_result("未找到视频下载链接")
            return

        yield event.plain_result(f"正在下载视频...")
        
        video_title = info_data.get("data", {}).get("title", "bilibili_video")
        safe_title = re.sub(r'[\/*?:"<>|]', "", video_title) or "bilibili_video"
        safe_title = safe_title[:50]
        final_path = self.temp_dir / f"{safe_title}.mp4"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=None)) as resp:
                    resp.raise_for_status()
                    async with aiofiles.open(final_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(128 * 1024):
                            await f.write(chunk)
            
            video_node = Video.fromFileSystem(str(final_path))
            yield event.chain_result([video_node])
            logger.info(f"文件发送成功: {final_path}")
        except Exception as e:
            logger.warning(f"文件发送失败: {e}")
            yield event.plain_result(f"下载失败: {e}")

    @filter.regex(r".*(bilibili\.com/video/|BV[a-zA-Z0-9]{10}|b23\.tv).*")
    async def handle_bilibili_link(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        bvid = self._extract_bvid(msg)
        if not bvid:
            return

        if not bvid.startswith("BV"):
            resolved = await self._resolve_b23_shortlink(bvid)
            if not resolved:
                yield event.plain_result("短链解析失败，请稍后重试或使用完整BV号。")
                return
            bvid = resolved

        async for result in self._process_video(event, bvid):
            yield result

    @filter.command("search")
    async def search_entry(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        if msg == "search" or msg == "/search":
            yield event.plain_result("告诉我你想搜索的关键词吧～")
            return

        parts = msg.split(maxsplit=1)
        if len(parts) < 2:
            yield event.plain_result("格式：search 关键词")
            return
        keyword = parts[1].strip()
        async for result in self._do_search(event, keyword):
            yield result

    async def _do_search(self, event: AstrMessageEvent, keyword: str):
        encoded_keyword = quote(keyword)
        data = await self._fetch_api(f"/bilibili/search/{encoded_keyword}")
        if "error" in data:
            yield event.plain_result(f"搜索失败: {data['error']}")
            return

        videos = []
        if isinstance(data, dict):
            if "data" in data:
                videos = data["data"].get("result") or []
            elif "result" in data:
                videos = data["result"]

        if not videos:
            yield event.plain_result(f"未找到关于 '{keyword}' 的视频。")
            return

        videos = videos[:10]
        result_lines = []
        for idx, v in enumerate(videos, 1):
            title = v.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", "")
            bvid = v.get("bvid") or ""
            author = v.get("author") or "未知"
            duration = v.get("duration") or "未知"
            play = v.get("play") or "0"
            line = f"{idx}. {title}\nBV:{bvid} | UP:{author}\n时长:{duration} | 播放:{play}"
            result_lines.append(line)
        full_result = "\n\n".join(result_lines)
        
        if HAS_PILLOW:
            try:
                img_path = await self._generate_search_image(videos, keyword)
                if img_path:
                    yield event.image_result(str(img_path))
                else:
                    raise Exception("图片生成返回空路径")
            except Exception as e:
                logger.warning(f"生成搜索图片失败: {e}，回退到文本模式")
                yield event.plain_result(full_result)
        else:
            logger.info("Pillow 未安装，使用纯文本搜索结果")
            yield event.plain_result(full_result)

        self.user_sessions[event.unified_msg_origin] = {
            "state": "awaiting_selection",
            "videos": videos
        }

    @filter.regex(r".*", priority=50)
    async def handle_user_reply(self, event: AstrMessageEvent):
        session_key = event.unified_msg_origin
        if session_key not in self.user_sessions:
            return

        session = self.user_sessions[session_key]
        msg = event.message_str.strip()

        if session["state"] == "awaiting_selection":
            videos = session.get("videos", [])
            try:
                idx = int(msg) - 1
                if idx < 0 or idx >= len(videos):
                    yield event.plain_result("序号无效，请重新输入有效序号：")
                    return
                video = videos[idx]
                bvid = video.get("bvid")
                if not bvid:
                    yield event.plain_result("无法获取BV号。")
                    return
            except ValueError:
                yield event.plain_result("请输入有效数字序号：")
                return

            del self.user_sessions[session_key]
            async for result in self._process_video(event, bvid):
                yield result
