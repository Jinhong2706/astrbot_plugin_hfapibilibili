```markdown
<div align="center">

# 🎬 astrbot_plugin_hfapibilibili

**AstrBot B站视频插件**  
群内解析 B 站视频链接，自动下载并发送高清视频，支持关键词搜索

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot->=4.16-green.svg)](https://github.com/Soulter/AstrBot)
[![OneBot v11](https://img.shields.io/badge/OneBot-v11-black)](https://onebot.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

---

## 📖 简介

在群聊中发送 B 站视频链接或 BV 号，自动获取视频详情、封面图，并下载指定画质的视频文件发送。  
支持 b23 短链还原、Dash 流音视频合并（需 ffmpeg），并提供关键词搜索功能，搜索结果支持图文展示（需 Pillow）。

---

## 📥 安装

- **插件市场**：AstrBot 管理面板搜索 `astrbot_plugin_hfapibilibili` 安装。
- **手动**：将本仓库放入 `data/plugins/` 目录，重启 / 重载插件。
- **依赖安装**：
  ```bash
  pip install -r requirements.txt
  ```

---

## ⚙️ 前置要求

- AstrBot ≥ 4.16（< 5），aiocqhttp 适配器。
- Python 依赖：`aiohttp>=3.8.0`、`aiofiles>=0.8.0`、`Pillow>=9.0`（Pillow 可选，用于生成搜索图片）。
- 推荐安装 ffmpeg（见下方说明）。
- 插件使用第三方 API 获取 B 站数据，请确保网络可访问。

---

## 🔊 ffmpeg 需求说明

插件对 ffmpeg 的依赖取决于你选择的画质和视频类型：

| 画质设置 | ffmpeg 是否必需 | 说明 |
|----------|------------------|------|
| **720p** | 可选（推荐安装） | 大多数 720p 视频为单文件流，可直接下载播放。少数 Dash 流视频下载后无声音，安装 ffmpeg 可自动合并修复。 |
| **1080p** | **必需** | 1080p 视频均采用 Dash 分离流（视频与音频分轨），**必须安装 ffmpeg 才能合并出完整视频**，否则下载的文件将没有音频。 |

### 安装 ffmpeg

- **Ubuntu/Debian**：`sudo apt install ffmpeg`
- **macOS**：`brew install ffmpeg`
- **Windows**：从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载，解压后将 `bin` 目录加入系统 PATH 环境变量，重启生效。

### 检测方式

插件启动时会自动检测 ffmpeg 是否可用。若未检测到且当前画质设为 1080p，机器人会提示 **“当前环境未安装ffmpeg，下载的视频将没有声音”**。

---

## 🚀 使用方法

### 直接解析视频

在群聊中发送以下任意格式，机器人会自动回复视频信息与封面，随后发送下载完成的 MP4 视频文件：

- 完整链接：`https://www.bilibili.com/video/BV1U47T6UE1t`
- 纯 BV 号：`BV1U47T6UE1t`
- b23 短链：`https://b23.tv/BV14XLq64EQf`（自动还原为 BV 号）

### 搜索视频

发送 `search 关键词`（例如 `search 猫猫`）进行搜索。  
搜索结果优先以图片形式展示（需 Pillow + 中文字体），否则回退为文字列表。

在搜索结果返回后，**直接回复数字序号**（如 `3`），机器人即会下载序号对应的视频。

---

## 🔧 配置项

以下配置可在 AstrBot 插件管理界面或配置文件中修改（依据 `_conf_schema.json`）：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `quality` | string | `"720p"` | 视频画质选择：`"720p"` 或 `"1080p"`。1080p 必须安装 ffmpeg。 |
| `cache_dir` | string | `""` | 视频缓存目录，留空则使用系统临时目录。 |
| `temp_file_retention` | int | `600` | 临时文件保留时间（秒），超时自动清理，建议 300～3600。 |
| `search_result_count` | int | `20` | 搜索结果展示数量，最大限制为 50。 |
| `proxy` | string | `""` | HTTP 代理地址，如 `http://127.0.0.1:7890`。 |
| `api_base_url` | string | `"https://jinhong270-api.hf.space"` | B 站 API 服务地址，一般无需修改。 |

---

## ❓ 常见问题

**Q: 下载的视频没有声音？**  
A: 请检查画质设置是否为 1080p，若是则必须安装 ffmpeg。720p 下部分视频也可能需要 ffmpeg，建议统一安装。

**Q: 搜索结果为什么是文字而不是图片？**  
A: 图片搜索依赖 Pillow 库和系统中文字体。若 Pillow 未安装或字体缺失，将自动回退为纯文字结果。安装 Pillow 并确保字体可用即可启用图文搜索。

**Q: 支持哪些 B 站链接格式？**  
A: 支持纯 BV 号、`https://www.bilibili.com/video/BV...` 以及 b23.tv 短链接。短链会自动还原为 BV 号后解析。

**Q: 如何设置代理？**  
A: 在插件配置中填写 `proxy` 字段，例如 `http://127.0.0.1:7890`。设置后 API 请求和视频下载均会通过该代理。

**Q: 1080p 画质没有生效？**  
A: 确保配置中 `quality` 设为 `"1080p"`，且环境已安装 ffmpeg。部分视频可能不提供 1080p 流，插件会自动降级选择最佳可用画质。

---

## 👤 作者

- **Jinhong270**
- 仓库：https://github.com/Jinhong270/astrbot_plugin_hfapibilibili
- 反馈：Issues 页面

---

<p align="center">觉得有用的话，点个 ⭐ Star 吧</p>
```