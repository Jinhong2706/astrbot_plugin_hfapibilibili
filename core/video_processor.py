import asyncio
import re
from pathlib import Path

from astrbot.api import logger
from astrbot.api.message_components import Video, File

from ..utils.helpers import extract_best_streams, format_video_info, extract_cover
from ..utils.http_client import download_file

async def merge_audio_video(video_path: Path, audio_path: Path, output_path: Path, has_ffmpeg: bool) -> bool:
    if not has_ffmpeg:
        return False
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path), "-c", "copy", str(output_path)]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False

async def download_and_process_video(event, bvid: str, bili_api, session, proxy, quality,
                                     has_ffmpeg, temp_dir, aria2_path, download_method):
    if quality == "1080p" and not has_ffmpeg:
        yield event.plain_result("当前环境未安装 ffmpeg，1080p 画质下载的视频将没有声音。建议安装 ffmpeg 以获得完整体验。")
    info_data = await bili_api.get_video_info(bvid)
    if "error" in info_data:
        return
    cover_url = extract_cover(info_data)
    info_text = format_video_info(info_data)
    if cover_url:
        from astrbot.api.message_components import Image, Plain
        yield event.chain_result([Image.fromURL(cover_url), Plain(text=info_text)])
    else:
        yield event.plain_result(info_text)
    download_data = await bili_api.get_download_urls(bvid, quality)
    if "error" in download_data:
        return
    streams = extract_best_streams(download_data, quality)
    if not streams:
        return
    video_url, audio_url = streams
    raw_data = info_data.get("data") if info_data and "data" in info_data else info_data
    video_title = raw_data.get("title", "bilibili_video") if raw_data else "bilibili_video"
    safe_title = re.sub(r'[\\/*?:"<>|]', "", video_title) or "bilibili_video"
    safe_title = safe_title[:50]
    base_path = temp_dir / safe_title
    temp_video_path = base_path.with_suffix(".video.mp4")
    temp_audio_path = base_path.with_suffix(".audio.m4s") if audio_url else None
    final_path = base_path.with_suffix(".mp4")
    yield event.plain_result("正在下载视频，请稍候...")
    if audio_url and temp_audio_path:
        video_task = asyncio.create_task(download_file(video_url, temp_video_path, session=session, proxy=proxy, aria2_path=aria2_path, download_method=download_method))
        audio_task = asyncio.create_task(download_file(audio_url, temp_audio_path, session=session, proxy=proxy, aria2_path=aria2_path, download_method=download_method))
        video_success, audio_success = await asyncio.gather(video_task, audio_task)
    else:
        video_success = await download_file(video_url, temp_video_path, session=session, proxy=proxy, aria2_path=aria2_path, download_method=download_method)
        audio_success = True
        temp_audio_path = None
    if not video_success or not temp_video_path.exists():
        if temp_audio_path and temp_audio_path.exists():
            temp_audio_path.unlink(missing_ok=True)
        return
    if audio_url and temp_audio_path and not audio_success:
        temp_video_path.unlink(missing_ok=True)
        return
    if audio_url and not has_ffmpeg and quality == "1080p":
        video_node = Video.fromFileSystem(str(temp_video_path))
        audio_node = File(file=str(temp_audio_path), name=f"{safe_title}_音频.m4s")
        yield event.chain_result([video_node])
        yield event.chain_result([audio_node])
        return
    if audio_url:
        merged = await merge_audio_video(temp_video_path, temp_audio_path, final_path, has_ffmpeg)
        if not merged or not final_path.exists() or final_path.stat().st_size == 0:
            yield event.plain_result("音视频合并失败，请检查 ffmpeg 是否正常。")
            return
        temp_video_path.unlink(missing_ok=True)
        temp_audio_path.unlink(missing_ok=True)
        final_video = final_path
    else:
        final_video = temp_video_path
    try:
        yield event.chain_result([Video.fromFileSystem(str(final_video))])
    except Exception:
        pass
