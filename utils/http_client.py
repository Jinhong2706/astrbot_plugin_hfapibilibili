import aiohttp
import asyncio
from pathlib import Path
from typing import Optional

from astrbot.api import logger
from .helpers import format_download_error

class RangeDownloader:
    def __init__(self, session: aiohttp.ClientSession, url: str, save_path: Path,
                 file_size: int, headers: dict = None, proxy: str = None):
        self.session = session
        self.url = url
        self.save_path = save_path
        self.file_size = file_size
        self.headers = headers or {}
        self.proxy = proxy
        self.chunk_size = 4 * 1024 * 1024
        self.max_concurrent = 64
        self.max_retries_per_chunk = 2

    async def _download_chunk_with_retry(self, idx: int, chunk_start: int, chunk_end: int, write_lock: asyncio.Lock) -> bool:
        range_header = {"Range": f"bytes={chunk_start}-{chunk_end}"}
        req_headers = {**self.headers, **range_header}
        proxy_kwargs = {"proxy": self.proxy} if self.proxy else {}
        for attempt in range(self.max_retries_per_chunk):
            try:
                timeout = aiohttp.ClientTimeout(total=300)
                async with self.session.get(self.url, headers=req_headers, timeout=timeout, **proxy_kwargs) as resp:
                    if resp.status not in (200, 206):
                        raise Exception(f"HTTP {resp.status}")
                    data = await resp.read()
                    expected = chunk_end - chunk_start + 1
                    if len(data) != expected:
                        raise Exception(f"分片长度不符: {len(data)} vs {expected}")
                    async with write_lock:
                        with open(self.save_path, "r+b") as f:
                            f.seek(chunk_start)
                            f.write(data)
                return True
            except Exception as e:
                error_msg = format_download_error(e)
                if attempt < self.max_retries_per_chunk - 1:
                    logger.warning(f"分片 {idx} 第 {attempt+1} 次失败: {error_msg}，重试")
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    logger.warning(f"分片 {idx} 最终失败: {error_msg}")
                    return False
        return False

    async def run(self) -> bool:
        num_chunks = (self.file_size + self.chunk_size - 1) // self.chunk_size
        if num_chunks <= 1:
            return False
        logger.info(f"启用 Range 并发下载: {self.save_path.name}，大小 {self.file_size//1024//1024} MB，分 {num_chunks} 片，并发 {self.max_concurrent}")
        self.save_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.save_path, "wb") as f:
                f.truncate(self.file_size)
        except Exception as e:
            logger.warning(f"预分配文件失败: {e}")
            return False

        semaphore = asyncio.Semaphore(self.max_concurrent)
        write_lock = asyncio.Lock()
        failed_chunks = []

        async def bounded_download(idx: int, start: int, end: int):
            async with semaphore:
                success = await self._download_chunk_with_retry(idx, start, end, write_lock)
                if not success:
                    failed_chunks.append(idx)

        tasks = []
        for i in range(num_chunks):
            start = i * self.chunk_size
            end = min(start + self.chunk_size - 1, self.file_size - 1)
            tasks.append(bounded_download(i, start, end))
        await asyncio.gather(*tasks)

        if failed_chunks:
            logger.warning(f"共有 {len(failed_chunks)} 个分片失败，降级使用普通下载")
            self.save_path.unlink(missing_ok=True)
            return False

        if self.save_path.stat().st_size != self.file_size:
            logger.warning("Range 下载大小校验失败")
            self.save_path.unlink(missing_ok=True)
            return False

        logger.info(f"Range 下载成功: {self.save_path}")
        return True

async def get_file_size(session: aiohttp.ClientSession, url: str, headers: dict = None, proxy: str = None) -> int:
    proxy_kwargs = {"proxy": proxy} if proxy else {}
    try:
        async with session.head(url, headers=headers or {}, timeout=10, **proxy_kwargs) as resp:
            if resp.status == 200:
                cl = resp.headers.get("Content-Length")
                if cl:
                    return int(cl)
        range_headers = {**(headers or {}), "Range": "bytes=0-0"}
        async with session.get(url, headers=range_headers, timeout=10, **proxy_kwargs) as resp:
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

async def range_download_file(session: aiohttp.ClientSession, url: str, save_path: Path,
                              file_size: int, headers: dict = None, proxy: str = None) -> bool:
    downloader = RangeDownloader(session, url, save_path, file_size, headers, proxy)
    return await downloader.run()

async def download_file(session: aiohttp.ClientSession, url: str, save_path: Path,
                        max_retries=3, proxy: str = None) -> bool:
    proxy_kwargs = {"proxy": proxy} if proxy else {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com",
        "Origin": "https://www.bilibili.com"
    }

    file_size = await get_file_size(session, url, headers, proxy)
    use_range = file_size > 100 * 1024 * 1024

    if file_size > 0:
        dynamic_timeout = min(1800, 300 + (file_size // (10 * 1024 * 1024)) * 10)
    else:
        dynamic_timeout = 600

    total_timeout = aiohttp.ClientTimeout(total=dynamic_timeout, connect=10, sock_read=dynamic_timeout)

    for attempt in range(max_retries):
        if attempt == 0 and use_range:
            logger.info(f"尝试 Range 下载 (size={file_size//1024//1024}MB): {url}")
            success = await range_download_file(session, url, save_path, file_size, headers, proxy)
            if success:
                return True
            logger.warning("Range 下载失败，降级为普通下载")

        try:
            async with session.get(url, headers=headers, timeout=total_timeout, **proxy_kwargs) as resp:
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
            error_msg = format_download_error(e)
            logger.warning(f"下载失败 (第 {attempt+1}/{max_retries} 次): {error_msg}")
            if save_path.exists():
                save_path.unlink(missing_ok=True)
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (2 ** attempt))
            else:
                logger.error(f"下载最终失败: {url}")

    return False