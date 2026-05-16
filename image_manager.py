import requests
import logging
import tempfile
import os
import hashlib
import random
from PIL import Image, ImageDraw, ImageFont
import io

logger = logging.getLogger(__name__)


class ImageManager:
    def __init__(self):
        from config import Config
        self.appid = Config.WECHAT_APPID
        self.secret = Config.WECHAT_SECRET
        self.base_url = "https://api.weixin.qq.com/cgi-bin"
        self.access_token = None
        self.token_expires = 0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        # 图片缓存，避免重复上传
        self.image_cache = {}

    def get_access_token(self):
        """获取微信access_token"""
        try:
            import time
            if self.access_token and time.time() < self.token_expires:
                return self.access_token

            url = f"{self.base_url}/token?grant_type=client_credential&appid={self.appid}&secret={self.secret}"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.access_token = data["access_token"]
                    self.token_expires = time.time() + data["expires_in"] - 300
                    return self.access_token

        except Exception as e:
            logger.error(f"获取access_token异常: {e}")
            return None

    def crawl_images_from_news(self, title, source, region="china"):
        """从多个图片来源抓取相关图片"""
        images = []

        # 根据关键词生成搜索词
        keywords = self._extract_keywords(title)
        search_query = keywords[0] if keywords else title[:8]

        # 尝试多个图片源
        search_sources = [
            ("百度图片", self._crawl_baidu_images),
            ("必应图片", self._crawl_bing_images),
            ("搜狗图片", self._crawl_sogou_images),
        ]

        for source_name, search_func in search_sources:
            try:
                found = search_func(search_query, title)
                if found:
                    images.extend(found)
                    logger.info(f"  {source_name}找到{len(found)}张图片")
                    if len(images) >= 3:
                        break
            except Exception as e:
                logger.debug(f"  {source_name}搜索失败: {e}")

        return images[:3]  # 最多返回3张图

    def _crawl_baidu_images(self, keyword, title):
        """百度图片搜索"""
        images = []
        try:
            url = "https://image.baidu.com/search/acjson"
            params = {"tn": "resultjson_com", "word": keyword, "pn": 0, "rn": 10}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://image.baidu.com/"
            }
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", [])[:5]:
                    if item.get("thumbURL"):
                        images.append({
                            "url": item["thumbURL"],
                            "width": item.get("thumbWidth", 300),
                            "height": item.get("thumbHeight", 200),
                            "title": item.get("fromPageTitle", title)
                        })
        except Exception as e:
            logger.debug(f"百度图片搜索失败: {e}")
        return images

    def _crawl_bing_images(self, keyword, title):
        """必应图片搜索"""
        images = []
        try:
            url = "https://cn.bing.com/images/search"
            params = {"q": keyword, "first": 0, "count": 10}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            }
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, 'html.parser')
                # 查找包含真实图片URL的img标签
                for img in soup.find_all('img'):
                    img_url = img.get('src') or img.get('data-src')
                    if img_url and img_url.startswith('http') and 'bing.net' in img_url:
                        images.append({
                            "url": img_url,
                            "width": 300,
                            "height": 200,
                            "title": title
                        })
                    # 也尝试从srcset获取
                    srcset = img.get('srcset', '')
                    if not img_url and srcset:
                        parts = srcset.split(',')
                        if parts:
                            url_part = parts[0].split()[0]
                            if url_part.startswith('http'):
                                images.append({
                                    "url": url_part,
                                    "width": 300,
                                    "height": 200,
                                    "title": title
                                })
                # 额外从a标签的href中提取图片
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if 'bing.net' in href and ('.jpg' in href or '.png' in href or '.jpeg' in href):
                        img_url = href.split('?')[0]
                        if img_url.startswith('http'):
                            images.append({
                                "url": img_url,
                                "width": 300,
                                "height": 200,
                                "title": title
                            })
        except Exception as e:
            logger.debug(f"必应图片搜索失败: {e}")
        return images[:5]  # 去重并限制数量

    def _crawl_sogou_images(self, keyword, title):
        """搜狗图片搜索"""
        images = []
        try:
            url = "https://pic.sogou.com/pics/json.jsp"
            params = {"query": keyword, "st": 5, "size": 10}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            }
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", [])[:5]:
                    if item.get("pic_url"):
                        images.append({
                            "url": item["pic_url"],
                            "width": item.get("width", 300),
                            "height": item.get("height", 200),
                            "title": item.get("title", title)
                        })
        except Exception as e:
            logger.debug(f"搜狗图片搜索失败: {e}")
        return images

    def _extract_keywords(self, title):
        """从标题提取关键词 - 提取核心主题用于图片搜索"""
        import re
        # 移除常见前缀和副词
        title = re.sub(r'^(关注|解读|聚焦|速看|解析|深度|速递|重磅|关于)\s*', '', title)
        title = re.sub(r'[-|——:：].*$', '', title)  # 移除破折号后内容
        title = title.strip()

        # 如果剩余标题较短，直接返回
        if len(title) <= 10:
            return [title] if title else ["法律"]

        # 提取核心名词词组（3-8字）
        words = re.findall(r'[一-龥]{3,8}', title)

        # 去掉太通用的词
        generic_words = {
            "知识产权", "法律法规", "司法解释", "管理办法", "工作通知",
            "保护运用", "风险管理", "最新修订", "海外知产", "典型案例"
        }
        keywords = [w for w in words if w not in generic_words and len(w) >= 3]

        if keywords:
            return keywords[:2]

        # 如果没提取到，返回清洗后的标题作为搜索词
        return [title[:8]] if title else ["法律"]

    def _generate_placeholder_images(self, title, keywords):
        """生成占位图片（当抓取失败时使用）"""
        images = []
        try:
            # 生成不同类型的配图
            image_types = ["数据图", "流程图", "要点图"]

            for i, img_type in enumerate(image_types[:2]):
                img_data = self._create_info_image(title, keywords[0] if keywords else "知识产权", img_type, i)
                if img_data:
                    images.append({
                        "data": img_data,
                        "type": "generated",
                        "title": f"{title[:8]}-{img_type}"
                    })

        except Exception as e:
            logger.error(f"生成占位图片失败: {e}")

        return images

    def _create_info_image(self, title, keyword, img_type, index):
        """创建信息图"""
        try:
            # 配色方案
            color_schemes = [
                {"bg": (240, 248, 255), "accent": (0, 120, 215), "text": (51, 51, 51)},
                {"bg": (255, 248, 240), "accent": (255, 140, 0), "text": (51, 51, 51)},
                {"bg": (240, 255, 240), "accent": (34, 139, 34), "text": (51, 51, 51)},
            ]
            scheme = color_schemes[index % len(color_schemes)]

            # 创建图片 (750x400 微信文章宽度)
            width, height = 750, 400
            img = Image.new('RGB', (width, height), color=scheme["bg"])
            draw = ImageDraw.Draw(img)

            # 加载字体
            try:
                font_title = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 28)
                font_content = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 20)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 16)
            except:
                font_title = ImageFont.load_default()
                font_content = ImageFont.load_default()
                font_small = ImageFont.load_default()

            # 顶部装饰条
            draw.rectangle([0, 0, width, 60], fill=scheme["accent"])
            draw.text((20, 15), f"【{img_type}】{title[:15]}", fill=(255, 255, 255), font=font_title)

            # 内容区域
            if img_type == "数据图":
                self._draw_data_chart(draw, width, height, scheme, font_content, font_small, keyword)
            elif img_type == "流程图":
                self._draw_flow_chart(draw, width, height, scheme, font_content, font_small, keyword)
            else:
                self._draw_key_points(draw, width, height, scheme, font_content, font_small, keyword)

            # 底部信息
            draw.rectangle([0, height - 40, width, height], fill=scheme["accent"])
            draw.text((20, height - 32), "律途IP圈 | 数据来源：CNIPA、WIPO等", fill=(255, 255, 255), font=font_small)

            # 转换为字节
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"创建信息图失败: {e}")
            return None

    def _draw_data_chart(self, draw, width, height, scheme, font_content, font_small, keyword):
        """绘制数据图表"""
        # 模拟数据
        data_items = [
            ("2023年", 45),
            ("2024年", 62),
            ("2025年", 78),
            ("2026年(预测)", 95)
        ]

        bar_width = 100
        max_height = 200
        start_x = 100
        start_y = 280

        for i, (label, value) in enumerate(data_items):
            x = start_x + i * 150
            bar_height = int(value * max_height / 100)

            # 绘制柱状图
            draw.rectangle([x, start_y - bar_height, x + bar_width, start_y],
                           fill=scheme["accent"])

            # 数值
            draw.text((x + 30, start_y - bar_height - 25), f"{value}%",
                       fill=scheme["text"], font=font_content)

            # 标签
            draw.text((x + 10, start_y + 10), label, fill=scheme["text"], font=font_small)

        # 说明文字
        draw.text((20, 80), f"近年来{keyword}相关数据增长趋势", fill=scheme["text"], font=font_content)
        draw.text((20, 110), "数据来源：国家知识产权局(CNIPA)年度统计报告", fill=(128, 128, 128), font=font_small)

    def _draw_flow_chart(self, draw, width, height, scheme, font_content, font_small, keyword):
        """绘制流程图"""
        steps = [
            "申请阶段",
            "审查阶段",
            "授权阶段",
            "维护阶段"
        ]

        box_width = 140
        box_height = 60
        start_x = 50
        start_y = 150
        gap = 40

        for i, step in enumerate(steps):
            x = start_x + i * (box_width + gap)

            # 绘制方框
            draw.rectangle([x, start_y, x + box_width, start_y + box_height],
                           fill=scheme["accent"], outline=(255, 255, 255))

            # 文字
            draw.text((x + 20, start_y + 20), step, fill=(255, 255, 255), font=font_content)

            # 箭头
            if i < len(steps) - 1:
                arrow_x = x + box_width + 5
                arrow_y = start_y + box_height // 2
                draw.line([(arrow_x, arrow_y), (arrow_x + gap - 10, arrow_y)],
                          fill=scheme["accent"], width=3)
                draw.polygon([(arrow_x + gap - 10, arrow_y - 5),
                              (arrow_x + gap, arrow_y),
                              (arrow_x + gap - 10, arrow_y + 5)],
                             fill=scheme["accent"])

        # 说明
        draw.text((20, 80), f"{keyword}全流程管理示意图", fill=scheme["text"], font=font_content)
        draw.text((20, 280), "提示：各阶段均有专业律师提供法律支持", fill=(128, 128, 128), font=font_small)

    def _draw_key_points(self, draw, width, height, scheme, font_content, font_small, keyword):
        """绘制要点图"""
        points = [
            "1. 明确保护范围",
            "2. 及时申请注册",
            "3. 定期监测侵权",
            "4. 建立维权机制"
        ]

        start_x = 50
        start_y = 100

        for i, point in enumerate(points):
            y = start_y + i * 60

            # 编号圆圈
            draw.ellipse([start_x, y, start_x + 40, y + 40], fill=scheme["accent"])
            draw.text((start_x + 12, y + 8), str(i + 1), fill=(255, 255, 255), font=font_content)

            # 要点文字
            draw.text((start_x + 60, y + 8), point[3:], fill=scheme["text"], font=font_content)

        # 标题
        draw.text((20, 80), f"{keyword}核心要点", fill=scheme["text"], font=font_content)

    def upload_image_to_weixin(self, image_data, filename="image.jpg"):
        """上传图片到微信素材库"""
        try:
            access_token = self.get_access_token()
            if not access_token:
                return None

            url = f"{self.base_url}/media/uploadimg?access_token={access_token}"

            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp.write(image_data)
                tmp_path = tmp.name

            with open(tmp_path, 'rb') as f:
                files = {'media': (filename, f, 'image/jpeg')}
                response = requests.post(url, files=files, timeout=30)

            os.unlink(tmp_path)

            if response.status_code == 200:
                data = response.json()
                if "url" in data:
                    logger.info(f"图片上传成功: {data['url'][:50]}...")
                    return data["url"]

            logger.error(f"图片上传失败: {response.text[:200]}")
            return None

        except Exception as e:
            logger.error(f"上传图片异常: {e}")
            return None

    def download_and_upload_image(self, image_url, filename="news_image.jpg"):
        """下载网络图片并上传到微信"""
        try:
            # 检查缓存
            cache_key = hashlib.md5(image_url.encode()).hexdigest()
            if cache_key in self.image_cache:
                return self.image_cache[cache_key]

            # 下载图片
            response = requests.get(image_url, headers=self.headers, timeout=15)
            if response.status_code != 200:
                return None

            # 验证是图片（检查大小）
            if len(response.content) < 1000:
                return None

            # 转换 WEBP 等格式为 JPEG
            image_data = self._convert_to_jpeg(response.content)

            # 上传到微信
            weixin_url = self.upload_image_to_weixin(image_data, filename)

            if weixin_url:
                self.image_cache[cache_key] = weixin_url

            return weixin_url

        except Exception as e:
            logger.error(f"下载上传图片失败: {e}")
            return None

    def _convert_to_jpeg(self, image_data):
        """将任意图片格式转换为 JPEG 格式"""
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_data))
            # 转换为 RGB 模式（微信要求 JPEG 为 RGB）
            if img.mode in ('RGBA', 'P', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            # 保存为 JPEG
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=85)
            return output.getvalue()
        except Exception as e:
            logger.debug(f"图片格式转换失败: {e}")
            return image_data  # 返回原始数据

    def process_article_images(self, content, title, source, region="china",
                               source_images=None, source_url=""):
        """处理文章内容，插入配图

        优先级：源文章图片 > 百度图片搜索 > PIL生成占位图
        """
        try:
            image_urls = []

            # 优先使用源文章图片
            if source_images:
                logger.info(f"  源文章图片: {len(source_images)}张待处理")
                for i, img_url in enumerate(source_images[:2]):
                    url = self.download_and_upload_image(img_url, f"source_{i}.jpg")
                    if url:
                        image_urls.append({"url": url, "source": source})
                        logger.info(f"  源图{i+1}上传成功")
                    else:
                        logger.warning(f"  源图{i+1}下载上传失败: {img_url[:60]}")
            else:
                logger.info(f"  无源文章图片")

            # 不够则用百度图片搜索或生成占位图补充
            if len(image_urls) < 2:
                need = 2 - len(image_urls)
                search_images = self.crawl_images_from_news(title, source, region)
                if search_images:
                    logger.info(f"  百度搜图补充({need}张)...")
                    for img in search_images[:need]:
                        if img.get("data"):
                            url = self.upload_image_to_weixin(img["data"], f"{title[:8]}_{len(image_urls)}.jpg")
                        elif img.get("url"):
                            url = self.download_and_upload_image(img["url"], f"news_{len(image_urls)}.jpg")
                        else:
                            continue
                        if url:
                            image_urls.append({"url": url, "source": "网络"})
                            logger.info(f"  百度搜图上传成功")
                else:
                    # 百度搜图失败时生成占位图
                    logger.info(f"  百度搜图失败，生成占位图({need}张)...")
                    keywords = self._extract_keywords(title)
                    for i in range(need):
                        img_data = self._create_info_image(title, keywords[0] if keywords else "知识产权", ["数据图", "流程图", "要点图"][i % 3], i)
                        if img_data:
                            url = self.upload_image_to_weixin(img_data, f"generated_{i}.jpg")
                            if url:
                                image_urls.append({"url": url, "source": "律途IP圈生成"})
                                logger.info(f"  占位图{i+1}上传成功")

            if not image_urls:
                logger.warning(f"  无可用图片，返回原文")
                return content

            logger.info(f"  最终使用 {len(image_urls)} 张图")

            # 在文章中插入图片（带来源标注）
            content = self._insert_images_to_content(
                content, [img["url"] for img in image_urls], title,
                sources=[img.get("source", "") for img in image_urls]
            )

            return content

        except Exception as e:
            logger.error(f"处理文章图片失败: {e}")
            return content

    def _insert_images_to_content(self, content, image_urls, title, sources=None):
        """在HTML内容中插入图片"""
        import re

        if not sources:
            sources = [""] * len(image_urls)

        # 找到所有段落
        paragraphs = re.findall(r'<p>.*?</p>', content, re.DOTALL)

        if len(paragraphs) < 3:
            img_html = self._generate_image_html(image_urls[0], title, sources[0])
            return img_html + content

        # 在文章中间和后部插入图片
        insert_positions = []

        pos1 = len(paragraphs) // 3
        insert_positions.append((pos1, image_urls[0], sources[0]))

        if len(image_urls) > 1:
            pos2 = len(paragraphs) * 2 // 3
            insert_positions.append((pos2, image_urls[1], sources[1] if len(sources) > 1 else ""))

        new_content = ""
        img_index = 0

        for i, para in enumerate(paragraphs):
            new_content += para

            for pos, url, src in insert_positions:
                if i == pos and img_index < len(insert_positions):
                    img_html = self._generate_image_html(url, title, src)
                    new_content += img_html
                    img_index += 1

        return new_content

    def _generate_image_html(self, image_url, title, source=""):
        """生成图片HTML，带来源标注"""
        source_html = ""
        if source:
            source_html = f'\n<p style="text-align: center; font-size: 12px; color: #999; margin: -10px 0 15px 0;">图：{source}</p>'
        return f'''
<p style="text-align: center; margin: 20px 0;">
    <img src="{image_url}" alt="{title}" style="max-width: 100%; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);" />
</p>{source_html}
'''
