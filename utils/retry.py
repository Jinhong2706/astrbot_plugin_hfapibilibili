import asyncio
from astrbot.api import logger

async def with_retry(func, *args, max_retries=5, delay=5, label="", **kwargs):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"{label} 第 {attempt}/{max_retries} 次失败，{delay}s 后重试: {e}")
                await asyncio.sleep(delay)
    logger.error(f"{label} 重试 {max_retries} 次全部失败: {last_error}")
    raise last_error
