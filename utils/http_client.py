import asyncio
import aiohttp
import shutil
from pathlib import Path

from astrbot.api import logger
from ..config import HEADERS
from .retry import with_retry

def check_aria2(aria2_path: str = "") -> bool:
    if aria2_path:
        return shutil.which(aria2_path) is not None
    return shutil.which("aria2c") is not None

async def direct_download(session, url: str, save_path: Path, proxy: str = None) -> bool:
    async def _do():
        async with session.get(
            url, proxy=proxy, headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=600)
        ) as resp:
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    f.write(chunk)

    try:
        await with_retry(_do, max_retries=5, delay=5, label=f"下载 {save_path.name}")
        logger.info(f"下载成功: {save_path}")
        return True
    except Exception as e:
        logger.error(f"下载失败: {e}")
        if save_path.exists():
            save_path.unlink(missing_ok=True)
        return False

async def aria2_download(url: str, save_path: Path, aria2_path: str, proxy: str = None) -> bool:
    cmd = [
        aria2_path if aria2_path else "aria2c",
        "-x", "16", "-s", "16", "-k", "1M",
        "--out", save_path.name,
        "--dir", str(save_path.parent),
        "--user-agent", HEADERS["User-Agent"],
        "--referer", HEADERS["Referer"],
        "--header", "Origin: " + HEADERS["Origin"],
        url
    ]
    if proxy:
        cmd.extend(["--all-proxy", proxy])

    async def _do():
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            msg = stderr.decode() if stderr else f"aria2c exit {proc.returncode}"
            raise RuntimeError(msg)

    try:
        await with_retry(_do, max_retries=5, delay=5, label=f"aria2 {save_path.name}")
        logger.info(f"aria2 下载成功: {save_path}")
        return True
    except Exception as e:
        logger.error(f"aria2 下载失败: {e}")
        if save_path.exists():
            save_path.unlink(missing_ok=True)
        return False

async def download_file(url: str, save_path: Path, session=None, proxy: str = None,
                        aria2_path: str = "", download_method: str = "aria2c") -> bool:

    if download_method == "direct":
        if session is None:
            async with aiohttp.ClientSession(headers=HEADERS) as s:
                return await direct_download(s, url, save_path, proxy)
        return await direct_download(session, url, save_path, proxy)

    if check_aria2(aria2_path):
        result = await aria2_download(url, save_path, aria2_path, proxy)
        if result:
            return True
        logger.warning("aria2 下载失败，降级为普通下载。")
    else:
        logger.warning("aria2 未找到，降级为普通下载。")

    if session is None:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            return await direct_download(s, url, save_path, proxy)
    return await direct_download(session, url, save_path, proxy)
