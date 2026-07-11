import ollama
import platform
import subprocess
from config.config import Config
from app.utils.model_utils import get_ollama_model

async def check_ollama_status() -> bool:
    """Kiểm tra dịch vụ Ollama đã bật chưa."""
    try:
        await ollama.AsyncClient(timeout=5).list()
        return True
    except Exception as e:
        print(f"❌ [SYSTEM] Ollama check FAILED: Dịch vụ chưa bật hoặc lỗi kết nối! Chi tiết: {e}")
        return False


def kill_ollama_runner() -> None:
    """Kill only model runners; Ollama daemon stays available for reload."""
    is_windows = platform.system() == "Windows"
    names = ["ollama_llama_server.exe", "llama-server.exe"] if is_windows else ["ollama_llama_server", "llama-server"]
    for name in names:
        command = ["taskkill", "/F", "/IM", name, "/T"] if is_windows else ["pkill", "-9", "-x", name]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


async def reset_ollama_model() -> None:
    """Unload cleanly, then kill runner only when its API is stuck."""
    try:
        await ollama.AsyncClient(timeout=5).generate(
            model=get_ollama_model(), prompt="", keep_alive=0
        )
    except Exception as error:
        print(f"⚠️ [OLLAMA] Graceful unload failed: {error}. Killing stuck runner.")
        kill_ollama_runner()

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
