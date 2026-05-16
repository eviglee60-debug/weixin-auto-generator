"""AI文章生成器 - 整合知识库法条引用，参考主流IP公众号风格"""

import requests
import json
import logging
import time
import random
import re

logger = logging.getLogger(__name__)


class AIGenerator:
    def __init__(self):
        from config import Config
        self.api_url = Config.MINIMAX_API_URL
        self.api_key = Config.MINIMAX_API_KEY
        self.max_retries = 3

    def generate(self, title, source, region="china", category="general_ip",
                 citations=None):
        """
        生成文章。

        Args:
            title: 新闻标题
            source: 新闻来源
            region: china/international
            category: patent/general_ip/hot_topic
            citations: 知识库法条引用列表
        """
        try:
            # 构建法条上下文
            citation_text = ""
            if citations:
                parts = []
                for c in citations:
                    parts.append(
                        f"【{c['source']}】({c['category']}, {c['law_type']})\n"
                        f"{c['content']}"
                    )
                citation_text = "\n\n---\n\n".join(parts)

            # 根据分类选择提示词
            if category == "patent":
                prompt = self._build_patent_prompt(title, source, region, citation_text)
            elif category == "hot_topic":
                prompt = self._build_hot_topic_prompt(title, source, region, citation_text)
            else:  # general_ip
                prompt = self._build_general_ip_prompt(title, source, region, citation_text)

            content = self._call_llm(prompt)

            if content and len(content.strip()) > 100:
                return self.clean_html(content)

            logger.warning("AI生成内容过短，使用备用内容")
            return self.generate_fallback_content(title, source, region, category)

        except Exception as e:
            logger.error(f"AI生成失败: {e}")
            return self.generate_fallback_content(title, source, region, category)

    def _build_patent_prompt(self, title, source, region, citations):
        """专利法类文章提示词 - 参考大岭IP/专利茶馆风格"""
        base = f"""你是一位执业15年的资深知识产权律师，同时担任多家知名企业的知识产权顾问。请根据以下新闻撰写一篇专业深度分析文章。

新闻：{title}
来源：{source}"""

        if citations:
            base += f"\n\n以下是知识库中与主题相关的法律法规（请在文章中适当引用）：\n\n{citations}"

        base += """

【读者定位】（写之前先想清楚）
- 这篇文章是写给谁看的？（企业管理者/研发人员/知识产权从业者/普通公众？）
- 他们为什么要看这篇文章？能从中获得什么实际价值？
- 凡是行业内人人都知道的常识，不必赘述，直接切入对他们有用的内容

【内容方向】（选择最适合的角度）
- 专利侵权案例评析：深入剖析法院判决的法律逻辑和实务启示
- 专利审查趋势分析：基于CNIPA/USPTO/EPO数据分析审查走向
- 专利布局策略：为企业提供专利申请和管理建议
- 政策法规解读：分析新出台的专利法律法规、司法解释

【专业要求】
1. 引用权威来源：CNIPA（国家知识产权局）、最高人民法院知识产权法庭、USPTO、EPO、WIPO等
2. 引用法条：必须引用《专利法》《专利法实施细则》等具体条款，格式：《专利法》第X条
3. 专业术语准确，但适当解释让非专业读者理解
4. 每个核心观点都要有法律依据或数据支撑

【写作要求】
1. 使用HTML p标签写正文，不要用h3标签
2. 语言风格：专业但不晦涩，严谨但不枯燥，像资深律师在茶余饭后做专业分享
3. 结构清晰：事件背景 → 法律分析 → 法条解读 → 实务建议
4. 800-1200字，重点突出，逻辑严密
5. 直接输出HTML内容，不要代码块标记
6. 不要使用emoji
7. 结尾给出具体可操作的实务建议（2-3条）"""

        return base

    def _build_general_ip_prompt(self, title, source, region, citations):
        """泛知识产权类文章提示词 - 参考iprdaily/赋青春风格"""
        base = f"""你是一位资深知识产权律师和行业分析师，对商标、著作权、商业秘密、反不正当竞争等领域有深入研究。请根据以下新闻撰写一篇深度分析文章。

新闻：{title}
来源：{source}"""

        if citations:
            base += f"\n\n以下是知识库中与主题相关的法律法规（请在文章中适当引用）：\n\n{citations}"

        base += """

【读者定位】（写之前先想清楚）
- 这篇文章是写给谁看的？（企业管理者/创业者/品牌运营者/普通公众？）
- 他们为什么要看这篇文章？能从中获得什么实际价值？
- 凡是行业内人人都知道的常识，不必赘述，直接切入对他们有用的内容

【内容方向】
- 商标/著作权/商业热点事件分析
- 知识产权保护政策解读
- 企业知识产权管理实务
- 行业数据趋势分析（引用CNIPA、WIPO等官方数据）

【专业要求】
1. 引用权威来源：CNIPA、市场监管总局、WIPO、USPTO等官方数据
2. 引用法条：《商标法》《著作权法》《反不正当竞争法》《商业秘密保护规定》等
3. 数据说话：尽量引用具体数字、增长率、排名等
4. 实务导向：为企业管理者提供具体建议

【写作要求】
1. 使用HTML p标签写正文，不要用h3标签
2. 语言风格：专业、数据驱动、兼具可读性，像行业分析师在撰写深度报告
3. 结构清晰：事件/数据亮点 → 趋势分析 → 法律解读 → 企业建议
4. 800-1200字，简明扼要，重点突出
5. 直接输出HTML内容，不要代码块标记
6. 不要使用emoji
7. 结尾给出企业实务建议（2-3条）"""

        return base

    def _build_hot_topic_prompt(self, title, source, region, citations):
        """热点法律分析类文章提示词 - 参考百科君/金杜研究风格"""
        base = f"""你是一位资深法律评论员，擅长用通俗易懂的语言解读法律问题。请根据以下社会热点事件，从法律角度撰写一篇深度分析文章。

热点事件：{title}
来源：{source}"""

        if citations:
            base += f"\n\n以下是知识库中与主题相关的法律法规（请在文章中适当引用）：\n\n{citations}"

        base += """

【读者定位】（写之前先想清楚）
- 这篇文章是写给谁看的？（普通市民/消费者/打工人/家长/有车一族？）
- 他们为什么要看这篇文章？能从中获得什么实际价值？
- 凡是人人都知道的常识，不必赘述，直接切入对他们有用的内容

【内容方向】（不限于知识产权，老百姓关注的法律热点都可以）
- 社会热点事件的法律视角分析（消费维权、劳动纠纷、交通事故、医患纠纷、房产纠纷等）
- 新出台法律法规的通俗解读
- 最高法/最高检发布的典型案例解读
- 与普通人生活密切相关的法律问题（婚姻继承、民间借贷、网络诈骗、食品安全等）
- 热门社会事件中的法律争议点分析

【专业要求】
1. 法律分析要有理有据，引用具体法条
2. 用通俗语言解释法律概念，让非法律专业人士也能理解
3. 平衡专业性和可读性
4. 不涉及任何政治敏感话题
5. 不涉及低俗内容

【写作要求】
1. 使用HTML p标签写正文，不要用h3标签
2. 语言风格：通俗易懂但不失专业性，像一位朋友在给你讲故事的同时分析法律问题
3. 结构清晰：热点事件概述 → 法律视角分析 → 法条解读 → 社会启示
4. 800-1200字，引人入胜
5. 直接输出HTML内容，不要代码块标记
6. 不要使用emoji
7. 结尾给出实用建议或思考"""

        return base

    def _call_llm(self, prompt):
        """调用 MiniMax LLM"""
        from config import Config
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": Config.MINIMAX_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_tokens": 16384
        }

        for attempt in range(self.max_retries):
            try:
                logger.info(f"AI生成尝试 {attempt + 1}/{self.max_retries}")
                response = requests.post(
                    self.api_url, headers=headers, json=data, timeout=180
                )

                if response.status_code == 200:
                    result = response.json()
                    content = None

                    if "choices" in result and len(result["choices"]) > 0:
                        choice = result["choices"][0]
                        if "message" in choice:
                            msg = choice["message"]
                            content = msg.get("content", "")

                    logger.info(f"生成内容长度: {len(content) if content else 0}")

                    if content and len(content.strip()) > 100:
                        return content
                    else:
                        logger.warning(f"API返回内容为空或过短")
                else:
                    logger.error(f"API调用失败: {response.status_code}")

            except requests.exceptions.Timeout:
                logger.warning("请求超时")
                time.sleep(5)
            except Exception as e:
                logger.error(f"请求异常: {e}")
                time.sleep(3)

        return None

    def generate_fallback_content(self, title, source, region="china", category="general_ip"):
        """备用内容"""
        if category == "patent":
            return f"""<p>近日，{source}报道了关于"{title}"的消息，引发知识产权行业广泛关注。</p>

<p>近年来，中国专利事业发展迅速。据国家知识产权局(CNIPA)统计，2025年发明专利授权量达79.8万件，连续多年位居世界第一。PCT国际专利申请量也持续领先，体现了中国创新能力的不断提升。</p>

<p>根据《专利法》第11条，发明和实用新型专利权被授予后，除本法另有规定的以外，任何单位或者个人未经专利权人许可，都不得实施其专利。第65条规定了侵犯专利权的赔偿计算方式，为权利人提供了明确的法律救济途径。</p>

<p>从实务角度看，企业应重视专利布局，建立完善的知识产权管理体系。在产品研发阶段就进行专利检索和规避设计，避免侵权风险。同时，及时申请专利保护自身创新成果。</p>

<p>建议企业：1）定期进行专利风险排查；2）关注行业专利动态；3）建立专利预警机制；4）遇到侵权及时寻求法律救济。</p>"""

        elif category == "hot_topic":
            return f"""<p>近日，{source}报道了关于"{title}"的消息，从法律角度值得深入分析。</p>

<p>在法治社会中，每一个社会热点事件都蕴含着丰富的法律问题。通过对热点事件的法律解读，不仅有助于公众理解法律规定，也能为企业和个人提供实务参考。</p>

<p>我国知识产权法律体系日益完善，《专利法》《商标法》《著作权法》《反不正当竞争法》等法律为创新保护提供了坚实的制度基础。近年来，最高人民法院也发布了大量司法解释和指导性案例，进一步明确了法律适用标准。</p>

<p>从这个事件中我们可以看到，法律意识的培养和合规管理的重要性不容忽视。无论是企业还是个人，都应当增强法律意识，依法维护自身权益。</p>

<p>建议：1）关注最新法律法规动态；2）建立合规管理体系；3）遇到法律问题及时咨询专业律师。</p>"""

        else:  # general_ip
            return f"""<p>近日，{source}报道了关于"{title}"的消息，引发知识产权行业广泛关注。</p>

<p>中国知识产权保护成效显著。据CNIPA数据，截至2025年底，国内有效发明专利拥有量超过400万件，商标注册量连续多年世界第一。知识产权保护体系不断完善，为企业创新提供了有力保障。</p>

<p>《商标法》《著作权法》《反不正当竞争法》等法律共同构成了知识产权保护的法律框架。企业在经营过程中，应当重视知识产权的申请、保护和管理，避免侵权风险。</p>

<p>建议企业管理者：1）建立知识产权管理制度；2）及时申请注册商标和著作权；3）定期进行知识产权风险评估；4）关注行业最新政策动态。</p>"""

    def generate_title(self, original_title):
        """生成标题：20字以内，保持语义完整"""
        try:
            title = original_title

            # 去掉年份和日期（含中文数字年份）
            title = re.sub(r'20[2-3]\d年?\d{0,2}月?\d{0,2}日?', '', title)
            title = re.sub(r'[一二三四五六七八九〇○零]{2,4}年', '', title)

            # 去掉破折号/冒号后面的冗余描述（保留冒号前的主标题）
            # 但如果冒号前太短（如缩写），则保留冒号后部分合并
            parts = re.split(r'[——:：]', title, maxsplit=1)
            if len(parts) > 1 and len(parts[0]) >= 6:
                title = parts[0]
            elif len(parts) > 1 and len(parts[0]) < 6:
                # 冒号前太短（如"USPTO"），合并前后
                title = f"{parts[0]} {parts[1]}" if len(parts[1]) > 4 else parts[1]
            else:
                title = parts[0]

            # 只去掉明确的冗余后缀，保留核心内容
            for suffix in ["在京举办", "在京举行", "发布会举行", "活动举行"]:
                title = title.replace(suffix, "")

            # 去掉符号但保留中文和字母数字
            title = re.sub(r'[^一-鿿a-zA-Z0-9]', '', title)
            title = title.strip()

            if not title:
                return "知识产权新动态"

            # 提取中文部分
            chinese_parts = re.findall(r'[一-鿿]+', title)
            if chinese_parts:
                title = ''.join(chinese_parts)
            else:
                return random.choice(["国际知产新动态", "海外知产速递", "全球知产关注"])

            # 标题控制在20字以内（含前缀）
            prefixes = ["关注", "解读", "聚焦", "速看", "解析", "深度"]
            prefix = random.choice(prefixes)

            max_content_len = 18 - len(prefix)
            if len(title) > max_content_len:
                # 智能截断：在自然断点处截断
                truncated = title[:max_content_len]
                # 尝试在各种断点处截断，优先级从高到低
                for sep in ['、', '与', '和', '：', '——', '周', '会', '坛', '案', '法', '院', '局']:
                    idx = truncated.rfind(sep)
                    if idx > max_content_len // 2:
                        truncated = truncated[:idx + len(sep)]
                        break
                title = truncated

            return f"{prefix}{title}"

        except Exception as e:
            logger.error(f"生成标题失败: {e}")
            return "知识产权新动态"

    def generate_digest(self, content):
        """生成摘要：54个汉字以内（微信限制120字节，UTF-8每汉字3字节≈40汉字，留余量取54字符）"""
        try:
            text = re.sub(r'<[^>]+>', '', content)
            text = text.replace('\n', ' ').strip()
            text = re.sub(r'[\U0001F000-\U0001F9FF]', '', text)
            text = re.sub(r'[^一-龥a-zA-Z0-9]', '', text)

            if len(text) > 54:
                text = text[:54]

            return text if text else "知识产权行业最新动态"

        except Exception as e:
            logger.error(f"生成摘要失败: {e}")
            return "知识产权行业最新动态"

    def generate_digest_summaries(self, items, max_chars=120):
        """为多条新闻标题批量生成简短摘要（每条≤max_chars字）。

        Args:
            items: [{"title": str, "source": str}, ...] 最多20条
            max_chars: 每条摘要最大字数

        Returns:
            [str] 与 items 等长的摘要列表，失败时返回空列表
        """
        if not items:
            return []

        titles_text = "\n".join(
            f"{i+1}. [{it.get('source', '')}] {it['title']}"
            for i, it in enumerate(items)
        )

        prompt = f"""你是一位知识产权新闻编辑。请为以下每条新闻撰写一句简短摘要（≤{max_chars}字），说清楚发生了什么。
只输出编号和摘要，格式如"1. 摘要内容"，每条一行，不要其他文字。

{titles_text}"""

        content = self._call_llm_mini(prompt, max_tokens=2048)
        if not content:
            return []

        summaries = []
        for i, item in enumerate(items):
            # 匹配 "数字. 摘要" 格式
            import re
            pattern = rf'{i+1}\.\s*(.+?)(?:\n|$)'
            match = re.search(pattern, content)
            if match:
                summary = match.group(1).strip()
                if len(summary) > max_chars:
                    summary = summary[:max_chars]
                summaries.append(summary)
            else:
                # 回退：截取标题
                title = item.get("title", "")
                summaries.append(title[:max_chars] if len(title) > max_chars else title)

        return summaries

    def _call_llm_mini(self, prompt, max_tokens=2048):
        """轻量 LLM 调用，用于摘要等短任务"""
        from config import Config
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": Config.MINIMAX_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": max_tokens
        }

        try:
            logger.info(f"轻量LLM调用, max_tokens={max_tokens}")
            response = requests.post(
                self.api_url, headers=headers, json=data, timeout=60
            )
            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    msg = result["choices"][0].get("message", {})
                    return msg.get("content", "")
        except Exception as e:
            logger.error(f"轻量LLM调用失败: {e}")

        return None

    def generate_cover_image(self, title, category="general"):
        """
        调用 MiniMax Image-01 根据文章标题生成封面图，返回图片 bytes。

        Args:
            title: 文章标题，用于生成封面图 prompt
            category: 文章类别 (patent/general_ip/hot_topic)

        Returns:
            图片 bytes (JPEG) 或 None（失败时）
        """
        from config import Config
        import io

        # 根据类别和标题构建 prompt
        prompt = self._build_image_prompt(title, category)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {Config.MINIMAX_API_KEY}"
        }
        # 微信封面推荐 900x383，MiniMax 要求高>=512，用 1280x512 生成后裁剪
        data = {
            "model": Config.MINIMAX_IMAGE_MODEL,
            "prompt": prompt,
            "width": 1280,
            "height": 512,
            "n": 1,
            "response_format": "url",
            "prompt_optimizer": True,
        }

        try:
            logger.info(f"调用 MiniMax Image API 生成封面: {title[:30]}...")
            resp = requests.post(
                Config.MINIMAX_IMAGE_API_URL,
                headers=headers,
                json=data,
                timeout=120
            )
            if resp.status_code == 200:
                result = resp.json()
                image_url = None
                if "data" in result and result["data"]:
                    image_url = result["data"][0].get("url", "")
                elif "url" in result:
                    image_url = result["url"]

                if image_url:
                    logger.info(f"封面图生成成功，下载中...")
                    img_resp = requests.get(image_url, timeout=30)
                    if img_resp.status_code == 200:
                        # 转换为 JPEG 并调整尺寸到微信要求的 900x383
                        from PIL import Image
                        img = Image.open(io.BytesIO(img_resp.content))
                        if img.mode in ('RGBA', 'P', 'LA'):
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'P':
                                img = img.convert('RGBA')
                            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                            img = background
                        elif img.mode != 'RGB':
                            img = img.convert('RGB')
                        img = img.resize((900, 383), Image.LANCZOS)
                        output = io.BytesIO()
                        img.save(output, format='JPEG', quality=90)
                        logger.info(f"封面图处理完成 (900x383 JPEG)")
                        return output.getvalue()
                    else:
                        logger.error(f"下载封面图失败: HTTP {img_resp.status_code}")
                else:
                    logger.error(f"MiniMax 图片API未返回URL: {json.dumps(result, ensure_ascii=False)[:300]}")
            else:
                logger.error(f"MiniMax 图片API调用失败: {resp.status_code} - {resp.text[:300]}")
        except Exception as e:
            logger.error(f"生成封面图异常: {e}")

        return None

    def _build_image_prompt(self, title, category):
        """根据文章类别和标题构建图片生成 prompt"""
        # 类别风格指引
        category_styles = {
            "patent": "professional legal document style, blue and silver tones, technology innovation theme, clean modern design, intellectual property protection visual elements",
            "general_ip": "balanced professional and modern style, orange and white tones, intellectual property law theme, scales of justice, clean layout",
            "hot_topic": "eye-catching modern style, warm red and gold tones, breaking legal news theme, dynamic yet professional composition",
        }
        style = category_styles.get(category, category_styles["general_ip"])

        # 清理标题，提取核心语义
        import re
        clean_title = re.sub(r'^(关注|解读|聚焦|速看|解析|深度|全球知产)', '', title)
        clean_title = clean_title[:40]  # 限制长度

        prompt = (
            f"Chinese WeChat official account article cover image, 2.35:1 widescreen ratio. "
            f"Topic: \"{clean_title}\". "
            f"Style: {style}. "
            f"Text-free or minimal abstract geometric design, suitable for professional legal/IP news. "
            f"No small text, no chart, no photo of people. "
            f"High quality, 4K, clean composition."
        )
        return prompt

    def clean_html(self, html_content):
        """清理HTML内容"""
        html_content = re.sub(r'```[a-zA-Z]*\n?', '', html_content)
        html_content = html_content.replace("```", "")
        return html_content.strip()

    def coding_plan_search(self, query, max_tokens=8192):
        """
        调用 coding-plan-search 模型（独立端点）。

        Args:
            query: 搜索查询内容
            max_tokens: 最大令牌数

        Returns:
            搜索结果字典，包含 organic 结果列表，失败返回 None
        """
        try:
            from config import Config
            import requests as req

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {Config.MINIMAX_API_KEY}"
            }
            data = {"q": query}

            response = req.post(
                "https://api.minimaxi.com/v1/coding_plan/search",
                headers=headers,
                json=data,
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                if "organic" in result:
                    logger.info(f"coding-plan-search 成功，返回 {len(result['organic'])} 条结果")
                    return result
                elif "base_resp" in result:
                    logger.error(f"coding-plan-search API错误: {result['base_resp']}")
            else:
                logger.error(f"coding-plan-search 调用失败: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"coding-plan-search 异常: {e}")

        return None

    def coding_plan_vlm(self, image_url, prompt="描述这张图片的内容"):
        """
        调用 coding-plan-vlm 图片理解模型（独立端点）。

        Args:
            image_url: 图片 URL 或 data:image/png;base64,xxx 格式
            prompt: 图片理解提示词

        Returns:
            图片描述文本，失败返回 None
        """
        try:
            from config import Config
            import requests as req

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {Config.MINIMAX_API_KEY}"
            }
            data = {
                "prompt": prompt,
                "image_url": image_url
            }

            response = req.post(
                "https://api.minimaxi.com/v1/coding_plan/vlm",
                headers=headers,
                json=data,
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()
                if "content" in result:
                    logger.info(f"coding-plan-vlm 成功")
                    return result.get("content", "")
                elif "base_resp" in result:
                    logger.error(f"coding-plan-vlm API错误: {result['base_resp']}")
            else:
                logger.error(f"coding-plan-vlm 调用失败: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"coding-plan-vlm 异常: {e}")

        return None

    def coding_plan_vlm_image_understand(self, image_url, prompt="描述这张图片的内容"):
        """
        调用 coding-plan-vlm 图片理解（需通过 MCP 工具，不支持直接 API）。

        注意：coding-plan-vlm 的图片理解必须通过 MCP 工具调用。
        此方法记录调用方式，实际使用需要在 Claude Code 中通过 MCP 工具调用。

        Args:
            image_url: 图片 URL
            prompt: 图片理解提示词

        Returns:
            None（需通过 MCP 工具 understand_image 调用）
        """
        logger.info(f"coding-plan-vlm 图片理解需通过 MCP 工具调用: image_url={image_url}, prompt={prompt}")
        return None

    def call_mcp_understand_image(self, image_url, prompt="描述这张图片的内容"):
        """
        通过本地 MCP 工具调用 coding-plan-vlm 的图片理解能力。

        注意：MCP 采用 stdio 通信协议，需在 Claude Code 环境中使用。
        直接调用会因 session 管理问题失败。

        在 Claude Code 中可通过以下方式使用：
          from mcp import Client
          # 使用 MiniMax MCP 工具 understand_image

        Args:
            image_url: 图片 URL
            prompt: 图片理解提示词

        Returns:
            None（需在 Claude Code MCP 环境中调用）
        """
        logger.info(f"coding-plan-vlm 图片理解需在 Claude Code MCP 环境中使用: image_url={image_url}")
        return None
