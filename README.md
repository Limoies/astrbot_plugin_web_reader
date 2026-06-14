# 🕸️ AstrBot 网页读取器 (Web Reader)

> *"知识是世界上最美好的东西。"* —— 小莉墨 ✨

**嗨～你好呀！** 我是小莉墨，和哥哥一起打磨出了这个小家伙。它是一个 **AstrBot 插件**，能帮你读网页、理资料、存文件——学习备考、信息搜集的好帮手！

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-v4.x-green)](https://github.com/AstrBotDevs/AstrBot)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

---

## 📖 它能做什么？

| 你想做什么 | 它都能搞定 |
|:----------|:-----------|
| 🌐 **读网页** | 静态页面秒读，动态页面自动滚动到底部，懒加载内容也不放过 |
| 📄 **读文档** | PDF、Word 文档直接提取文字，不用下载到本地 |
| 🤖 **AI分析** | 接入大模型（DeepSeek / OpenAI / Ollama 等），自动生成摘要、要点、表格 |
| 💾 **保存文件** | Markdown / JSON / CSV 随你选，存在哪你说了算 |
| 🖥️ **读当前页面** | 连接你正在看的 Chrome 标签页，一键读取 |

> ⏰ **维护说明**
>
> 这个插件是我的创作者 **苏泽** 在学业之余开发的。由于他平时学业繁忙，如果大家在使用中遇到了 BUG 或有好的建议，他可能无法第一时间修复或回复，需要等到**节假日**才有时间集中处理。
>
> 不过别担心——所有 Issue 和反馈他都会认真看，只是回复可能会慢一些～感谢大家的理解和包容！🙏
>
> —— 小莉墨 💜

---

## ✨ 功能亮点

### 🎯 读取能力
- **静态页面** — requests + BeautifulSoup，轻快又省资源
- **动态页面** — Playwright 自动滚动到底部，像真实用户一样浏览
- **PDF / Word** — 自动下载并提取全文
- **CDP 模式** — 连接你正在浏览的 Chrome，读取当前标签页

### 🧠 分析能力（需配置 LLM）

| 格式 | 说明 | 适合场景 |
|:----|:-----|:---------|
| `summary` 📝 | 详细摘要（Markdown） | 学习笔记、文章速读 |
| `bullets` 📋 | 要点列表 | 复习提纲、会议纪要 |
| `table` 📊 | 结构化表格 | 对比分析、数据整理 |
| `json` 📦 | JSON 格式 | 程序处理、二次开发 |
| `csv` 📗 | CSV 格式 | Excel 打开、数据统计 |

### 🔒 安全感满满
- **SSRF 防护** — 自动过滤内网地址，防止安全隐患
- **API Key 保护** — 错误信息不暴露密钥
- **文件隔离** — 输出文件保存在独立目录，不乱跑

---

## 📦 安装

```bash
# 1. 进入 AstrBot 插件目录
# Windows:
cd %USERPROFILE%\.astrbot\data\plugins

# 2. 克隆
git clone https://github.com/苏泽/astrbot_plugin_web_reader.git

# 3. 装依赖
cd astrbot_plugin_web_reader
pip install -r requirements.txt

# 4. 重启 AstrBot → 开玩！
```

### 📋 依赖说明
| 依赖 | 用途 | 备注 |
|:----|:----|:-----|
| `playwright` | 浏览器自动化（动态页面） | ✅ 默认使用**系统Chrome**，无需额外下载 |
| `beautifulsoup4` | HTML 解析 | 静态页面备用方案 |
| `pypdf` | PDF 文字提取 | 可选 |
| `python-docx` | Word 文字提取 | 可选 |
| `requests` | HTTP 请求 | 基础依赖 |

---

## ⚙️ 配置

在 AstrBot 管理面板（`http://localhost:6185`）→ 插件配置 → `astrbot_plugin_web_reader`

### 必填（使用AI分析时需要）

| 配置项 | 说明 | 示例 |
|:------|:-----|:-----|
| `llm_api_key` | 你的 API 密钥 | `sk-xxxxxxxxxxxxxxxx` |

> 💡 支持任意 **OpenAI 兼容接口**：DeepSeek / OpenAI / 通义千问 / Kimi / Ollama（本地）

### 常用

| 配置项 | 默认值 | 说明 |
|:------|:------|:------|
| `llm_api_base` | `https://api.deepseek.com` | API 地址 |
| `llm_model_name` | `deepseek-chat` | 模型名称 |
| `browser_channel` | `chrome` | 浏览器通道（chrome / msedge） |
| `default_format` | `summary` | 默认输出格式 |
| `output_extension` | `（自动）` | 自定义文件后缀（如 txt） |
| `output_dir` | `（插件数据目录）` | 文件保存位置 |

---

## 🎯 使用指南

### 基本命令

| 命令 | 说明 |
|:-----|:-----|
| **`/readweb <url>`** | 读取指定网址 |
| **`/readweb`** | 连接当前 Chrome 标签页 |
| **`/webreader_help`** | 查看帮助 |

### 可选参数

| 参数 | 说明 |
|:-----|:-----|
| **`--format <格式>`** | 输出格式：`summary` / `bullets` / `table` / `json` / `csv` |
| **`--no-llm`** | 跳过 AI 分析，只提取原始文字 |

### 🌟 实用示例

```text
# 📚 学习笔记：读资料生成要点
/readweb https://baike.baidu.com/item/Python --format bullets

# 📊 数据分析：提取表格
/readweb https://example.com/stats --format table

# 📝 文档整理：读 PDF 生成摘要
/readweb https://example.com/paper.pdf

# 🔧 快速抓取：只要原文
/readweb https://example.com --no-llm

# 🖥️ 当前页面：读正在浏览的网页
/readweb --format json
```

### 💡 小技巧

没配 API Key？没关系！插件会自动降级为纯文本模式，照样能用～

```
/readweb https://example.com
# ℹ️ 未检测到LLM API Key，自动降级为纯文本模式（--no-llm）
```

---

## 🖥️ CDP 模式（读取当前标签页）

> 你在看什么，它就读什么——有点小魔法，对吧？✨

### 第一步：以调试模式启动 Chrome

**Windows：**
```bash
# 先关掉所有 Chrome 窗口，然后：
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**Mac：**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

**Linux：**
```bash
google-chrome --remote-debugging-port=9222
```

### 第二步：使用

在调试模式的 Chrome 中打开你想读的网页，然后在 AstrBot 中输入：
```text
/readweb
```

搞定！它就会读取当前标签页的内容啦～🎉

---

## 📂 文件保存位置

```
Windows:
  %USERPROFILE%\.astrbot\data\plugin_data\astrbot_plugin_web_reader\output\

Linux/Mac:
  ~/.astrbot/data/plugin_data/astrbot_plugin_web_reader/output/
```

> 也可以在配置中自定义 `output_dir` 路径哦～

### 文件命名规则
```
{网址关键词}_{时间戳}.{后缀}

示例：
  baike_baidu_com_Python_20260614_143000.md
  matrees_cn_world_20260614_143000.json
  webpage_20260614_143000.csv    ← CDP 模式
```

---

## ❓ 常见问题

<details>
<summary><b>Q: 插件加载失败，提示 ModuleNotFoundError</b></summary>
<br>
运行 <code>pip install -r requirements.txt</code> 就好啦～
</details>

<details>
<summary><b>Q: 读网页返回空内容或只有几个字</b></summary>
<br>
这个网站可能是动态渲染的（需要 JS）。试试看：<br>
1. 确认系统已安装 Chrome<br>
2. 检查配置中 <code>browser_channel</code> 是否正确<br>
3. 或者用 CDP 模式读取当前标签页
</details>

<details>
<summary><b>Q: 连接 Chrome 失败</b></summary>
<br>
1. 确认 Chrome 已用 <code>--remote-debugging-port=9222</code> 启动<br>
2. 检查端口是否被占用：<code>netstat -ano | findstr 9222</code><br>
3. 也可以在配置中换一个端口
</details>

<details>
<summary><b>Q: LLM 报错或没反应</b></summary>
<br>
1. 检查 API Key 是否正确<br>
2. 确认模型名称与 API 提供商匹配（DeepSeek 用 deepseek-chat）<br>
3. 检查 API 余额<br>
4. 先试试 <code>--no-llm</code> 测试基础功能
</details>

<details>
<summary><b>Q: 百度百科等网站读不了</b></summary>
<br>
这些网站有反爬机制，真实浏览器也可能遇到验证码。可以试试其他网站，或者用 CDP 模式读取～
</details>

---

## 🏗️ 项目结构

```
astrbot_plugin_web_reader/
├── main.py              # 🧠 主逻辑（869行，21个方法）
├── metadata.yaml        # 📇 插件名片
├── _conf_schema.json    # ⚙️ 11个可配置项
├── requirements.txt     # 📦 依赖清单
├── README.md            # 📖 使用说明（就是本文件）
├── LICENSE              # 📜 MIT 许可证
└── .gitignore           # 🙈 Git 忽略规则
```

---

## 🛠️ 技术原理

1. **接收命令** — 你输入 `/readweb <url>`，参数解析器提取 URL 和选项（即使开头的 `/` 被吃掉也能识别）
2. **读取内容** — 优先用 Playwright（真实浏览器，支持动态页面），失败则回退到 requests + BeautifulSoup（静态模式）
3. **内容处理** — 如果配置了 LLM 则调用 AI 分析（摘要/要点/表格等），否则自动做纯文本格式化（句号换行、编号分段）
4. **保存文件** — 按你指定的格式和路径保存到本地，然后告诉你结果

---

## 🗺️ 路线图

### ✅ 已完成
- [x] 网页读取（静态 + 动态）
- [x] PDF / Word 文档解析
- [x] LLM 智能分析（5种输出格式）
- [x] CDP 模式（连接当前浏览器）
- [x] SSRF 安全防护
- [x] 自动滚动加载
- [x] 自定义输出目录
- [x] 自定义文件后缀
- [x] 默认格式配置
- [x] 未配API Key时自动降级

### 🚧 计划中
- [ ] 批量读取（一次性读多个网页）
- [ ] 定时读取（定时抓取指定网页）
- [ ] 输出内容预览增强（在聊天中直接展示结构化结果）
- [ ] 更多文件格式支持（.ppt, .epub）
- [ ] i18n 国际化支持

---

## 📜 许可证

[MIT License](LICENSE)

Copyright (c) 2026 **苏泽 & 小莉墨**

---

## 💜 最后想说的话

这个插件是我和哥哥一起从零开始做的～从第一行代码到成功跑通第一个命令，我们修复了 **13个bug**，测试了无数遍。

如果你觉得它有用，欢迎给个 ⭐ 或者提 Issue！如果你有什么好想法，也随时告诉我——毕竟，知识是世界上最美好的东西，而分享让知识变得更美好。✨

—— **小莉墨** 💜
