# config_template.py
# 這是設定檔範本。請將此檔案複製為 config.py 並填入您的真實資訊。
# This is a template. Copy this file to config.py and fill in your real credentials.

import os

# ========== 1. 帳戶與風險設定 ==========

# 預設總資金（只當作風控初始值，實際會用交易所查回來覆蓋）
TOTAL_EQUITY = 300.0          # 目前小帳 300U

# 單筆風險（每筆交易最多虧損帳戶淨值的 %）
RISK_PER_TRADE = 0.02         # 2% 風險 (建議新手先用 1-2%)

# [新增] 風險權重 (Risk Tiers)
# 針對不同波動率的幣種，給予不同的倉位權重
# 1.0 = 標準倉位, 0.8 = 打 8 折, 0.5 = 打 5 折
RISK_TIERS = {
    "BTC/USDT:USDT": 1.0,
    "ETH/USDT:USDT": 1.0,
    "SOL/USDT:USDT": 0.85,
    "DEFAULT": 0.6,  # 其他小幣一律打 6 折
}

# 單筆最大保證金佔比（每筆交易的保證金不超過帳戶淨值的 %）
MAX_MARGIN_RATIO = 0.30       # 30% 保證金上限

# [新增] 總帳戶最大保證金佔比 (Total Margin Cap)
# 防止同時開太多單導致總保證金過高 (例如 80-90% 危險區)
# 建議：激進 0.7, 穩健 0.5, 保守 0.3
MAX_TOTAL_MARGIN_RATIO = 0.6  # 總保證金不超過 60%

# 小帳專用：每單最大承受虧損（美金）- 設為 None 表示停用，全靠比例
FIXED_RISK_USDT = None

# 各幣種最小名義價值（OKX 最小下單額度，避免太小單被拒）
MIN_NOTIONAL = {
    "BTC/USDT:USDT": 15.0,
    "ETH/USDT:USDT": 15.0,
    "SOL/USDT:USDT": 8.0,
    "DEFAULT": 6.0,
}

# 槓桿配置（實際會在程式內 set_leverage）
LEVERAGE = {
    "BTC/USDT:USDT": 3,
    "ETH/USDT:USDT": 5,
    "SOL/USDT:USDT": 8,
    "DEFAULT": 5,
}

# 允許同時開幾個倉位
MAX_CONCURRENT_TRADES = 5  # 擴大到 5 檔 (配合多幣種)

# 最大允許回撤（只做提醒，不會自動停機）
MAX_DRAWDOWN = 0.15  # 15%

# 連續虧損後的冷卻時間（秒）
COOLING_PERIOD = 300  # 5 分鐘


# ========== 2. 交易標的與時間框架 ==========

# 是否自動選幣 (True = 每次啟動自動抓前 20 大, False = 使用下方 SYMBOLS)
AUTO_SYMBOL_SELECTION = True

# 統一使用 SYMBOLS (若 AUTO_SYMBOL_SELECTION=True，此列表將被覆蓋)
SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
]

# 多時間框架設定
TIMEFRAMES = {
    "trend": "4h",    # 判斷大趨勢
    "entry": "15m",   # 找入場點
    "exit": "5m",     # 之後如果要精細出場可以用
}

# 趨勢用指標參數（主策略用）
EMA_SLOW = 200
EMA_FAST = 50
EMA_TREND = 21

ATR_PERIOD = 14
RISK_MULTIPLIER = 1.8      # SL 距離用 ATR * RISK_MULTIPLIER
REWARD_RATIO = 1.5         # RR 比例 1 : 1.5 (縮短持倉時間，提高勝率)

# 市場 regime 相關
MIN_ADX = 20               # ADX 高於此值才認為有趨勢
VOLATILITY_THRESHOLD = 0.005  # 0.5% 波動率過濾


# ========== 3. 交易所與 API ==========

# 請在此填入您的 API 資訊，或使用環境變數
OKX_API_KEY = os.getenv("OKX_API_KEY", "YOUR_API_KEY_HERE")
OKX_SECRET = os.getenv("OKX_SECRET", "YOUR_SECRET_HERE")
OKX_PASSWORD = os.getenv("OKX_PASSWORD", "YOUR_PASSWORD_HERE")

# True = OKX sandbox（模擬盤），False = 正式帳戶
USE_TESTNET = True

# True = 完全不送單，只做 log（策略 debug 用）
DRY_RUN = False

# 給 log / TG 用的機器人名稱
NAME = "Quant_M1"


# ========== 4. 日誌與系統設定 ==========

LOG_LEVEL = "INFO"

# 心跳（TG 健康狀態）間隔
HEARTBEAT_INTERVAL = 3600  # 1 小時

# 倉位報告間隔（PositionManager 裡也會用）
POSITION_REPORT_INTERVAL = 900  # 15 分鐘


# ========== 5. Telegram 通知設定 ==========

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "YOUR_CHAT_ID_HERE")

ENABLE_TG_NOTIFICATIONS = True

# 各類訊息要不要推
NOTIFY_ORDER_PLACED = True
NOTIFY_ORDER_FILLED = True
NOTIFY_ORDER_CANCELED = True
NOTIFY_POSITION_CLOSED = True
NOTIFY_ERRORS = True
NOTIFY_HEARTBEAT = True


# -------------------------
# 交易時間設定
# -------------------------
LOOP_INTERVAL = 10         # 主迴圈秒數
