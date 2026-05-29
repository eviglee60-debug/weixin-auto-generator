"""热点法律话题发现器 - 基于 last30days-cn 技能搜索中国平台热点"""

import json
import logging
import os
import re
import requests
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# last30days-cn 技能路径
SKILL_SCRIPT = os.path.expanduser("~/.claude/skills/last30days-cn/scripts/last30days.py")

# 热点话题搜索关键词 — 覆盖四类大众话题 + 法律底色
# 工具性目标：搜到有讨论量的热点，再用 LLM 打分筛选（>60分入选）
LEGAL_SEARCH_QUERIES = [
    # === 八卦娱乐向：明星动态、影视热播、综艺爆点 ===
    "明星 八卦 热搜 话题 讨论",
    "热播剧 热议 讨论 剧情",
    "综艺 节目 爆点 话题 热搜",
    "娱乐圈 热点 新闻 讨论",
    "网红 事件 热议 话题 热搜",
    "影视 热映 讨论 票房 话题",
    # === 时尚潮流向：穿搭/美妆/消费趋势 ===
    "穿搭 潮流 趋势 热门 话题",
    "美妆 护肤 新品 推荐 热门",
    "消费 趋势 生活方式 热门",
    "时尚 话题 讨论 热门 趋势",
    # === 养生保健向：健康科普/饮食/慢病 ===
    "健康 科普 养生 知识 热门",
    "饮食 健康 营养 话题 热搜",
    "慢性病 管理 保健 中老年",
    "中老年 健康 养生 保健 话题",
    # === 法律向：保持IP/法律底色 ===
    "天价 赔偿 判决 案例",
    "消费 维权 案例 最新",
    "法律 热点 社会 话题",
    "纠纷 案例 法律 解读",
    "平台 监管 处罚 案例",
    "个人信息 泄露 维权 判决",
    "食品安全 违规 处罚 案例",
]

# 热门平台关键词（用于筛选结果）
HOT_PLATFORMS = ["weibo", "bilibili", "zhihu", "toutiao"]

# 热点话题 LLM 评分 Prompt — 100分制，>60分入选
HOTSPOT_SCORE_PROMPT = """对以下文章按100分制打分，标准：
- 话题热度与流量潜力（微博/抖音/小红书是否在讨论，能否带来阅读量）：40分
- 情绪触发（能引发共鸣/好奇/争议/讨论欲）：35分
- 受众广度（老中青均可读懂）：15分
- 不低俗即可（非色情暴力赌博吸毒）：10分（低俗则0分）
注意：不需要考虑政治合规，只排除明显低俗内容。
只返回分数和一句理由。
格式: 分数|理由"""


class HotTopicFinder:
    def __init__(self):
        self.skill_script = SKILL_SCRIPT
        self.available = os.path.exists(self.skill_script)

    def find_hot_topic(self, query=None, days=7):
        """
        搜索热点话题，最多尝试3个不同搜索词，直到找到>50分的热点。

        Returns:
            dict: {"title": str, "source": str, "url": str, "content": str, "score": int}
            None: 如果3次均未找到合适话题
        """
        if not self.available:
            logger.warning("last30days-cn 技能不可用")
            return None

        for attempt in range(3):
            if attempt == 0 and query:
                search_query = query
            else:
                search_query = self._select_query(attempt)

            logger.info(f"搜索热点话题 (attempt {attempt+1}/3): {search_query}")

            try:
                result = self._run_search(search_query, days)
                if not result:
                    logger.warning(f"  搜索无结果, 尝试下一个关键词")
                    continue

                topic = self._select_best_topic(result, search_query)
                if topic:
                    logger.info(f"发现热点话题: {topic['title'][:40]}... (score={topic.get('score', 0)})")
                    return topic

                logger.info(f"  未找到>50分话题, 尝试下一个关键词")
            except Exception as e:
                logger.warning(f"  搜索异常: {e}, 尝试下一个关键词")
                continue

        logger.info("3次搜索均未找到合适的热点话题")
        return None

    def _select_query(self, attempt=0):
        """轮换搜索关键词 — 首次偏爱八卦/时尚/养生，重试保证不重复"""
        t = int(time.time()) // 60  # 分钟级粒度
        if attempt == 0:
            # 优先从吸睛类中选取（八卦娱乐6 + 时尚潮流4 + 养生保健4 = 14个）
            engaging = LEGAL_SEARCH_QUERIES[:14]
            return engaging[t % len(engaging)]
        else:
            # 重试时全量轮换，素数偏移保证不同
            primes = [11, 17]
            offset = primes[(attempt - 1) % len(primes)]
            return LEGAL_SEARCH_QUERIES[(t + offset) % len(LEGAL_SEARCH_QUERIES)]

    def _run_search(self, query, days=7):
        """执行 last30days-cn 搜索"""
        try:
            cmd = [
                "python3", self.skill_script,
                query,
                "--emit", "json",
                "--quick",
                "--days", str(days),
            ]

            env = os.environ.copy()
            env["PYTHONPATH"] = os.path.dirname(self.skill_script)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )

            if result.returncode != 0:
                logger.warning(f"搜索命令失败: {result.stderr[:200]}")
                return None

            # 解析 JSON 输出
            output = result.stdout
            # 找到 JSON 开始的位置
            json_start = output.find('{')
            if json_start == -1:
                logger.warning("输出中未找到 JSON")
                return None

            data = json.loads(output[json_start:])
            return data

        except subprocess.TimeoutExpired:
            logger.warning("搜索超时")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"执行搜索异常: {e}")
            return None

    def _select_best_topic(self, data, query):
        """从搜索结果中选择最佳话题 — 关键词初筛 + LLM终评（>50分入选）"""
        all_items = []

        # 收集所有平台的结果
        for platform in HOT_PLATFORMS:
            items = data.get(platform, [])
            for item in items:
                item["_platform"] = platform
                all_items.append(item)

        if not all_items:
            return None

        # 硬性过滤 + 关键词初评
        filtered = []
        for item in all_items:
            # 获取文本内容（优先 title，其次 description，最后 why_relevant）
            text = item.get("title", "") or item.get("description", "") or item.get("why_relevant", "")
            if not text or text == "-":
                text = item.get("title", "")

            # 跳过太短或空的内容
            if len(text.strip()) < 10:
                continue

            # 使用 _should_skip 进行硬性过滤
            if self._should_skip(text):
                continue

            # 计算综合基础分数（关键词 + 互动）
            score = item.get("score", 0)
            engagement = item.get("engagement", {})

            likes = engagement.get("likes", 0)
            comments = engagement.get("num_comments", 0)
            reposts = engagement.get("reposts", 0)
            engagement_score = min(50, likes // 10 + comments * 3 + reposts * 2)

            # 四类话题关键词评分
            hot_keywords = [
                # 法律专业词（高权重 ×4）
                "维权", "赔偿", "纠纷", "判决", "法院", "律师", "法律",
                "诈骗", "消费者", "劳动", "工伤", "侵权", "违法", "处罚",
                "监管", "合规", "受害者", "被告", "原告", "索赔", "起诉",
                # 八卦娱乐词（中权重 ×3）
                "明星", "热播", "综艺", "娱乐圈", "影视", "网红", "票房",
                "八卦", "热议", "争议", "曝光", "揭秘", "反转", "天价",
                # 时尚潮流词（中权重 ×3）
                "穿搭", "美妆", "护肤", "时尚", "潮流", "新品", "消费趋势",
                "生活方式", "种草", "测评",
                # 养生保健词（中权重 ×3）
                "健康", "养生", "饮食", "保健", "慢性病", "中老年", "营养",
                "减肥", "睡眠", "运动",
                # 通用场景词
                "房产", "婚姻", "继承", "交通", "医疗", "教育", "就业",
                "合同", "债务", "假冒", "虚假", "食品安全", "个人信息",
            ]
            legal_kw_count = sum(1 for kw in hot_keywords[:20] if kw in text)
            hot_kw_count = sum(1 for kw in hot_keywords[20:] if kw in text)
            hot_relevance = legal_kw_count * 4 + hot_kw_count * 3

            completeness = 20 if len(text) > 100 else 0

            final_score = score + engagement_score + hot_relevance + completeness
            item["_final_score"] = final_score
            item["_text"] = text  # 保存提取的文本
            filtered.append(item)

        if not filtered:
            return None

        # 按关键词分数排序，取前5名送LLM终评
        filtered.sort(key=lambda x: x["_final_score"], reverse=True)
        candidates = filtered[:5]

        # LLM 评分（>50分入选）
        best = None
        best_llm_score = 0
        for candidate in candidates:
            text = candidate.get("_text", "")
            llm_score, llm_reason = self._score_with_llm(text)
            if llm_score is None:
                continue
            candidate["_llm_score"] = llm_score
            candidate["_llm_reason"] = llm_reason
            logger.info(f"  LLM评分 {llm_score}/100: {text[:30]}... | {llm_reason}")
            if llm_score >= 50 and llm_score > best_llm_score:
                best = candidate
                best_llm_score = llm_score

        if best is None:
            logger.info("  LLM评分无>50分的候选话题，不替换")
            return None

        text = best.get("_text", "")
        title = self._extract_title(text)

        return {
            "title": title,
            "source": self._platform_name(best.get("_platform", "")),
            "url": best.get("url", ""),
            "content": text[:500],
            "score": best_llm_score,
            "engagement": best.get("engagement", {}),
            "date": best.get("date", ""),
        }

    def _score_with_llm(self, text):
        """LLM评分热点话题 — 返回 (分数, 理由) 或 (None, None)"""
        try:
            from config import Config
            payload = {
                "model": Config.MINIMAX_MODEL,
                "messages": [
                    {"role": "user", "content": f"{HOTSPOT_SCORE_PROMPT}\n\n文章内容:\n{text[:500]}"}
                ],
                "temperature": 0.3,
                "max_tokens": 512,  # 增加 tokens，避免 reasoning_content 消耗完
            }
            resp = requests.post(
                Config.MINIMAX_API_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {Config.MINIMAX_API_KEY}",
                },
                json=payload,
                timeout=30,
            )
            if resp.status_code != 200:
                logger.warning(f"  LLM评分请求失败: {resp.status_code}")
                return None, None

            result = resp.json()
            content = ""
            if "choices" in result and len(result["choices"]) > 0:
                msg = result["choices"][0].get("message", {})
                content = msg.get("content", "")
                # 如果 content 为空，尝试从 reasoning_content 提取
                if not content:
                    reasoning = msg.get("reasoning_content", "")
                    if reasoning:
                        # 尝试从推理内容中提取分数
                        score_match = re.search(r'(\d{1,3})\s*[分/]', reasoning)
                        if score_match:
                            score = int(score_match.group(1))
                            # 提取理由（分数后面的内容）
                            reason_start = reasoning.find(score_match.group(0))
                            reason = reasoning[reason_start:reason_start+100] if reason_start >= 0 else ""
                            return score, reason

            if not content:
                return None, None

            # 解析 "分数|理由"
            parts = content.strip().split("|", 1)
            score_str = re.sub(r'[^\d]', '', parts[0])
            score = int(score_str) if score_str else 0
            reason = parts[1].strip() if len(parts) > 1 else ""
            return score, reason

        except Exception as e:
            logger.warning(f"  LLM评分异常: {e}")
            return None, None

    def _extract_title(self, text):
        """从文本中提取合适的标题"""
        import html
        # 解码 HTML 实体
        text = html.unescape(text)
        # 移除话题标签
        text = re.sub(r'#\S+#', '', text)
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text).strip()

        # 取前50个字符，找到合适的断句点
        if len(text) <= 50:
            return text

        # 在50个字符附近找到标点符号断句
        for i in range(45, min(55, len(text))):
            if text[i] in '，。！？；：':
                return text[:i + 1]

        return text[:50] + "..."

    def _platform_name(self, platform):
        """平台名称映射"""
        names = {
            "weibo": "微博",
            "bilibili": "B站",
            "zhihu": "知乎",
            "toutiao": "今日头条",
            "xiaohongshu": "小红书",
            "douyin": "抖音",
            "wechat": "微信公众号",
            "baidu": "百度",
        }
        return names.get(platform, platform)

    def find_digest_items(self, categories=None, days=7):
        """
        搜索多类法律资讯，用于速览文章。

        Args:
            categories: 搜索类别列表，默认为各类法律热点
            days: 回溯天数

        Returns:
            list: [{"title": str, "source": str, "url": str, "category": str}]
        """
        if not self.available:
            return []

        if not categories:
            # 扩展搜索类别 - 覆盖用户关心的各类实用法律资讯 + 社会热点
            # 确保知识产权相关内容占比超过1/3
            categories = [
                # === 知识产权法律法规与政策（8个）===
                {"query": "知识产权 政策 办法 施行", "label": "知识产权新规", "priority": 3},
                {"query": "专利法 实施细则 修改 发布", "label": "专利法新规", "priority": 3},
                {"query": "商标法 修改 规定 发布", "label": "商标法新规", "priority": 3},
                {"query": "著作权法 修改 施行", "label": "著作权法新规", "priority": 3},
                {"query": "知识产权 侵权 赔偿 判决 典型", "label": "知产侵权案例", "priority": 3},
                {"query": "知识产权 申请 审查 变化 公告", "label": "知产流程变化", "priority": 3},
                {"query": "海外知识产权 保护 纠纷 案例", "label": "海外知产保护", "priority": 3},
                {"query": "WIPO EPO USPTO 最新 动态", "label": "国际知产动态", "priority": 3},
                # === 其他法律法规与政策（4个）===
                {"query": "国务院 条例 规章 发布 实施", "label": "新规速递", "priority": 2},
                {"query": "最高人民法院 司法解释 规定", "label": "司法解释", "priority": 2},
                {"query": "市场监管 法规 公告", "label": "市场监管", "priority": 2},
                {"query": "反垄断 处罚 典型案例", "label": "反垄断案例", "priority": 2},
                # === 典型案例（4个）===
                {"query": "最高人民法院 典型案例 指导性案例", "label": "最高院案例", "priority": 2},
                {"query": "高级法院 典型案例 公布", "label": "高院案例", "priority": 2},
                {"query": "法院 立案 改革 新规 流程", "label": "诉讼流程变化", "priority": 2},
                {"query": "专利 商标 审查 时限 调整", "label": "审查周期调整", "priority": 2},
                # === 一带一路与国际（2个）===
                {"query": "一带一路 投资 法律 合规 风险", "label": "一带一路", "priority": 2},
                {"query": "跨境电商 法律 合规 案例", "label": "跨境电商", "priority": 2},
                # === 社会热点法律问题（6个）===
                {"query": "消费者 权益 保护 典型案例", "label": "消费维权", "priority": 2},
                {"query": "劳动纠纷 典型案例 判决", "label": "劳动纠纷", "priority": 2},
                {"query": "个人信息保护 数据 法律 案例", "label": "数据合规", "priority": 2},
                {"query": "平台经济 反垄断 监管 案例", "label": "平台监管", "priority": 2},
                # === 普通老百姓关注的社会热点（6个）===
                {"query": "食品安全 违规 处罚 热搜", "label": "食品安全", "priority": 1},
                {"query": "教育 培训 退款 纠纷 曝光", "label": "教育维权", "priority": 1},
                {"query": "医疗 美容 纠纷 投诉 热搜", "label": "医疗维权", "priority": 1},
                {"query": "房价 楼盘 烂尾 维权 最新", "label": "房产维权", "priority": 1},
                {"query": "网购 假货 投诉 维权 最新", "label": "网购维权", "priority": 1},
                {"query": "旅游 出行 纠纷 维权 热搜", "label": "旅游维权", "priority": 1},
            ]

        # 知识产权相关的标签（用于后续统计）
        IP_LABELS = {"知识产权新规", "专利法新规", "商标法新规", "著作权法新规", "知产侵权案例",
                     "知产流程变化", "海外知产保护", "国际知产动态"}

        seen_titles = set()

        # 并发搜索，4线程
        priority_groups = {3: [], 2: [], 1: []}
        max_workers = min(4, len(categories))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._run_search, cat["query"], days): cat
                for cat in categories
            }
            for future in as_completed(futures):
                cat_info = futures[future]
                label = cat_info["label"]
                priority = cat_info.get("priority", 2)
                try:
                    result = future.result()
                    if not result:
                        continue
                    cat_items = []
                    for platform in HOT_PLATFORMS:
                        for item in result.get(platform, []):
                            text = item.get("text", "")
                            url = item.get("url", "")
                            if len(text.strip()) < 20:
                                continue
                            title = self._extract_title(text)
                            if title in seen_titles:
                                continue
                            seen_titles.add(title)
                            if self._should_skip(text):
                                continue
                            cat_items.append({
                                "title": title,
                                "source": self._platform_name(platform),
                                "url": url,
                                "category": label,
                                "score": item.get("score", 0) + priority * 10,
                            })
                    cat_items.sort(key=lambda x: x["score"], reverse=True)
                    for item in cat_items[:3]:
                        priority_groups[priority].append(item)
                except Exception as e:
                    logger.warning(f"搜索 {label} 失败: {e}")

        # 合并：IP内容(item_limit_per_priority, ip_target_ratio)保证知产占比
        import random
        item_limit_per_priority = {3: 6, 2: 8, 1: 6}
        ip_target_ratio = 1.0 / 3  # IP内容至少占1/3

        ip_pool = {p: [it for it in priority_groups[p] if it.get("category") in IP_LABELS] for p in [3, 2, 1]}
        non_ip_pool = {p: [it for it in priority_groups[p] if it.get("category") not in IP_LABELS] for p in [3, 2, 1]}

        for p in [3, 2, 1]:
            random.shuffle(ip_pool[p])
            random.shuffle(non_ip_pool[p])

        result_items = []
        total_ip = 0
        for priority in [3, 2, 1]:
            limit = item_limit_per_priority.get(priority, 6)
            # 取IP条目（不超过limit的2/3）
            ip_limit = min(len(ip_pool[priority]), limit * 2 // 3)
            taken_ip = ip_pool[priority][:ip_limit]
            total_ip += len(taken_ip)
            result_items.extend(taken_ip)
            # 用非IP条目补足到limit
            remaining = limit - len(taken_ip)
            taken_non_ip = non_ip_pool[priority][:remaining]
            result_items.extend(taken_non_ip)

        # 如果IP内容仍不足1/3，用剩余IP替换尾部非IP
        target_ip = max(int(len(result_items) * ip_target_ratio) + 1, total_ip)
        if total_ip < target_ip:
            deficit = target_ip - total_ip
            # 收集所有未使用的IP条目
            unused_ip = []
            for p in [3, 2, 1]:
                used_ip_titles = {it["title"] for it in result_items if it.get("category") in IP_LABELS}
                for it in ip_pool[p]:
                    if it["title"] not in used_ip_titles:
                        unused_ip.append(it)
            random.shuffle(unused_ip)
            # 从后往前替换非IP条目
            for i in range(len(result_items) - 1, -1, -1):
                if deficit <= 0:
                    break
                if result_items[i].get("category") not in IP_LABELS and unused_ip:
                    result_items[i] = unused_ip.pop(0)
                    deficit -= 1

        return result_items[:20]

    def _should_skip(self, text):
        """硬性过滤：政治敏感 / 低俗色情 / 暴力 / 会议活动 / 无意义内容"""
        political_keywords = ["总书记", "国家主席", "总理", "常委", "政治局", "中央", "国务院",
                              "党委", "党支部", "党员", "反动", "颠覆", "分裂", "抗议", "示威", "游行",
                              "马英九", "台湾", "国民党", "民进党", "两岸"]  # 政治人物/事件
        vulgar_keywords = ["色情", "裸体", "性侵", "强奸", "卖淫", "嫖娼", "赌博", "毒品",
                           "暴力", "血腥", "恐怖", "自杀", "虐待"]
        # 会议/活动类内容（不适合吸睛主题）
        meeting_keywords = ["研讨会", "交流会", "论坛", "峰会", "座谈会", "发布会",
                           "启动仪式", "开幕式", "闭幕式", "培训", "讲座", "宣讲"]
        # 无意义/广告内容
        skip_patterns = ["关于搜狗", "企业推广", "反馈", "点击链接", "转发抽奖", "广告推广",
                        "corp.sogou.com", "sogou.com"]

        for kw in political_keywords + vulgar_keywords + meeting_keywords + skip_patterns:
            if kw in text:
                return True

        return False


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    finder = HotTopicFinder()
    topic = finder.find_hot_topic("知识产权 法律 热点")
    if topic:
        print(f"标题: {topic['title']}")
        print(f"来源: {topic['source']}")
        print(f"分数: {topic['score']}")
        print(f"链接: {topic['url']}")
    else:
        print("未找到话题")
