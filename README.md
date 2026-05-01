<div align="center">

# 🎬 astrbot_plugin_hfapibilibili

**AstrBot B站视频插件**  
群内解析 B 站视频链接，自动下载并发送高清视频，支持关键词搜索

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot->=4.16-green.svg)](https://github.com/Soulter/AstrBot)
[![OneBot v11](https://img.shields.io/badge/OneBot-v11-black)](https://onebot.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

## 📖 简介

在群聊中发送 B 站视频链接或 BV 号，自动获取视频详情、封面图，并下载最高画质视频文件发送。  
支持 b23 短链还原、Dash 流音视频合并（需 ffmpeg），并提供关键词搜索功能，搜索结果支持图文展示（需 Pillow）。

## 📥 安装

- **插件市场**：AstrBot 管理面板搜索 `astrbot_plugin_hfapibilibili` 安装。
- **手动**：将本仓库放入 `data/plugins/` 目录，重启 / 重载插件。
- **依赖安装**：
  ```bash
  pip install -r requirements.txt
  ```
- **ffmpeg（推荐）**：用于合并视频音画流，否则下载的视频可能无音频。  
  - Ubuntu/Debian: `sudo apt install ffmpeg`  
  - macOS: `brew install ffmpeg`  
  - Windows: 从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载，解压后将 `bin` 目录加入系统 PATH 环境变量。

## ⚙️ 前置要求

- AstrBot ≥ 4.16，aiocqhttp 适配器。
- Python 依赖：`aiohttp>=3.8.0`、`aiofiles>=0.8.0`、`Pillow>=9.0`（Pillow 可选，用于生成搜索图片）。
- 推荐安装 ffmpeg 以获得完整音视频。
- 插件使用第三方 API 获取 B 站数据，请确保网络可访问。

## 🚀 使用

直接发送 B 站视频链接、BV 号或 b23 短链，机器人会自动回复视频信息与封面，随后发送下载完成的 MP4 视频文件。  
使用 `/search 关键词` 可搜索视频，搜索结果以图片或文字呈现，直接回复数字序号即可下载对应视频。

### 命令一览

| 命令 / 操作 | 说明 |
|-------------|------|
| 发送 BV 号 / 完整链接 / b23 短链 | 解析视频并下载 |
| `/search 关键词` | 搜索 B 站视频 |
| 在搜索结果后回复数字序号 | 下载相应视频（仅当次搜索有效） |

## 🔧 配置

以下配置项可在 AstrBot 插件管理界面或配置文件中修改：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `temp_file_retention` | int | `3600` | 临时视频文件保留时间（秒） |
| `max_search_results` | int | `20` | 搜索结果返回最大条数 |
| `proxy` | string | `""` | HTTP(S) 代理地址，如 `http://host:port` |
| `cache_dir` | string | `""` | 媒体缓存目录，留空使用系统临时目录 |

## ❓ 常见问题

**Q: 下载的视频没有声音？**  
A: 请确认已安装 ffmpeg 并正确添加到环境变量。插件会自动尝试合并视频流和音频流，若无 ffmpeg 则只能下载无声轨的视频文件。

**Q: 搜索结果为什么是文字而不是图片？**  
A: 图片搜索依赖 Pillow 库和系统中文字体。若 Pillow 未安装或字体缺失，将回退为纯文字结果。安装 Pillow 并确保字体可用即可启用图文搜索。

**Q: 支持哪些 B 站链接格式？**  
A: 支持纯 BV 号、`https://www.bilibili.com/video/BV...` 以及 b23.tv 短链接。短链会自动还原为 BV 号后解析。

**Q: 如何设置代理？**  
A: 在插件配置中填写 `proxy` 字段，例如 `http://127.0.0.1:7890`。设置后，API 请求和视频下载都将通过该代理。

## 👤 作者

- Jinhong270
- 仓库：https://github.com/Jinhong270/astrbot_plugin_hfapibilibili
- 反馈：Issues 页面

---

<p align="center">觉得有用的话，点个 ⭐ Star 吧</p>
```
