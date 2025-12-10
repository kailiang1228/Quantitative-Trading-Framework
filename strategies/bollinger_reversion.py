# strategies/bollinger_reversion.py
# 策略：布林通道逆勢策略 (Bollinger Mean Reversion) - 基礎版
#
# 邏輯：
# 1. 專門針對「震盪盤 (Ranging Market)」設計。
# 2. 假設價格會回歸均值 (Mean Reversion)。
# 3. 指標：
#    - Bollinger Bands (20, 2.0)。
#
# 進場：
#    - 做多：收盤價 < 布林下軌。
#    - 做空：收盤價 > 布林上軌。

from typing import Optional, Dict, Any
from indicators.advanced_indicators import bollinger_bands, atr
from utils.logger_util import log
from config import TIMEFRAMES, ATR_PERIOD

class BollingerReversionStrategy:
    def __init__(self, rr: float = 1.5):
        self.name = "BollingerReversion"
        self.rr = rr
        self.bb_period = 20
        self.bb_std = 2.0

    def analyze(self, api, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            # 1. 獲取數據
            tf_entry = TIMEFRAMES["entry"]
            ohlcv_entry = api.fetch_ohlcv(symbol, tf_entry, limit=100)

            if not ohlcv_entry or len(ohlcv_entry) < 50:
                return None

            # --- 數據處理 ---
            closes = [c[4] for c in ohlcv_entry]
            highs = [c[2] for c in ohlcv_entry]
            lows = [c[3] for c in ohlcv_entry]

            upper, middle, lower = bollinger_bands(closes, self.bb_period, self.bb_std)
            atr_vals = atr(highs, lows, closes, ATR_PERIOD)

            idx = -2 # 看上一根收盤確定的 K 線
            
            if idx < 0 or abs(idx) >= len(upper):
                return None

            close_price = closes[idx]
            current_atr = atr_vals[idx]
            
            signal = None

            # 觸碰下軌 -> 做多
            if close_price < lower[idx]:
                sl_price = close_price - (2 * current_atr) # 寬止損
                risk = close_price - sl_price
                tp_price = middle[idx] # 回歸中軌止盈
                
                # 確保 RR 合理
                if (tp_price - close_price) / risk >= 1.0:
                    signal = {
                        'symbol': symbol,
                        'side': 'buy',
                        'entry': close_price,
                        'sl': sl_price,
                        'tp': tp_price,
                        'atr': current_atr,
                        'strategy': self.name
                    }

            # 觸碰上軌 -> 做空
            elif close_price > upper[idx]:
                sl_price = close_price + (2 * current_atr)
                risk = sl_price - close_price
                tp_price = middle[idx]
                
                if (close_price - tp_price) / risk >= 1.0:
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
