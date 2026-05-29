import re
import time
import shutil
from pathlib import Path
from typing import Optional
from astrbot.api import logger

def format_download_error(exc: BaseException) -> str:
    import aiohttp
    import asyncio
    if isinstance(exc, aiohttp.ClientResponseError):
        return f"HTTP {exc.status}: {exc.message}"
    if isinstance(exc, asyncio.TimeoutError):
        return "请求超时"
    text = str(exc).strip()
    return text or type(exc).__name__

def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def find_chinese_font() -> Optional[Path]:
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

def extract_bvid(text: str) -> Optional[str]:
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

def extract_avid(text: str) -> Optional[int]:
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

def format_video_info(data: dict) -> str:
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

def extract_cover(data: dict) -> Optional[str]:
    if not data:
        return None
    if "data" in data:
        data = data["data"]
    return data.get("pic") or data.get("Pic") or None

def select_video_stream(videos: list, quality: str) -> Optional[str]:
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

def extract_best_streams(download_data: dict, quality: str = "720p") -> Optional[tuple]:
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
            video_url = select_video_stream(videos, quality)
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