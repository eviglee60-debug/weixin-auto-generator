import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    WECHAT_APPID = os.environ.get("WECHAT_APPID")
    WECHAT_SECRET = os.environ.get("WECHAT_SECRET")

    MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY")
    MINIMAX_API_URL = os.environ.get("MINIMAX_API_URL", "https://api.minimax.chat/v1/text/chatcompletion_v2")
    MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7")

    # MiniMax Anthropic 兼容端点（用于 coding-plan 系列模型）
    MINIMAX_API_BASE_URL = os.environ.get("MINIMAX_API_BASE_URL", "https://api.minimaxi.com/anthropic/v1")
    # coding-plan-search 增强编程/分析能力
    MINIMAX_CODING_PLAN_SEARCH = os.environ.get("MINIMAX_CODING_PLAN_SEARCH", "coding-plan-search")
    # coding-plan-vlm 图片理解（需通过 MCP 工具调用，非直接 API）
    MINIMAX_CODING_PLAN_VLM = os.environ.get("MINIMAX_CODING_PLAN_VLM", "coding-plan-vlm")

    # MiniMax Image Generation API
    MINIMAX_IMAGE_API_URL = os.environ.get("MINIMAX_IMAGE_API_URL", "https://api.minimaxi.com/v1/image_generation")
    MINIMAX_IMAGE_MODEL = os.environ.get("MINIMAX_IMAGE_MODEL", "image-01")

    MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
    MYSQL_USER = os.environ.get("MYSQL_USER")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD")
    MYSQL_DB = os.environ.get("MYSQL_DB")

    # 法律知识库 API
    LEGAL_AI_URL = os.environ.get("LEGAL_AI_URL", "http://127.0.0.1:8002")

    SCHEDULE_HOUR = 5
    SCHEDULE_MINUTE = 0
    DAILY_ARTICLE_COUNT = 3
    LOG_DIR = "/opt/weixin-auto-generator/logs"

    # 去重追溯天数
    DEDUP_DAYS = 30

    # 每日文章分类配额
    ARTICLE_CATEGORIES = ["patent", "general_ip", "hot_topic"]

    # 新闻源配置
    NEWS_SOURCES = {
        # === patent 专利类 ===
        "cnipa_patent": {
            "name": "国家知识产权局",
            "url": "https://www.cnipa.gov.cn/",
            "category": "patent",
            "region": "china",
        },
        "spc_ip": {
            "name": "最高人民法院知识产权法庭",
            "url": "https://ipc.court.gov.cn/zh-cn/news/more-12-12.html",
            "base_url": "https://ipc.court.gov.cn",
            "category": "patent",  # 主要算专利，但内容包含泛知产
            "region": "china",
        },
        "uspto": {
            "name": "美国专利商标局",
            "url": "https://www.uspto.gov/about-us/news-updates",
            "category": "patent",
            "region": "international",
        },
        "epo": {
            "name": "欧洲专利局",
            "url": "https://www.epo.org/news-events/news.html",
            "category": "patent",
            "region": "international",
        },
        "jpo": {
            "name": "日本特许厅",
            "url": "https://www.jpo.go.jp/news/index.html",
            "category": "patent",
            "region": "international",
        },
        "tipo": {
            "name": "台湾智慧财产局",
            "url": "https://www.tipo.gov.tw/zh-tw/news.html",
            "category": "patent",
            "region": "international",
        },
        "fuqingtuang": {
            "name": "赋青春",
            "url": "https://weixin.sogou.com/weixin?type=1&s_from=input&query=赋青春&ie=utf8",
            "base_url": "https://weixin.sogou.com",
            "category": "patent",
            "region": "china",
        },
        "spc_case_research": {
            "name": "最高人民法院司法案例研究院",
            "url": "https://weixin.sogou.com/weixin?type=1&s_from=input&query=最高人民法院司法案例研究院&ie=utf8",
            "base_url": "https://weixin.sogou.com",
            "category": "patent",
            "region": "china",
        },
        "finnegan_cn": {
            "name": "美国飞翰律师事务所",
            "url": "https://weixin.sogou.com/weixin?type=1&s_from=input&query=美国飞翰律师事务所&ie=utf8",
            "base_url": "https://weixin.sogou.com",
            "category": "patent",
            "region": "international",
        },
        # === general_ip 泛知识产权类 ===
        "samr": {
            "name": "市场监管总局",
            "url": "https://www.samr.gov.cn/xw/mtjj/index.html",
            "api_url": "https://www.samr.gov.cn/api-gateway/jpaas-publish-server/front/page/build/unit",
            "api_params": {
                "parseType": "bulidstatic",
                "webId": "29e9522dc89d4e088a953d8cede72f4c",
                "tplSetId": "5c30fb89ae5e48b9aefe3cdf49853830",
                "pageType": "column",
                "tagId": "内容区域",
                "editType": "null",
                "pageId": "fd590d1789974f8b9f1db6d2e7da751a",
            },
            "category": "general_ip",
            "region": "china",
        },
        "cnipa_general": {
            "name": "国家知识产权局",
            "url": "https://www.cnipa.gov.cn/",
            "category": "general_ip",
            "region": "china",
        },
        "tipo_general": {
            "name": "台湾智慧财产局",
            "url": "https://www.tipo.gov.tw/zh-tw/news.html",
            "category": "general_ip",
            "region": "international",
        },
        # 一带一路联盟国家知识产权局
        "saic": {
            "name": "沙特知识产权局",
            "url": "https://www.saip.gov.sa/en/news/",
            "category": "general_ip",
            "region": "international",
        },
        "myipo": {
            "name": "马来西亚知识产权局",
            "url": "https://www.mymipo.gov.my/news",
            "category": "general_ip",
            "region": "international",
        },
        # === hot_topic 热点法律类 ===
        "spc": {
            "name": "最高人民法院",
            "url": "https://www.court.gov.cn/zixun.html",
            "base_url": "https://www.court.gov.cn",
            "category": "hot_topic",
            "region": "china",
        },
        "us_supreme": {
            "name": "美国最高法院",
            "url": "https://www.supremecourt.gov/opinions/slipopinion/25",
            "category": "hot_topic",
            "region": "international",
        },
        "high_court": {
            "name": "高级人民法院",
            "url": "https://www.chinacourt.org/article/index/coluId/5",
            "base_url": "https://www.chinacourt.org",
            "category": "hot_topic",
            "region": "china",
        },
    }

    # 敏感词过滤 - 严格版本
    SENSITIVE_WORDS = [
        # 政治组织
        "党", "总书记", "国家主席", "总理", "常委", "政治局", "中央", "国务院",
        "党委", "党支部", "党校", "入党", "党员", "党组织",
        # 领导人
        "领导人", "领导核心", "最高领导",
        # 社会稳定
        "反动", "颠覆", "分裂", "邪教", "暴恐", "六四", "天安门",
        "法轮功", "达赖", "疆独", "藏独", "台独", "港独",
        # 争议事件
        "文化大革命", "大跃进", "反右", "文革",
        # 敏感政治词汇
        "人权", "民主运动", "学生运动", "抗议", "示威", "游行",
        "上访", "信访", "强拆",
        # 涉密
        "机密", "绝密", "泄密",
        # 其他
        "反华", "辱华", "卖国", "汉奸", "间谍", "叛国",
        # 国家领导人相关活动
        "习近平", "李克强", "李强", "赵乐际", "王沪宁",
        "蔡奇", "丁薛祥", "李希", "韩正", "刘鹤",
        "胡锦涛", "温家宝",
    ]

    # 会议/活动类过滤关键词 — 匹配则跳过
    MEETING_FILTER_KEYWORDS = [
        "主持召开", "学习贯彻", "精神传达", "重要讲话",
        "主题教育", "党建", "党组", "党委中心组",
        "大会开幕", "大会召开", "座谈会召开",
        "调研考察", "视察", "出席活动",
    ]

    # ============================================================
    # 实践画像 (Practice Profile)
    # 参考 claude-for-legal CLAUDE.md 模式，定义此项目的实践偏好。
    # 所有技能（生成/爬取/发布）从此读取，修改此处即全局生效。
    # 编辑此文件，不需要重新部署。
    # ============================================================

    # --- 读者画像 ---
    PRACTICE_READER = {
        "primary": "企业知识产权管理者、法务人员",
        "secondary": "知识产权从业者（代理人/律师/审查员）",
        "level": "专业但不艰深 — 法务能决策，从业者能参考",
    }

    # --- 内容边界 ---
    PRACTICE_CONTENT_SCOPE = {
        "cover": [
            "专利审查动态与趋势",
            "商标/著作权侵权案例评析",
            "知识产权政策法规解读",
            "国际知产动态（USPTO/EPO/WIPO）",
            "社会热点法律分析",
        ],
        "avoid": [
            "纯政治内容（含会议报道/领导人活动）",
            "公司公告类新闻（X公司获得X专利）",
            "未经核实的传闻/猜测",
            "涉及国家安全的敏感技术讨论",
            "对其他律所/代理机构的评价",
        ],
    }

    # --- 输出风格 ---
    PRACTICE_OUTPUT_STYLE = {
        "article_length": "800-1200字",
        "tone": "专业但可读 — 像资深律师在茶余饭后做专业分享",
        "structure": "事件背景 → 法律分析 → 法条解读 → 实务建议",
        "citation_style": "引用法条注明法律名称+条款号（如《专利法》第22条）",
        "digest_summary_length": "≤120字，说清楚发生了什么",
        "digest_max_items": 20,
    }

    # --- 文章护栏 ---
    PRACTICE_GUARDRAILS = {
        # 引用出处层次
        "provenance_tiers": [
            ("官方来源", "CNIPA/USPTO/EPO/最高法 等官网获取"),
            ("知识库引用", "本地 ChromaDB 法律知识库检索结果"),
            ("AI 生成", "MiniMax 模型生成，需人工审查"),
            ("待验证", "来源不明，发布前必须核实"),
        ],
        # Reviewer Note 模板（每篇文章生成后追加）
        "reviewer_note_template": (
            "> **审查者注释**\n"
            "> - **来源:** {sources}\n"
            "> - **法条引用:** {citation_count} 处，{verified_count} 处已核\n"
            "> - **标记审查:** {review_flags} 处 `[review]`\n"
            "> - **发布前:** {before_publish}"
        ),
    }

    # --- 发布决策姿态 ---
    PRACTICE_PUBLISH_POSTURE = {
        "mode": "conservative",  # aggressive / measured / conservative
        "auto_publish": False,   # 不自动发布 — 所有文章存入草稿箱
        "requires_review": True, # 发布前需人工审查
        "escalation_triggers": [
            "涉及未决诉讼的评论",
            "对现行政策的批评性分析",
            "引用未经核实的第三方数据",
            "涉及知名企业的侵权指控",
        ],
    }

    # --- 选题优先级 ---
    PRACTICE_TOPIC_PRIORITY = {
        "patent": 10,       # 最高 — 核心领域
        "general_ip": 8,
        "hot_topic": 6,
        "international": 5,
    }
