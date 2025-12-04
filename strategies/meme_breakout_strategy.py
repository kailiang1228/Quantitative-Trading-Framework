# strategies/meme_breakout_strategy.py
# 策略：Meme 幣瘋狗流突破策略 (Meme Coin Breakout Strategy)
#
# 專為高波動、高成交量的 Meme 幣設計。
# 核心邏輯：
# 1. 捕捉極端波動率突破 (Keltner Channel 2.5倍)。
# 2. 極度依賴成交量 (Volume > 2.0倍均量)，確認是莊家拉盤。
# 3. 寬止盈、緊止損、快速移動止損。
#
# 適用幣種：DOGE, PEPE, WIF, BONK 等高波動幣。
# 建議槓桿：10x - 20x (請在 config 或 exchange_api 設定)
# 建議倉位：小倉位 (1% - 3% 總資金)

from typing import Optional, Dict, Any
from indicators.advanced_indicators import ema, atr, rsi
from utils.logger_util import log
from config import TIMEFRAMES

class MemeBreakoutStrategy:
    def __init__(self, rr: float = 3.0):
        self.name = "MemeBreakout"
        self.rr = rr  # 建議 3.0 以上，吃大波段
        
        # Keltner Channel 參數 (更寬，過濾雜訊)
        self.kc_period = 20
        self.kc_mult = 2.5 
        
        # 趨勢濾網 (降級為 1H，反應更快)
        self.trend_ema_period = 50 # 1H EMA
        
        # 成交量濾網 (嚴格)
        self.vol_mult = 2.0 # 必須大於 2 倍均量

    def analyze(self, api, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            # 1. 獲取數據
            tf_entry = "15m"  # 強制使用 15m
            tf_trend = "1h"   # 強制使用 1h
            
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
            
            # 取倒數第二根 (已完成 K 線)
            idx = -2
            c = closes[idx]
            basis = ema_basis[idx]
            current_atr = atr_vals[idx]
            v = volumes[idx]
            
            if None in (basis, current_atr):
                return None

            upper_band = basis + (self.kc_mult * current_atr)
            lower_band = basis - (self.kc_mult * current_atr)

            # 量能過濾：大於 20 均量的 2.0 倍 (瘋狗特徵)
            # [新增] 實體 K 線過濾：避免十字星/小 K 線的假突破 (Wash Trading)
            candle_body = abs(c - ohlcv_entry[idx][1]) # Close - Open
            is_valid_candle = candle_body > (0.5 * current_atr)

            if len(volumes) >= 22:
                vol_ma = sum(volumes[idx-20:idx]) / 20
                is_high_volume = (v > (vol_ma * self.vol_mult)) and is_valid_candle
            else:
                is_high_volume = False

            # --- 1H 數據處理 (趨勢濾網) ---
            closes_trend = [c[4] for c in ohlcv_trend]
            ema_trend_vals = ema(closes_trend, self.trend_ema_period)
            trend_ema_val = ema_trend_vals[-1]
            trend_close = closes_trend[-1]

            if trend_ema_val is None:
                return None

            # 2. 交易邏輯

            # [做多] 突破上軌 + 順 1H 大勢 + 爆量
            if (c > upper_band and 
                trend_close > trend_ema_val and 
                is_high_volume):
                
                entry = closes[-1] # 下一根開盤進場
                
                # 止損：設在 Keltner 中軌 (EMA 20) 或 1.5 ATR
                # Meme 幣波動大，用 ATR 保護比較好
                sl_dist = 1.5 * current_atr
                sl = entry - sl_dist
                
                # 止盈：讓獲利奔跑，至少 3R
                tp = entry + (self.rr * sl_dist)

                return {
                    "side": "buy",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "atr": current_atr,
                    "strategy": self.name,
                    "reason": f"Meme Breakout Up (Vol x{v/vol_ma:.1f})",
                    "trailing_stop_atr": 1.0 # 超緊移動止損
                }

            # [做空] 跌破下軌 + 順 1H 大勢 + 爆量
            if (c < lower_band and 
                trend_close < trend_ema_val and 
                is_high_volume):
                
                entry = closes[-1]
                
                sl_dist = 1.5 * current_atr
                sl = entry + sl_dist
                
                tp = entry - (self.rr * sl_dist)

                return {
                    "side": "sell",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "atr": current_atr,
                    "strategy": self.name,
                    "reason": f"Meme Breakout Down (Vol x{v/vol_ma:.1f})",
                    "trailing_stop_atr": 1.0 # 超緊移動止損
                }

            return None

        except Exception as e:
            log(f"❌ {self.name} 分析錯誤 {symbol}: {e}")
            return None
