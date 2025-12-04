# ============================================================
# strategies/multi_timeframe_trend.py
#
# 多時間框架 趨勢回撤策略 (主策略)
#
# 流程：
#   1) 1h K 線判斷大方向（多 / 空 / 不交易）
#   2) 1h 判斷市場是否為「有趨勢」：
#         - ADX >= MIN_ADX
#         - RSI 不過熱 (30 ~ 70) 避免追到尾巴
#         - 波動率 > VOLATILITY_THRESHOLD 避免死盤
#   3) 15m K 線找「回調到 EMA21」且順勢收 K 的點進場
#   4) 用 ATR 設止損，RR 固定 REWARD_RATIO（例如 2.5）
# ============================================================

from typing import Optional, Dict, Any
import numpy as np

from indicators.advanced_indicators import ema, atr, adx, rsi
from utils.logger_util import log
from config import (
    TIMEFRAMES,
    EMA_SLOW,
    EMA_FAST,
    EMA_TREND,
    ATR_PERIOD,
    REWARD_RATIO,
    MIN_ADX,
    VOLATILITY_THRESHOLD,
)


class MultiTimeframeTrendStrategy:
    """
    多時間框架 趨勢回撤策略：

    - trend TF（預設 1h）: 判斷大方向、多空 & 市場 regime
    - entry TF（預設 15m）: 找順勢回調到 EMA 的進場點
    """

    def __init__(self):
        self.name = "MultiTimeframeTrend"
        # [策略參數設定] 將參數封裝在策略內部，避免修改外部 Config
        self.trailing_stop_atr = 3.0  # 移動止損 ATR 倍數
        self.reward_ratio = 2.0       # 盈虧比
        self.rsi_entry_long = 55      # 做多 RSI 上限
        self.rsi_entry_short = 45     # 做空 RSI 下限

    # --------------------------------------------------------
    # 主入口：給 QuantBot 呼叫
    # --------------------------------------------------------
    def analyze(self, api, symbol: str) -> Optional[Dict[str, Any]]:
        """
        :param api: ExchangeAPI instance
        :param symbol: 交易對，例如 "BTC/USDT:USDT"
        :return: signal dict or None
        """
        try:
            # 0) 判斷是否需要「嚴格模式」 (Strict Mode)
            # 針對 BTC/ETH (噪音多) 或 5m (雜訊大) 啟用更嚴格的過濾條件
            is_major = "BTC" in symbol or "ETH" in symbol
            tf_entry = TIMEFRAMES["entry"]
            is_low_tf = tf_entry in ["5m", "1m"]
            
            strict_mode = is_major or is_low_tf
            if strict_mode:
                # log(f"🛡️ {symbol} 啟用嚴格過濾模式 (Major Coin or Low TF)")
                pass

            # 1) 取得 1h K 線
            tf_trend = TIMEFRAMES["trend"]
            ohlcv_1h = api.fetch_ohlcv(symbol, tf_trend, limit=300)
            if not ohlcv_1h or len(ohlcv_1h) < 250:
                log(f"⚠️ {symbol} 1h K 線不足，略過策略判斷")
                return None

            # 2) 分析大趨勢方向
            trend_direction = self._analyze_trend_direction(ohlcv_1h)
            if trend_direction == "none":
                return None

            # 3) 分析市場是否是「趨勢盤」
            regime = self._analyze_regime(ohlcv_1h, strict_mode)
            if regime != "trending":
                return None

            # [新增] 資金費率過濾 (Sentiment Filter)
            # 如果做多：資金費率不能過高 (例如 > 0.05% 代表過熱，容易回調)
            # 如果做空：資金費率不能過低 (例如 < -0.05% 代表過度看空，容易軋空)
            funding_rate = api.fetch_funding_rate(symbol)
            
            # 4) 取得 15m K 線（找入場點）
            ohlcv_15m = api.fetch_ohlcv(symbol, tf_entry, limit=120)
            if not ohlcv_15m or len(ohlcv_15m) < 60:
                log(f"⚠️ {symbol} {tf_entry} K 線不足，無法找入場點")
                return None

            signal = self._find_entry_signal(ohlcv_15m, trend_direction, funding_rate, strict_mode)
            if signal:
                log(
                    f"🎯 {symbol} {trend_direction.upper()} 信號 | "
                    f"entry={signal['entry']:.2f}, sl={signal['sl']:.2f}, tp={signal['tp']:.2f}"
                )
            return signal

        except Exception as e:
            log(f"❌ 策略分析錯誤 {symbol}: {e}")
            return None

        # --------------------------------------------------------
    # 1h 判斷大方向
    # --------------------------------------------------------
    def _analyze_trend_direction(self, ohlcv) -> str:
        """
        使用三條 EMA 判斷大方向：
          - EMA_FAST（50）
          - EMA_SLOW（200）
          - EMA_TREND（21）
        條件（偏保守）：
          - 多頭：EMA_FAST > EMA_SLOW，close > EMA_TREND > EMA_SLOW
          - 空頭：EMA_FAST < EMA_SLOW，close < EMA_TREND < EMA_SLOW
        
        [修正] 使用倒數第二根 K 線 (Completed Candle) 判斷，避免訊號閃爍
        """
        # 確保數據足夠
        if len(ohlcv) < max(EMA_SLOW, EMA_FAST, EMA_TREND) + 5:
            return "none"

        closes = [c[4] for c in ohlcv]
        
        ema_slow = ema(closes, EMA_SLOW)
        ema_fast = ema(closes, EMA_FAST)
        ema_tr = ema(closes, EMA_TREND)

        # 取倒數第二根 (已收盤)
        c = closes[-2]
        es = ema_slow[-2]
        ef = ema_fast[-2]
        et = ema_tr[-2]

        if None in (es, ef, et):
            return "none"

        bullish = (ef > es) and (c > et) and (et > es)
        bearish = (ef < es) and (c < et) and (et < es)

        if bullish:
            # log(f"📈 大趨勢：BULLISH")
            return "bullish"
        if bearish:
            # log(f"📉 大趨勢：BEARISH")
            return "bearish"

        return "none"

    # --------------------------------------------------------
    # 1h 判斷市場狀態（trend / range）
    # --------------------------------------------------------
    def _analyze_regime(self, ohlcv, strict_mode: bool = False) -> str:
        """
        使用 ADX + RSI + volatility 判斷是否為「有趨勢的市場」
        [修正] 使用倒數第二根 K 線 (Completed Candle)
        """
        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        closes = [c[4] for c in ohlcv]

        adx_vals = adx(highs, lows, closes, period=14)
        rsi_vals = rsi(closes, period=14)

        # 取倒數第二根
        current_adx = adx_vals[-2] if adx_vals and len(adx_vals) >= 2 and adx_vals[-2] is not None else 0
        current_rsi = rsi_vals[-2] if rsi_vals and len(rsi_vals) >= 2 and rsi_vals[-2] is not None else 50

        # 最近 20 根收盤價的波動率 (取到 -2)
        if len(closes) >= 22:
            recent = closes[-22:-2]
            volatility = float(np.std(recent) / np.mean(recent))
        else:
            volatility = 0.0

        # 設定 ADX 門檻
        required_adx = MIN_ADX
        if strict_mode:
            required_adx = MIN_ADX + 5  # 嚴格模式下，要求更強的趨勢 (例如 25 -> 30)

        if (
            current_adx >= required_adx
            and 25 <= current_rsi <= 75
            and volatility >= VOLATILITY_THRESHOLD
        ):
            # log("📊 市場狀態：TRENDING")
            return "trending"

        # log("📊 市場狀態：RANGING，略過")
        return "ranging"

    # --------------------------------------------------------
    # 15m 找入場點
    # --------------------------------------------------------
    def _find_entry_signal(self, ohlcv, trend_direction: str, funding_rate: float = 0.0, strict_mode: bool = False) -> Optional[Dict[str, Any]]:
        """
        15m 入場條件（順勢回調）：
        [修正] 使用倒數第二根 K 線 (Completed Candle) 判斷，避免訊號閃爍
        """
        if len(ohlcv) < 50:
            return None

        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        closes = [c[4] for c in ohlcv]
        opens = [c[1] for c in ohlcv]
        volumes = [c[5] for c in ohlcv]

        ema_fast = ema(closes, 21)
        atr_vals = atr(highs, lows, closes, period=ATR_PERIOD)
        rsi_vals = rsi(closes, period=14)

        # 取倒數第二根 (已收盤)
        e = ema_fast[-2]
        a = atr_vals[-2]
        c = closes[-2]
        h = highs[-2]
        l = lows[-2]
        o = opens[-2]
        v = volumes[-2]
        r = rsi_vals[-2] if rsi_vals and len(rsi_vals) >= 2 and rsi_vals[-2] is not None else 50

        # 計算 Volume MA (20) (取到 -2)
        if len(volumes) >= 22:
            vol_ma = sum(volumes[-22:-2]) / 20
        else:
            vol_ma = 0

        if e is None or a is None:
            return None

        pullback_ratio = abs(c - e) / e  # 價格偏離 EMA 的比例

        # （可視需求再調）目前設定 1% 內偏離視為「回調到均線附近」
        max_pullback = 0.01
        
        # 設定 RSI 入場門檻
        rsi_long_limit = self.rsi_entry_long
        rsi_short_limit = self.rsi_entry_short
        
        # 設定止損 ATR 倍數
        sl_atr_mult = 0.2
        
        if strict_mode:
            # 嚴格模式：要求更深的回調，避免追高殺低
            rsi_long_limit = 50   # 必須回調到 RSI < 50
            rsi_short_limit = 50  # 必須反彈到 RSI > 50
            sl_atr_mult = 0.5     # 給予更大的止損空間，避免被掃出場

        if trend_direction == "bullish":
            # [Sentiment Filter] 資金費率過高 (>0.03%)，代表市場過熱，暫停做多
            if funding_rate > 0.0003:
                log(f"⚠️ 資金費率過熱 ({funding_rate*100:.4f}%)，暫停做多")
                return None

            # 多頭入場：回調到 EMA 上方附近，再收一根不錯的陽線
            if (
                c > e
                and pullback_ratio <= max_pullback
                and c > o  # 陽線
                and l >= e * 0.997  # 不要跌太深
                and r < rsi_long_limit  # [Filter] RSI 檢查
            ):
                # [修正] Entry 設為當前 K 線 ([-1]) 的開盤價，因為我們是在 [-2] 收盤後進場
                entry = closes[-1] # 其實就是 [-2] 的 close，也就是 [-1] 的 open
                sl = min(l, e * 0.997) - sl_atr_mult * a  # 稍微給點 buffer
                if sl <= 0 or sl >= entry:
                    return None
                risk = entry - sl
                tp = entry + self.reward_ratio * risk

                return {
                    "side": "buy",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "atr": a,
                    "strategy": self.name,
                    "trailing_stop_atr": self.trailing_stop_atr
                }

        elif trend_direction == "bearish":
            # [Sentiment Filter] 資金費率過低 (<-0.03%)，代表市場過度看空，暫停做空
            if funding_rate < -0.0003:
                log(f"⚠️ 資金費率過低 ({funding_rate*100:.4f}%)，暫停做空")
                return None

            # 空頭入場：回調到 EMA 下方附近，再收一根不錯的陰線
            if (
                c < e
                and pullback_ratio <= max_pullback
                and c < o  # 陰線
                and h <= e * 1.003  # 不要往上刺太多
                and r > rsi_short_limit  # [Filter] RSI 檢查
            ):
                entry = closes[-1]
                sl = max(h, e * 1.003) + sl_atr_mult * a
                if sl <= entry:
                    return None
                risk = sl - entry
                tp = entry - self.reward_ratio * risk

                return {
                    "side": "sell",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "atr": a,
                    "strategy": self.name,
                    "trailing_stop_atr": self.trailing_stop_atr
                }

        return None
