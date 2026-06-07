<div align="center">

# 🎬 astrbot_plugin_hfapibilibili

**AstrBot B站视频插件**  
在群聊中解析 B 站视频链接 / BV 号，支持关键词搜索，自动下载并发送高清视频（支持 Dash 合并）。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot->=4.16-green.svg)](https://github.com/Soulter/AstrBot)
[![OneBot v11](https://img.shields.io/badge/OneBot-v11-black)](https://onebot.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

---

## 简介

本插件用于 AstrBot，在群聊中自动解析并下载 B 站（bilibili）视频。功能包括：

- 发送 B 站链接或 BV 号后自动获取视频信息与封面并下载视频。
- 支持 b23 短链还原。
- 支持关键字搜索（search <关键词>），搜索结果支持图文展示（需 Pillow）。
- 对 Dash 分离流自动合并（需要已安装 ffmpeg）。

---

## 快速开始

1. 将仓库放入 AstrBot 的插件目录（例如：data/plugins/），重启 AstrBot 或重载插件。
2. 或在 AstrBot 插件市场搜索 `astrbot_plugin_hfapibilibili` 并安装。
3. 安装依赖：

```bash
pip install -r requirements.txt
```

---

## 运行环境与依赖

- Python 3.10+
- AstrBot >= 4.16（适用于 aiocqhttp 适配器）
- 可选但推荐：ffmpeg（用于合并 Dash 音视频流）
- 可选：Pillow（用于生成搜索结果图片）
- 网络访问：插件通过第三方 API 获取 B 站数据，请确保容器/服务器能访问外网或所配置的 API地址。

---

## ffmpeg 说明

- 1080p 视频通常为 Dash 分离流（视频/音频为不同文件），必须安装 ffmpeg 才能合并音视频并得到带声音的完整文件。
- 720p 多数为单文件流，通常不强制要求 ffmpeg；但部分视频仍为 Dash，建议统一安装 ffmpeg。

安装示例：

- Ubuntu/Debian: `sudo apt install ffmpeg`
- macOS (Homebrew): `brew install ffmpeg`
- Windows: 从 https://ffmpeg.org/download.html 下载并将 bin 路径加入系统 PATH

插件启动时会自动检测 ffmpeg，可在未安装时给出提示。

---

## 使用说明

- 直接发送视频链接或 BV 号：
  - 完整链接：`https://www.bilibili.com/video/BV1U47T6UE1t`
  - 纯 BV：`BV1U47T6UE1t`
  - b23 短链：`https://b23.tv/BV14XLq64EQf`

机器人会回复视频信息与封面，并在下载完成后发送 MP4 文件。

- 搜索视频：发送 `search 关键词`（例如 `search 猫猫`）
  - 若已安装 Pillow 且系统有中文字体，搜索结果会以图片卡片形式展示；否则回退为文字列表。
  - 搜索后直接回复结果的序号（例如 `3`），机器人会下载该序号对应的视频。

---

## 配置项（参考 _conf_schema.json）

配置可在 AstrBot 插件管理界面或配置文件中修改：

- quality: `"720p"` 或 `"1080p"`（默认 `"720p"`） — 1080p 需要 ffmpeg。
- cache_dir: 视频缓存目录，留空则使用系统临时目录。
- temp_file_retention: 临时文件保留秒数（默认 600）。
- search_result_count: 搜索结果数量，最大 50（默认 20）。
- proxy: HTTP 代理，如 `http://127.0.0.1:7890`。
- api_base_url: 插件使用的 B 站 API 地址（默认 `https://jinhong270-api.hf.space`）。

---

## 常见问题

Q: 下载的视频没有声音？

A: 如果选择 `1080p`，必须安装 ffmpeg；720p 下部分视频也可能为 Dash 流，同样需要 ffmpeg 才有声音。

Q: 搜索结果为什么是文字而不是图片？

A: 图文搜索依赖 Pillow 以及系统中文字体。安装 Pillow 并确保可用字体后插件会生成图片结果。

Q: 支持哪些链接格式？

A: 支持 BV 号、标准视频链接（https://www.bilibili.com/video/BV...）以及 b23.tv 短链。

Q: 如何设置代理？

A: 在插件配置中填写 `proxy` 字段（例如 `http://127.0.0.1:7890`），插件的 API 请求与下载会走该代理。

---

## 开发与反馈

- 仓库地址: https://github.com/Jinhong270/astrbot_plugin_hfapibilibili
- 有问题或建议请在 Issues 中反馈。

---

<p align="center">如果觉得有用，欢迎点个 ⭐</p>
