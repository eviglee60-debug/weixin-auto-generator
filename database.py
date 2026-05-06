import logging
import pymysql

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        from config import Config
        self.host = Config.MYSQL_HOST
        self.port = Config.MYSQL_PORT
        self.user = Config.MYSQL_USER
        self.password = Config.MYSQL_PASSWORD
        self.db = Config.MYSQL_DB

        self.init_db()

    def get_connection(self):
        return pymysql.connect(
            host=self.host, port=self.port, user=self.user,
            password=self.password, database=self.db,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )

    def init_db(self):
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS articles (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        title VARCHAR(100),
                        content TEXT,
                        media_id VARCHAR(100),
                        status VARCHAR(20),
                        category VARCHAR(20),
                        keywords TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 尝试给已有表加字段（兼容旧表）
                for col, dtype in [
                    ("category", "VARCHAR(20)"),
                    ("keywords", "TEXT"),
                ]:
                    try:
                        cursor.execute(f"ALTER TABLE articles ADD COLUMN {col} {dtype}")
                    except Exception:
                        pass  # 字段已存在

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pending_news (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        title VARCHAR(200),
                        source VARCHAR(100),
                        category VARCHAR(20),
                        region VARCHAR(20),
                        url TEXT,
                        keywords TEXT,
                        used BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 尝试给已有表加url字段
                try:
                    cursor.execute("ALTER TABLE pending_news ADD COLUMN url TEXT")
                except Exception:
                    pass  # 字段已存在
            conn.commit()
            conn.close()
            logger.info("数据库初始化成功")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")

    def save_article(self, title, content, media_id, status="draft",
                     category=None, keywords=None):
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO articles (title, content, media_id, status, category, keywords) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (title, content, media_id, status, category, keywords)
                )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"保存文章失败: {e}")
            return False

    def get_recent_articles(self, days=30):
        """查询最近N天已发布文章"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, title, category, keywords, created_at "
                    "FROM articles WHERE created_at > DATE_SUB(NOW(), INTERVAL %s DAY) "
                    "ORDER BY created_at DESC",
                    (days,)
                )
                results = cursor.fetchall()
            conn.close()
            return results
        except Exception as e:
            logger.error(f"查询最近文章失败: {e}")
            return []

    def get_recent_keywords(self, days=30):
        """提取最近文章的关键词集合，用于去重"""
        articles = self.get_recent_articles(days)
        keywords = set()
        for article in articles:
            if article.get("title"):
                keywords.add(article["title"])
            if article.get("keywords"):
                for kw in article["keywords"].split(","):
                    kw = kw.strip()
                    if kw:
                        keywords.add(kw)
        return keywords

    def save_pending_news(self, news_list):
        """存储未使用的新闻到待用队列"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                for news in news_list:
                    cursor.execute(
                        "INSERT INTO pending_news (title, source, category, region, url, keywords) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (
                            news.get("title", ""),
                            news.get("source", ""),
                            news.get("category", ""),
                            news.get("region", ""),
                            news.get("url", ""),
                            ",".join(news.get("keywords", [])),
                        )
                    )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"保存待用新闻失败: {e}")
            return False

    def get_pending_news(self, category, limit=3):
        """从待用队列取未使用的新闻"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, title, source, category, region, url, keywords "
                    "FROM pending_news WHERE used = FALSE AND category = %s "
                    "ORDER BY created_at DESC LIMIT %s",
                    (category, limit)
                )
                results = cursor.fetchall()
            conn.close()
            return results
        except Exception as e:
            logger.error(f"获取待用新闻失败: {e}")
            return []

    def mark_used_pending(self, news_id):
        """标记待用新闻已使用"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE pending_news SET used = TRUE WHERE id = %s",
                    (news_id,)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"标记待用新闻失败: {e}")

    def cleanup_old_pending(self, days=60):
        """清理过期待用新闻"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM pending_news WHERE created_at < DATE_SUB(NOW(), INTERVAL %s DAY)",
                    (days,)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"清理待用新闻失败: {e}")
