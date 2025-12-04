import pandas as pd
import numpy as np
from enum import Enum
from indicators.advanced_indicators import adx, atr, bollinger_bands

class MarketRegime(Enum):
    TRENDING = "TRENDING"       # 趨勢明顯 (ADX > 25)
    RANGING = "RANGING"         # 盤整震盪 (ADX < 20, Bandwidth Low)
    VOLATILE = "VOLATILE"       # 劇烈波動 (ATR Spike)
    UNCERTAIN = "UNCERTAIN"     # 不確定

class RegimeDetector:
    def __init__(self):
        pass

    def detect_regime(self, ohlcv: list) -> MarketRegime:
        """
        根據 OHLCV (list of [ts, o, h, l, c, v]) 判斷市場狀態
        """
        if not ohlcv or len(ohlcv) < 50:
            return MarketRegime.UNCERTAIN

        # 轉換數據
        highs = [x[2] for x in ohlcv]
        lows = [x[3] for x in ohlcv]
        closes = [x[4] for x in ohlcv]

        # 計算指標
        # 1. ADX (14)
        adx_vals = adx(highs, lows, closes, 14)
        if not adx_vals or adx_vals[-1] is None:
            return MarketRegime.UNCERTAIN
        current_adx = adx_vals[-1]

        # 2. Bollinger Bands (20, 2)
        upper, middle, lower = bollinger_bands(closes, 20, 2.0)
        if not upper or upper[-1] is None:
            return MarketRegime.UNCERTAIN
        
        u, l, c = upper[-1], lower[-1], closes[-1]
        
        # 3. Bandwidth %
        bandwidth = (u - l) / c if c > 0 else 0

        # 4. 判斷邏輯
        
        # --- 判斷趨勢 (Trending) ---
        if current_adx > 25:
            return MarketRegime.TRENDING
            
        # --- 判斷盤整 (Ranging) ---
        # ADX < 20 且 Bandwidth 相對較小 (這裡暫定 < 0.1，即 10% 波動範圍內)
        if current_adx < 20:
            return MarketRegime.RANGING
            
        return MarketRegime.UNCERTAIN
