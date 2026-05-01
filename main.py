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
from astrbot.api import logger
from astrbot.api.message_components import Video, Plain, Image

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com"
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


@register("astrbot_plugin_bilibili", "Jinhong270", "B站视频下载器", "1.1.3")
class Jinhong270BilibiliPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        config = context.get_config() or {}
        self.api_base_url = "https://jinhong270-api.hf.space"
        self.temp_retention = config.get("temp_file_retention", 3600)
        self.max_search_results = config.get("max_search_results", 20)
        self.proxy = config.get("proxy", "")
        self.user_sessions: Dict[str, dict] = {}
        self.has_ffmpeg = self._check_ffmpeg()
        self.font_path = self._find_chinese_font()

        cache_dir = config.get("cache_dir", "")
        if cache_dir:
            self.temp_dir = Path(cache_dir)
        else:
            self.temp_dir = Path(tempfile.gettempdir()) / "astrbot_bilibili_cache"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._clean_task = asyncio.create_task(self._clean_temp_files_loop())

    @staticmethod
    def _check_ffmpeg() -> bool:
        return shutil.which("ffmpeg") is not None

    @staticmethod
    def _find_chinese_font() -> Optional[Path]:
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

    async def _fetch_api(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.api_base_url}{endpoint}"
        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
                async with session.get(url, params=params) as resp:
                    resp.raise_for_status()
                    return await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"API请求失败 {endpoint}: {e}")
            return {"error": str(e)}

    async def _download_file(self, url: str, save_path: Path) -> bool:
        timeout = aiohttp.ClientTimeout(total=None)
        proxy_kwargs = {"proxy": self.proxy} if self.proxy else {}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
                async with session.get(url, **proxy_kwargs) as resp:
                    resp.raise_for_status()
                    async with aiofiles.open(save_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            await f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"下载失败: {e}")
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
            f"观看👀：{view}    弹幕📟：{danmaku}\n\n"
            f"原始链接：{link}\n"
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

    async def _resolve_b23_shortlink(self, short_code: str) -> Optional[str]:
        url = f"https://b23.tv/{short_code}"
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
                async with session.head(url, allow_redirects=False) as resp:
                    if resp.status in (301, 302, 307, 308):
                        location = resp.headers.get("Location", "")
                        if location:
                            bvid = self._extract_bvid(location)
                            if bvid:
                                return bvid
        except Exception as e:
            logger.error(f"解析短链失败 {short_code}: {e}")
        return None

    def _extract_best_streams(self, download_data: dict) -> Optional[Tuple[str, Optional[str]]]:
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
                video_url = None
                for v in videos:
                    u = v.get("baseUrl") or v.get("base_url")
                    if u:
                        video_url = u
                        break
                audio_url = None
                if isinstance(audios, list) and audios:
                    for a in audios:
                        u = a.get("baseUrl") or a.get("base_url")
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

        download_data = await self._fetch_api(f"/bilibili/video/download/{bvid}")
        if "error" in download_data:
            yield event.plain_result(f"获取下载链接失败: {download_data['error']}")
            return

        streams = self._extract_best_streams(download_data)
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

        success = await self._download_file(video_url, temp_video_path)
        if not success or not temp_video_path.exists():
            yield event.plain_result("视频下载失败。")
            return

        if audio_url and temp_audio_path:
            audio_success = await self._download_file(audio_url, temp_audio_path)
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
            yield event.plain_result(f"文件发送失败，可手动复制下载链接:\n{video_url}")

    @filter.regex(r'.*(bilibili\.com/video/|BV[a-zA-Z0-9]{10}|b23\.tv).*')
    async def handle_bilibili_link(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        bvid = self._extract_bvid(msg)
        if not bvid:
            return

        if not bvid.startswith("BV"):
            resolved = await self._resolve_b23_shortlink(bvid)
            if not resolved:
                yield event.plain_result("短链解析失败，请稍后重试或使用完整 BV 号。")
                return
            bvid = resolved

        async for result in self._process_video_by_bvid(event, bvid):
            yield result

    @filter.command("search")
    async def search_entry(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        if msg == "search" or msg == "/search":
            self.user_sessions[event.unified_msg_origin] = {"state": "awaiting_keyword"}
            yield event.plain_result("告诉我你的关键词吧～")
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
        data = await self._fetch_api(f"/bilibili/search/{encoded_keyword}",
                                     params={"page": 1, "page_size": self.max_search_results})
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

        videos = videos[:self.max_search_results]

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
            "videos": videos
        }

    async def _generate_search_image(self, videos: list, keyword: str) -> Optional[Path]:
        if not videos:
            return None

        WIDTH = 1280
        HEIGHT = 720
        PADDING = 16
        n = len(videos)
        ROW_HEIGHT = (HEIGHT - 2 * PADDING) / n
        COVER_WIDTH = int(ROW_HEIGHT * 1.6)
        COVER_HEIGHT = int(ROW_HEIGHT) - 8
        TEXT_X = PADDING + COVER_WIDTH + 12
        MAX_TITLE_WIDTH = WIDTH - TEXT_X - PADDING
        TITLE_FONT_SIZE = max(14, int(ROW_HEIGHT * 0.22))
        INFO_FONT_SIZE = max(11, int(ROW_HEIGHT * 0.16))

        if self.font_path:
            try:
                title_font = ImageFont.truetype(str(self.font_path), TITLE_FONT_SIZE)
                info_font = ImageFont.truetype(str(self.font_path), INFO_FONT_SIZE)
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

        img = PILImage.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        for i, (video, cover_path) in enumerate(zip(videos, cover_paths)):
            y_base = PADDING + i * ROW_HEIGHT

            if i > 0:
                draw.line([(PADDING, y_base), (WIDTH - PADDING, y_base)], fill=(230, 230, 230), width=1)

            if cover_path and cover_path.exists():
                try:
                    cover_img = PILImage.open(cover_path).convert("RGB")
                    cover_img = cover_img.resize((COVER_WIDTH, COVER_HEIGHT), PILImage.Resampling.LANCZOS)
                    img.paste(cover_img, (PADDING, int(y_base + (ROW_HEIGHT - COVER_HEIGHT) / 2)))
                except Exception as e:
                    logger.warning(f"封面处理失败: {e}")
            else:
                draw.rectangle(
                    [PADDING, int(y_base + (ROW_HEIGHT - COVER_HEIGHT) / 2),
                     PADDING + COVER_WIDTH, int(y_base + (ROW_HEIGHT - COVER_HEIGHT) / 2) + COVER_HEIGHT],
                    fill=(200, 200, 200)
                )

            title = video.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", "")
            author = video.get("author") or video.get("owner", {}).get("name") or "未知"
            duration = video.get("duration") or "未知"
            play = video.get("play") or video.get("stat", {}).get("view") or "0"

            line1, line2 = self._split_title_for_display(title, title_font, MAX_TITLE_WIDTH)
            self._draw_colored_text(draw, line1, (TEXT_X, int(y_base + 6)), title_font, keyword)
            if line2:
                self._draw_colored_text(draw, line2, (TEXT_X, int(y_base + 6 + TITLE_FONT_SIZE + 2)), title_font, keyword)

            meta = f"UP: {author} | 时长: {duration} | 播放: {play}"
            draw.text((TEXT_X, int(y_base + ROW_HEIGHT - INFO_FONT_SIZE - 6)), meta, fill=(100, 100, 100), font=info_font)

        timestamp = int(time.time())
        img_filename = f"search_{re.sub(r'[\\/*?:\"<>|]', '_', keyword)}_{timestamp}.png"
        img_path = self.temp_dir / img_filename
        img.save(str(img_path), "PNG")
        logger.info(f"搜索图片已生成: {img_path}")
        return img_path

    def _split_title_for_display(self, title: str, font, max_width: int) -> Tuple[str, str]:
        draw = ImageDraw.Draw(PILImage.new("RGB", (1, 1)))
        if draw.textlength(title, font=font) <= max_width:
            return title, ""

        cut = len(title) // 2
        for _ in range(len(title)):
            prefix = title[:cut]
            if draw.textlength(prefix, font=font) <= max_width:
                suffix = title[cut:]
                if draw.textlength(suffix, font=font) > max_width:
                    suffix = suffix[:max(1, int(max_width / (font.size or 12)))] + "..."
                return prefix, suffix
            cut -= 1
            if cut <= 0:
                break
        return title[: len(title)//2], title[len(title)//2:] + "..."

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

    @filter.regex(r'.*', priority=50)
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
            try:
                idx = int(msg) - 1
                if idx < 0 or idx >= len(videos):
                    yield event.plain_result("序号无效，请重新输入有效序号：")
                    return
                video = videos[idx]
                bvid = video.get("bvid") or video.get("bvid_str")
                if not bvid:
                    yield event.plain_result("无法获取BV号。")
                    return
            except ValueError:
                yield event.plain_result("请输入有效数字序号：")
                return

            del self.user_sessions[session_key]
            async for result in self._process_video_by_bvid(event, bvid):
                yield result

    async def terminate(self):
        if self._clean_task and not self._clean_task.done():
            self._clean_task.cancel()
        logger.info("Jinhong270 Bilibili 插件已停止。")
