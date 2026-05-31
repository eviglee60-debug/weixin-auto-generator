"""调度器 - 每日3篇文章：专利法 + 泛知识产权 + 热点吸睛内容"""

import logging
import time
import schedule
import sys
import os
from datetime import datetime

os.makedirs("/opt/weixin-auto-generator/logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/weixin-auto-generator/logs/scheduler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

import warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

from config import Config
from news_crawler import NewsCrawler
from ai_generator import AIGenerator
from weixin_publisher import WeixinPublisher
from database import Database
from image_manager import ImageManager
from knowledge_client import KnowledgeClient
from hot_topic_finder import HotTopicFinder


class Scheduler:
    def __init__(self):
        self.crawler = NewsCrawler()
        self.generator = AIGenerator()
        self.publisher = WeixinPublisher(ai_generator=self.generator)
        self.db = Database()
        self.image_manager = ImageManager()
        self.kb_client = KnowledgeClient()
        self.hot_topic_finder = HotTopicFinder()

    def generate_and_publish(self):
        try:
            logger.info("=" * 60)
            logger.info("开始每日文章生成任务")
            logger.info("=" * 60)

            # ============================================================
            # 步骤1: 获取已发布和已选用的标题集合（用于去重）
            # ============================================================
            logger.info("步骤1: 获取去重标题集合...")
            recent_titles = self.db.get_recent_titles(days=Config.DEDUP_DAYS)
            # 合并备选库中的标题（备选库文章可被选中，但需要去重）
            pending_titles = self.db.get_all_pending_titles()
            dedup_titles = set(recent_titles) | set(pending_titles)
            logger.info(f"去重标题集合: 已发布{len(recent_titles)}个 + 备选库{len(pending_titles)}个 = {len(dedup_titles)}个")

            # ============================================================
            # 步骤2: 爬取新闻（爬取阶段去重，比对爬取主题）
            # ============================================================
            logger.info("步骤2: 爬取多源新闻...")
            grouped = self.crawler.crawl_all(recent_titles=dedup_titles)

            # ============================================================
            # 步骤3: 合并备选库文章（备选库文章可被选中，排序最高）
            # ============================================================
            logger.info("步骤3: 合并备选库文章...")
            pending_ids_in_pool = set()
            for cat in ["patent", "general_ip"]:
                pending_articles = self.db.get_pending_news(cat, limit=20)
                merged_count = 0
                for pa in pending_articles:
                    title = pa["title"]
                    # 过滤公司公告
                    if self.crawler._is_company_announcement(title):
                        self.db.mark_used_pending(pa["id"])
                        continue
                    # 过滤纪念/讣告
                    if self.crawler._is_memorial(title):
                        self.db.mark_used_pending(pa["id"])
                        continue
                    # 避免与当日新爬取文章重复（精确匹配）
                    if any(n.get("title") == title for n in grouped.get(cat, [])):
                        continue
                    # 模糊去重：比对已发布标题，避免同主题不同标题重复发布
                    if self.crawler._is_similar_to_recent(title, recent_titles):
                        self.db.mark_used_pending(pa["id"])
                        logger.debug(f"  备选库模糊去重: {title[:30]}...")
                        continue
                    # 备选库文章插入到列表头部（排序最高）
                    # 计算时效性衰减：每过1天扣2分，最多扣30分
                    created_at = pa.get("created_at")
                    if created_at:
                        days_old = (datetime.now() - created_at).days
                        age_penalty = min(days_old * 2, 30)
                    else:
                        age_penalty = 0
                    grouped[cat].insert(0, {
                        "title": title,
                        "source": pa.get("source", ""),
                        "category": pa["category"],
                        "region": pa.get("region", ""),
                        "url": pa.get("url", ""),
                        "keywords": pa.get("keywords", "").split(",") if pa.get("keywords") else [],
                        "_from_pending": True,
                        "_pending_id": pa["id"],
                        "_age_penalty": age_penalty,
                    })
                    pending_ids_in_pool.add(pa["id"])
                    merged_count += 1
                if merged_count > 0:
                    logger.info(f"  备选库合并 [{cat}]: {merged_count} 条（排序最高）")

            total_crawled = sum(len(v) for v in grouped.values())
            logger.info(f"爬取结果(含备选库): 专利={len(grouped.get('patent', []))}, "
                        f"泛知产={len(grouped.get('general_ip', []))}")

            # ============================================================
            # 步骤4: 选择文章1（专利）和文章2（泛知产）
            # ============================================================
            logger.info("步骤4: 选择文章...")
            selected = []

            # 文章1：专利领域
            patent_news = grouped.get("patent", [])
            if patent_news:
                patent_news.sort(key=lambda x: self.crawler._priority_score(x), reverse=True)
                selected.append(patent_news[0])
                logger.info(f"  文章1(专利): {patent_news[0]['title'][:30]}...")

            # 文章2：泛知产领域
            general_ip_news = grouped.get("general_ip", [])
            if general_ip_news:
                general_ip_news.sort(key=lambda x: self.crawler._priority_score(x), reverse=True)
                selected.append(general_ip_news[0])
                logger.info(f"  文章2(泛知产): {general_ip_news[0]['title'][:30]}...")

            # 标记被选中的待用队列文章为已用
            for news in selected:
                if news.get("_from_pending") and news.get("_pending_id"):
                    self.db.mark_used_pending(news["_pending_id"])
                    logger.info(f"  备选库文章被选用 [{news.get('category', '')}]: {news['title'][:30]}...")

            # 未选中的文章存入备选库（仅当日新爬取的，已在库中的不重复存）
            all_news_flat = []
            for cat in ["patent", "general_ip"]:
                for news in grouped.get(cat, []):
                    if not any(n.get("title") == news.get("title") for n in selected):
                        all_news_flat.append(news)
            new_pending = [n for n in all_news_flat if not n.get("_from_pending")]
            if new_pending:
                self.db.save_pending_news(new_pending)
                logger.info(f"存入备选库: {len(new_pending)} 条")

            # ============================================================
            # 步骤5: 从 last30days-cn 选材（文章3：热点吸睛内容）
            # ============================================================
            logger.info("步骤5: 从 last30days-cn 选材...")
            hot_topic = self._find_hot_topic()
            if hot_topic:
                selected.append(hot_topic)
                logger.info(f"  文章3(热点): {hot_topic['title'][:30]}...")
            else:
                logger.warning("  last30days-cn 未找到合适热点，跳过文章3")
                # 不再从备选库补充低质量文章

            logger.info(f"最终选定 {len(selected)} 条新闻")

            if not selected:
                logger.error("未获取到任何新闻，任务终止")
                return

            # ============================================================
            # 步骤6: 补充源文章图片
            # ============================================================
            logger.info("步骤6: 提取源文章配图...")
            self.crawler.enrich_with_images(selected)
            for news in selected:
                imgs = news.get("images", [])
                if imgs:
                    logger.info(f"  [{news.get('source', '')}] {news['title'][:20]}... 获取到 {len(imgs)} 张源图")

            # ============================================================
            # 步骤7: 生成文章
            # ============================================================
            logger.info("步骤7: 生成文章...")
            articles = []

            for i, news in enumerate(selected[:Config.DAILY_ARTICLE_COUNT]):
                category = news.get("category", "general_ip")
                title = news["title"]
                source = news.get("source", "")
                region = news.get("region", "china")

                logger.info(f"生成文章 {i+1}/{min(len(selected), Config.DAILY_ARTICLE_COUNT)}: [{category}] {title[:30]}...")

                # 从知识库获取法条引用
                citations = []
                try:
                    citations = self.kb_client.get_citations(title, top_k=3)
                    if citations:
                        logger.info(f"  知识库引用: {len(citations)} 条 ({', '.join(c['source'][:15] for c in citations)})")
                except Exception as e:
                    logger.warning(f"  知识库检索失败: {e}")

                # AI生成文章
                content = self.generator.generate(
                    title=title,
                    source=source,
                    region=region,
                    category=category,
                    citations=citations,
                )

                if content and len(content.strip()) > 100:
                    # 检测AI拒绝生成（模型认为内容不适合撰写）
                    if self.generator._is_refusal(content):
                        logger.warning(f"  AI拒绝生成此话题，跳过: {title[:30]}...")
                        continue
                    short_title = self.generator.generate_title(title, category=category)
                    digest = self.generator.generate_digest(content)

                    # 处理配图
                    logger.info(f"  为文章处理配图...")
                    content_with_images = self.image_manager.process_article_images(
                        content, short_title, source, region,
                        source_images=news.get("images", []),
                        source_url=news.get("url", ""),
                    )

                    articles.append({
                        "title": short_title,
                        "original_title": title,
                        "digest": digest,
                        "content": content_with_images,
                        "source": source,
                        "author": "律途IP圈",
                        "category": category,
                        "keywords": ",".join(news.get("keywords", [])),
                    })

                    logger.info(f"  文章生成成功: {short_title} [{category}]")
                else:
                    logger.warning(f"  文章生成失败或内容过短")

            logger.info(f"成功生成 {len(articles)} 篇文章")

            # 步骤7.5: 生成新闻速览（第4篇）
            digest_article = self._build_digest_article(grouped, selected)
            if digest_article:
                articles.append(digest_article)
                logger.info(f"  新闻速览生成成功: {digest_article['title']}")

            if not articles:
                logger.error("没有成功生成的文章，任务终止")
                return

            # ============================================================
            # 步骤8: 创建草稿
            # ============================================================
            logger.info("步骤8: 创建微信草稿...")
            media_id = self.publisher.create_draft(articles)

            if media_id:
                logger.info(f"草稿创建成功！Media ID: {media_id}")

                try:
                    for article in articles:
                        self.db.save_article(
                            title=article["title"],
                            content=article["content"],
                            media_id=media_id,
                            status="draft",
                            category=article.get("category"),
                            keywords=article.get("keywords"),
                            original_title=article.get("original_title"),
                        )
                    logger.info("文章已保存到数据库")
                except Exception as e:
                    logger.error(f"保存数据库失败: {e}")
            else:
                logger.error("草稿创建失败")

            # 清理过期待用新闻
            self.db.cleanup_old_pending(days=14)

            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"任务执行异常: {e}", exc_info=True)

    def _build_digest_article(self, grouped, selected):
        """将未选中的新闻整理为一篇新闻速览文章"""
        selected_titles = {n["title"] for n in selected}

        all_remaining = []
        seen = set()
        for cat in ["patent", "general_ip"]:
            for news in grouped.get(cat, []):
                if news["title"] in selected_titles:
                    continue
                if news["title"] in seen:
                    continue
                seen.add(news["title"])
                all_remaining.append(news)

        # 使用 last30days-cn 搜索更多有价值的法律资讯
        try:
            digest_items = self.hot_topic_finder.find_digest_items()
            if digest_items:
                logger.info(f"  last30days-cn 搜索到 {len(digest_items)} 条额外资讯")
                for item in digest_items:
                    title = item.get("title", "")
                    if title and title not in seen:
                        seen.add(title)
                        all_remaining.append({
                            "title": title,
                            "source": item.get("source", ""),
                            "category": "hot_topic",
                            "url": item.get("url", ""),
                            "_extra_cat": item.get("category", ""),
                        })
        except Exception as e:
            logger.warning(f"  last30days-cn 搜索失败: {e}")

        # 过滤会议/活动类内容
        from config import Config
        meeting_keywords = Config.MEETING_FILTER_KEYWORDS
        all_remaining = [
            n for n in all_remaining
            if not any(kw in n.get("title", "") for kw in meeting_keywords)
        ]

        if len(all_remaining) < 3:
            return None

        category_labels = {
            "patent": "专利动态",
            "general_ip": "泛知产资讯",
            "hot_topic": "热点关注",
        }

        # 英文标题翻译映射（常见法律术语）
        en_translate = {
            # 机构和角色
            "v.": "诉", "vs.": "诉", "V.": "诉",
            "Inc.": "公司", "Corp.": "公司", "LLC": "公司", "LP": "公司",
            "Co.": "公司", "Ltd.": "公司", "PLC": "公司",
            "Court": "法院", "Supreme": "最高", "District": "地区",
            "Federal": "联邦", "Circuit": "巡回", "Justice": "大法官", "Judge": "法官",
            "Chief Justice": "首席大法官", "Justice": "大法官",
            # 法律术语
            "opinion": "意见", "Opinion": "意见", "Order": "命令", "Rule": "规则",
            "decision": "裁决", "Decision": "裁决", "ruling": "裁定",
            "patent": "专利", "Patent": "专利", "patents": "专利",
            "trademark": "商标", "Trademark": "商标", "trademark": "商标",
            "copyright": "著作权", "Copyright": "著作权",
            "design": "外观设计", "Design": "外观设计",
            "Appeal": "上诉", "appeal": "上诉", "appellate": "上诉",
            "Infringement": "侵权", "infringement": "侵权", "Infringe": "侵权",
            "Litigation": "诉讼", "litigation": "诉讼", "sue": "起诉",
            "Settlement": "和解", "settlement": "和解", "negotiate": "协商",
            "Damages": "赔偿", "damages": "赔偿", "compensation": "赔偿",
            "License": "许可", "license": "许可", "licensing": "许可",
            "Application": "申请", "application": "申请", "apply": "申请",
            "Examination": "审查", "examination": "审查", "examining": "审查",
            "Grant": "授权", "grant": "授权", "granted": "授权",
            "Validity": "有效性", "validity": "有效性", "invalid": "无效",
            "Claim": "权利要求", "claim": "权利要求", "claims": "权利要求",
            "Specification": "说明书", "specification": "说明书",
            "Prior Art": "现有技术", "prior art": "现有技术",
            "intellectual property": "知识产权", "IP": "知识产权",
            "Trade Secret": "商业秘密", "trade secret": "商业秘密",
            "Antitrust": "反垄断", "antitrust": "反垄断", "monopoly": "垄断",
            "Registration": "注册", "registration": "注册", "registered": "已注册",
            "Renewal": "续展", "renewal": "续展", "expire": "到期",
            "Office": "局", "office action": "审查意见", "action": "审查意见",
            "Petition": "请愿", "petition": "请愿", "request": "请求",
            "Inter Partes Review": "双方复审", "IPR": "双方复审",
            "Post-Grant": "授权后", "preissuance": "授权前",
        }

        items_html = ""
        links_data = []  # 收集链接数据用于生成汇总页面

        # 优先使用 last30days-cn 的内容（更新的资讯），放在前面
        digest_news = [n for n in all_remaining if n.get("_extra_cat")]
        crawler_news = [n for n in all_remaining if not n.get("_extra_cat")]
        # 混合：last30days 内容尽量多保留 + 爬虫内容补充，最多15条
        display_news = (digest_news + crawler_news)[:15]

        # 批量生成摘要（≤120字）
        summaries = {}
        try:
            summary_items = [{"title": n["title"], "source": n.get("source", "")} for n in display_news]
            summary_list = self.generator.generate_digest_summaries(summary_items)
            if summary_list:
                summaries = {
                    n["title"]: summary_list[i]
                    for i, n in enumerate(display_news)
                    if i < len(summary_list) and summary_list[i]
                }
                logger.info(f"  批量摘要生成成功: {len(summaries)}条")
        except Exception as e:
            logger.warning(f"  批量摘要生成失败，使用标题: {e}")

        for news in display_news:
            title = news["title"]
            source = news.get("source", "")
            url = news.get("url", "")
            # 优先使用 last30days-cn 的分类标签
            extra_cat = news.get("_extra_cat", "")
            cat = extra_cat if extra_cat else category_labels.get(news.get("category", ""), "综合")

            # 英文标题添加中文翻译
            en_chars = sum(1 for c in title if c.isascii() and c.isalpha())
            if en_chars > len(title) * 0.4 and len(title) > 10:
                # 翻译常见法律术语
                zh_title = title
                for en, zh in en_translate.items():
                    zh_title = zh_title.replace(en, zh)
                if zh_title != title:
                    title = f'{title}（{zh_title}）'
                else:
                    # 无法翻译时标注来源
                    region_label = "美国" if "supreme" in source.lower() or "美国" in source else "海外"
                    title = f'{title}（{region_label}司法案例）'

            # 收集链接
            if url and url.startswith("http"):
                links_data.append({"title": title, "source": source, "url": url, "cat": cat})

            # 构建链接行（微信会自动识别https://开头的链接，长按可复制）
            link_html = ""
            if url and url.startswith("http"):
                link_html = f'<br><span style="color:#2980b9;font-size:12px;text-decoration:underline;">{url}</span>'

            # 摘要
            summary_text = summaries.get(news["title"], "")
            summary_html = ""
            if summary_text:
                summary_html = f'<br><span style="color:#666;font-size:13px;">{summary_text}</span>'

            items_html += f'''<li style="margin-bottom:14px;line-height:1.8;">
<span style="background:#e8f4f8;color:#2980b9;font-size:12px;padding:2px 6px;border-radius:3px;margin-right:6px;">{cat}</span>
<strong style="color:#1a5276;">{title}</strong>
{summary_html}
<span style="color:#999;font-size:12px;margin-left:6px;">来源：{source}</span>
{link_html}
</li>
'''

        # 生成链接汇总页面并获取URL
        links_page_url = self._generate_links_page(links_data)

        readmore_hint = ""

        content = f'''<p style="font-size:15px;color:#555;margin-bottom:20px;">今日知识产权领域热点速览：</p>
<ul style="list-style:none;padding:0;font-size:14px;color:#333;">
{items_html}
</ul>
{readmore_hint}
<p style="font-size:12px;color:#999;margin-top:20px;text-align:right;">整理：律途IP圈 | {time.strftime("%Y-%m-%d")}</p>'''

        result = {
            "title": f"今日热点速览 | {time.strftime('%m月%d日')}更多资讯",
            "digest": f"今日知识产权领域热点速览，{len(display_news)}条精选资讯",
            "content": content,
            "source": "律途IP圈",
            "author": "律途IP圈",
            "category": "hot_topic",
            "keywords": "热点速览,知识产权,资讯",
        }

        if links_page_url:
            result["content_source_url"] = links_page_url
            logger.info(f"  阅读原文链接: {links_page_url}")

        return result

    def _generate_links_page(self, links_data):
        """生成链接汇总HTML页面，保存到web服务器，返回URL"""
        if not links_data:
            return None

        try:
            date_str = time.strftime("%Y-%m-%d")
            date_short = time.strftime("%m月%d日")

            links_html = ""
            for i, item in enumerate(links_data, 1):
                links_html += f'''
        <div class="item">
            <span class="tag">{item["cat"]}</span>
            <div class="title">{item["title"]}</div>
            <div class="source">来源：{item["source"]}</div>
            <div class="url" onclick="copyLink(this)" data-url="{item["url"]}">{item["url"]}</div>
            <div class="copy-hint">👆 点击链接自动复制</div>
        </div>'''

            html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>今日热点速览 | {date_short}链接汇总</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f7fa; padding: 16px; padding-bottom: 60px; }}
.header {{ background: linear-gradient(135deg, #1a5276, #2980b9); color: white; padding: 20px; border-radius: 12px; margin-bottom: 16px; text-align: center; }}
.header h1 {{ font-size: 18px; margin-bottom: 6px; }}
.header p {{ font-size: 13px; opacity: 0.85; }}
.item {{ background: white; border-radius: 10px; padding: 14px; margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }}
.tag {{ display: inline-block; background: #e8f4f8; color: #2980b9; font-size: 11px; padding: 2px 8px; border-radius: 4px; margin-bottom: 6px; }}
.title {{ font-size: 15px; font-weight: 600; color: #1a5276; line-height: 1.5; margin-bottom: 4px; }}
.source {{ font-size: 12px; color: #999; margin-bottom: 8px; }}
.url {{ font-size: 12px; color: #2980b9; word-break: break-all; background: #f0f8ff; padding: 8px 10px; border-radius: 6px; cursor: pointer; border: 1px solid #d6eaf8; }}
.url:active {{ background: #d6eaf8; }}
.copy-hint {{ font-size: 11px; color: #aaa; margin-top: 4px; text-align: center; }}
.footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 20px; }}
.toast {{ position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.75); color: white; padding: 10px 24px; border-radius: 20px; font-size: 14px; display: none; z-index: 999; }}
</style>
</head>
<body>
<div class="header">
    <h1>📋 今日热点速览 | {date_short}</h1>
    <p>点击任意链接即可复制到剪贴板</p>
</div>
{links_html}
<div class="footer">整理：律途IP圈 | {date_str}</div>
<div class="toast" id="toast">✅ 已复制到剪贴板</div>
<script>
function copyLink(el) {{
    var url = el.getAttribute("data-url");
    if (navigator.clipboard) {{
        navigator.clipboard.writeText(url).then(function() {{ showToast(); }});
    }} else {{
        var ta = document.createElement("textarea");
        ta.value = url;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        showToast();
    }}
}}
function showToast() {{
    var t = document.getElementById("toast");
    t.style.display = "block";
    setTimeout(function() {{ t.style.display = "none"; }}, 1500);
}}
</script>
</body>
</html>'''

            # 保存到web服务器目录
            save_dir = "/www/wwwroot/attoney.top/links"
            os.makedirs(save_dir, exist_ok=True)
            filename = f"links_{time.strftime('%Y%m%d')}.html"
            filepath = os.path.join(save_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)

            url = f"https://attoney.top/links/{filename}"
            logger.info(f"  链接汇总页面已保存: {filepath}")

            # 清理旧文件（保留最近14天）
            self._cleanup_old_links_files(save_dir, keep_days=14)

            return url

        except Exception as e:
            logger.error(f"  生成链接汇总页面失败: {e}")
            return None

    def _cleanup_old_links_files(self, save_dir, keep_days=14):
        """清理旧的链接汇总页面文件"""
        try:
            if not os.path.exists(save_dir):
                return
            import re
            cutoff = datetime.now().timestamp() - keep_days * 86400
            count = 0
            for fname in os.listdir(save_dir):
                if not re.match(r"links_\d{8}\.html", fname):
                    continue
                fpath = os.path.join(save_dir, fname)
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    count += 1
            if count > 0:
                logger.info(f"  清理过期链接文件: {count}个")
        except Exception as e:
            logger.warning(f"  清理旧链接文件失败: {e}")

    def _find_hot_topic(self):
        """使用 last30days-cn 搜索热点话题（八卦/时尚/养生等吸睛内容）"""
        try:
            topic = self.hot_topic_finder.find_hot_topic()
            if not topic:
                return None

            # 构造 news 格式
            return {
                "title": topic["title"],
                "source": topic.get("source", "社交平台"),
                "category": "hot_topic",
                "region": "china",
                "url": topic.get("url", ""),
                "keywords": ["热点", "吸睛", topic.get("source", "")],
                "images": [],
                "_from_trending": True,
                "_trending_data": topic,
            }
        except Exception as e:
            logger.warning(f"搜索热点话题失败: {e}")
            return None

    def run(self):
        logger.info("启动调度器，每日 02:00 和 06:00 执行...")
        schedule.every().day.at("02:00").do(self.generate_and_publish)
        schedule.every().day.at("06:00").do(self.generate_and_publish)

        logger.info("立即执行一次任务...")
        self.generate_and_publish()

        while True:
            schedule.run_pending()
            time.sleep(60)


if __name__ == "__main__":
    scheduler = Scheduler()
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        scheduler.generate_and_publish()
    else:
        scheduler.run()
