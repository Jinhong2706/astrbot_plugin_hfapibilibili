import aiohttp
from urllib.parse import quote

from astrbot.api import logger

class BiliAPI:
    def __init__(self, session: aiohttp.ClientSession, base_url: str):
        self.session = session
        self.base_url = base_url.rstrip('/')

    async def _fetch(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        try:
            async with self.session.get(url, params=params,
                                        timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"API请求失败 {endpoint}: {e}")
            return {"error": str(e)}

    async def get_hot(self, ps: int = 50) -> dict:
        return await self._fetch("/bilibili/hot", params={"ps": ps})

    async def get_video_info(self, bvid: str) -> dict:
        return await self._fetch(f"/bilibili/video/{bvid}")

    async def get_video_info_by_aid(self, aid: int) -> dict:
        return await self._fetch(f"/bilibili/video/aid/{aid}")

    async def get_download_urls(self, bvid: str, quality: str = "720p") -> dict:
        if quality == "1080p":
            endpoint = f"/bilibili/video/download/1080/{bvid}"
        else:
            endpoint = f"/bilibili/video/download/{bvid}"
        return await self._fetch(endpoint)

    async def get_download_urls_by_aid(self, aid: int, quality: str = "720p") -> dict:
        if quality == "1080p":
            endpoint = f"/bilibili/video/download/aid/1080/{aid}"
        else:
            endpoint = f"/bilibili/video/download/aid/{aid}"
        return await self._fetch(endpoint)

    async def search(self, keyword: str, page: int = 1, page_size: int = 20) -> dict:
        encoded = quote(keyword)
        return await self._fetch(f"/bilibili/search/{encoded}",
                                 params={"page": page, "page_size": page_size})
