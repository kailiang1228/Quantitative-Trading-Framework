# ============================================================
# indicators/advanced_indicators.py
#
# 功能：
#   - 提供較完整的一組常用技術指標：
#       EMA, ATR, ADX, RSI, Bollinger Bands, Volume Profile
#   - 給策略層（如 MultiTimeframeTrendStrategy）呼叫
#
# 注意：
#   - 所有函式皆回傳「長度跟原始 series 一樣」的 list
#   - 前面因為計算不足的部份用 None 補齊
# ============================================================

from typing import List, Tuple
import numpy as np


# ------------------------------------------------------------
# 指數移動平均線 (EMA)
# ------------------------------------------------------------
def ema(series: List[float], period: int) -> List[float]:
    """
    指數移動平均線 (Exponential Moving Average)

    :param series: 價格序列（例如收盤價 list）
    :param period: 週期
    :return: 與 series 長度相同的 list，前面不足資料的部份為 None
    """
    if len(series) < period:
        return [None] * len(series)

    alpha = 2 / (period + 1)
    ema_vals = []
    # 初始 EMA 用前 period 根的簡單平均
    ema_prev = sum(series[:period]) / period

    for i, price in enumerate(series):
        if i < period - 1:
            ema_vals.append(None)
        elif i == period - 1:
            ema_vals.append(ema_prev)
        else:
            ema_prev = alpha * price + (1 - alpha) * ema_prev
            ema_vals.append(ema_prev)

    return ema_vals


# ------------------------------------------------------------
# 平均真實波幅 (ATR)
# ------------------------------------------------------------
def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """
    平均真實波幅 (Average True Range)

    :param highs: 高點序列
    :param lows: 低點序列
    :param closes: 收盤價序列
    :param period: 週期
    :return: ATR list（長度與 highs 相同）
    """
    n = len(highs)
    if n == 0 or n != len(lows) or n != len(closes) or n < period:
        return [None] * n

    trs = []
    prev_close = closes[0]

    for i in range(n):
        if i == 0:
            tr = highs[i] - lows[i]
        else:
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - prev_close),
                abs(lows[i] - prev_close),
            )
        trs.append(tr)
        prev_close = closes[i]

    # 用 EMA 平滑 TR，得到 ATR
    atr_vals = ema(trs, period)
    return atr_vals


# ------------------------------------------------------------
# RSI（相對強弱指標）
# ------------------------------------------------------------
def rsi(closes: List[float], period: int = 14) -> List[float]:
    """
    相對強弱指標 (Relative Strength Index)

    :param closes: 收盤價序列
    :param period: 週期
    :return: RSI list（長度與 closes 相同）
    """
    n = len(closes)
    if n < period + 1:
        return [None] * n

    deltas = np.diff(closes)  # 長度 n-1
    gains = np.maximum(deltas, 0)
    losses = np.maximum(-deltas, 0)

    rsi_vals = [None] * n

    for i in range(period, n):
        # 注意：deltas/gains/losses 少一個 index，所以要對齊
        start = i - period
        end = i
        avg_gain = np.mean(gains[start:end])
        avg_loss = np.mean(losses[start:end])

        if avg_loss == 0:
            rsi_val = 100
        else:
            rs = avg_gain / avg_loss
            rsi_val = 100 - (100 / (1 + rs))

        rsi_vals[i] = float(rsi_val)

    return rsi_vals


# ------------------------------------------------------------
# ADX（平均趨向指標）
# ------------------------------------------------------------
def adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """
    平均趨向指標 (Average Directional Index)

    :param highs: 高點序列
    :param lows: 低點序列
    :param closes: 收盤價序列
    :param period: 週期
    :return: ADX list（長度與 closes 相同）
    """
    n = len(closes)
    if n <= period or n != len(highs) or n != len(lows):
        return [None] * n

    plus_dm = [0.0]
    minus_dm = [0.0]
    tr = [highs[0] - lows[0]]

    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

        current_tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr.append(current_tr)

    plus_di = []
    minus_di = []
    dx_list = []
    adx_vals = [None] * n

    for i in range(n):
        if i < period:
            plus_di.append(None)
            minus_di.append(None)
            dx_list.append(None)
            continue

        # 使用 period 根的平均值
        plus_dm_smooth = float(np.mean(plus_dm[i - period + 1 : i + 1]))
        minus_dm_smooth = float(np.mean(minus_dm[i - period + 1 : i + 1]))
        tr_smooth = float(np.mean(tr[i - period + 1 : i + 1]))

        if tr_smooth == 0:
            pdi_val = 0.0
            mdi_val = 0.0
        else:
            pdi_val = 100 * plus_dm_smooth / tr_smooth
            mdi_val = 100 * minus_dm_smooth / tr_smooth

        plus_di.append(pdi_val)
        minus_di.append(mdi_val)

        if pdi_val + mdi_val == 0:
            dx_val = 0.0
        else:
            dx_val = 100 * abs(pdi_val - mdi_val) / (pdi_val + mdi_val)

        dx_list.append(dx_val)

        # ADX 通常在 2*period 之後開始有值
        if i >= period * 2 - 1:
            adx_val = float(np.mean(dx_list[i - period + 1 : i + 1]))
            adx_vals[i] = adx_val

    return adx_vals


# ------------------------------------------------------------
# 布林帶 (Bollinger Bands)
# ------------------------------------------------------------
def bollinger_bands(
    closes: List[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Tuple[List[float], List[float], List[float]]:
    """
    布林帶 (Bollinger Bands)

    :return: (upper_band, middle_band, lower_band)
    """
    n = len(closes)
    if n < period:
        return [None] * n, [None] * n, [None] * n

    upper_band = []
    middle_band = []
    lower_band = []

    for i in range(n):
        if i < period - 1:
            upper_band.append(None)
            middle_band.append(None)
            lower_band.append(None)
        else:
            slice_closes = closes[i - period + 1 : i + 1]
            sma = float(np.mean(slice_closes))
            std = float(np.std(slice_closes))

            upper = sma + std_dev * std
            lower = sma - std_dev * std

            upper_band.append(upper)
            middle_band.append(sma)
            lower_band.append(lower)

    return upper_band, middle_band, lower_band


# ------------------------------------------------------------
# 成交量分布（簡化版 Volume Profile）
# ------------------------------------------------------------
def volume_profile(volumes: List[float], period: int = 20) -> List[float]:
    """
    成交量分布（非常簡化版）：
    - 回傳一個「最近 period 根平均成交量」的時間序列
    """
    n = len(volumes)
    if n < period:
        return [None] * n

    profile = []
    for i in range(n):
        if i < period - 1:
            profile.append(None)
        else:
            avg_volume = float(np.mean(volumes[i - period + 1 : i + 1]))
            profile.append(avg_volume)

    return profile


# ------------------------------------------------------------
# 超級趨勢指標 (Supertrend)
# ------------------------------------------------------------
def supertrend(
    highs: List[float], 
    lows: List[float], 
    closes: List[float], 
    period: int = 10, 
    multiplier: float = 3.0
) -> Tuple[List[float], List[bool]]:
    """
    超級趨勢指標 (Supertrend)

    :param highs: 高點序列
    :param lows: 低點序列
    :param closes: 收盤價序列
    :param period: ATR 週期
    :param multiplier: ATR 倍數
    :return: (supertrend_values, trend_directions)
             supertrend_values: 指標數值
             trend_directions: True 為看多 (綠色), False 為看空 (紅色)
    """
    n = len(closes)
    if n < period:
        return [None] * n, [None] * n

    # 1. 計算 ATR
    atr_vals = atr(highs, lows, closes, period)

    # 2. 初始化變數
    supertrend_vals = [None] * n
    trend_dirs = [None] * n  # True=Up, False=Down

    # 為了計算方便，先算出 Basic Bands
    # 但 Supertrend 需要遞迴計算，所以用迴圈處理
    
    # 初始值 (假設從第 period 根開始)
    # 這裡簡單處理：前 period 根都設為 None
    
    final_upper = [0.0] * n
    final_lower = [0.0] * n
    
    for i in range(period, n):
        if atr_vals[i] is None:
            continue
            
        hl2 = (highs[i] + lows[i]) / 2
        basic_upper = hl2 + multiplier * atr_vals[i]
        basic_lower = hl2 - multiplier * atr_vals[i]
        
        prev_close = closes[i-1]
        prev_final_upper = final_upper[i-1] if i > 0 else 0.0
        prev_final_lower = final_lower[i-1] if i > 0 else 0.0
        
        # 計算 Final Upper Band
        if (basic_upper < prev_final_upper) or (prev_close > prev_final_upper):
            final_upper[i] = basic_upper
        else:
            final_upper[i] = prev_final_upper
            
        # 計算 Final Lower Band
        if (basic_lower > prev_final_lower) or (prev_close < prev_final_lower):
            final_lower[i] = basic_lower
        else:
            final_lower[i] = prev_final_lower
            
        # 判斷趨勢方向
        prev_trend = trend_dirs[i-1] if i > period else True # 預設初始為多
        prev_supertrend = supertrend_vals[i-1] if i > period else 0.0
        
        current_trend = prev_trend # 預設不變
        current_supertrend = prev_supertrend
        
        if prev_trend: # 目前是多頭
            if closes[i] < final_lower[i]: # 跌破下軌 -> 轉空
                current_trend = False
                current_supertrend = final_upper[i]
            else:
                current_trend = True
                current_supertrend = final_lower[i]
        else: # 目前是空頭
            if closes[i] > final_upper[i]: # 突破上軌 -> 轉多
                current_trend = True
                current_supertrend = final_lower[i]
            else:
                current_trend = False
                current_supertrend = final_upper[i]
                
        supertrend_vals[i] = current_supertrend
        trend_dirs[i] = current_trend
        
    return supertrend_vals, trend_dirs
