"""法律知识库客户端 - 调用 legal-ai API 获取法条引用"""

import requests
import logging

logger = logging.getLogger(__name__)


class KnowledgeClient:
    def __init__(self):
        from config import Config
        self.base_url = Config.LEGAL_AI_URL

    def search(self, query, top_k=5, category=None, law_type=None):
        """调用知识库检索API"""
        try:
            payload = {"query": query, "top_k": top_k}
            if category:
                payload["category"] = category
            if law_type:
                payload["law_type"] = law_type

            resp = requests.post(
                f"{self.base_url}/api/search",
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
            else:
                logger.warning(f"知识库检索失败: {resp.status_code}")
                return []
        except Exception as e:
            logger.error(f"知识库检索异常: {e}")
            return []

    def get_citations(self, topic, top_k=3):
        """获取与主题相关的法律引用，用于文章中"""
        results = self.search(topic, top_k=top_k)
        citations = []
        for r in results:
            citations.append({
                "source": r.get("source", ""),
                "category": r.get("category", ""),
                "law_type": r.get("law_type", ""),
                "content": r.get("content", "")[:300],
            })
        return citations

    def format_citations_for_prompt(self, citations):
        """将法条引用格式化为提示词上下文"""
        if not citations:
            return ""
        parts = []
        for c in citations:
            parts.append(
                f"【{c['source']}】({c['category']}, {c['law_type']})\n{c['content']}"
            )
        return "\n\n---\n\n".join(parts)

    def get_categories(self):
        """获取知识库所有分类"""
        try:
            resp = requests.get(f"{self.base_url}/api/categories", timeout=5)
            if resp.status_code == 200:
                return resp.json().get("categories", [])
        except Exception:
            pass
        return []
