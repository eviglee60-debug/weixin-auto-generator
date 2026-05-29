"""多源新闻爬取器 - 支持10+官方渠道"""

import requests
from bs4 import BeautifulSoup
import feedparser
import logging
import random
import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class NewsCrawler:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        from config import Config
        self.sensitive_words = Config.SENSITIVE_WORDS
        self.meeting_filter = Config.MEETING_FILTER_KEYWORDS
        self.sources = Config.NEWS_SOURCES
        self.seen_hashes = set()

    def contains_sensitive(self, text):
        """检查是否包含敏感词"""
        for word in self.sensitive_words:
            if word in text:
                return True
        return False

    def contains_meeting(self, text):
        """检查是否为会议/活动类内容"""
        for word in self.meeting_filter:
            if word in text:
                return True
        return False

    def get_title_hash(self, title):
        return hashlib.md5(title.encode()).hexdigest()

    def is_duplicate(self, title):
        """批次内去重"""
        title_hash = self.get_title_hash(title)
        if title_hash in self.seen_hashes:
            return True
        self.seen_hashes.add(title_hash)
        return False

    def extract_keywords(self, title):
        """从标题提取关键词（先清洗干扰标点，避免智能引号等造成分块偏移）"""
        title = re.sub(r'^(关注|解读|聚焦|速看|解析|重磅|突发|最新)', '', title)
        # 清除干扰标点：智能引号/中文引号/全角符号
        title = re.sub(r'[“”‘’「」『』「」『』""'']', '', title)
        words = re.findall(r'[一-鿿]{2,8}', title)
        return words[:5]

    def crawl_all(self, recent_titles=None):
        """
        并发爬取所有源，返回按分类分组的新闻。

        Args:
            recent_titles: 最近已发布和已选用的文章标题集合，用于去重（比对爬取主题）
        """
        self.seen_hashes = set()
        all_news = []

        # 使用线程池并发爬取（I/O密集型任务，6线程）
        max_workers = 6
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for source_id, source_cfg in self.sources.items():
                future = executor.submit(self._crawl_source, source_id, source_cfg)
                futures[future] = source_id

            for future in as_completed(futures):
                source_id = futures[future]
                try:
                    news_list = future.result()
                    if news_list:
                        all_news.extend(news_list)
                        logger.info(f"[{source_id}] 获取到 {len(news_list)} 条新闻")
                    else:
                        logger.info(f"[{source_id}] 无新闻")
                except Exception as e:
                    logger.error(f"[{source_id}] 爬取异常: {e}")

        # 过滤：敏感词 + 批次去重 + 历史去重（比对爬取主题）+ 公司公告
        filtered = []
        for news in all_news:
            if self.contains_sensitive(news["title"]):
                continue
            if self.contains_meeting(news["title"]):
                continue
            if self.is_duplicate(news["title"]):
                continue
            if recent_titles and self._is_similar_to_recent(news["title"], recent_titles):
                continue
            if self._is_company_announcement(news["title"]):
                continue
            if self._is_memorial(news["title"]):
                continue
            news["keywords"] = self.extract_keywords(news["title"])
            filtered.append(news)

        # 按分类分组
        grouped = {"patent": [], "general_ip": [], "hot_topic": []}
        for news in filtered:
            cat = news.get("category", "hot_topic")
            if cat in grouped:
                grouped[cat].append(news)

        # 基于内容关键词的二次分类（补充泛知产内容）
        # 泛知产关键词：商标、著作权、版权、商业秘密、不正当竞争、开源、数据合规
        general_ip_keywords = ["商标", "著作权", "版权", "商业秘密", "不正当竞争", "开源", "数据合规",
                              "反垄断", "反不正当竞争", "地理标志", "集成电路布图设计"]
        # 从 patent 和 hot_topic 中移动符合条件的到 general_ip
        additional_general_ip = []
        for cat in ["patent", "hot_topic"]:
            remaining = []
            for news in grouped[cat]:
                title = news.get("title", "")
                if any(kw in title for kw in general_ip_keywords):
                    news_copy = news.copy()
                    news_copy["category"] = "general_ip"
                    additional_general_ip.append(news_copy)
                else:
                    remaining.append(news)
            grouped[cat] = remaining
        grouped["general_ip"].extend(additional_general_ip)

        # 检查 general_ip 文章是否真的含IP关键词（非IP源如SAMR会混入食品/行政内容）
        ip_check_kw = ["商标", "著作权", "版权", "商业秘密", "不正当竞争", "专利",
                       "知识产权", "反垄断", "反不正当竞争", "地理标志", "集成电路",
                       "侵权", "赔偿", "发明", "实用新型", "外观设计"]
        legit_ip = []
        for news in grouped["general_ip"]:
            title = news.get("title", "")
            if any(kw in title for kw in ip_check_kw):
                legit_ip.append(news)
            else:
                # 不含IP关键词 → 移到 hot_topic（仍有可能是好内容，但不算泛知产）
                news_copy = news.copy()
                news_copy["category"] = "hot_topic"
                grouped["hot_topic"].append(news_copy)
        grouped["general_ip"] = legit_ip

        # 百度新闻兜底
        for cat in ["patent", "general_ip", "hot_topic"]:
            if not grouped[cat]:
                fallback = self._crawl_baidu_fallback(cat)
                if fallback:
                    grouped[cat].extend(fallback)

        return grouped

    def select_articles(self, grouped, count_per_category=1):
        """每组选最重要的文章，返回选中列表和待用列表"""
        selected = []
        pending = []

        for cat in ["patent", "general_ip", "hot_topic"]:
            news_list = grouped.get(cat, [])
            if not news_list:
                continue

            # 按优先级排序：官方源 > 时效性 > 标题长度
            news_list.sort(key=lambda x: self._priority_score(x), reverse=True)

            # 选中第一条
            selected.append(news_list[0])
            # 其余存入待用队列
            pending.extend(news_list[1:])

        return selected[:count_per_category * 3], pending

    def _crawl_source(self, source_id, source_cfg):
        """爬取单个源"""
        news_list = []

        if source_id == "spc_guide_cases":
            items = self._crawl_spc_guide_cases(source_cfg)
        elif source_id == "spc_gazette":
            items = self._crawl_spc_gazette(source_cfg)
        elif source_id.startswith("cnipa") and "api_url" in source_cfg:
            items = self._crawl_cnipa_api(source_cfg)
        elif source_id == "samr" and "api_url" in source_cfg:
            items = self._crawl_samr_api(source_cfg)
        elif "rss_url" in source_cfg:
            items = self._crawl_rss(source_cfg)
        else:
            items = self._crawl_source_html(source_id, source_cfg)

        for item in items:
            if len(item.get("title", "")) > 8:
                item["source"] = source_cfg["name"]
                item["category"] = source_cfg["category"]
                item["region"] = source_cfg["region"]
                news_list.append(item)

        return news_list[:5]  # 每个源最多5条

    def _crawl_source_html(self, source_id, source_cfg):
        """通过HTML爬取单个源"""
        items = []
        base_url = source_cfg.get("base_url", "")
        if not base_url:
            from urllib.parse import urlparse
            parsed = urlparse(source_cfg["url"])
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        urls = [source_cfg["url"]]
        if "fallback_urls" in source_cfg:
            urls.extend(source_cfg["fallback_urls"])

        for url in urls:
            try:
                resp = requests.get(url, headers=self.headers, timeout=15, verify=False,
                                    allow_redirects=True)
                if resp.status_code != 200:
                    continue

                resp.encoding = resp.apparent_encoding or 'utf-8'
                soup = BeautifulSoup(resp.text, 'html.parser')

                if source_id in ("spc", "spc_ip"):
                    items = self._extract_spc_items(soup, base_url, source_id)
                elif source_id.startswith("cnipa"):
                    items = self._extract_cnipa_items(soup)
                else:
                    items = self._extract_news_items(soup, source_id, base_url)

                if items:
                    break
            except Exception as e:
                logger.debug(f"[{source_id}] {url} 请求失败: {e}")
                continue

        return items

    def enrich_with_images(self, news_list, max_per_item=3):
        """为新闻列表补充源文章页面的图片"""
        for news in news_list:
            article_url = news.get("url", "")
            if not article_url or not article_url.startswith("http"):
                news.setdefault("images", [])
                logger.warning(f"  跳过图片提取 - 无有效URL: {news.get('title', '')[:30]}")
                continue
            try:
                logger.info(f"  提取图片: {article_url[:60]}...")
                images = self._extract_images_from_article(article_url)
                news["images"] = images[:max_per_item]
                logger.info(f"  提取到 {len(images)} 张图片")
            except Exception as e:
                logger.error(f"  提取图片失败 [{article_url}]: {e}")
                news.setdefault("images", [])
        return news_list

    def _extract_images_from_article(self, article_url):
        """访问文章详情页，提取正文区域的图片URL"""
        images = []
        skip_patterns = [
            'logo', 'icon', 'banner', 'avatar', 'qrcode', 'weixin',
            'wechat', 'share', 'arrow', 'loading', 'sprite',
            '.gif', 'ico/', 'foot', 'header', 'nav', 'menu',
        ]
        try:
            resp = requests.get(article_url, headers=self.headers, timeout=15, verify=False)
            if resp.status_code != 200:
                logger.warning(f"    HTTP状态码: {resp.status_code}")
                return images
            resp.encoding = resp.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')

            # 优先在正文区域找图
            content_area = (
                soup.find('div', class_=re.compile(r'(article|content|detail|text|body|TRS_Editor|main)', re.I))
                or soup.find('div', id=re.compile(r'(article|content|detail|text|body|main)', re.I))
                or soup.find('article')
                or soup.find('main')
                or soup  # fallback to whole page
            )

            all_imgs = content_area.find_all('img', src=True)
            logger.info(f"    页面图片总数: {len(all_imgs)}")

            for img in all_imgs:
                src = img['src']
                if not src or src.startswith('data:'):
                    continue
                # 补全相对路径
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    from urllib.parse import urlparse
                    parsed = urlparse(article_url)
                    src = f"{parsed.scheme}://{parsed.netloc}{src}"
                elif not src.startswith('http'):
                    continue

                # 过滤非内容图片
                src_lower = src.lower()
                if any(p in src_lower for p in skip_patterns):
                    logger.debug(f"    跳过图片(匹配过滤规则): {src[:60]}")
                    continue

                # 检查尺寸属性（过滤小图标）
                width = img.get('width', '')
                height = img.get('height', '')
                if width and width.isdigit() and int(width) < 150:
                    logger.debug(f"    跳过图片(宽度{width}): {src[:60]}")
                    continue
                if height and height.isdigit() and int(height) < 100:
                    logger.debug(f"    跳过图片(高度{height}): {src[:60]}")
                    continue

                # 检查style中的尺寸
                style = img.get('style', '')
                if 'width' in style:
                    w_match = re.search(r'width:\s*(\d+)', style)
                    if w_match and int(w_match.group(1)) < 150:
                        logger.debug(f"    跳过图片(style宽度{w_match.group(1)}): {src[:60]}")
                        continue

                if src not in images:
                    images.append(src)
                    logger.info(f"    有效图片: {src[:80]}")

        except Exception as e:
            logger.error(f"    访问文章页失败: {e}")

        return images

    def _crawl_cnipa_api(self, source_cfg):
        """国家知识产权局 - 通过 dataproxy.jsp API 获取 JS 渲染的列表内容"""
        news_list = []
        seen = set()
        try:
            resp = requests.get(
                source_cfg["api_url"],
                params=source_cfg["api_params"],
                headers=self.headers,
                timeout=15,
                verify=False,
            )
            if resp.status_code != 200:
                logger.warning(f"[cnipa] API HTTP {resp.status_code}")
                return news_list

            # 响应格式: <record><![CDATA[<li><a href="art/...">title</a><span>date</span></li>]]></record>
            import re as regex
            for match in regex.finditer(
                r'<a\s+href="([^"]+)"[^>]*>([^<]+)</a>',
                resp.text,
            ):
                href = match.group(1)
                title = match.group(2).strip()
                if len(title) < 8:
                    continue
                if not href.startswith("http"):
                    href = "https://www.cnipa.gov.cn/" + href.lstrip("/")
                title_key = hashlib.md5(title.encode()).hexdigest()
                if title_key in seen:
                    continue
                seen.add(title_key)
                news_list.append({"title": title, "url": href})

            logger.info(f"[cnipa] API 获取到 {len(news_list)} 条新闻")
        except Exception as e:
            logger.error(f"[cnipa] API 爬取异常: {e}")
        return news_list

    def _crawl_samr_api(self, source_cfg):
        """市场监管总局 - 通过API获取JS渲染内容"""
        news_list = []
        try:
            resp = requests.get(
                source_cfg["api_url"],
                params=source_cfg["api_params"],
                headers=self.headers,
                timeout=15,
                verify=False,
            )
            if resp.status_code == 200:
                data = resp.json()
                html_content = data.get("data", {}).get("html", "")
                if html_content:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    for a in soup.find_all('a', href=True):
                        title = a.get("title", "") or a.get_text(strip=True)
                        href = a["href"]
                        if len(title) > 8 and href.endswith(".html"):
                            if not href.startswith("http"):
                                href = "https://www.samr.gov.cn" + href
                            news_list.append({"title": title, "url": href})
        except Exception as e:
            logger.debug(f"[samr] API请求失败: {e}")
        return news_list[:5]

    def _crawl_rss(self, source_cfg):
        """通过 RSS/Atom feed 爬取新闻源"""
        news_list = []
        rss_url = source_cfg.get("rss_url", "")
        if not rss_url:
            return news_list

        try:
            logger.info(f"[rss] 解析 feed: {rss_url}")
            # 用 requests 先获取内容（使用爬虫UA，避免被Cloudflare拦截），
            # 再用 feedparser 解析响应文本
            resp = requests.get(rss_url, headers=self.headers, timeout=15, verify=False)
            if resp.status_code != 200:
                logger.warning(f"[rss] HTTP {resp.status_code}: {rss_url}")
                return news_list

            feed = feedparser.parse(resp.text)

            if feed.bozo and not feed.entries:
                logger.warning(f"[rss] feed 解析失败: {feed.bozo_exception}")
                return news_list

            entries = feed.entries[:10]  # 取最近10条
            for entry in entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()

                # 清理 HTML 标签
                if re.search(r'<[^>]+>', title):
                    title = re.sub(r'<[^>]+>', '', title)

                if len(title) < 8:
                    continue

                news_list.append({"title": title, "url": link})

            logger.info(f"[rss] {source_cfg.get('name')} 获取 {len(news_list)} 条")
        except Exception as e:
            logger.error(f"[rss] {rss_url} 爬取异常: {e}")

        return news_list[:5]

    def _crawl_spc_guide_cases(self, source_cfg):
        """最高人民法院指导案例 - 多页爬取 + IP相关过滤"""
        news_list = []
        base_url = source_cfg.get("base_url", "https://www.court.gov.cn")
        max_pages = source_cfg.get("max_pages", 3)
        seen_urls = set()

        # IP相关关键词（只选取知识产权类指导案例）
        ip_keywords = [
            "专利", "商标", "著作权", "版权", "不正当竞争", "商业秘密",
            "知识产权", "植物新品种", "集成电路布图设计", "计算机软件",
            "发明", "实用新型", "外观设计", "垄断", "技术秘密",
        ]

        for page_num in range(1, max_pages + 1):
            if page_num == 1:
                page_url = source_cfg["url"]
            else:
                page_url = f"{base_url}/shenpan/gengduo/77_{page_num}.html"

            try:
                logger.info(f"[spc_guide_cases] 爬取第{page_num}页: {page_url}")
                resp = requests.get(page_url, headers=self.headers, timeout=15,
                                   verify=False, allow_redirects=True)
                if resp.status_code != 200:
                    logger.warning(f"[spc_guide_cases] 第{page_num}页 HTTP {resp.status_code}")
                    continue

                resp.encoding = resp.apparent_encoding or 'utf-8'
                soup = BeautifulSoup(resp.text, 'html.parser')

                page_items = 0
                for a in soup.find_all('a', href=True):
                    href = a["href"]
                    if "/shenpan/xiangqing/" not in href:
                        continue

                    # 优先取 title 属性（完整案由），否则取链接文本
                    title = (a.get("title", "") or a.get_text(strip=True)).strip()
                    if not title or len(title) < 10:
                        continue

                    # 补全URL
                    if href.startswith("/"):
                        href = base_url + href

                    # URL去重
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)

                    # IP相关性过滤
                    if not any(kw in title for kw in ip_keywords):
                        continue

                    news_list.append({"title": title, "url": href})
                    page_items += 1

                logger.info(f"[spc_guide_cases] 第{page_num}页找到 {page_items} 条IP相关案例")

                # 每页都会抓，凑够10条以上就停止翻页
                if len(news_list) >= 10:
                    break

            except Exception as e:
                logger.error(f"[spc_guide_cases] 第{page_num}页爬取异常: {e}")
                continue

        logger.info(f"[spc_guide_cases] 共获取 {len(news_list)} 条IP相关指导案例")
        return news_list

    def _crawl_spc_gazette(self, source_cfg):
        """最高人民法院公报 - 爬取 fabu.html 主站 + 司法解释/司法文件/通知等栏目页"""
        news_list = []
        base_url = source_cfg.get("base_url", "https://www.court.gov.cn")
        max_pages = source_cfg.get("max_pages", 2)
        columns = source_cfg.get("columns", [])
        seen_urls = set()

        ip_keywords = [
            "专利", "商标", "著作权", "版权", "不正当竞争", "商业秘密",
            "知识产权", "植物新品种", "集成电路布图设计", "计算机软件",
            "发明", "实用新型", "外观设计", "垄断", "技术秘密",
            "反不正当竞争", "反垄断", "数据", "信息网络",
        ]

        for col_path in columns:
            pages = [col_path]
            # 栏目列表页支持分页: /fabu/gengduo/16.html → /fabu/gengduo/16_2.html
            if "/gengduo/" in col_path:
                for p in range(2, max_pages + 1):
                    pages.append(col_path.replace(".html", f"_{p}.html"))

            for page_path in pages:
                page_url = base_url + page_path
                try:
                    logger.info(f"[spc_gazette] 爬取: {page_url}")
                    resp = requests.get(page_url, headers=self.headers, timeout=15,
                                        verify=False, allow_redirects=True)
                    if resp.status_code != 200:
                        logger.warning(f"[spc_gazette] HTTP {resp.status_code}: {page_url}")
                        continue

                    resp.encoding = resp.apparent_encoding or 'utf-8'
                    soup = BeautifulSoup(resp.text, 'html.parser')

                    page_items = 0
                    for a in soup.find_all('a', href=True):
                        href = a["href"]
                        if "xiangqing" not in href:
                            continue

                        title = (a.get("title", "") or a.get_text(strip=True)).strip()
                        if not title or len(title) < 10:
                            continue

                        # 补全URL
                        if href.startswith("/"):
                            href = base_url + href
                        elif not href.startswith("http"):
                            continue

                        if href in seen_urls:
                            continue
                        seen_urls.add(href)

                        # IP相关性过滤
                        if not any(kw in title for kw in ip_keywords):
                            continue

                        news_list.append({"title": title, "url": href})
                        page_items += 1

                    logger.info(f"[spc_gazette] {page_path} 找到 {page_items} 条IP相关")

                except Exception as e:
                    logger.error(f"[spc_gazette] {page_url} 爬取异常: {e}")
                    continue

        logger.info(f"[spc_gazette] 共获取 {len(news_list)} 条IP相关公报内容")
        return news_list

        """最高人民法院 / 最高法IP庭 - 基于<a>标签title属性提取"""
        items = []
        seen_urls = set()
        for a in soup.find_all('a', href=True):
            title = (a.get("title", "") or a.get_text(strip=True)).strip()
            href = a["href"]
            if not title or len(title) < 8:
                continue
            # 补全相对路径
            if href.startswith("/"):
                href = base_url + href
            elif not href.startswith("http"):
                continue
            # 只保留新闻详情链接
            if source_id == "spc" and "xiangqing" not in href:
                continue
            if source_id == "spc_ip" and "view-" not in href:
                continue
            # 用URL去重（同一文章可能有多个链接文本）
            if href in seen_urls:
                continue
            seen_urls.add(href)
            items.append({"title": title, "url": href})
        return items

    def _extract_cnipa_items(self, soup):
        """国家知识产权局 - 提取/art/路径的新闻链接"""
        items = []
        seen = set()
        for a in soup.find_all('a', href=True):
            title = a.get_text(strip=True)
            href = a["href"]
            if not title or len(title) < 8:
                continue
            if "/art/" not in href:
                continue
            if not href.startswith("http"):
                href = "https://www.cnipa.gov.cn" + href
            title_key = hashlib.md5(title.encode()).hexdigest()
            if title_key in seen:
                continue
            seen.add(title_key)
            items.append({"title": title, "url": href})
        return items

    def _extract_news_items(self, soup, source_id, base_url=""):
        """通用新闻链接提取"""
        items = []
        seen = set()

        # 策略1：找所有 <a> 标签中看起来像新闻标题的
        for a in soup.find_all('a', href=True):
            title = a.get_text(strip=True)
            href = a['href']

            # 过滤条件
            if not title or len(title) < 8 or len(title) > 200:
                continue
            # 排除导航、菜单等
            if any(skip in title.lower() for skip in [
                '首页', '关于', '联系', '登录', '注册', '更多', '下一页',
                '上一页', '导航', 'footer', 'header', 'menu',
                'copyright', 'icp', '备案', '网站地图', 'contact us',
                'patent basics', 'go to overview', 'search',
            ]):
                continue
            # 排除非新闻链接
            if any(skip in href.lower() for skip in [
                'javascript:', '#', '.css', '.js', '.png', '.jpg',
                'mailto:', 'tel:',
            ]):
                continue

            title_key = hashlib.md5(title.encode()).hexdigest()
            if title_key in seen:
                continue
            seen.add(title_key)

            # 补全URL
            if href.startswith('/'):
                if base_url:
                    href = base_url.rstrip('/') + href
                else:
                    continue  # 没有base_url则跳过
            elif not href.startswith('http'):
                continue

            items.append({"title": title, "url": href})

        return items

    def _crawl_baidu_fallback(self, category):
        """百度新闻兜底爬取"""
        keyword_map = {
            "patent": ["专利 发明 实用新型", "专利侵权 判决", "PCT国际专利"],
            "general_ip": ["商标注册 著作权", "知识产权保护", "商业秘密 侵权"],
            "hot_topic": ["知识产权 热点", "法律 新规", "知识产权 判决"],
        }
        keywords = keyword_map.get(category, keyword_map["hot_topic"])
        news_list = []

        for keyword in keywords[:1]:
            try:
                url = "https://www.baidu.com/s"
                params = {"wd": keyword, "tn": "news", "rtt": 1, "bsst": 1}
                resp = requests.get(url, params=params, headers=self.headers, timeout=15)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for a in soup.select('.news-title_1YtI1 a, .c-title a'):
                        title = a.get_text(strip=True)
                        if title and len(title) > 10:
                            if self._is_company_announcement(title):
                                logger.debug(f"百度兜底跳过公司公告: {title[:30]}")
                                continue
                            news_list.append({
                                "title": title,
                                "source": "百度新闻",
                                "category": category,
                                "region": "china",
                            })
                            break
            except Exception as e:
                logger.debug(f"百度新闻兜底失败 [{keyword}]: {e}")

        return news_list

    def _priority_score(self, news):
        """计算新闻优先级分数 — 奖励案例/法规/解读，惩罚会议/活动"""
        score = 0
        title = news.get("title", "")
        category = news.get("category", "")
        source = news.get("source", "")

        # 会议/党建/低价值活动类关键词 — 直接返回-100分（完全过滤）
        meeting_signals = [
            # 政治/党建
            "会议", "座谈", "调研", "考察",
            "讲话", "精神", "部署", "推进",
            "党建", "党组", "党委", "带头", "抓落实",
            # IP 低价值活动（讲座/培训/研讨会/发布会等纯通知）
            "讲座", "培训", "研讨会", "交流会", "论坛", "峰会",
            "启动仪式", "开幕式", "闭幕式", "发布会",
            "活动预告", "议程", "计划安排",
            "专利文献馆", "公益讲座", "宣讲会",
            "服务万里行", "督察组", "统计督察",
            # EPO/国际组织低价值内容
            "监督审核", "年度研讨会", "合作备忘录",
        ]
        for kw in meeting_signals:
            if kw in title:
                return -100  # 直接返回-100分，完全过滤

        # 最高法公报 — 最高优先级（司法解释/司法文件/通知）
        if "最高人民法院公报" in source:
            score += 30

        # 最高法指导案例
        if "最高人民法院指导案例" in source:
            score += 20

        # 官方源优先
        official_sources = [
            "国家知识产权局", "市场监管总局", "最高人民法院",
            "最高人民法院知识产权法庭", "美国专利商标局", "欧洲专利局",
        ]
        if source in official_sources:
            score += 10

        # 实质法律内容高分关键词（案例/法规/解读）
        legal_keywords = [
            "判决", "裁定", "案例", "典型", "指导性",
            "侵权", "赔偿", "无效", "纠纷",
        ]
        for kw in legal_keywords:
            if kw in title:
                score += 4

        # 法规/政策关键词
        regulatory_keywords = [
            "新规", "法规", "规章", "办法", "条例", "通知",
            "解读", "修订", "修改", "发布",
            "保护", "审查", "授权", "申请",
        ]
        for kw in regulatory_keywords:
            if kw in title:
                score += 2

        # 实质内容检查：无法律/法规关键词 = 纯公告/统计数字，严重扣分
        all_substance_keywords = legal_keywords + regulatory_keywords
        has_substance = any(kw in title for kw in all_substance_keywords)
        if not has_substance:
            score -= 15

        # 标题长度适中加分
        title_len = len(title)
        if 15 <= title_len <= 50:
            score += 3

        return score

    def _is_similar_to_recent(self, title, recent_titles, threshold=0.6):
        """检查标题是否与最近已发布/已选用的文章标题相似（比对爬取主题）

        中文走关键词重叠率（阈值0.6），英文走单词重叠率（阈值0.4，因为英文标题词数少）。
        历史数据中的智能引号等问题在 extract_keywords 内部统一清洗。
        """
        if not recent_titles:
            return False

        title_words = set(self.extract_keywords(title))
        is_english = not title_words

        if is_english:
            # 英文回退：按空格分词，取3字符以上的词干
            import string as _string
            eng_words = set()
            for w in title.split():
                w = w.strip(_string.punctuation).lower()
                if len(w) >= 3:
                    eng_words.add(w)
            title_words = eng_words
            threshold_to_use = 0.4
        else:
            threshold_to_use = threshold

        if not title_words:
            return False

        for recent_title in recent_titles:
            if is_english:
                # 英文：同样分词后比较
                recent_eng = set()
                for w in recent_title.split():
                    w = w.strip(_string.punctuation).lower()
                    if len(w) >= 3:
                        recent_eng.add(w)
                recent_words = recent_eng
            else:
                # 中文：清洗标点后提取关键词
                cleaned_recent = re.sub(r'[“”‘’「」『』「」『』""'']', '', recent_title)
                recent_words = set(re.findall(r'[一-鿿]{2,8}', cleaned_recent))
            if not recent_words:
                continue
            overlap = len(title_words & recent_words)
            total = min(len(title_words), len(recent_words))
            if total > 0 and overlap / total >= threshold_to_use:
                return True

        return False

    def _is_company_announcement(self, title):
        """检查是否为公司公告（如"泰林生物:关于取得商标注册证书..."）"""
        # 匹配 "公司名:关于..." 或 "公司名：关于..." 模式
        if re.search(r'[\w]{2,10}[:：]\s*关于[取得获得收到]', title):
            return True
        # 匹配纯公司公告关键词
        announcement_patterns = [
            r'关于取得[商标专利著作权]',
            r'关于获得[商标专利著作权]',
            r'关于收到[商标专利著作权]',
            r'关于[取得获得收到].*证书',
            r'关于[取得获得收到].*注册',
        ]
        for pattern in announcement_patterns:
            if re.search(pattern, title):
                return True
        return False

    def _is_memorial(self, title):
        """检查是否为纪念/悼念/讣告类文章"""
        memorial_keywords = [
            "纪念", "悼念", "缅怀", "逝世", "讣告", "追思",
            "in memory of", "in memoriam", "remembering",
            "obituary", "passed away", "tribute to",
        ]
        title_lower = title.lower()
        for kw in memorial_keywords:
            if kw in title_lower:
                return True
        return False
