<div align="center">

# 🎬 astrbot_plugin_hfapibilibili

**AstrBot B 站视频插件**
在群聊中解析 B 站链接 / BV / AV / b23 短链，支持点播搜索并下载高清视频（支持 Dash 合并）。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot->=4.16-green.svg)](https://github.com/Soulter/AstrBot)
[![OneBot v11](https://img.shields.io/badge/OneBot-v11-black)](https://onebot.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

---

## 简介

本插件为 AstrBot 提供 B 站视频解析与点播功能，新增 **热门视频** 快速查看。

- 自动解析并下载 B 站视频（支持 BV、AV、bilibili 链接与 b23 短链）。
- 支持按关键词点播搜索，返回图文卡片（需 Pillow 与中文字体）或纯文本结果。
- **新增**：发送 `b站热门` 或 `B站热门` 快速浏览当前热门视频（结果以图片呈现，无关键词标红）。
- 支持 Dash 分离流的音视频合并（需要系统已安装 ffmpeg）。
- 使用 **aria2** 实现多线程高速下载，大幅提升下载速度。
- 支持通过代理下载（配置项 proxy）。
- **新增** 下载方式选择：可选 `aria2c`（多线程）或 `direct`（普通下载）。若选择 `aria2c` 但未安装 aria2，将自动降级为普通下载。

---

## 快速安装

1. 将本仓库放入 AstrBot 的插件目录（例如：data/plugins/），重启或重载插件；或在 AstrBot 插件市场安装 `astrbot_plugin_hfapibilibili`。
2. 安装 Python 依赖：

```bash
pip install -r requirements.txt
```

3. **（可选）安装 aria2** 可获得多线程下载加速：
   - Linux/macOS：`sudo apt install aria2` 或 `brew install aria2`
   - Windows：下载 aria2 并将 `aria2c.exe` 所在目录加入 PATH，或在配置中指定 `aria2_path`
4. （可选）安装 ffmpeg 与中文字体以获得完整体验。

---

## 使用说明

- 直接发送视频链接或编号，机器人会自动解析并开始下载：
  - 完整链接：`https://www.bilibili.com/video/BV1U47T6UE1t`
  - 纯 BV：`BV1U47T6UE1t`
  - AV 号：`av116339171728674`（插件会尝试根据 AV 获取 BV 后解析）
  - b23 短链：`https://b23.tv/BV14XLq64EQf`（会自动还原为 BV）

- 点播搜索（交互式）：
  - 发送：`b站点播 关键词` 或 `B站点播 关键词`，插件会搜索并返回结果（图片卡或文本列表）。
  - 若只发送 `b站点播`，插件会提示你输入关键词（进入点播会话）；随后回复关键词开始搜索。
  - 搜索结果返回后，直接回复序号（如 `3`）即可下载对应视频。
  - 发送 `停止点播` 可退出点播会话。

- **热门视频**：
  - 发送 `b站热门` 或 `B站热门`，插件将展示当前热门视频图片卡（数量可在配置中调整，默认 20）。

---

## 配置项（可在 AstrBot 插件管理界面或 _conf_schema.json 中修改）

- `quality`: `"720p"` 或 `"1080p"`（默认 `"720p"`） — 选择视频画质；1080p 多数为 Dash 分离流，需 ffmpeg 合并。
- `download_method`: `"aria2c"` 或 `"direct"`（默认 `"aria2c"`） — 下载方式。若选择 `aria2c` 但未检测到 aria2 可执行文件，将自动降级为 `direct`。
- `cache_dir`: 视频缓存目录（留空使用系统临时目录）。
- `temp_file_retention`: 临时文件保留时间（秒，默认 600）。
- `search_result_count`: 搜索结果数量（默认 20，最大 50）。
- `hot_count`: 热门视频展示数量（默认 20，最大 50）。
- `proxy`: HTTP 代理地址（示例：`http://127.0.0.1:7890`），用于 API 请求和下载。
- `api_base_url`: 插件调用的 B 站 API 地址（默认 `https://jinhong270-api.hf.space`）。
- `custom_font_path`: 自定义中文字体路径（优先于系统检测）。
- `enable_search_image`: 是否生成搜索/热门图片（默认 true，需要 Pillow）。
- `aria2_path`: aria2c 可执行文件路径（留空则自动从系统 PATH 查找）。

---

## 依赖与能力说明

- Python: 3.10+
- 运行依赖：`aiohttp`（API 请求与普通下载）、`Pillow`（图片生成，可选）。
- **aria2**：可选，用于高速多线程下载。不安装 aria2 插件将自动使用普通下载。
- ffmpeg：用于合并 Dash 音视频流（1080p 等分离流必需）。插件会在启动或下载时检测 ffmpeg 是否可用。
- 字体：若需生成中文搜索/热门图片，请确保容器/服务器安装中文字体或在配置中指定 `custom_font_path`。

---

## 常见问题

**Q: 下载的视频没有声音？**

A: 若选择 `1080p`（或目标流为 Dash 分离流），必须安装 ffmpeg 才能合并音视频。建议统一在运行环境中安装 ffmpeg。

**Q: 搜索结果/热门显示为纯文本而非图片？**

A: 生成图片卡依赖 Pillow 与可用的中文字体。若未安装 Pillow 或找不到字体，插件会回退为文本列表。

**Q: 插件如何设置代理？**

A: 在插件配置中填写 `proxy` 字段（例如 `http://127.0.0.1:7890`），插件的 API 请求与下载会走该代理。

**Q: 提示“aria2c 未找到”怎么办？**

A: 请确保 aria2 已正确安装，并配置 `aria2_path` 指向可执行文件（或确保 `aria2c` 在系统 PATH 中）。如果不安装 aria2，请在配置中将 `download_method` 设为 `direct`，插件会使用普通下载。

**Q: 支持哪些链接格式？**

A: 支持 BV、AV、完整 bilibili 视频链接与 b23.tv 短链。

---

## 开发者信息

- 插件作者：Jinhong270
- 当前版本：2.0.1
- 仓库：https://github.com/Jinhong270/astrbot_plugin_hfapibilibili
- 如遇问题请在 Issues 中反馈。

---

<p align="center">如果觉得本插件有用，欢迎点个 ⭐ 支持开源！</p>
