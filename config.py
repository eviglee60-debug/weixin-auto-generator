import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    WECHAT_APPID = os.environ.get("WECHAT_APPID")
    WECHAT_SECRET = os.environ.get("WECHAT_SECRET")

    MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY")
    MINIMAX_API_URL = os.environ.get("MINIMAX_API_URL", "https://api.minimax.chat/v1/text/chatcompletion_v2")

    MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
    MYSQL_USER = os.environ.get("MYSQL_USER")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD")
    MYSQL_DB = os.environ.get("MYSQL_DB")

    # 法律知识库 API
    LEGAL_AI_URL = os.environ.get("LEGAL_AI_URL", "http://127.0.0.1:8002")

    SCHEDULE_HOUR = 8
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
            "category": "patent",
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
            "url": "https://www.cnipa.gov.cn/col/col1141/index.html",
            "base_url": "https://www.cnipa.gov.cn",
            "category": "patent",
            "region": "china",
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
    ]
