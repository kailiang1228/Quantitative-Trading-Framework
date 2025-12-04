# ============================================================
# main.py — QuantBot 啟動入口 (精簡版)
# ============================================================

import os
from utils.logger_util import log, log_error
from utils.file_logger import LOG_PATH
from utils.trade_recorder import TRADES_PATH
from core.quant_bot import QuantBot

def main():
    log("🚀 QuantBot 系統初始化...")
    log(f"📂 Log 檔案路徑: {LOG_PATH}")
    log(f"📂 CSV 記錄路徑: {TRADES_PATH}")
    
    try:
        # 實例化機器人
        bot = QuantBot()
        
        # 啟動主迴圈 (所有邏輯都在 QuantBot.run 裡面)
        bot.run()
        
    except Exception as e:
        log_error(f"❌ 系統啟動失敗: {e}")

if __name__ == "__main__":
    main()
