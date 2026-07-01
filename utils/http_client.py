import asyncio
import shutil
from pathlib import Path

from astrbot.api import logger

from ..config import HEADERS

def check_aria2(aria2_path: str = "") -> bool:
    if aria2_path:
        return shutil.which(aria2_path) is not None
    return shutil.which("aria2c") is not None

async def direct_download(session, url: str, save_path: Path, proxy: str = None) -> bool:
    headers = HEADERS.copy()
    if proxy:
        headers["Proxy"] = proxy
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=600)) as resp:
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    f.write(chunk)
        logger.info(f"普通下载成功: {save_path}")
        return True
    except Exception as e:
        logger.error(f"普通下载失败: {e}")
        if save_path.exists():
            save_path.unlink(missing_ok=True)
        return False

async def download_file(url: str, save_path: Path, session=None, proxy: str = None,
                        max_retries: int = 3, aria2_path: str = "",
                        download_method: str = "aria2c") -> bool:
    if download_method == "direct":
        logger.info("使用普通下载方式。")
        if session is None:
            import aiohttp
            async with aiohttp.ClientSession(headers=HEADERS) as s:
                return await direct_download(s, url, save_path, proxy)
        return await direct_download(session, url, save_path, proxy)

    if check_aria2(aria2_path):
        cmd = [
            aria2_path if aria2_path else "aria2c",
            "-x", "16",
            "-s", "16",
            "-k", "1M",
            "--out", save_path.name,
            "--dir", str(save_path.parent),
            "--user-agent", HEADERS["User-Agent"],
            "--referer", HEADERS["Referer"],
            "--header", "Origin: " + HEADERS["Origin"],
            url
        ]
        if proxy:
            cmd.extend(["--all-proxy", proxy])
        for attempt in range(max_retries):
            try:
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr = await proc.communicate()
                if proc.returncode == 0:
                    logger.info(f"aria2 下载成功: {save_path}")
                    return True
                logger.warning(f"aria2 下载失败 (尝试 {attempt+1}/{max_retries}): {stderr.decode()}")
                if save_path.exists():
                    save_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"aria2 异常 (尝试 {attempt+1}/{max_retries}): {e}")
                if save_path.exists():
                    save_path.unlink(missing_ok=True)
            await asyncio.sleep(1)
        logger.warning("aria2 下载失败，降级为普通下载。")
    else:
        logger.warning("aria2 未找到，降级为普通下载。")

    if session is None:
        import aiohttp
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            return await direct_download(s, url, save_path, proxy)
    return await direct_download(session, url, save_path, proxy)
