# strategies/supertrend_strategy.py
# 策略：超級趨勢策略 (Supertrend Strategy) - 基礎版
#
# 邏輯：
# 1. 經典趨勢跟隨策略。
# 2. 指標：Supertrend (10, 3.0)。
# 3. 進場：
#    - 做多：收盤價突破 Supertrend 上軌 (轉綠)。
#    - 做空：收盤價跌破 Supertrend 下軌 (轉紅)。
# 4. 止損：使用 Supertrend 線作為移動止損點。

from typing import Optional, Dict, Any
from indicators.advanced_indicators import supertrend, atr
from utils.logger_util import log
from config import TIMEFRAMES, ATR_PERIOD

class SupertrendStrategy:
    def __init__(self, rr: float = 2.0):
        self.name = "SupertrendStrategy"
        self.rr = rr
        self.st_period = 10      # 標準 10
        self.st_multiplier = 3.0 # 標準 3.0

    def analyze(self, api, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            # 1. 獲取 Entry Timeframe 數據
            tf_entry = TIMEFRAMES["entry"]
            ohlcv_entry = api.fetch_ohlcv(symbol, tf_entry, limit=100)
            
            if not ohlcv_entry or len(ohlcv_entry) < 50:
                return None

            # --- 處理數據 ---
            highs = [c[2] for c in ohlcv_entry]
            lows = [c[3] for c in ohlcv_entry]
            closes = [c[4] for c in ohlcv_entry]

            # 2. 計算指標
            st_trend, st_dir, st_long, st_short = supertrend(highs, lows, closes, self.st_period, self.st_multiplier)
            atr_vals = atr(highs, lows, closes, ATR_PERIOD)

            # 3. 交易邏輯
            idx = -2 # 看上一根收盤確定的 K 線
            
            # 確保數據足夠
            if idx < 0 or abs(idx) >= len(st_dir):
                return None

            current_dir = st_dir[idx]
            prev_dir = st_dir[idx-1]
            close_price = closes[idx]
            current_atr = atr_vals[idx]

            signal = None
            
            # 判斷趨勢反轉
            # 由紅轉綠 -> 做多
            if prev_dir == -1 and current_dir == 1:
                sl_price = st_trend[idx]
                risk = close_price - sl_price
                if risk > 0:
                    tp_price = close_price + (risk * self.rr)
                    signal = {
                        'symbol': symbol,
                        'side': 'buy',
                        'entry': close_price,
                        'sl': sl_price,
                        'tp': tp_price,
                        'atr': current_atr,
                        'strategy': self.name
                    }

            # 由綠轉紅 -> 做空
            elif prev_dir == 1 and current_dir == -1:
                sl_price = st_trend[idx]
                risk = sl_price - close_price
                if risk > 0:
                    tp_price = close_price - (risk * self.rr)
                    signal = {
                        'symbol': symbol,
                        'side': 'sell',
                        'entry': close_price,
                        'sl': sl_price,
                        'tp': tp_price,
                        'atr': current_atr,
                        'strategy': self.name
                    }

            return signal

        except Exception as e:
            log(f"策略分析錯誤 ({self.name}): {e}", level="error")
            return None
