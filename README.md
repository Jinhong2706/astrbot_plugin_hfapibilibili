# 🎬 astrbot_plugin_hfapibilibili

AstrBot B 站视频插件 —— 在聊天中解析、点播并下载 B 站高清视频。

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot->=4.16-green.svg)](https://github.com/Soulter/AstrBot)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 功能

- 整条消息仅为完整 B 站视频链接（BV1 / av116339171728674）时自动解析并下载
- 按关键词点播搜索，返回图文卡片 / 纯文本结果
- `b站热门` 快速查看当前热门视频
- Dash 分离流音视频合并（需 ffmpeg）
- aria2 多线程高速下载，自动降级为普通下载
- 支持 HTTP 代理
- 交互式点播会话管理，超时自动清理
- **用户隔离**：每个用户独立的点播会话，互不干扰
- **停止点播自动清理**：说出"停止点播"后自动删除该用户已下载的封面图片
- **黑名单**：支持通过用户 ID 配置黑名单，禁止指定用户使用插件

## 安装

1. 将本仓库放入 AstrBot 插件目录（`data/plugins/`），重启或重载插件
2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. （可选）安装 `aria2` 获取多线程下载加速：

```bash
sudo apt install aria2   # Linux
brew install aria2       # macOS
```

4. （可选）安装 `ffmpeg` 与中文字体获得完整体验

## 使用

| 触发方式 | 说明 |
|----------|------|
| 整条消息发送完整 B 站视频链接 | 自动解析并下载视频 |
| `b站点播 关键词` | 搜索并选择下载 |
| `b站点播` | 进入交互式点播对话 |
| `b站热门` | 展示当前热门视频 |
| `停止点播` | 退出点播会话并清理封面图片 |
| 搜索结果中回复序号 | 下载对应视频 |

### 用户隔离

每个用户的点播会话相互独立。当用户 A 进入点播模式后，仅用户 A 的后续消息会被识别为搜索词输入，其他用户的消息不会影响 A 的会话。

### 自动下载触发规则

**仅当整条消息内容就是一条完整视频链接时才会触发下载**（前后可有空白，不可夹杂其他文字）：

| 格式 | 示例 |
|------|------|
| BV1 视频链接 | `https://www.bilibili.com/video/BV1U47T6UE1t` |
| av116339171728674 开头的 AV 视频链接 | `https://www.bilibili.com/video/av116339171728674` |

以下情况**不会**触发自动下载：

- 单独的 BV 号 / AV 号（如 `BV1U47T6UE1t`、`av116339171728674`）
- 消息中混有其他文字，如 `看看这个 https://www.bilibili.com/video/BV1...`
- 链接中的 BV 不以 `BV1` 开头
- 链接中的 AV 不以 `av116339171728674` 开头（如 `av116339171728674`、`av116339171728674`）
- b23.tv 短链

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `quality` | string | `720p` | 视频画质：`720p` / `1080p` |
| `download_method` | string | `aria2c` | 下载方式：`aria2c` / `direct` |
| `cache_dir` | string | (空) | 视频缓存目录，留空使用系统临时目录 |
| `temp_file_retention` | int | `600` | 临时文件保留时间（秒） |
| `search_result_count` | int | `20` | 搜索结果展示数量（最大 50） |
| `hot_count` | int | `20` | 热门视频展示数量（最大 50） |
| `proxy` | string | (空) | HTTP 代理地址，如 `http://127.0.0.1:7890` |
| `api_base_url` | string | `https://jinhong270-api.hf.space` | B 站 API 服务地址 |
| `custom_font_path` | string | (空) | 自定义中文字体路径 |
| `enable_search_image` | bool | `true` | 是否生成搜索/热门图片（需 Pillow） |
| `aria2_path` | string | (空) | aria2c 可执行文件路径 |
| `enable_blacklist` | bool | `false` | 是否启用黑名单 |
| `blacklist_ids` | text | (空) | 黑名单用户 ID，每行一个 |

## 重试机制

所有 API 请求和下载操作均内置 **5 次重试**，每次间隔 **5 秒**。网络波动时自动重试，无需手动干预。达到最大重试次数后才会返回错误。

## 依赖

- Python 3.10+
- `aiohttp` — API 请求与下载
- `Pillow` — 图片生成（可选，未安装时回退为文本列表）
- `ffmpeg` — 1080p Dash 流合并（可选，未安装时音视频分离发送）
- `aria2` — 多线程下载加速（可选，未安装时自动降级为普通下载）

## 常见问题

**Q: 下载的视频没有声音？**

A: 1080p 多为 Dash 分离流，需安装 ffmpeg 合并音视频。

**Q: 搜索结果显示为纯文本而非图片？**

A: 图片卡片依赖 Pillow 与中文字体。未安装时自动回退为文本列表。

**Q: 如何设置代理？**

A: 在插件配置中填写 `proxy` 字段，如 `http://127.0.0.1:7890`。

**Q: 提示"aria2c 未找到"？**

A: 安装 aria2 或将 `download_method` 设为 `direct` 使用普通下载。

**Q: 如何禁止某个用户使用插件？**

A: 在插件配置中启用 `enable_blacklist`，然后在 `blacklist_ids` 中填写该用户的 ID（每行一个），该用户将无法使用本插件的任何功能。

**Q: 发送了视频链接为什么没有下载？**

A: 请确认整条消息只有一条完整 `https://www.bilibili.com/video/...` 链接（BV1 或 av116339171728674 开头），不要只发 BV/AV 号，也不要夹杂其他文字。b23.tv 短链不会自动下载。

## 开发者

- 作者：Jinhong270
- 版本：2.0.4
- 仓库：[Jinhong270/astrbot_plugin_hfapibilibili](https://github.com/Jinhong270/astrbot_plugin_hfapibilibili)
- 问题反馈：[Issues](https://github.com/Jinhong270/astrbot_plugin_hfapibilibili/issues)

---

<p align="center">如果觉得本插件有用，欢迎点个 ⭐ 支持开源！</p>
