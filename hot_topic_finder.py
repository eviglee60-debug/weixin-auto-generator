"""热点法律话题发现器 - 基于 last30days-cn 技能搜索中国平台热点"""

import json
import logging
import os
import re
import subprocess
import time

logger = logging.getLogger(__name__)

# last30days-cn 技能路径
SKILL_SCRIPT = os.path.expanduser("~/.claude/skills/last30days-cn/scripts/last30days.py")

# 法律相关搜索关键词（按热度轮换，覆盖老百姓关注的各类法律热点）
LEGAL_SEARCH_QUERIES = [
    "最新法律案例 热点",
    "法院 判决 热门",
    "法律 纠纷 热搜",
    "维权 案例 最新",
    "法律 解读 社会",
    "消费 维权 案例",
    "劳动 纠纷 判决",
    "婚姻 继承 纠纷",
    "房产 纠纷 案例",
    "交通事故 赔偿 判决",
    "网络 诈骗 维权",
    "医患 纠纷 案例",
]

# 热门平台关键词（用于筛选结果）
HOT_PLATFORMS = ["weibo", "bilibili", "zhihu", "toutiao"]


class HotTopicFinder:
    def __init__(self):
        self.skill_script = SKILL_SCRIPT
        self.available = os.path.exists(self.skill_script)

    def find_hot_topic(self, query=None, days=7):
        """
        搜索热点法律话题，返回最适合做文章的话题。

        Returns:
            dict: {"title": str, "source": str, "url": str, "content": str, "score": int}
            None: 如果未找到合适话题
        """
        if not self.available:
            logger.warning("last30days-cn 技能不可用")
            return None

        # 选择搜索关键词
        if not query:
            query = self._select_query()

        logger.info(f"搜索热点法律话题: {query}")

        try:
            # 调用 last30days-cn 技能
            result = self._run_search(query, days)

            if not result:
                logger.warning("搜索无结果")
                return None

            # 分析结果，选择最佳话题
            topic = self._select_best_topic(result, query)

            if topic:
                logger.info(f"发现热点话题: {topic['title'][:40]}... (score={topic.get('score', 0)})")
            else:
                logger.info("未找到合适的热点话题")

            return topic

        except Exception as e:
            logger.error(f"搜索热点话题失败: {e}")
            return None

    def _select_query(self):
        """轮换搜索关键词，避免重复"""
        # 使用时间戳来轮换关键词
        index = int(time.time()) % len(LEGAL_SEARCH_QUERIES)
        return LEGAL_SEARCH_QUERIES[index]

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
        """从搜索结果中选择最佳话题"""
        all_items = []

        # 收集所有平台的结果
        for platform in HOT_PLATFORMS:
            items = data.get(platform, [])
            for item in items:
                item["_platform"] = platform
                all_items.append(item)

        if not all_items:
            return None

        # 过滤并选择最佳话题（老百姓关注、能用法律视角分析的热点）
        filtered = []
        for item in all_items:
            text = item.get("text", "")
            title = item.get("text", "")[:100]

            # 跳过太短或空的内容
            if len(text.strip()) < 20:
                continue

            # 跳过纯广告或推广
            if any(skip in text for skip in ["转发抽奖", "点击链接", "广告推广"]):
                continue

            # 跳过政治敏感内容
            political_keywords = ["总书记", "国家主席", "总理", "常委", "政治局", "中央", "国务院",
                                  "党委", "党支部", "党员", "反动", "颠覆", "分裂", "抗议", "示威", "游行"]
            if any(kw in text for kw in political_keywords):
                continue

            # 跳过低俗内容
            vulgar_keywords = ["色情", "裸体", "性侵", "强奸", "卖淫", "嫖娼", "赌博", "毒品"]
            if any(kw in text for kw in vulgar_keywords):
                continue

            # 计算综合分数
            score = item.get("score", 0)
            engagement = item.get("engagement", {})

            # 增加互动权重（老百姓爱看的内容互动高）
            likes = engagement.get("likes", 0)
            comments = engagement.get("num_comments", 0)
            reposts = engagement.get("reposts", 0)
            engagement_score = min(50, likes // 10 + comments * 3 + reposts * 2)

            # 热点事件相关性（能用法律视角分析的关键词）
            hot_keywords = ["维权", "赔偿", "纠纷", "判决", "法院", "律师", "法律",
                            "诈骗", "投诉", "曝光", "揭秘", "消费者", "劳动", "工伤",
                            "房产", "婚姻", "继承", "交通", "医疗", "教育", "就业",
                            "合同", "债务", "侵权", "假冒", "虚假", "违法", "处罚"]
            hot_relevance = sum(1 for kw in hot_keywords if kw in text) * 3

            final_score = score + engagement_score + hot_relevance

            item["_final_score"] = final_score
            filtered.append(item)

        if not filtered:
            return None

        # 按分数排序
        filtered.sort(key=lambda x: x["_final_score"], reverse=True)

        # 选择最佳话题
        best = filtered[0]
        text = best.get("text", "")

        # 提取标题（前50个字符，找到合适的断句点）
        title = self._extract_title(text)

        return {
            "title": title,
            "source": self._platform_name(best.get("_platform", "")),
            "url": best.get("url", ""),
            "content": text[:500],
            "score": best.get("_final_score", 0),
            "engagement": best.get("engagement", {}),
            "date": best.get("date", ""),
        }

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
            # 扩展搜索类别 - 覆盖用户关心的各类实用法律资讯
            categories = [
                # === 法律法规与政策 ===
                {"query": "国务院 条例 规章 发布 实施", "label": "新规速递", "priority": 3},
                {"query": "最高人民法院 司法解释 规定", "label": "司法解释", "priority": 3},
                {"query": "知识产权 政策 办法 施行", "label": "知识产权新规", "priority": 3},
                {"query": "市场监管 法规 公告", "label": "市场监管", "priority": 2},
                # === 典型案例 ===
                {"query": "最高人民法院 典型案例 指导性案例", "label": "最高院案例", "priority": 3},
                {"query": "高级法院 典型案例 公布", "label": "高院案例", "priority": 2},
                {"query": "知识产权 侵权 赔偿 判决 典型", "label": "知产侵权案例", "priority": 3},
                {"query": "反垄断 处罚 典型案例", "label": "反垄断案例", "priority": 2},
                # === 流程与制度改革 ===
                {"query": "法院 立案 改革 新规 流程", "label": "诉讼流程变化", "priority": 2},
                {"query": "知识产权 申请 审查 变化 公告", "label": "知产流程变化", "priority": 3},
                {"query": "专利 商标 审查 时限 调整", "label": "审查周期调整", "priority": 2},
                # === 一带一路与国际 ===
                {"query": "一带一路 投资 法律 合规 风险", "label": "一带一路", "priority": 3},
                {"query": "跨境电商 法律 合规 案例", "label": "跨境电商", "priority": 2},
                {"query": "海外知识产权 保护 纠纷 案例", "label": "海外知产保护", "priority": 3},
                {"query": "WIPO EPO USPTO 最新 动态", "label": "国际知产动态", "priority": 2},
                # === 社会热点法律问题 ===
                {"query": "消费者 权益 保护 典型案例", "label": "消费维权", "priority": 2},
                {"query": "劳动纠纷 典型案例 判决", "label": "劳动纠纷", "priority": 2},
                {"query": "个人信息保护 数据 法律 案例", "label": "数据合规", "priority": 2},
                {"query": "平台经济 反垄断 监管 案例", "label": "平台监管", "priority": 2},
            ]

        all_items = []
        seen_titles = set()

        # 按优先级分组搜索，每类最多取3条
        priority_groups = {3: [], 2: [], 1: []}
        for cat_info in categories:
            query = cat_info["query"]
            label = cat_info["label"]
            priority = cat_info.get("priority", 2)

            try:
                result = self._run_search(query, days)
                if not result:
                    continue

                # 收集结果
                cat_items = []
                for platform in HOT_PLATFORMS:
                    items = result.get(platform, [])
                    for item in items:
                        text = item.get("text", "")
                        url = item.get("url", "")

                        # 跳过太短或重复的内容
                        if len(text.strip()) < 20:
                            continue

                        title = self._extract_title(text)
                        if title in seen_titles:
                            continue
                        seen_titles.add(title)

                        # 跳过政治和低俗内容
                        if self._should_skip(text):
                            continue

                        cat_items.append({
                            "title": title,
                            "source": self._platform_name(platform),
                            "url": url,
                            "category": label,
                            "score": item.get("score", 0) + priority * 10,  # 优先级加权
                        })

                # 每类最多取3条，按分数排序
                cat_items.sort(key=lambda x: x["score"], reverse=True)
                for item in cat_items[:3]:
                    priority_groups[priority].append(item)

            except Exception as e:
                logger.warning(f"搜索 {label} 失败: {e}")
                continue

        # 合并：高优先级6条 + 中优先级8条 + 低优先级6条，共20条
        import random
        result_items = []
        for priority in [3, 2, 1]:
            items = priority_groups[priority]
            random.shuffle(items)  # 打乱同优先级顺序避免单调
            limit = 8 if priority == 2 else 6
            for item in items[:limit]:
                result_items.append(item)

        return result_items[:20]

    def _should_skip(self, text):
        """检查是否应该跳过（政治敏感或低俗内容）"""
        political_keywords = ["总书记", "国家主席", "总理", "常委", "政治局", "中央", "国务院",
                              "党委", "党支部", "党员", "反动", "颠覆", "分裂", "抗议", "示威", "游行"]
        vulgar_keywords = ["色情", "裸体", "性侵", "强奸", "卖淫", "嫖娼", "赌博", "毒品"]

        for kw in political_keywords + vulgar_keywords:
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
