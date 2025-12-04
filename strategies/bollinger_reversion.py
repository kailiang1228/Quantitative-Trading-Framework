# strategies/bollinger_reversion.py
# 策略：趨勢回調策略 (Trend Pullback Strategy) - 優化版
# (原 Bollinger Reversion 改良)
#
# 邏輯：
# 1. 不做逆勢回歸，只做「順大勢的深回調」。
# 2. 結合多重時間級別 (4H) 確保順勢。
# 3. 指標：
#    - Bollinger Bands (20, 2.0): 判斷價格極端位置。
#    - 4H EMA (50): 判斷大趨勢。
#    - RSI (14): 確認超賣/超買。
#
# 進場：
#    - 做多：4H 趨勢向上 + 15m 價格觸及布林下軌 + RSI < 30 (超賣)。
#    - 做空：4H 趨勢向下 + 15m 價格觸及布林上軌 + RSI > 70 (超買)。
#
# 優勢：
#    - 相比純逆勢，順大勢回調勝率更高。
#    - 相比純趨勢突破，進場成本更低 (買在回調低點)。

from typing import Optional, Dict, Any
from indicators.advanced_indicators import bollinger_bands, rsi, atr, ema
from utils.logger_util import log
from config import TIMEFRAMES, ATR_PERIOD

class BollingerReversionStrategy:
    def __init__(self, rr: float = 1.5):
        self.name = "BollingerReversion" # 保持名稱以便相容
        self.rr = rr
        self.bb_period = 20
        self.bb_std = 2.0        # 回歸標準 2.0 (提高頻率)
        self.trend_ema_period = 50 # 4H EMA
        self.rsi_period = 14
        self.min_bandwidth = 0.02 # [新增] 最小通道寬度 2% (避免死魚盤)

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

            upper, middle, lower = bollinger_bands(closes, self.bb_period, self.bb_std)
            rsi_vals = rsi(closes, self.rsi_period)
            atr_vals = atr(highs, lows, closes, ATR_PERIOD)

            # 取倒數第二根 (已完成 K 線)
            idx = -2
            c = closes[idx]
            u = upper[idx]
            l = lower[idx]
            r = rsi_vals[idx]
            current_atr = atr_vals[idx]

            if None in (u, l, r, current_atr):
                return None
            
            # [新增] 通道寬度檢查
            # Bandwidth = (Upper - Lower) / Middle
            bandwidth = (u - l) / middle[idx]
            if bandwidth < self.min_bandwidth:
                return None # 波動太小，利潤不夠付手續費，跳過

            # --- 4H 數據處理 (趨勢濾網) ---
            closes_trend = [c[4] for c in ohlcv_trend]
            ema_trend_vals = ema(closes_trend, self.trend_ema_period)
            trend_ema_val = ema_trend_vals[-1]
            trend_close = closes_trend[-1]

            if trend_ema_val is None:
                return None

            # 2. 交易邏輯

            # [做多] 4H 趨勢向上 + 15m 觸及下軌 + RSI 超賣
            if (trend_close > trend_ema_val and 
                c <= l and 
                r < 30):
                
                entry = closes[-1]
                # 止損：再往下 2 倍 ATR (標準設置)
                sl = entry - (2.0 * current_atr)
                risk = entry - sl
                tp = entry + (self.rr * risk)

                return {
                    "side": "buy",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "atr": current_atr,
                    "strategy": self.name,
                    "reason": f"Trend Pullback Buy (4H Up + BB Lower + RSI<30)"
                }

            # [做空] 4H 趨勢向下 + 15m 觸及上軌 + RSI 超買
            if (trend_close < trend_ema_val and 
                c >= u and 
                r > 70):
                
                entry = closes[-1]
                # 止損：再往上 2 倍 ATR
                sl = entry + (2.0 * current_atr)
                risk = sl - entry
                tp = entry - (self.rr * risk)

                return {
                    "side": "sell",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "atr": current_atr,
                    "strategy": self.name,
                    "reason": f"Trend Pullback Sell (4H Down + BB Upper + RSI>70)"
                }

            return None

        except Exception as e:
            log(f"❌ {self.name} 分析錯誤 {symbol}: {e}")
            return None
