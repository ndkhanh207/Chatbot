import anyio
import ollama
from config.config import Config

async def check_ollama_status() -> bool:
    """Kiểm tra dịch vụ Ollama đã bật chưa."""
    try:
        # Chạy ollama.list() trong thread riêng để tránh block event loop
        await anyio.to_thread.run_sync(ollama.list)
        return True
    except Exception as e:
        print(f"❌ [SYSTEM] Ollama check FAILED: Dịch vụ chưa bật hoặc lỗi kết nối! Chi tiết: {e}")
        return False

async def check_mysql_status() -> bool:
    """Kiểm tra kết nối tới cơ sở dữ liệu MySQL."""
    try:
        import pymysql
        connection = pymysql.connect(
            host=Config.MYSQL_HOST,
            port=int(Config.MYSQL_PORT),
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            connect_timeout=5
        )
        connection.close()
        return True
    except Exception as e:
        print(f"❌ [SYSTEM] MySQL check FAILED: Không thể kết nối DB! Chi tiết: {e}")
        return False
