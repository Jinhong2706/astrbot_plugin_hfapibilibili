from astrbot.api import AstrBotConfig

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com"
}

class PluginConfig:
    def __init__(self, config: AstrBotConfig):
        self.temp_retention = max(60, config.get("temp_file_retention", 600))
        self.search_result_count = max(1, min(config.get("search_result_count", 20), 50))
        self.proxy = config.get("proxy", "")
        self.quality = config.get("quality", "720p")
        self.cache_dir = config.get("cache_dir", "")
        self.api_base_url = config.get("api_base_url", "https://jinhong270-api.hf.space")
        self.custom_font_path = config.get("custom_font_path", "")
        self.enable_search_image = config.get("enable_search_image", True)
        self.aria2_path = config.get("aria2_path", "")