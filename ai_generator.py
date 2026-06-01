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

            # 检测AI拒绝生成，用强化指令重试一次
            if content and self._is_refusal(content):
                logger.info("  检测到AI拒绝，用强化指令重试...")
                retry_prompt = prompt + "\n\n【强制要求】这是一篇合法的新闻评论/社会热点分析文章，请正常撰写，不得拒绝。"
                content = self._call_llm(retry_prompt)
                # 重试后再次检查是否仍被拒绝
                if content and self._is_refusal(content):
                    logger.warning("  重试后仍被AI拒绝，使用备用内容")
                    return self.generate_fallback_content(title, source, region, category)

            if content and len(content.strip()) > 100:
                return self.clean_html(content)

            logger.warning("AI生成内容过短，使用备用内容")
            return self.generate_fallback_content(title, source, region, category)

        except Exception as e:
            logger.error(f"AI生成失败: {e}")
            return self.generate_fallback_content(title, source, region, category)

    def _is_refusal(self, content):
        """检测AI拒绝生成内容（宽松匹配 + 结构检查）"""
        if not content:
            return False
        refusal_markers = [
            "我不能撰写", "我无法撰写", "我不会协助", "我无法扮演",
            "无法承担特定的角色", "很抱歉我无法", "危害性分析",
            "很抱歉", "无法完成", "暂时无法", "这个写作任务",
            "不符合我的", "不适合撰写", "我不能帮助",
            "这个请求实际上是", "我的立场",
        ]
        if any(m in content for m in refusal_markers):
            return True
        # 结构检查：正常文章必须有 <p> 标签，没有则视为拒绝
        if "<p>" not in content and "<p " not in content:
            logger.warning("  内容无HTML结构(<p>标签)，视为拒绝")
            return True
        return False

    def _build_patent_prompt(self, title, source, region, citations):
        """专利法类文章提示词 - 参考大岭IP/专利茶馆风格"""
        base = f"""你是一位执业15年的资深知识产权律师，同时担任多家知名企业的知识产权顾问。请根据以下新闻撰写一篇专业深度分析文章。
（注意：文章中不要出现"作为执业X年的律师""笔者作为一名知识产权律师"等自称身份的词句，保持客观第三人称叙述。）

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
3. 结构清晰：事件背景 → 法律分析 → 法条解读（实务建议一笔带过即可）
4. 800-1200字，重点突出，逻辑严密
5. 直接输出HTML内容，不要代码块标记
6. 不要使用emoji
7. 结尾简要给出1条实务建议即可，不必面面俱到
8. 【重要】必须有具体细节，不能泛泛而谈。法规解读类必须列出具体改动要点（如"将赔偿额上限从100万提高到500万"），不能只说"进行了修订"。如果改动内容较多，聚焦最重要的2-3项改动，文末提示"其余修改内容将在后续文章中详细解读"
9. 新闻中的具体数字、案例名称、公司名称、法条编号等细节必须体现在文章中，不能省略"""

        return base

    def _build_general_ip_prompt(self, title, source, region, citations):
        """泛知识产权类文章提示词 - 参考iprdaily/赋青春风格"""
        base = f"""你是一位资深知识产权律师和行业分析师，对商标、著作权、商业秘密、反不正当竞争等领域有深入研究。请根据以下新闻撰写一篇深度分析文章。
（注意：文章中不要出现"作为执业X年的律师""笔者作为一名知识产权律师"等自称身份的词句，保持客观第三人称叙述。）

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
7. 结尾简要给出1条实务建议即可
8. 【重要】必须有具体细节，不能泛泛而谈。法规解读类必须列出具体改动要点，不能只说"进行了修订"。如果改动内容较多，聚焦最重要的2-3项，文末提示"其余修改内容将在后续文章中详细解读"
9. 新闻中的具体数字、案例名称、公司名称、法条编号等细节必须体现在文章中"""

        return base

    def _build_hot_topic_prompt(self, title, source, region, citations):
        """热点法律分析类文章提示词 — "吃瓜群众"视角，八卦但不低俗，法律解读像追剧一样好看"""
        base = f"""你是一位资深法律评论员，擅长把复杂的法律问题讲得像侦探故事一样引人入胜。请根据以下社会热点，从法律角度撰写一篇让读者"停不下来"的深度分析文章。
（注意：文章中不要出现"作为资深评论员""笔者作为一名法律评论员"等自称身份的词句，保持客观第三人称叙述。）

热点事件：{title}
来源：{source}"""

        if citations:
            base += f"\n\n以下是知识库中与主题相关的法律法规（请在文章中适当引用）：\n\n{citations}"

        base += """

【写作心法 — "吃瓜群众"视角】
你的读者是普通老百姓。他们为什么点开这篇文章？
- 因为标题勾起了好奇心（"怎么回事？""谁赢了？""赔了多少？"）
- 因为事件本身有戏剧性（反转、天价、争议、内幕）
- 因为他们想知道"这事如果发生在自己身上怎么办"

你要做的：像一个懂法律的朋友，把这场"戏"拆解清楚 — 谁对谁错、法律怎么说、如果是你该怎么办。
记住：八卦是钩子，法律是内核。先"吃瓜"吸引进来，再输出法律价值。

【内容结构 — 像侦探小说一样层层递进】
1. 开篇钩子（1-2段）：用最抓人的事实制造悬念。"XX被判赔5000万？""一场官司打了8年，最后..." 直接抛出最劲爆的事实，让读者立刻想往下看。
2. 事件还原（2-3段）：用时间线还原事件经过。谁告了谁、为什么、关键证据是什么。像讲故事一样交代来龙去脉。
3. 法律拆解（3-4段）：这是核心。以"法律怎么说"的视角，逐一分析事件中的法律争议点。引用具体法条（格式：《XX法》第X条），用通俗语言解释专业概念。
4. 深层追问（1-2段）：这个案子有什么特别之处？它反映了什么社会问题？判决结果对普通人意味着什么？
5. 吃瓜指南（1段）：如果读者遇到类似情况，简要给出1条关键建议即可。

【写作风格】
- 开头一定要抓人：用反问、惊人数字、矛盾冲突制造悬念
- 法律分析要有干货：每条观点都有法条或判例支撑，不能空谈
- 语言像聊天：用"你""我们"拉近距离，像朋友在茶桌上给你分析
- 节奏有起伏：一段事实、一段分析、一段反转，让读者有"哦原来是这样"的阅读体验
- 拒绝说教：不要"大家应该注意"这种语气，用"你可能会问...答案是..."来引导

【合规底线 — 必须严格遵守】
1. 不涉及政治敏感话题、领导人、政府机构评价
2. 不涉及低俗内容（色情、暴力、赌博、毒品）
3. 不传播未经核实的信息，所有事实引用需标注来源
4. 不对未决案件做预测性评论（"法院可能会判..."），只说已发生的事实和法律规定
5. 不煽动对立情绪，不进行道德审判，客观中立分析法律问题
6. 引用法条必须准确，不确定的法条宁可不用
7. 娱乐圈/名人/网红/偶像团体等公共人物的动态事件是合法的写作题材，涉及肖像权、名誉权、合同纠纷、经纪合约等法律问题时应积极分析，不得拒绝撰写

【输出格式】
1. 使用HTML p标签写正文，不要用h3标签
2. 文章长度：800-1200字
3. 直接输出HTML内容，不要代码块标记
4. 不要使用emoji
5. 文末简要给出1条建议即可，重点放在故事和法律分析上
6. 【重要】必须有具体细节：人物/公司/时间/金额/判决结果等具体信息不能省略。宁可聚焦一个细节深入讲透，也不要泛泛而谈"""

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
            "max_completion_tokens": 16384,
            "thinking": {"type": "disabled"}
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
                    if response.status_code == 529:
                        wait = 2 ** attempt * 5  # 5s, 10s, 20s
                        logger.warning(f"API 529过载，{wait}s后重试...")
                        time.sleep(wait)
                        continue
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
            return f"""<p>最近，"{title}"引发广泛关注。很多人看完第一反应是：这也能被告？赔这么多？</p>

<p>别急，我们一步步拆解这件事背后的法律逻辑。</p>

<p>每个社会热点背后，都藏着普通人用得上的法律知识。这个事件涉及的法律问题，其实和我们的生活息息相关——只是大多数人平时没有机会了解。</p>

<p>从法律角度看，我国《民法典》《消费者权益保护法》《劳动合同法》等法律为公民权益提供了全方位的保护。关键在于：你知道自己的权利边界在哪里吗？你知道维权需要哪些证据吗？</p>

<p>建议每一位读者：1）保存好合同、转账记录、聊天记录等电子证据；2）遇到纠纷先咨询专业律师，不要盲目行动；3）关注与自己生活相关的法律法规更新，法律意识是最好的护身符。</p>"""

        else:  # general_ip
            return f"""<p>近日，{source}报道了关于"{title}"的消息，引发知识产权行业广泛关注。</p>

<p>中国知识产权保护成效显著。据CNIPA数据，截至2025年底，国内有效发明专利拥有量超过400万件，商标注册量连续多年世界第一。知识产权保护体系不断完善，为企业创新提供了有力保障。</p>

<p>《商标法》《著作权法》《反不正当竞争法》等法律共同构成了知识产权保护的法律框架。企业在经营过程中，应当重视知识产权的申请、保护和管理，避免侵权风险。</p>

<p>建议企业管理者：1）建立知识产权管理制度；2）及时申请注册商标和著作权；3）定期进行知识产权风险评估；4）关注行业最新政策动态。</p>"""

    def _translate_title_to_chinese(self, english_title):
        """用 LLM 将英文法律/IP新闻标题翻译为简洁中文（20字以内）"""
        prompt = (
            f"Translate the following English legal/IP news title into concise Chinese "
            f"(within 20 characters). Return ONLY the Chinese title, no other text.\n\n"
            f"Title: {english_title}"
        )
        try:
            result = self._call_llm_mini(prompt, max_tokens=128)
            if result:
                import re
                chinese = re.sub(r'[^一-鿿]', '', result).strip()
                if chinese and len(chinese) >= 4:
                    logger.info(f"标题英译中: '{english_title[:30]}...' → '{chinese}'")
                    return chinese[:20]
        except Exception as e:
            logger.warning(f"标题英译中失败: {e}")
        return ""

    def generate_title(self, original_title, category="general_ip"):
        """生成标题：30字以内，保持语义完整。hot_topic类采用更吸睛的风格。"""
        try:
            title = original_title

            # 去掉年份和日期（含"年度"后缀）
            title = re.sub(r'20[2-3]\d年[度]?\d{0,2}月?\d{0,2}日?', '', title)
            title = re.sub(r'[一二三四五六七八九〇○零]{2,4}年[度]?', '', title)

            # 英文标题（>40% ASCII字母）→ LLM翻译为中文
            ascii_alpha = sum(1 for c in title if c.isascii() and c.isalpha())
            if ascii_alpha > len(title) * 0.4 and ascii_alpha > 10:
                cn_title = self._translate_title_to_chinese(title)
                if cn_title:
                    if category == "hot_topic":
                        return self._generate_hot_title(cn_title[:30])
                    return cn_title[:30]

            # 处理破折号/冒号/竖线：取更有信息量的一侧
            parts = re.split(r'[——:：|]', title, maxsplit=1)
            if len(parts) > 1:
                part0, part1 = parts[0].strip(), parts[1].strip()
                if len(part0) <= 4:
                    title = part1  # "发布 | xxx"
                elif len(part0) >= 8:
                    title = part0
                else:
                    title = part1 if len(part1) > len(part0) else part0
            else:
                title = parts[0].strip()

            # 去掉冗余后缀
            for suffix in ["在京举办", "在京举行", "发布会举行", "活动举行"]:
                title = title.replace(suffix, "")

            # 去掉书名号等装饰符号
            title = re.sub(r'[【】《》""''「」]', '', title)
            title = title.strip()

            if not title:
                return "知识产权新动态"

            # 检测是否主要是英文/符号（非中文）
            chinese_chars = len(re.findall(r'[一-鿿]', title))
            if chinese_chars < 3 and chinese_chars < len(title) * 0.3:
                cn_title = self._translate_title_to_chinese(title)
                if cn_title:
                    return cn_title[:30]
                return random.choice(["国际知产新动态", "海外知产速递", "全球知产关注"])

            # 去除标点获得纯文本
            title = re.sub(r'[^一-鿿a-zA-Z0-9\s]', '', title)
            title = re.sub(r'\s+', '', title)
            title = title.strip()

            # === hot_topic 类别：吸睛标题策略 ===
            if category == "hot_topic":
                return self._generate_hot_title(title)
            # ===================================

            # 控制在28字以内（留2字余量给前缀）
            if len(title) > 28:
                for sep in ['，', '、', '与', '和', '；', ' ', ',', '：', ':']:
                    idx = title.rfind(sep, 14, 28)
                    if idx > 0:
                        title = title[:idx]
                        break
                else:
                    title = title[:28]

            # 标题本身>=20字则不加前缀，够醒目
            if len(title) >= 20:
                return title

            # 短标题加前缀
            prefix = random.choice(["关注", "解读", "聚焦", "深度"])
            candidate = f"{prefix}{title}"
            if len(candidate) <= 30:
                return candidate
            return title

        except Exception as e:
            logger.error(f"生成标题失败: {e}")
            return "知识产权新动态"

    def _generate_hot_title(self, title):
        """为 hot_topic 类别生成吸睛标题（八卦但不低俗，合法合规）。
        策略：优先保留原标题的悬念感，否则用钩子句式重写。
        """
        # 策略1：标题本身已有数字/金额/问号 → 直接使用（天然的吸睛元素）
        has_number = bool(re.search(r'\d+', title))
        has_hook = any(kw in title for kw in ['？', '?', '！', '!', '赔偿', '判决',
                                                '反转', '惊人', '天价', '曝光', '争议',
                                                '翻车', '索赔', '起诉', '维权', '胜诉',
                                                '败诉', '背后', '真相', '内幕'])
        if has_number and has_hook and len(title) <= 30:
            return title

        # 策略2：标题已足够吸睛（含钩子词）→ 直接使用
        if has_hook and len(title) <= 28:
            return title

        # 策略3：截断后用钩子句式包装
        # 先截到合适长度
        short = title
        if len(short) > 22:
            for sep in ['，', '、', '与', '和', '；', ' ', ',', '：', ':']:
                idx = short.rfind(sep, 10, 22)
                if idx > 0:
                    short = short[:idx]
                    break
            else:
                short = short[:22]

        # 吸睛句式模板（随机选用，增加多样性）
        hooks = [
            f"{short}？律师这样看",
            f"{short}背后的法律逻辑",
            f"{short}如何维权",
            f"深度解读{short}",
            f"{short}案的法律启示",
            f"关注{short}",
        ]
        candidate = random.choice(hooks)
        if len(candidate) <= 30:
            return candidate

        # 兜底：钩子+短标题
        short2 = short[:18] if len(short) > 18 else short
        candidate2 = f"{short2}？法律怎么说"
        if len(candidate2) <= 30:
            return candidate2
        return short[:30]

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

        每批3条分别调用 LLM，小批次避免 token 被推理消耗殆尽。

        Returns:
            [str] 与 items 等长的摘要列表（失败时用标题截断兜底）
        """
        if not items:
            return []

        import re
        batch_size = 3
        all_summaries = [""] * len(items)

        for batch_start in range(0, len(items), batch_size):
            batch_end = min(batch_start + batch_size, len(items))
            batch_items = items[batch_start:batch_end]

            titles_text = "\n".join(
                f"{j+1}. [{it.get('source', '')}] {it['title']}"
                for j, it in enumerate(batch_items)
            )

            prompt = f"""你是一位知识产权新闻编辑。请为以下每条新闻撰写一句简短摘要（≤{max_chars}字），说清楚发生了什么。
只输出编号和摘要，格式如"1. 摘要内容"，每条一行，不要其他文字。

{titles_text}"""

            logger.info(f"批量摘要 LLM 调用: {batch_start+1}-{batch_end}/{len(items)} ({len(batch_items)}条)")
            content = self._call_llm_mini(prompt, max_tokens=8192)
            if not content:
                logger.warning(f"批次 {batch_start+1}-{batch_end} LLM 返回为空（已自动重试），使用标题兜底")
                for j, item in enumerate(batch_items):
                    title = item.get("title", "")
                    all_summaries[batch_start + j] = title[:max_chars] if len(title) > max_chars else title
                continue

            for j, item in enumerate(batch_items):
                idx = j + 1
                patterns = [
                    rf'{idx}\.\s*(.+?)(?:\n|$)',
                    rf'{idx}[、]\s*(.+?)(?:\n|$)',
                    rf'{idx}\)\s*(.+?)(?:\n|$)',
                    rf'{idx}\s+(\S.+?)(?:\n|$)',
                    rf'{idx}[：:]\s*(.+?)(?:\n|$)',
                ]
                matched = False
                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        summary = match.group(1).strip()
                        if len(summary) >= 8 and not summary.startswith('['):
                            if len(summary) > max_chars:
                                summary = summary[:max_chars]
                            all_summaries[batch_start + j] = summary
                            matched = True
                            break

                if not matched:
                    title = item.get("title", "")
                    all_summaries[batch_start + j] = title[:max_chars] if len(title) > max_chars else title

        ai_count = len([s for s in all_summaries if s and len(s) < 120 and s != ""])
        logger.info(f"批量摘要生成: {ai_count}/{len(items)} 条（含AI生成）")
        return all_summaries

    def _call_llm_mini(self, prompt, max_tokens=2048):
        """轻量 LLM 调用，用于摘要/翻译等短任务（含529过载重试）"""
        from config import Config
        import time, json
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": Config.MINIMAX_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_completion_tokens": max(max_tokens, 2048),
            "thinking": {"type": "disabled"}
        }

        for attempt in range(3):
            try:
                t0 = time.time()
                logger.info(f"轻量LLM调用 attempt={attempt+1}, max_tokens={data['max_completion_tokens']}, prompt_len={len(prompt)}")
                response = requests.post(
                    self.api_url, headers=headers, json=data, timeout=120
                )
                elapsed = time.time() - t0

                if response.status_code == 200:
                    result = response.json()
                    if "choices" in result and len(result["choices"]) > 0:
                        choice = result["choices"][0]
                        msg = choice.get("message", {})
                        content = msg.get("content", "")
                        finish = choice.get("finish_reason", "")

                        if not content and finish == "length" and attempt < 2:
                            data["max_completion_tokens"] = data["max_completion_tokens"] * 2
                            logger.warning(f"轻量LLM content为空(finish=length)，加倍max_tokens={data['max_completion_tokens']}重试")
                            time.sleep(2)
                            continue

                        if not content:
                            logger.warning(f"轻量LLM返回空content, finish={finish}: {json.dumps(result, ensure_ascii=False)[:300]}")
                        else:
                            logger.info(f"轻量LLM完成: {elapsed:.1f}s, content_len={len(content)}")
                        return content
                    else:
                        logger.warning(f"轻量LLM返回无choices: {json.dumps(result, ensure_ascii=False)[:300]}")
                        return None
                elif response.status_code == 529:
                    wait = 2 ** attempt * 5
                    logger.warning(f"轻量LLM 529过载，{wait}s后重试...")
                    time.sleep(wait)
                    continue
                else:
                    logger.error(f"轻量LLM调用失败: HTTP {response.status_code} - {response.text[:200]}")
                    return None

            except requests.exceptions.Timeout:
                logger.error(f"轻量LLM超时 (>{120}s)")
                if attempt < 2:
                    time.sleep(3)
            except Exception as e:
                logger.error(f"轻量LLM调用异常: {e}")
                if attempt < 2:
                    time.sleep(3)

        return None

    def generate_cover_image(self, title, category="general"):
        """
        从 Unsplash 搜索并下载封面图，返回符合微信要求(900x383)的 JPEG bytes。

        Args:
            title: 文章标题，用于提取搜索关键词
            category: 文章类别 (patent/general_ip/hot_topic)

        Returns:
            图片 bytes (JPEG) 或 None（失败时）
        """
        from config import Config
        import io

        query = self._build_unsplash_query(title, category)
        image_url = self._search_unsplash(query, orientation="landscape", count=5)

        # 首次搜索无结果 → 用纯类别主题词兜底重试
        if not image_url:
            fallback_themes = {
                "patent": "patent office technology law innovation",
                "general_ip": "intellectual property law justice",
                "hot_topic": "news media journalism headlines newspaper",
            }
            fallback = fallback_themes.get(category, "law technology abstract")
            logger.info(f"Unsplash 首次搜索无结果，兜底重试: {fallback}")
            image_url = self._search_unsplash(fallback, orientation="landscape", count=5)

        if not image_url:
            logger.warning(f"Unsplash 封面图搜索无结果: {title[:30]}...")
            return None

        try:
            logger.info(f"Unsplash 封面图下载中...")
            img_resp = requests.get(image_url, timeout=30)
            if img_resp.status_code == 200:
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
                logger.info(f"Unsplash 封面图处理完成 (900x383 JPEG)")
                return output.getvalue()
            else:
                logger.error(f"下载 Unsplash 封面图失败: HTTP {img_resp.status_code}")
        except Exception as e:
            logger.error(f"Unsplash 封面图处理异常: {e}")

        return None

    def _search_unsplash(self, query, orientation="landscape", count=5):
        """搜索 Unsplash 图片，返回最合适的图片 URL"""
        from config import Config
        try:
            url = f"{Config.UNSPLASH_API_URL}/search/photos"
            headers = {
                "Authorization": f"Client-ID {Config.UNSPLASH_ACCESS_KEY}",
                "Accept-Version": "v1",
            }
            params = {
                "query": query,
                "orientation": orientation,
                "per_page": count,
            }
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    # 取第1张（相关性最高）或随机取一张增加多样性
                    import random
                    chosen = random.choice(results[:min(count, len(results))])
                    img_url = chosen["urls"].get("regular") or chosen["urls"].get("raw")
                    desc = chosen.get("alt_description") or chosen.get("description") or ""
                    user = chosen.get("user", {})
                    photographer = user.get("name", "")
                    if photographer:
                        logger.info(f"Unsplash 图片: {desc[:40]}... (Photographer: {photographer})")
                    return img_url
            elif resp.status_code == 403:
                logger.error(f"Unsplash API 403 (可能超过限流): {resp.text[:200]}")
            else:
                logger.error(f"Unsplash API 错误: {resp.status_code} - {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Unsplash 搜索异常: {e}")
        return None

    def _translate_to_english_keywords(self, title):
        """用 LLM 将中文标题翻译为 Unsplash 英文搜索关键词"""
        prompt = (
            f"Translate the following Chinese article title into 3-5 English keywords "
            f"suitable for searching photos on Unsplash. Return ONLY the keywords separated "
            f"by spaces, no other text, no punctuation.\n\nTitle: {title}"
        )
        try:
            result = self._call_llm_mini(prompt, max_tokens=128)
            if result:
                # 清理：只保留英文单词和空格
                import re
                keywords = re.sub(r'[^a-zA-Z\s]', '', result).strip()
                if keywords and len(keywords) >= 6:
                    logger.info(f"Unsplash 中译英: '{title[:30]}...' → '{keywords}'")
                    return keywords
        except Exception as e:
            logger.warning(f"Unsplash 关键词翻译失败: {e}")
        return ""

    def _build_unsplash_query(self, title, category):
        """根据文章标题和类别构建 Unsplash 英文搜索词"""
        import re

        # 类别到英文主题词的映射
        category_themes = {
            "patent": "technology innovation abstract",
            "general_ip": "intellectual property law justice abstract",
            "hot_topic": "law justice society abstract",
        }
        theme = category_themes.get(category, category_themes["general_ip"])

        # 通用英文词（对图片搜索无帮助）
        common_words = {
            "the", "and", "for", "with", "from", "that", "this", "have",
            "been", "will", "about", "more", "news", "update", "latest",
            "today", "daily", "read", "subscribe", "contact", "page",
        }

        # 1. 从标题中提取有意义的英文关键词（过滤全大写缩写词和通用词）
        english_words = [w for w in re.findall(r'[a-zA-Z]{3,}', title)
                        if not w.isupper() and w.lower() not in common_words]
        if english_words:
            en_keywords = " ".join(english_words[:3])
            query = f"{en_keywords} {theme}"
            # 如果构建的 query 过长（>80字符），截断
            if len(query) > 80:
                query = query[:80]
            return query

        # 2. 检查标题是否包含中文 — 走 LLM 翻译
        chinese_chars = len(re.findall(r'[一-鿿]', title))
        if chinese_chars >= 3 or not english_words:
            # 有中文 或 英文词全被过滤 → 用 LLM 翻译
            translated = self._translate_to_english_keywords(title)
            if translated:
                return f"{translated} {theme}"

        return theme

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
