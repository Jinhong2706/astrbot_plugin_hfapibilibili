import asyncio
import shutil
from pathlib import Path

from astrbot.api import logger

def check_aria2(aria2_path: str = "") -> bool:
    if aria2_path:
        return shutil.which(aria2_path) is not None
    return shutil.which("aria2c") is not None

async def download_file(url: str, save_path: Path, proxy: str = None, max_retries: int = 3, aria2_path: str = "") -> bool:
    if not check_aria2(aria2_path):
        logger.error("aria2c 未找到，请安装 aria2 或在配置中指定 aria2_path")
        return False
    cmd = [
        aria2_path if aria2_path else "aria2c",
        "-x", "16",
        "-s", "16",
        "-k", "1M",
        "--out", save_path.name,
        "--dir", str(save_path.parent),
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "--referer", "https://www.bilibili.com",
        "--header", "Origin: https://www.bilibili.com",
        url
    ]
    if proxy:
        cmd.extend(["--all-proxy", proxy])
    for attempt in range(max_retries):
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info(f"下载成功: {save_path}")
                return True
            logger.warning(f"aria2 下载失败 (尝试 {attempt+1}/{max_retries}): {stderr.decode()}")
            if save_path.exists():
                save_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"aria2 异常 (尝试 {attempt+1}/{max_retries}): {e}")
            if save_path.exists():
                save_path.unlink(missing_ok=True)
        await asyncio.sleep(1)
    return False
