import requests
import json
import logging
import time
import os
import tempfile

logger = logging.getLogger(__name__)

class WeixinPublisher:
    def __init__(self):
        from config import Config
        self.appid = Config.WECHAT_APPID
        self.secret = Config.WECHAT_SECRET
        self.base_url = "https://api.weixin.qq.com/cgi-bin"
        self.access_token = None
        self.token_expires = 0
        self.default_thumb_media_id = None
        
    def get_access_token(self):
        try:
            if self.access_token and time.time() < self.token_expires:
                return self.access_token
            
            url = f"{self.base_url}/token?grant_type=client_credential&appid={self.appid}&secret={self.secret}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.access_token = data["access_token"]
                    self.token_expires = time.time() + data["expires_in"] - 300
                    logger.info("获取access_token成功")
                    return self.access_token
                    
        except Exception as e:
            logger.error(f"获取access_token异常: {e}")
            return None
    
    def create_default_thumb_simple(self):
        """创建默认封面"""
        try:
            access_token = self.get_access_token()
            if not access_token:
                return None

            url = f"{self.base_url}/material/add_material?access_token={access_token}&type=thumb"

            jpeg_data = self.create_simple_jpeg()

            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp.write(jpeg_data)
                tmp_path = tmp.name

            with open(tmp_path, 'rb') as f:
                files = {'media': ('thumb.jpg', f, 'image/jpeg')}
                response = requests.post(url, files=files, timeout=30)

            os.unlink(tmp_path)

            if response.status_code == 200:
                data = response.json()
                if "media_id" in data:
                    self.default_thumb_media_id = data["media_id"]
                    logger.info(f"默认封面上传成功")
                    return data["media_id"]

            return None

        except Exception as e:
            logger.error(f"创建默认封面异常: {e}")
            return None

    def create_thumb_for_article(self, title, index=0, category="general"):
        """为指定文章创建封面"""
        try:
            access_token = self.get_access_token()
            if not access_token:
                return None

            url = f"{self.base_url}/material/add_material?access_token={access_token}&type=thumb"

            jpeg_data = self.create_simple_jpeg(title=title, index=index, category=category)

            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp.write(jpeg_data)
                tmp_path = tmp.name

            with open(tmp_path, 'rb') as f:
                files = {'media': ('thumb.jpg', f, 'image/jpeg')}
                response = requests.post(url, files=files, timeout=30)

            os.unlink(tmp_path)

            if response.status_code == 200:
                data = response.json()
                if "media_id" in data:
                    logger.info(f"文章封面上传成功: {title}")
                    return data["media_id"]

            return None

        except Exception as e:
            logger.error(f"创建文章封面异常: {e}")
            return None
    
    def create_simple_jpeg(self, title="", index=0, category="general"):
        """创建符合微信要求的封面图片 (900x383像素)，根据主题适配不同样式"""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import io

            # 根据主题选择配色和图标
            themes = {
                "patent": {
                    "colors": [(0, 90, 156), (0, 119, 182)],  # 深蓝渐变 - 专利
                    "icon": "PATENT",
                    "subtitle": "专利分析"
                },
                "trademark": {
                    "colors": [(39, 174, 96), (46, 204, 113)],  # 绿色渐变 - 商标
                    "icon": "TM",
                    "subtitle": "商标资讯"
                },
                "copyright": {
                    "colors": [(142, 68, 173), (155, 89, 182)],  # 紫色渐变 - 著作权
                    "icon": "©",
                    "subtitle": "著作权"
                },
                "international": {
                    "colors": [(44, 62, 80), (52, 73, 94)],  # 深灰蓝 - 国际
                    "icon": "GLOBAL",
                    "subtitle": "国际视野"
                },
                "general": {
                    "colors": [(211, 84, 0), (230, 126, 34)],  # 橙色 - 综合
                    "icon": "IP",
                    "subtitle": "知识产权"
                }
            }

            # 根据标题关键词判断主题
            detected_category = category
            if title:
                if any(kw in title for kw in ["专利", "发明", "PCT", "实用新型", "外观设计"]):
                    detected_category = "patent"
                elif any(kw in title for kw in ["商标", "品牌", "驰名"]):
                    detected_category = "trademark"
                elif any(kw in title for kw in ["著作权", "版权", "软件"]):
                    detected_category = "copyright"
                elif any(kw in title for kw in ["国际", "WIPO", "EPO", "USPTO", "海外", "全球"]):
                    detected_category = "international"

            theme = themes.get(detected_category, themes["general"])

            # 创建渐变背景
            img = Image.new('RGB', (900, 383))
            draw = ImageDraw.Draw(img)

            # 绘制渐变背景
            for y in range(383):
                r = int(theme["colors"][0][0] + (theme["colors"][1][0] - theme["colors"][0][0]) * y / 383)
                g = int(theme["colors"][0][1] + (theme["colors"][1][1] - theme["colors"][0][1]) * y / 383)
                b = int(theme["colors"][0][2] + (theme["colors"][1][2] - theme["colors"][0][2]) * y / 383)
                draw.line([(0, y), (900, y)], fill=(r, g, b))

            # 添加装饰元素 - 网格背景
            for x in range(0, 900, 50):
                draw.line([(x, 0), (x, 383)], fill=(255, 255, 255, 20), width=1)
            for y in range(0, 383, 50):
                draw.line([(0, y), (900, y)], fill=(255, 255, 255, 20), width=1)

            # 添加装饰边框
            draw.rectangle([25, 25, 875, 358], outline=(255, 255, 255, 100), width=2)
            draw.rectangle([40, 40, 860, 343], outline=(255, 255, 255, 80), width=1)

            # 加载字体
            try:
                font_icon = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
                font_large = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 42)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 24)
                font_tag = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 18)
            except:
                try:
                    font_icon = ImageFont.load_default()
                    font_large = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 42)
                    font_small = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 24)
                    font_tag = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 18)
                except:
                    font_icon = ImageFont.load_default()
                    font_large = ImageFont.load_default()
                    font_small = ImageFont.load_default()
                    font_tag = ImageFont.load_default()

            # 左侧图标区域
            icon_text = theme["icon"]
            bbox = draw.textbbox((0, 0), icon_text, font=font_icon)
            icon_width = bbox[2] - bbox[0]
            draw.text((80 - icon_width // 2, 130), icon_text, fill=(255, 255, 255), font=font_icon)

            # 右侧内容区域
            # 标题标签
            tag_text = f"【{theme['subtitle']}】"
            draw.text((180, 80), tag_text, fill=(255, 255, 200), font=font_tag)

            # 显示文章标题
            if title:
                # 截取标题，避免太长
                display_title = title[:15] if len(title) > 15 else title
                draw.text((180, 120), display_title, fill=(255, 255, 255), font=font_large)

                # 副标题
                draw.text((180, 185), "深度解析 · 专业视角", fill=(255, 255, 200), font=font_small)

            # 底部信息栏
            draw.rectangle([160, 260, 820, 262], fill=(255, 255, 255, 100))
            draw.text((180, 280), "律途IP圈 | 知识产权专业媒体", fill=(255, 255, 255), font=font_tag)
            draw.text((600, 280), "每日精选 · 深度解读", fill=(255, 255, 200), font=font_tag)

            # 转换为JPEG字节
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=90)
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"创建封面图片失败: {e}")
            # 返回一个最小的有效JPEG
            return self._create_minimal_jpeg()

    def _create_minimal_jpeg(self):
        """创建最小的有效JPEG图片"""
        return bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
            0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
            0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
            0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
            0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
            0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
            0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
            0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
            0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
            0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
            0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
            0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
            0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
            0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
            0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
            0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94, 0x11, 0x00, 0x00, 0x00, 0x00, 0x00,
            0xFF, 0xD9
        ])
    
    def create_draft(self, articles):
        try:
            access_token = self.get_access_token()
            if not access_token:
                logger.error("无法获取access_token")
                return None

            url = f"{self.base_url}/draft/add?access_token={access_token}"

            articles_data = []
            for i, article in enumerate(articles):
                logger.info(f"处理文章{i+1}...")

                if not article.get('content') or len(article['content'].strip()) < 100:
                    logger.error(f"文章{i+1}内容为空或过短，跳过")
                    continue

                # 标题：已确保12字以内
                title = article.get("title", "知识产权新动态")

                # 摘要：已确保30字以内
                digest = article.get("digest", "知识产权行业最新动态")

                # 获取文章类别
                category = article.get("category", "general")

                logger.info(f"文章{i+1}标题: {title} ({len(title)}字)")
                logger.info(f"文章{i+1}摘要: {digest} ({len(digest)}字)")
                logger.info(f"文章{i+1}类别: {category}")

                # 为每篇文章创建不同主题的封面
                logger.info(f"为文章{i+1}创建封面...")
                thumb_media_id = self.create_thumb_for_article(title, i, category)
                if not thumb_media_id:
                    thumb_media_id = self.default_thumb_media_id or ""
                    logger.info(f"使用默认封面")

                article_data = {
                    "title": title,
                    "author": article.get("author", "律途IP圈"),
                    "digest": digest,
                    "content": article["content"],
                    "thumb_media_id": thumb_media_id,
                    "need_open_comment": 1,
                    "only_fans_can_comment": 0
                }

                # 设置"阅读原文"链接
                if article.get("content_source_url"):
                    article_data["content_source_url"] = article["content_source_url"]
                    logger.info(f"  阅读原文链接: {article['content_source_url'][:60]}...")

                articles_data.append(article_data)

            if not articles_data:
                logger.error("没有有效的文章数据")
                return None

            payload = {"articles": articles_data}
            headers = {"Content-Type": "application/json; charset=utf-8"}

            logger.info(f"发送草稿创建请求，文章数: {len(articles_data)}")

            # 使用 data=json.dumps(ensure_ascii=False) 确保中文正常显示
            response = requests.post(url, headers=headers, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'), timeout=30)

            logger.info(f"微信API响应状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                if "media_id" in data:
                    logger.info(f"✅ 草稿创建成功: {data['media_id']}")
                    return data["media_id"]
                else:
                    logger.error(f"❌ 创建草稿失败: {data}")
                    return None
            else:
                logger.error(f"请求失败: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"创建草稿异常: {e}", exc_info=True)
            return None
