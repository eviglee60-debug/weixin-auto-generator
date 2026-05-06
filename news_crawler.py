"""多源新闻爬取器 - 支持10+官方渠道"""

import requests
from bs4 import BeautifulSoup
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
        self.sources = Config.NEWS_SOURCES
        self.seen_hashes = set()

    def contains_sensitive(self, text):
        """检查是否包含敏感词"""
        for word in self.sensitive_words:
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
        """从标题提取关键词"""
        title = re.sub(r'^(关注|解读|聚焦|速看|解析|重磅|突发|最新)', '', title)
        words = re.findall(r'[一-鿿]{2,8}', title)
        return words[:5]

    def crawl_all(self, recent_keywords=None):
        """
        并发爬取所有源，返回按分类分组的新闻。

        Args:
            recent_keywords: 最近已发布文章的关键词集合，用于去重
        """
        self.seen_hashes = set()
        all_news = []

        # 使用线程池并发爬取
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {}
            for source_id, source_cfg in self.sources.items():
                future = executor.submit(self._crawl_source, source_id, source_cfg)
                futures[future] = source_id

            for future in as_completed(futures, timeout=30):
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

        # 过滤：敏感词 + 批次去重 + 历史去重
        filtered = []
        for news in all_news:
            if self.contains_sensitive(news["title"]):
                continue
            if self.is_duplicate(news["title"]):
                continue
            if recent_keywords and self._is_similar_to_recent(news["title"], recent_keywords):
                continue
            news["keywords"] = self.extract_keywords(news["title"])
            filtered.append(news)

        # 按分类分组
        grouped = {"patent": [], "general_ip": [], "hot_topic": []}
        for news in filtered:
            cat = news.get("category", "hot_topic")
            if cat in grouped:
                grouped[cat].append(news)

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
        # SAMR 走专用 API
        if source_id == "samr" and "api_url" in source_cfg:
            return self._crawl_samr_api(source_cfg)

        news_list = []
        base_url = source_cfg.get("base_url", "")
        # 如果没有配置base_url，从URL推导
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

                # 针对性提取策略
                if source_id in ("spc", "spc_ip"):
                    items = self._extract_spc_items(soup, base_url, source_id)
                elif source_id == "cnipa":
                    items = self._extract_cnipa_items(soup)
                else:
                    items = self._extract_news_items(soup, source_id, base_url)

                for item in items:
                    if len(item.get("title", "")) > 8:
                        item["source"] = source_cfg["name"]
                        item["category"] = source_cfg["category"]
                        item["region"] = source_cfg["region"]
                        news_list.append(item)

                if news_list:
                    break  # 有结果就不用 fallback URL
            except Exception as e:
                logger.debug(f"[{source_id}] {url} 请求失败: {e}")
                continue

        return news_list[:5]  # 每个源最多5条

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

    def _extract_spc_items(self, soup, base_url, source_id):
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
                'filing', 'policy', 'about us', 'home',
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
        """计算新闻优先级分数"""
        score = 0

        # 官方源优先
        official_sources = [
            "国家知识产权局", "市场监管总局", "最高人民法院",
            "最高人民法院知识产权法庭", "美国专利商标局", "欧洲专利局",
        ]
        if news.get("source", "") in official_sources:
            score += 10

        # 标题包含关键词加分
        important_keywords = [
            "判决", "裁定", "侵权", "保护", "新规", "修改", "发布",
            "授权", "申请", "审查", "纠纷", "赔偿", "无效",
        ]
        for kw in important_keywords:
            if kw in news.get("title", ""):
                score += 2

        # 标题长度适中加分
        title_len = len(news.get("title", ""))
        if 15 <= title_len <= 50:
            score += 3

        return score

    def _is_similar_to_recent(self, title, recent_keywords, threshold=0.6):
        """检查标题是否与最近已发布的文章相似"""
        if not recent_keywords:
            return False

        title_words = set(self.extract_keywords(title))
        if not title_words:
            return False

        for recent_title in recent_keywords:
            recent_words = set(re.findall(r'[一-鿿]{2,8}', recent_title))
            if not recent_words:
                continue
            overlap = len(title_words & recent_words)
            total = min(len(title_words), len(recent_words))
            if total > 0 and overlap / total >= threshold:
                return True

        return False
