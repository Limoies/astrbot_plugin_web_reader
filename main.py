"""
AstrBot 网页读取器插件
==========================
功能：
  - 读取网页/PDF/Word的文字内容
  - 自动滚动加载动态页面
  - 支持连接已打开的Chrome浏览器（CDP模式）
  - 调用LLM进行结构化分析
  - 保存为Markdown/JSON/CSV文件

作者: 苏泽 & 小莉墨
版本: v1.0.0
"""

import os
import re
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform import AstrMessageEvent

# ============================================================
# 修复：Windows长路径前缀兼容性（\\?\ 前缀导致Node.js报错）
# ============================================================
try:
    import playwright._impl._driver as _pw_driver
    _pw_original_compute = _pw_driver.compute_driver_executable
    def _pw_patched_compute():
        result = _pw_original_compute()
        if isinstance(result, tuple):
            return tuple(p.replace("\\\\?\\", "") if isinstance(p, str) else p for p in result)
        return str(result).replace("\\\\?\\", "") if isinstance(result, str) else result
    _pw_driver.compute_driver_executable = _pw_patched_compute
except ImportError:
    pass  # Playwright未安装，跳过路径修复


# ============================================================
# 日志配置
# ============================================================
logger = logging.getLogger("astrbot_plugin_web_reader")


class WebReaderPlugin(Star):
    """网页读取器插件主类"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # 数据目录（用于存放输出文件）
        self.data_dir = Path(StarTools.get_data_dir("astrbot_plugin_web_reader"))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 输出目录（用户可自定义，默认在data_dir下）
        output_dir = config.get("output_dir", "")
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = self.data_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"网页读取器插件已加载，输出目录: {self.output_dir}")


    # ============================================================
    # 生命周期
    # ============================================================
    async def initialize(self):
        """插件加载时触发"""
        logger.info("网页读取器插件初始化完成")

    async def terminate(self):
        """插件卸载时触发"""
        logger.info("网页读取器插件已卸载")

    # ============================================================
    # 辅助函数：判断URL类型
    # ============================================================
    @staticmethod
    def _detect_url_type(url: str) -> str:
        """判断URL指向的文件类型: html / pdf / docx / unknown"""
        path = urlparse(url).path.lower()
        if path.endswith(".pdf"):
            return "pdf"
        elif path.endswith(".docx"):
            return "docx"
        elif path.endswith(".doc"):
            return "docx"  # .doc 也可能实际上是 docx 格式
        else:
            return "html"

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """简单的URL格式检查"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """SSRF防护：检查URL是否指向内网地址"""
        import socket
        try:
            result = urlparse(url)
            if not result.hostname:
                return False
            # 解析域名获取IP
            ip = socket.gethostbyname(result.hostname)
            # 内网IP范围检查
            private_ranges = [
                ("127.0.0.0", "127.255.255.255"),
                ("10.0.0.0", "10.255.255.255"),
                ("172.16.0.0", "172.31.255.255"),
                ("192.168.0.0", "192.168.255.255"),
            ]
            ip_parts = [int(x) for x in ip.split(".")]
            ip_num = (ip_parts[0] << 24) + (ip_parts[1] << 16) + (ip_parts[2] << 8) + ip_parts[3]
            for start, end in private_ranges:
                start_parts = [int(x) for x in start.split(".")]
                end_parts = [int(x) for x in end.split(".")]
                start_num = (start_parts[0] << 24) + (start_parts[1] << 16) + (start_parts[2] << 8) + start_parts[3]
                end_num = (end_parts[0] << 24) + (end_parts[1] << 16) + (end_parts[2] << 8) + end_parts[3]
                if start_num <= ip_num <= end_num:
                    return False
            # 检查是否为本地回环地址
            if ip.startswith("0.") or ip == "255.255.255.255":
                return False
            return True
        except Exception:
            # DNS解析失败时，保守地禁止
            return False

    # ============================================================
    # 辅助函数：提取网页纯文本（静态方式）
    # ============================================================
    @staticmethod
    def _extract_text_from_html(html_content: str) -> str:
        """从HTML中提取纯文本"""
        soup = BeautifulSoup(html_content, "html.parser")

        # 移除脚本和样式
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # 获取文本
        text = soup.get_text(separator="\n", strip=True)

        # 清理多余的空行
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    # ============================================================
    # 功能：使用Playwright读取动态网页（含自动滚动）
    # ============================================================
    async def _read_with_playwright(
        self, url: str, use_cdp: bool = False, cdp_port: int = 9222
    ) -> str:
        """
        使用Playwright读取网页内容（支持动态加载）
        
        Args:
            url: 目标网址（CDP模式下可为空字符串）
            use_cdp: 是否连接已打开的Chrome
            cdp_port: Chrome调试端口
            
        Returns:
            网页纯文本内容
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("Playwright未安装，回退到静态模式")
            return await self._read_static(url)

        async with async_playwright() as p:
            if use_cdp:
                # 连接已打开的Chrome浏览器（CDP模式）
                logger.info(f"正在连接Chrome调试端口: {cdp_port}")
                browser = await p.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{cdp_port}"
                )
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                pages = context.pages
                if not pages:
                    raise Exception("Chrome浏览器中没有打开的标签页")
                page = pages[0]
                # 如果传入了url则跳转，否则保持当前页面
                if url:
                    logger.info(f"跳转到: {url}")
                    await page.goto(url, wait_until="networkidle", timeout=30000)
            else:
                # 无头模式启动系统已安装的 Chrome（无需额外下载浏览器）
                logger.info(f"无头模式启动系统Chrome，访问: {url}")
                # 从配置读取浏览器通道（chrome/msedge/留空）
                browser_channel = self.config.get("browser_channel", "chrome") or None
                launch_kwargs = {"headless": True}
                if browser_channel:
                    launch_kwargs["channel"] = browser_channel
                browser = await p.chromium.launch(**launch_kwargs)
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)

            # 自动滚动（懒加载内容）
            if self.config.get("auto_scroll", True):
                max_rounds = self.config.get("scroll_max_rounds", 30)
                await self._auto_scroll(page, max_rounds)

            # 等待一下确保内容完全加载
            await asyncio.sleep(2)

            # 提取页面文本内容
            title = await page.title()
            # 获取比较完整的文字内容（使用 evaluate 获取 body 的 innerText）
            body_text = await page.evaluate("""
                () => {
                    // 移除脚本和样式元素
                    const clones = document.body.cloneNode(true);
                    const removals = clones.querySelectorAll('script, style, nav, footer, header, aside');
                    removals.forEach(el => el.remove());
                    return clones.innerText || '';
                }
            """)

            # 清理多余的空白，但保留段落结构
            paragraphs = []
            current_para = []
            for line in body_text.splitlines():
                stripped = line.strip()
                if stripped:
                    current_para.append(stripped)
                else:
                    if current_para:
                        paragraphs.append(' '.join(current_para))
                        current_para = []
            if current_para:
                paragraphs.append(' '.join(current_para))
            
            clean_text = '\n\n'.join(paragraphs)
            
            # 段落太少时用行合并作为备选
            if len(paragraphs) <= 3:
                flines = [l.strip() for l in body_text.splitlines() if l.strip()]
                clean_text = '\n'.join(flines)

            result = f"标题: {title}\n\n{clean_text}" if title else clean_text

            await browser.close()
            return result

    @staticmethod
    async def _auto_scroll(page, max_rounds: int = 30):
        """自动滚动页面到底部，加载懒加载内容"""
        logger.info(f"开始自动滚动，最大轮数: {max_rounds}")
        prev_height = 0
        for i in range(max_rounds):
            # 滚动到底部
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)  # 等待新内容加载

            # 检查是否到达底部
            curr_height = await page.evaluate("document.body.scrollHeight")
            if curr_height == prev_height:
                logger.info(f"滚动完成，已到达底部（第{i+1}轮）")
                break
            prev_height = curr_height

            # 可选的：向上滚动一点再向下，触发某些特殊懒加载
            if i % 5 == 4:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight - 500)")
                await asyncio.sleep(0.5)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1)

    # ============================================================
    # 功能：静态方式读取网页（requests + BeautifulSoup）
    # ============================================================
    async def _read_static(self, url: str) -> str:
        """使用requests库静态读取网页"""
        logger.info(f"静态模式读取网页: {url}")
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://www.baidu.com/",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, lambda: requests.get(url, headers=headers, timeout=30)
            )
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding  # 自动检测编码
            text = self._extract_text_from_html(resp.text)
            return text
        except Exception as e:
            logger.error(f"静态读取失败: {e}")
            raise

    # ============================================================
    # 功能：读取PDF文件
    # ============================================================
    async def _read_pdf(self, url: str) -> str:
        """读取PDF文件内容（支持在线和本地）"""
        logger.info(f"读取PDF: {url}")
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("请安装 pypdf: pip install pypdf")

        loop = asyncio.get_event_loop()

        if self._is_valid_url(url):
            # 在线PDF：先下载到临时文件
            resp = await loop.run_in_executor(
                None, lambda: requests.get(url, timeout=30)
            )
            resp.raise_for_status()
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name
            try:
                text = await loop.run_in_executor(None, self._extract_pdf_text, tmp_path)
            finally:
                os.unlink(tmp_path)
        else:
            # 本地PDF
            text = await loop.run_in_executor(None, self._extract_pdf_text, url)

        return text

    @staticmethod
    def _extract_pdf_text(file_path: str) -> str:
        """从PDF文件中提取文字"""
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        texts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
        result = "\n\n".join(texts)
        return result if result else "（无法从PDF中提取文字内容）"

    # ============================================================
    # 功能：读取Word文档
    # ============================================================
    async def _read_docx(self, url: str) -> str:
        """读取Word文档内容（支持在线和本地）"""
        logger.info(f"读取Word文档: {url}")
        try:
            from docx import Document
        except ImportError:
            raise ImportError("请安装 python-docx: pip install python-docx")

        loop = asyncio.get_event_loop()

        if self._is_valid_url(url):
            resp = await loop.run_in_executor(
                None, lambda: requests.get(url, timeout=30)
            )
            resp.raise_for_status()
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name
            try:
                text = await loop.run_in_executor(None, self._extract_docx_text, tmp_path)
            finally:
                os.unlink(tmp_path)
        else:
            text = await loop.run_in_executor(None, self._extract_docx_text, url)

        return text

    @staticmethod
    def _extract_docx_text(file_path: str) -> str:
        """从Word文档中提取文字"""
        from docx import Document
        doc = Document(file_path)
        texts = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(texts) if texts else "（无法从Word文档中提取文字内容）"

    # ============================================================
    # 功能：调用LLM进行结构化分析
    # ============================================================
    async def _analyze_with_llm(
        self, text: str, format_type: str = "summary", url: str = ""
    ) -> str:
        """
        调用LLM对文本进行结构化分析
        
        Args:
            text: 原始文本
            format_type: 输出格式 (summary / bullets / table / json / csv)
            url: 来源URL（用于上下文提示）
            
        Returns:
            结构化后的文本
        """
        # 获取LLM配置
        api_base = self.config.get("llm_api_base", "https://api.deepseek.com")
        api_key = self.config.get("llm_api_key", "")
        model = self.config.get("llm_model_name", "deepseek-chat")
        max_tokens = self.config.get("llm_max_tokens", 4096)

        if not api_key:
            raise ValueError(
                "未配置LLM API Key！请在AstrBot管理面板中配置 llm_api_key，"
                "或使用 --no-llm 参数跳过分析。"
            )

        # 构建system提示词
        format_prompts = {
            "summary": (
                "请对以下网页内容进行详细的摘要整理，要求：\n"
                "1. 用中文回答\n"
                "2. 包含文章的核心主题、主要观点、关键数据\n"
                "3. 按逻辑分点呈现，使用标题和小标题\n"
                "4. 保留重要的事实和数据\n"
                "5. 格式为Markdown"
            ),
            "bullets": (
                "请将以下内容提炼为要点列表，要求：\n"
                "1. 用中文回答\n"
                "2. 每个要点简洁明了，突出重点\n"
                "3. 按逻辑分组，使用二级标题分类\n"
                "4. 保留关键数据\n"
                "5. 格式为Markdown的无序列表"
            ),
            "table": (
                "请将以下内容整理为表格形式，要求：\n"
                "1. 用中文回答\n"
                "2. 识别内容中的结构化信息\n"
                "3. 使用Markdown表格输出\n"
                "4. 如果有多组数据，用多个表格呈现\n"
                "5. 表头清晰明了"
            ),
            "json": (
                "请将以下内容整理为JSON格式，要求：\n"
                "1. 使用以下结构：{\"title\": \"...\", \"source\": \"...\", " 
                "\"summary\": \"...\", \"key_points\": [...], \"details\": {...}}\n"
                "2. 只输出JSON，不要其他文字\n"
                "3. 确保JSON格式正确，可被json.loads解析"
            ),
            "organize": (
                "请对以下网页内容进行结构整理，要求：\n"
                "1. **保留全部原文内容，不要删减或改写**\n"
                "2. 根据内容逻辑划分段落，添加合适的小标题\n"
                "3. 用 Markdown 标题层级（# ## ###）组织结构\n"
                "4. 识别列表、引用、代码块等特殊格式并标注\n"
                "5. 目标是让原文更清晰易读，而不是总结或提炼"
            ),
            "csv": (
                "请将以下内容整理为CSV格式，要求：\n"
                "1. 第一行为列名\n"
                "2. 后续每行为一条数据\n"
                "3. 用逗号分隔字段，字段含逗号时用双引号包裹\n"
                "4. 只输出CSV内容，不要额外文字"
            ),
        }

        system_prompt = format_prompts.get(
            format_type,
            "请对以下网页内容进行详细的中文摘要整理，使用Markdown格式。",
        )

        # 如果文本太长，截断到合理长度（约8万字符，对应约2万token）
        max_text_length = 80000
        if len(text) > max_text_length:
            logger.warning(f"文本过长({len(text)}字符)，截断前{max_text_length}字符")
            text = text[:max_text_length] + "\n\n...（内容过长，已截断）"

        # 构建消息
        user_message = f"来源URL: {url}\n\n以下是需要分析的网页内容：\n\n{text}"

        # 调用LLM（OpenAI兼容格式）
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }

        # 使用 urljoin 安全拼接 API 端点
        from urllib.parse import urljoin
        api_base = api_base.rstrip("/")
        if api_base.endswith("/chat/completions"):
            url_endpoint = api_base
        else:
            # 确保路径以 /v1/chat/completions 结尾
            if not api_base.endswith("/v1") and not api_base.endswith("/v1/"):
                api_base += "/v1" if not api_base.endswith("/v1") else ""
            url_endpoint = urljoin(api_base + "/", "chat/completions")

        logger.info(f"调用LLM: {model} @ {api_base}")
        logger.info(f"请求端点: {url_endpoint}")

        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    url_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=120,
                ),
            )
            resp.raise_for_status()
            result = resp.json()
            content = result["choices"][0]["message"]["content"]
            logger.info(f"LLM响应成功，长度: {len(content)}字符")
            return content
        except requests.exceptions.Timeout:
            raise TimeoutError("LLM请求超时，请检查网络或增加超时时间")
        except requests.exceptions.HTTPError as e:
            # 只返回状态码，不暴露响应体（防止泄露API Key等敏感信息）
            raise Exception(f"LLM API返回HTTP错误，状态码: {resp.status_code}，请检查API Key和模型名称是否正确")
        except (KeyError, json.JSONDecodeError) as e:
            raise Exception(f"LLM响应解析失败: {e}")

    @staticmethod
    def _format_plain_text(text: str) -> str:
        """对纯文本做基本格式化，提升 --no-llm 模式的可读性"""
        import re
        
        # 1. 句号、问号、感叹号后换行
        text = re.sub(r'([。！？；])', r'\1\n', text)
        
        # 2. 数字编号前换行（一、二、三... / 1. 2. 3.）
        text = re.sub(r'(?=[一二三四五六七八九十]+[、．.])', r'\n', text)
        text = re.sub(r'(?=\d+[、．.])', r'\n', text)
        
        # 3. Markdown标题前换行
        text = re.sub(r'(?=#{1,3}\s)', r'\n', text)
        
        # 4. 列表标记前换行
        text = re.sub(r'(?=[\-\*]\s)', r'\n', text)
        
        # 5. 清理多余空行（最多保留一个）
        text = re.sub(r'\n{3,}', r'\n\n', text)
        
        return text.strip()

    # ============================================================
    # 功能：保存文件
    # ============================================================
    def _save_file(self, content: str, format_type: str, url: str, title: str = "") -> Path:
        """
        保存内容到文件
        
        Returns:
            文件路径
        """
        # 生成文件名（基于URL和时间）
        
        # 从标题提取文件名关键词
        name_part = "webpage"
        if title:
            # 取标题前20个字，去掉特殊字符
            name_part = re.sub(r'[^\w\u4e00-\u9fff]', "", title)[:20]
        elif url:
            # 从URL提取域名+路径关键词
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            path_parts = [p for p in parsed.path.split("/") if p and not p.startswith("{")]
            path_key = "_".join(path_parts[:2]) if path_parts else ""
            name_part = f"{domain}_{path_key}" if path_key else domain
            name_part = re.sub(r"[^\w]", "_", name_part)[:30]

        ext_map = {
            "summary": ".md",
            "bullets": ".md",
            "table": ".md",
            "organize": ".md",
            "json": ".json",
            "csv": ".csv",
        }
        # 如果配置了自定义扩展名，覆盖默认
        custom_ext = self.config.get("output_extension", "").strip()
        if custom_ext:
            custom_ext = "." + custom_ext.lstrip(".")
            ext = custom_ext
        else:
            ext = ext_map.get(format_type, ".md")

        filename = f"{name_part}_{timestamp}{ext}"
        filepath = self.output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"文件已保存: {filepath}")
        return filepath

    # ============================================================
    # 主流程：读取并分析内容
    # ============================================================
    async def _read_and_analyze(
        self,
        url: str,
        format_type: str = "summary",
        use_cdp: bool = False,
        no_llm: bool = False,
    ) -> tuple:
        """
        读取内容并分析
        
        Returns:
            (分析结果文本, 文件路径, 原始文本长度)
        """
        # 第一步：读取内容
        url_type = self._detect_url_type(url) if url else "html"
        logger.info(f"URL类型: {url_type}")

        # SSRF防护：检查URL安全性（只对非CDP模式的有效URL进行检查）
        if url and not use_cdp and not self._is_safe_url(url):
            raise ValueError(f"不安全的URL（指向内网地址），已阻止访问: {url}")

        raw_text = ""
        if url_type == "pdf":
            raw_text = await self._read_pdf(url)
        elif url_type == "docx":
            raw_text = await self._read_docx(url)
        else:
            # 尝试Playwright动态读取
            try:
                raw_text = await self._read_with_playwright(url, use_cdp=use_cdp)
            except Exception as e:
                if use_cdp:
                    # CDP模式下不回退到静态模式（因为没有URL可用）
                    raise Exception(
                        "CDP模式连接失败，请确保：\n"
                        "1. Chrome已用 --remote-debugging-port=9222 参数启动\n"
                        "2. 或者直接提供URL：/readweb <网址>"
                    )
                # 非CDP模式回退到静态方式
                logger.warning(f"Playwright读取失败({e})，回退到静态模式")
                logger.warning(f"Playwright错误详情: {type(e).__name__}: {e}")
                raw_text = await self._read_static(url)

        if not raw_text.strip():
            raise Exception("未能提取到任何文字内容")

        logger.info(f"原始内容长度: {len(raw_text)} 字符")

        # 第二步：分析（或跳过）
        if no_llm:
            result_text = self._format_plain_text(raw_text)
            logger.info("跳过LLM分析（--no-llm）")
        else:
            result_text = await self._analyze_with_llm(raw_text, format_type, url)

        # 第三步：保存文件
        # 如果是no_llm模式，额外加一个说明头
        if no_llm:
            header = (
                f"# 网页原始内容\n\n"
                f"来源: {url}\n"
                f"提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"---\n\n"
            )
            result_text = header + result_text

        # 从内容中提取标题
        file_title = ""
        if result_text.startswith("标题: "):
            file_title = result_text.split("\n")[0].replace("标题: ", "").strip()
        
        filepath = self._save_file(result_text, format_type, url, title=file_title)

        return result_text, filepath, len(raw_text)

    @staticmethod
    def _parse_readweb_args(message: str) -> dict:
        """
        从消息文本中手动解析 /readweb 命令的参数
        
        支持的语法:
            /readweb <url>
            /readweb <url> --format <format> [--no-llm]
            /readweb --format <format> [--no-llm]
            /readweb --no-llm
            /readweb（CDP模式）
        """
        # 去掉命令前缀 /readweb
        text = message.strip()
        for prefix in ["/readweb", "／readweb", "readweb"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        result = {
            "url": None,
            "format": "summary",
            "no_llm": False,
        }

        # 如果没有任何参数，直接返回
        if not text:
            return result

        # 解析 --format 参数
        format_match = re.search(r'--format\s+(\S+)', text)
        valid_formats = ["summary", "bullets", "table", "organize", "json", "csv"]
        if format_match:
            fmt = format_match.group(1).lower()
            if fmt in valid_formats:
                result["format"] = fmt

        # 解析 --no-llm 参数
        if "--no-llm" in text:
            result["no_llm"] = True

        # 提取URL：按空格切分，过滤掉 -- 开头的参数，取第一个有效URL
        parts = text.split()
        url_candidate = None
        for part in parts:
            if not part.startswith("--"):
                url_candidate = part
                break
        if url_candidate and WebReaderPlugin._is_valid_url(url_candidate):
            result["url"] = url_candidate

        return result

    # ============================================================
    # 命令: /readweb
    # ============================================================
    @filter.command("readweb")
    async def readweb(self, event: AstrMessageEvent):
        """
        读取网页/PDF/Word内容并用LLM分析保存
        
        # 调试：打印收到的消息原文
        logger.info(f"收到消息原文: {event.message_str}")
        使用方式:
            /readweb [url] [--format <format>] [--no-llm]
        
        参数:
            url: 目标网址（留空则尝试连接当前Chrome）
            --format: summary(默认) / bullets / table / json / csv
            --no-llm: 跳过LLM分析，只提取原始文字
        """
        # --- 手动解析参数 ---
        args = self._parse_readweb_args(event.message_str)
        url = args["url"]
        format_type = args["format"]
        no_llm = args["no_llm"]
        
        # 如果用户没有指定 --format，使用配置中的默认格式
        if not re.search(r'--format\s+\S+', event.message_str):
            default_fmt = self.config.get("default_format", "summary")
            if default_fmt in ["summary", "bullets", "table", "json", "csv"]:
                format_type = default_fmt

        # 记录请求来源
        source_url = url or "当前浏览器标签页"
        yield event.plain_result(f"🔍 正在读取: {source_url}")

        try:
            # 判断是否使用CDP模式
            use_cdp = not bool(url)
            
            # 调试：打印收到的消息（当URL为空时）
            if not url:
                logger.info(f"URL为空! 收到的消息原文: '{event.message_str}'")
                yield event.plain_result(f"🪲 调试: 收到消息原文 → `{event.message_str}`")

            # 执行读取和分析
            yield event.plain_result("⏳ 正在提取文字内容...")
            
            # 如果没配API Key，自动降级为 --no-llm 模式
            if not no_llm and not self.config.get("llm_api_key", ""):
                no_llm = True
                yield event.plain_result("ℹ️ 未检测到LLM API Key，自动降级为纯文本模式（--no-llm）")
            
            result_text, filepath, raw_len = await self._read_and_analyze(
                url=url or "",
                format_type=format_type,
                use_cdp=use_cdp,
                no_llm=bool(no_llm),
            )

            # --- 返回结果 ---
            file_size = os.path.getsize(filepath)
            file_size_str = (
                f"{file_size / 1024:.1f} KB" if file_size > 1024 else f"{file_size} B"
            )

            response = (
                f"✅ **处理完成！**\n"
                f"📄 来源: {source_url}\n"
                f"📏 原始内容: {raw_len} 字符\n"
                f"📝 输出格式: {format_type}\n"
                f"💾 文件大小: {file_size_str}\n"
                f"📁 保存位置: `{filepath}`\n\n"
                f"--- 内容预览（前500字）---\n\n"
                f"{result_text[:500]}"
            )
            if len(result_text) > 500:
                response += f"\n\n...（完整内容共 {len(result_text)} 字，已保存到文件）"

            yield event.plain_result(response)

        except ImportError as e:
            yield event.plain_result(
                f"❌ **缺少依赖库**\n请安装: `pip install {str(e).split('安装')[-1]}`"
            )
        except TimeoutError as e:
            yield event.plain_result(f"⏰ **超时**: {e}")
        except ValueError as e:
            yield event.plain_result(f"⚠️ **配置错误**: {e}")
        except Exception as e:
            logger.exception("处理过程中出现错误")
            yield event.plain_result(f"❌ **出错了**: {str(e)}")

    # ============================================================
    # 命令: /webreader_help
    # ============================================================
    @filter.command("webreader_help")
    async def webreader_help(self, event: AstrMessageEvent):
        """显示网页读取器的详细帮助"""
        help_text = (
            "📖 **网页读取器 - 使用帮助**\n\n"
            "**命令:**\n"
            "  `/readweb <url>` — 读取指定网页并用LLM分析\n"
            "  `/readweb` — 连接当前Chrome，读取当前标签页\n\n"
            "**可选参数:**\n"
            "  `--format <格式>` — 输出格式\n"
            "    • summary - 摘要整理（默认）\n"
            "    • bullets - 要点列表\n"
            "    • table   - 表格形式\n"
            "    • json    - JSON格式\n"
            "    • csv     - CSV格式\n"
            "  `--no-llm` — 跳过LLM分析，只保存原始文字\n\n"
            "**支持的文件类型:**\n"
            "  • 网页（HTML，含动态加载页面）\n"
            "  • PDF文档\n"
            "  • Word文档（.docx）\n\n"
            "**配置（管理面板 → 插件配置）:**\n"
            "  • llm_api_base - API地址\n"
            "  • llm_api_key  - API密钥\n"
            "  • llm_model_name - 模型名称\n\n"
            "**示例:**\n"
            "  `/readweb https://example.com`\n"
            "  `/readweb https://example.com --format bullets`\n"
            "  `/readweb https://example.com --no-llm`\n"
            "  `/readweb --format table`（需先开启Chrome调试模式）"
        )
        yield event.plain_result(help_text)


    # ============================================================

