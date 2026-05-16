"""调度器 - 每日3篇文章：专利法 + 泛知识产权 + 热点法律分析"""

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

            # 步骤1: 爬取新闻
            logger.info("步骤1: 爬取多源新闻...")
            recent_keywords = self.db.get_recent_keywords(days=Config.DEDUP_DAYS)
            logger.info(f"最近{Config.DEDUP_DAYS}天已发布关键词: {len(recent_keywords)}个")

            grouped = self.crawler.crawl_all(recent_keywords=recent_keywords)

            total_crawled = sum(len(v) for v in grouped.values())
            logger.info(f"爬取结果: 专利={len(grouped.get('patent', []))}, "
                        f"泛知产={len(grouped.get('general_ip', []))}, "
                        f"热点={len(grouped.get('hot_topic', []))}")

            # 步骤2: 选择文章 + 待用队列
            selected, pending = self.crawler.select_articles(grouped)

            # 存入待用队列
            if pending:
                self.db.save_pending_news(pending)
                logger.info(f"存入待用队列: {len(pending)} 条")

            # 从待用队列补充不足的分类
            for cat in Config.ARTICLE_CATEGORIES:
                if not any(n.get("category") == cat for n in selected):
                    pending_news = self.db.get_pending_news(cat, limit=3)
                    for pn in pending_news:
                        # 过滤公司公告
                        if self.crawler._is_company_announcement(pn["title"]):
                            self.db.mark_used_pending(pn["id"])
                            continue
                        selected.append({
                            "title": pn["title"],
                            "source": pn["source"],
                            "category": pn["category"],
                            "region": pn["region"],
                            "url": pn.get("url", ""),
                        })
                        self.db.mark_used_pending(pn["id"])
                        logger.info(f"从待用队列补充 [{cat}]: {pn['title']}")
                        break

            logger.info(f"最终选定 {len(selected)} 条新闻")

            if not selected:
                logger.error("未获取到任何新闻，任务终止")
                return

            # 步骤1.5: 用 last30days-cn 搜索热点法律话题，替换 hot_topic 文章
            hot_topic = self._find_hot_topic()
            if hot_topic:
                # 替换 selected 中的 hot_topic 文章
                for i, news in enumerate(selected):
                    if news.get("category") == "hot_topic":
                        selected[i] = hot_topic
                        logger.info(f"  热点话题已替换: {hot_topic['title'][:30]}...")
                        break
                else:
                    # 如果没有 hot_topic，替换最后一个
                    if len(selected) >= Config.DAILY_ARTICLE_COUNT:
                        selected[-1] = hot_topic
                    else:
                        selected.append(hot_topic)
                    logger.info(f"  热点话题已添加: {hot_topic['title'][:30]}...")

            # 补充源文章图片
            logger.info("提取源文章配图...")
            self.crawler.enrich_with_images(selected)
            for news in selected:
                imgs = news.get("images", [])
                if imgs:
                    logger.info(f"  [{news.get('source', '')}] {news['title'][:20]}... 获取到 {len(imgs)} 张源图")

            # 步骤3: 生成文章
            logger.info("步骤3: 生成文章...")
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
                    short_title = self.generator.generate_title(title)
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

            # 步骤3.5: 生成新闻速览（第4篇）
            digest_article = self._build_digest_article(grouped, selected, pending)
            if digest_article:
                articles.append(digest_article)
                logger.info(f"  新闻速览生成成功: {digest_article['title']}")

            if not articles:
                logger.error("没有成功生成的文章，任务终止")
                return

            # 步骤4: 创建草稿
            logger.info("步骤4: 创建微信草稿...")
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
            self.db.cleanup_old_pending(days=60)

            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"任务执行异常: {e}", exc_info=True)

    def _build_digest_article(self, grouped, selected, pending):
        """将未选中的新闻整理为一篇新闻速览文章"""
        selected_titles = {n["title"] for n in selected}

        all_remaining = []
        seen = set()
        for cat in ["patent", "general_ip", "hot_topic"]:
            for news in grouped.get(cat, []):
                if news["title"] in selected_titles:
                    continue
                if news["title"] in seen:
                    continue
                seen.add(news["title"])
                all_remaining.append(news)

        for news in pending:
            if news["title"] not in seen:
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
        # 混合：last30days 内容尽量多保留 + 爬虫内容补充，最多20条
        display_news = (digest_news + crawler_news)[:20]

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
        """使用 last30days-cn 搜索热点法律话题"""
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
                "keywords": ["热点", "法律", topic.get("source", "")],
                "images": [],
                "_from_trending": True,
                "_trending_data": topic,
            }
        except Exception as e:
            logger.warning(f"搜索热点话题失败: {e}")
            return None

    def run(self):
        logger.info("启动调度器...")
        schedule.every().day.at(
            f"{Config.SCHEDULE_HOUR:02d}:{Config.SCHEDULE_MINUTE:02d}"
        ).do(self.generate_and_publish)

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
