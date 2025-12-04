# utils/file_logger.py
import os
from datetime import datetime

# 使用絕對路徑，確保 log 永遠寫在程式所在的 logs 資料夾下
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

date_str = datetime.now().strftime("%Y-%m-%d")
LOG_PATH = os.path.join(LOG_DIR, f"{date_str}.log")

def write_log_to_file(text: str):
    """
    把 log 另外寫到檔案，避免 terminal 滑不回去
    """
    # text 已經包含 timestamp，直接寫入即可
    line = f"{text}\n"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # 寫 log 失敗就算了，不要影響主程式
        pass
