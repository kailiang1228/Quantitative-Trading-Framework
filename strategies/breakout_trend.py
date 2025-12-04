# strategies/breakout_trend.py
# 策略：波動率突破策略 (Volatility Breakout Strategy) - 優化版
#
# 邏輯：
# 1. 捕捉市場波動率放大的瞬間 (Keltner Channel 突破)。
# 2. 結合多重時間級別 (4H) 確保順勢交易。
# 3. 指標：
#    - Keltner Channels (20, 2.0): 判斷波動率突破。
#    - 4H EMA (50): 判斷大趨勢。
#    - RSI (14): 確認動能方向。
#    - Volume: 確認突破量能。
#
# 進場：
#    - 做多：15m 收盤價突破 Keltner 上軌 + 4H 趨勢向上 + RSI > 50 + 量能放大。
#    - 做空：15m 收盤價跌破 Keltner 下軌 + 4H 趨勢向下 + RSI < 50 + 量能放大。

from typing import Optional, Dict, Any
from indicators.advanced_indicators import ema, atr, rsi
from utils.logger_util import log
from config import TIMEFRAMES, ATR_PERIOD

class BreakoutTrendStrategy:
    def __init__(self, rr: float = 2.0):
        self.name = "BreakoutTrend"
        self.rr = rr
        self.kc_period = 20
        self.kc_mult = 2.0
        self.trend_ema_period = 50 # 4H EMA
        self.rsi_period = 14

    def analyze(self, api, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            # 1. 獲取數據
            tf_entry = TIMEFRAMES["entry"] # 15m
            tf_trend = TIMEFRAMES["trend"] # 4h
            
            ohlcv_entry = api.fetch_ohlcv(symbol, tf_entry, limit=100)
            ohlcv_trend = api.fetch_ohlcv(symbol, tf_trend, limit=100)

            if not ohlcv_entry or len(ohlcv_entry) < 50 or not ohlcv_trend or len(ohlcv_trend) < self.trend_ema_period + 5:
                return None

            # --- 15m 數據處理 ---
            closes = [c[4] for c in ohlcv_entry]
            highs = [c[2] for c in ohlcv_entry]
            lows = [c[3] for c in ohlcv_entry]
            volumes = [c[5] for c in ohlcv_entry]

            # 計算 Keltner Channels
            ema_basis = ema(closes, self.kc_period)
            atr_vals = atr(highs, lows, closes, self.kc_period)
            rsi_vals = rsi(closes, self.rsi_period)

            # 取倒數第二根 (已完成 K 線)
            idx = -2
            c = closes[idx]
            basis = ema_basis[idx]
            current_atr = atr_vals[idx]
            r = rsi_vals[idx]
            v = volumes[idx]
            
            if None in (basis, current_atr, r):
                return None

            upper_band = basis + (self.kc_mult * current_atr)
            lower_band = basis - (self.kc_mult * current_atr)

            # 量能過濾：大於 20 均量的 1.2 倍
            if len(volumes) >= 22:
                vol_ma = sum(volumes[idx-20:idx]) / 20
                is_high_volume = v > (vol_ma * 1.2)
            else:
                is_high_volume = False

            # --- 4H 數據處理 (趨勢濾網) ---
            closes_trend = [c[4] for c in ohlcv_trend]
            ema_trend_vals = ema(closes_trend, self.trend_ema_period)
            trend_ema_val = ema_trend_vals[-1]
            trend_close = closes_trend[-1]

            if trend_ema_val is None:
                return None

            # 2. 交易邏輯

            # [做多] 突破上軌 + 順大勢 + RSI 強勢 + 有量
            if (c > upper_band and 
                trend_close > trend_ema_val and 
                r > 50 and 
                is_high_volume):
                
                entry = closes[-1] # 下一根開盤進場
                sl = basis # 止損設在 Keltner 中軌 (EMA 20)
                
                # 保護性止損：至少 1 ATR
                if (entry - sl) < current_atr:
                    sl = entry - current_atr

                risk = entry - sl
                tp = entry + (self.rr * risk)

                return {
                    "side": "buy",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "atr": current_atr,
                    "strategy": self.name,
                    "reason": f"KC Breakout Up + 4H Trend + Vol"
                }

            # [做空] 跌破下軌 + 順大勢 + RSI 弱勢 + 有量
            if (c < lower_band and 
                trend_close < trend_ema_val and 
                r < 50 and 
                is_high_volume):
                
                entry = closes[-1]
                sl = basis # 止損設在 Keltner 中軌
                
                if (sl - entry) < current_atr:
                    sl = entry + current_atr

                risk = sl - entry
                tp = entry - (self.rr * risk)

                return {
                    "side": "sell",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "atr": current_atr,
                    "strategy": self.name,
                    "reason": f"KC Breakout Down + 4H Trend + Vol"
                }

            return None

        except Exception as e:
            log(f"❌ {self.name} 分析錯誤 {symbol}: {e}")
            return None
