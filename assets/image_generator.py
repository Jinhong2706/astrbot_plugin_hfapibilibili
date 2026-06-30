import re
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Optional

from PIL import Image, ImageDraw, ImageFont
from astrbot.api import logger

from ..utils.http_client import download_file

async def generate_search_image(videos: List[Dict], keyword: str, temp_dir: Path,
                                font_path: Optional[Path], proxy: str) -> Optional[Path]:
    if not videos:
        return None

    COLS = 5
    WIDTH = 1920
    PADDING = 20
    GAP = 14
    n = len(videos)
    rows = (n + COLS - 1) // COLS

    card_w = (WIDTH - 2 * PADDING - (COLS - 1) * GAP) // COLS
    cover_h = int(card_w * 9 / 16)
    title_font_size = max(13, int(card_w * 0.04))
    info_font_size = max(10, int(card_w * 0.032))
    line_spacing = 4

    text_h = title_font_size * 2 + line_spacing * 2 + info_font_size + 10
    card_h = cover_h + text_h
    img_height = 2 * PADDING + rows * card_h + (rows - 1) * GAP

    if font_path:
        try:
            title_font = ImageFont.truetype(str(font_path), title_font_size)
            info_font = ImageFont.truetype(str(font_path), info_font_size)
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
            save_path = temp_dir / f"cover_{idx}_{int(time.time()*1000)}.jpg"
            success = await download_file(url, save_path, proxy=proxy)
            return save_path if success else None
        except Exception:
            return None

    tasks = []
    for idx, v in enumerate(videos):
        pic = v.get("pic") or v.get("cover") or ""
        if pic and not pic.startswith("http"):
            pic = "https:" + pic
        tasks.append(download_cover(idx, pic))
    cover_paths = await asyncio.gather(*tasks)

    img = Image.new("RGB", (WIDTH, img_height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    for i, (video, cover_path) in enumerate(zip(videos, cover_paths)):
        row = i // COLS
        col = i % COLS
        x = PADDING + col * (card_w + GAP)
        y = PADDING + row * (card_h + GAP)

        if cover_path and cover_path.exists():
            try:
                cover_img = Image.open(cover_path).convert("RGB")
                cover_img = cover_img.resize((card_w, cover_h), Image.Resampling.LANCZOS)
                img.paste(cover_img, (x, y))
            except Exception as e:
                logger.warning(f"封面处理失败: {e}")
                draw.rectangle([x, y, x + card_w, y + cover_h], fill=(200, 200, 200))
        else:
            draw.rectangle([x, y, x + card_w, y + cover_h], fill=(200, 200, 200))

        title = video.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", "")
        author = video.get("author") or video.get("owner", {}).get("name") or "未知"
        play = video.get("play") or video.get("stat", {}).get("view") or "0"
        duration = video.get("duration") or "未知"

        title_x = x + 4
        title_y = y + cover_h + 4
        max_title_width = card_w - 8
        draw_temp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        lines = []
        current_line = ""
        for char in title:
            test_line = current_line + char
            w = draw_temp.textlength(test_line, font=title_font)
            if w > max_title_width and current_line:
                lines.append(current_line)
                current_line = char
            else:
                current_line = test_line
        if current_line:
            lines.append(current_line)
        if len(lines) > 2:
            lines = lines[:2]
            if len(lines[1]) >= 2:
                lines[1] = lines[1][:-2] + "..."
            else:
                lines[1] += "..."

        def draw_colored_text(d, text, xy, font, kw):
            if not kw:
                d.text(xy, text, fill=(0, 0, 0), font=font)
                return
            parts = re.split(f'({re.escape(kw)})', text, flags=re.IGNORECASE)
            x, y = xy
            for part in parts:
                if not part:
                    continue
                color = (255, 0, 0) if part.lower() == kw.lower() else (0, 0, 0)
                d.text((x, y), part, fill=color, font=font)
                x += d.textlength(part, font=font)

        for j, line in enumerate(lines):
            draw_colored_text(draw, line, (title_x, title_y + j * (title_font_size + line_spacing)), title_font, keyword)

        info_y = y + card_h - info_font_size - 4
        meta = f"{author} · {play}播放 · {duration}"
        draw.text((title_x, info_y), meta, fill=(100, 100, 100), font=info_font)

    timestamp = int(time.time())
    img_filename = f"search_{re.sub(r'[\\/*?:\"<>|]', '_', keyword)}_{timestamp}.png"
    img_path = temp_dir / img_filename
    img.save(str(img_path), "PNG")
    logger.info(f"搜索图片已生成: {img_path}")
    return img_path