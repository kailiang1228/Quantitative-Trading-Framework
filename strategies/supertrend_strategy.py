# strategies/supertrend_strategy.py
# 策略：超級趨勢策略 (Supertrend Strategy) - 多重時間級別優化版
#
# 邏輯：
# 1. 經典趨勢跟隨策略，適合捕捉大波段。
# 2. 指標：Supertrend (10, 3.0) + ADX (20) + EMA (50 on 4H) + RSI (14)。
# 3. 進場：
#    - 做多：15m Supertrend 轉綠 + 4H 收盤價 > 4H EMA 50 + RSI < 75。
#    - 做空：15m Supertrend 轉紅 + 4H 收盤價 < 4H EMA 50 + RSI > 25。
# 4. 濾網：
#    - 4H EMA 50：確保順大勢 (約 8-10 天趨勢)。
#    - ADX > 20：確保 15m 有動能。
# 5. 止損：使用 Supertrend 線作為移動止損點。

from typing import Optional, Dict, Any
from indicators.advanced_indicators import supertrend, adx, atr, ema, rsi, bollinger_bands
from utils.logger_util import log
from config import TIMEFRAMES, ATR_PERIOD

class SupertrendStrategy:
    def __init__(self, rr: float = 2.0):
        self.name = "SupertrendStrategy"
        self.rr = rr
        self.st_period = 10      # 回歸標準 10 (提高頻率)
        self.st_multiplier = 3.0 # 回歸標準 3.0 (提高頻率)
        self.adx_threshold = 25  # 提高門檻 (原 20) -> 過濾盤整
        self.trend_ema_period = 50 # 4H 上的 EMA 50
        self.rsi_period = 14
        self.min_bandwidth = 0.02 # [新增] 最小通道寬度 2% (避免死魚盤)

    def analyze(self, api, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            # 1. 獲取 Entry Timeframe (15m) 數據
            tf_entry = TIMEFRAMES["entry"]
            ohlcv_entry = api.fetch_ohlcv(symbol, tf_entry, limit=200)
            
            # 2. 獲取 Trend Timeframe (4h) 數據
            tf_trend = TIMEFRAMES["trend"]
            ohlcv_trend = api.fetch_ohlcv(symbol, tf_trend, limit=100)

            if not ohlcv_entry or len(ohlcv_entry) < 50 or not ohlcv_trend or len(ohlcv_trend) < self.trend_ema_period + 5:
                return None

            # --- 處理 15m 數據 ---
            highs = [c[2] for c in ohlcv_entry]
            lows = [c[3] for c in ohlcv_entry]
            closes = [c[4] for c in ohlcv_entry]

            st_vals, st_dirs = supertrend(highs, lows, closes, self.st_period, self.st_multiplier)
            adx_vals = adx(highs, lows, closes, 14)
            atr_vals = atr(highs, lows, closes, ATR_PERIOD)
            rsi_vals = rsi(closes, self.rsi_period)
            
            # [新增] 計算 Bollinger Bandwidth
            upper, middle, lower = bollinger_bands(closes, 20, 2.0)

            idx = -2 # 已完成 K 線
            
            close_prev = closes[idx]
            st_dir_prev = st_dirs[idx]
            st_dir_prev_2 = st_dirs[idx-1]
            
            adx_val = adx_vals[idx]
            current_atr = atr_vals[idx]
            st_val = st_vals[idx]
            rsi_val = rsi_vals[idx]
            
            # 計算 Bandwidth
            u = upper[idx]
            l = lower[idx]
            m = middle[idx]
            bandwidth = 0
            if m and m != 0:
                bandwidth = (u - l) / m

            # --- 處理 4H 數據 (趨勢濾網) ---
            closes_trend = [c[4] for c in ohlcv_trend]
            ema_trend_vals = ema(closes_trend, self.trend_ema_period)
            
            # 取最新的 4H EMA (對應當前時間)
            # 注意：因為是回測，api.fetch_ohlcv 會回傳截至 current_time 的數據
            # 所以 ohlcv_trend[-1] 就是當前最新的 4H K線 (可能還沒收盤，但 EMA 用 Close 計算通常取最近一根)
            # 為了保守起見，我們取 [-1] 的 EMA 值與 [-1] 的 Close 比較
            trend_ema_val = ema_trend_vals[-1]
            trend_close = closes_trend[-1]
            
            if None in (st_dir_prev, st_dir_prev_2, adx_val, current_atr, st_val, trend_ema_val, rsi_val):
                return None

            # 3. 交易邏輯
            
            # 濾網 A: ADX 強度
            if adx_val < self.adx_threshold:
                return None
                
            # [新增] 濾網 D: 死魚盤過濾 (Dead Market Filter)
            if bandwidth < self.min_bandwidth:
                return None

            # 訊號: Supertrend 翻轉
            is_bullish_flip = (st_dir_prev is True and st_dir_prev_2 is False)
            is_bearish_flip = (st_dir_prev is False and st_dir_prev_2 is True)

            if not (is_bullish_flip or is_bearish_flip):
                return None
            
            # [新增] 實體 K 線過濾 (Candle Body Filter)
            # 避免十字星或極短 K 線造成的假突破
            open_prev = ohlcv_entry[idx][1]
            body_size = abs(close_prev - open_prev)
            if body_size < (0.3 * current_atr):
                return None # K 線實體太小，視為雜訊，跳過

            # [做多]
            if is_bullish_flip:
                # 濾網 B: 4H 趨勢向上 (價格 > EMA 50)
                # 濾網 C: RSI 不過熱 (< 75)
                if trend_close > trend_ema_val and rsi_val < 75:
                    entry = close_prev
                    sl = st_val 
                    
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
                        "reason": f"ST Flip Up + 4H_Trend_OK + ADX={adx_val:.1f}",
                        "trailing_stop_atr": self.st_multiplier
                    }

            # [做空]
            elif is_bearish_flip:
                # 濾網 B: 4H 趨勢向下 (價格 < EMA 50)
                # 濾網 C: RSI 不過冷 (> 25)
                if trend_close < trend_ema_val and rsi_val > 25:
                    entry = close_prev
                    sl = st_val 
                    
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
                        "reason": f"ST Flip Down + 4H_Trend_OK + ADX={adx_val:.1f}",
                        "trailing_stop_atr": self.st_multiplier
                    }

            return None

        except Exception as e:
            log(f"❌ {self.name} 分析錯誤 {symbol}: {e}")
            return None
