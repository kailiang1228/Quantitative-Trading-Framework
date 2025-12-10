# config.py
# 統一所有設定 & 風控參數

import os

# ========== 1. 帳戶與風險設定 ==========

# 預設總資金（只當作風控初始值，實際會用交易所查回來覆蓋）
TOTAL_EQUITY = 1000.0

# 單筆風險（每筆交易最多虧損帳戶淨值的 %）
RISK_PER_TRADE = 0.02         # 2% 風險

# 風險權重 (Risk Tiers)
# 針對不同波動率的幣種，給予不同的倉位權重
RISK_TIERS = {
    "BTC/USDT:USDT": 1.0,
    "ETH/USDT:USDT": 1.0,
    "DEFAULT": 0.8,
}

# 單筆最大保證金佔比
MAX_MARGIN_RATIO = 0.30       # 30% 保證金上限

# 總帳戶最大保證金佔比
MAX_TOTAL_MARGIN_RATIO = 0.6  # 總保證金不超過 60%

# 每單最大承受虧損（美金）- 設為 None 表示停用，全靠比例
FIXED_RISK_USDT = None

# 各幣種最小名義價值（OKX 最小下單額度）
MIN_NOTIONAL = {
    "DEFAULT": 6.0,
}

# 槓桿配置
LEVERAGE = {
    "BTC/USDT:USDT": 5,
    "ETH/USDT:USDT": 5,
    "DEFAULT": 3,
}

# ========== 2. 交易所 API 設定 ==========
# 請從環境變數讀取，不要直接寫在程式碼中
API_KEY = os.getenv("OKX_API_KEY", "")
API_SECRET = os.getenv("OKX_API_SECRET", "")
PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")
IS_SIMULATION = True  # 是否為模擬盤

# ========== 3. 時間級別設定 ==========
TIMEFRAMES = {
    "trend": "4h",   # 趨勢判斷
    "entry": "1h",   # 進場訊號
}

# ========== 4. 指標參數 ==========
ATR_PERIOD = 14
REWARD_RATIO = 2.0  # 預設盈虧比

# ========== 5. 系統設定 ==========
LOG_LEVEL = "INFO"
DB_PATH = "data/positions_db.json"
