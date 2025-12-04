import pandas as pd
import numpy as np
import os
import sys

# 讓這個檔案可以被 import
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

class VectorBacktester:
    """
    向量化回測引擎 (Vectorized Backtester)
    特點：
    1. 預先計算所有指標 (Pre-calculate Indicators)
    2. 預先計算所有訊號 (Pre-calculate Signals)
    3. 僅在持倉管理 (Position Management) 時使用迴圈，大幅提升速度
    """
    def __init__(self, csv_trend, csv_entry, trend_tf, entry_tf, start_date=None, end_date=None, initial_equity=1000.0):
        self.trend_tf = trend_tf
        self.entry_tf = entry_tf
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.trades = []
        
        # 1. 載入資料
        self.df_trend = self._load_csv(csv_trend)
        self.df_entry = self._load_csv(csv_entry)
        
        # 2. 時間過濾
        if start_date:
            start_ts = pd.to_datetime(start_date).timestamp() * 1000
            self.df_trend = self.df_trend[self.df_trend['timestamp'] >= start_ts]
            self.df_entry = self.df_entry[self.df_entry['timestamp'] >= start_ts]
        if end_date:
            end_ts = pd.to_datetime(end_date).timestamp() * 1000
            self.df_trend = self.df_trend[self.df_trend['timestamp'] <= end_ts]
            self.df_entry = self.df_entry[self.df_entry['timestamp'] <= end_ts]

        # 3. 合併資料 (Merge Trend Data into Entry Data)
        # 使用 merge_asof 將大時區資料對齊到小時區
        self.df = self._merge_data(self.df_trend, self.df_entry)
        
    def _load_csv(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        df = pd.read_csv(path)
        # 確保 timestamp 是整數 (ms)
        if 'timestamp' not in df.columns and 'datetime' in df.columns:
            df['timestamp'] = pd.to_datetime(df['datetime']).astype(np.int64) // 10**6
        
        # 強制轉型為 int64，避免 merge 時型別不合
        if 'timestamp' in df.columns:
            df['timestamp'] = df['timestamp'].astype('int64')
            
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df

    def _merge_data(self, df_trend, df_entry):
        """
        將 Trend TF 的指標合併到 Entry TF 的 DataFrame
        注意：必須避免 Look-ahead bias，所以要用 'backward' 方向的 merge，
        或者將 Trend 資料的時間戳記往後推一個單位。
        這裡簡化處理：假設 Trend 資料的 timestamp 是 K 線開盤時間，
        我們用 merge_asof 找「最近一個過去的 Trend K線」。
        """
        df_t = df_trend.copy().sort_values('timestamp')
        df_e = df_entry.copy().sort_values('timestamp')
        
        # 重新命名 Trend 的欄位，避免衝突
        df_t = df_t.rename(columns={
            'open': 'open_trend', 'high': 'high_trend', 'low': 'low_trend', 'close': 'close_trend', 'volume': 'vol_trend'
        })
        
        # merge_asof: 對於每個 Entry row，找到 timestamp <= Entry.timestamp 的最後一個 Trend row
        merged = pd.merge_asof(df_e, df_t, on='timestamp', direction='backward')
        
        # 填補 NaN (因為 Trend 資料比較稀疏，merge 後會有空值，用前值填補)
        merged = merged.ffill()
        return merged

    # ==========================================
    # 指標計算 (Vectorized)
    # ==========================================
    def calculate_indicators(self):
        """
        在這裡一次性計算所有需要的指標
        """
        df = self.df
        
        # --- Trend TF Indicators (基於 close_trend) ---
        # EMA 200, 50, 21
        df['ema200_trend'] = df['close_trend'].ewm(span=200, adjust=False).mean()
        df['ema50_trend'] = df['close_trend'].ewm(span=50, adjust=False).mean()
        df['ema21_trend'] = df['close_trend'].ewm(span=21, adjust=False).mean()
        
        # --- Entry TF Indicators (基於 close) ---
        # RSI 14
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR 14
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean() # 簡單版 ATR，也可以用 ewm
        
        self.df = df

    # ==========================================
    # 訊號生成 (Vectorized)
    # ==========================================
    def generate_signals(self):
        """
        根據策略邏輯生成 Buy/Sell 訊號
        這裡實作 MultiTimeframeTrendStrategy 的邏輯
        """
        df = self.df
        
        # 1. 趨勢判斷 (Trend Alignment)
        # Bullish: EMA50 > EMA200 AND Close > EMA21 AND EMA21 > EMA50
        # (這裡簡化一點，跟原本策略對齊)
        bullish_trend = (df['ema50_trend'] > df['ema200_trend']) & \
                        (df['close_trend'] > df['ema21_trend']) & \
                        (df['ema21_trend'] > df['ema50_trend'])
                        
        bearish_trend = (df['ema50_trend'] < df['ema200_trend']) & \
                        (df['close_trend'] < df['ema21_trend']) & \
                        (df['ema21_trend'] < df['ema50_trend'])
        
        # 2. 進場訊號 (RSI Pullback)
        # Long: Bullish Trend + RSI < 55
        # Short: Bearish Trend + RSI > 45
        long_signal = bullish_trend & (df['rsi'] < 55)
        short_signal = bearish_trend & (df['rsi'] > 45)
        
        # 標記訊號 (1: Buy, -1: Sell, 0: None)
        df['signal'] = 0
        df.loc[long_signal, 'signal'] = 1
        df.loc[short_signal, 'signal'] = -1
        
        self.df = df

    # ==========================================
    # 回測執行 (Event-Driven Loop over Signals)
    # ==========================================
    def run_backtest(self):
        """
        快速迴圈執行回測
        """
        df = self.df
        position = None # { 'side': 1/-1, 'entry': float, 'sl': float, 'tp': float, 'size': float }
        
        # 轉換成 numpy array 加速讀取
        timestamps = df['timestamp'].values
        opens = df['open'].values
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        atrs = df['atr'].values
        signals = df['signal'].values
        
        n = len(df)
        
        for i in range(n):
            # 1. 檢查出場 (如果有持倉)
            if position:
                # Trailing Stop Logic (Simplified)
                # 這裡用簡單的 ATR Trailing
                current_atr = atrs[i] if not np.isnan(atrs[i]) else 0
                
                if position['side'] == 1: # Long
                    # Update SL (Trailing)
                    new_sl = closes[i] - 3.0 * current_atr
                    if new_sl > position['sl']:
                        position['sl'] = new_sl
                    
                    # Check Hit
                    if lows[i] <= position['sl']:
                        self._close_position(timestamps[i], position['sl'], 'SL', position)
                        position = None
                    # (Optional TP check here)
                    
                elif position['side'] == -1: # Short
                    # Update SL (Trailing)
                    new_sl = closes[i] + 3.0 * current_atr
                    if new_sl < position['sl']:
                        position['sl'] = new_sl
                        
                    # Check Hit
                    if highs[i] >= position['sl']:
                        self._close_position(timestamps[i], position['sl'], 'SL', position)
                        position = None

            # 2. 檢查進場 (如果沒持倉)
            # 只有當有訊號時才進場
            if position is None and signals[i] != 0:
                current_atr = atrs[i]
                if np.isnan(current_atr) or current_atr <= 0:
                    continue
                    
                entry_price = closes[i]
                sl_dist = 3.0 * current_atr
                
                # 動態倉位計算：風險固定為權益的 2%
                risk_pct = 0.02
                risk_amt = self.equity * risk_pct
                
                # Size = Risk Amount / Stop Loss Distance
                # 例如：本金 1000，風險 20U。止損距離 100U。Size = 20 / 100 = 0.2 顆
                if sl_dist > 0:
                    size = risk_amt / sl_dist
                else:
                    size = 0
                
                # 槓桿保護：避免開太大 (例如限制最大 5 倍槓桿)
                max_leverage = 5.0
                if size * entry_price > self.equity * max_leverage:
                    size = (self.equity * max_leverage) / entry_price

                if signals[i] == 1: # Buy
                    sl = entry_price - sl_dist
                    tp = entry_price + (sl_dist * 2.0) # RR 1:2
                    position = {
                        'side': 1, 'entry': entry_price, 'sl': sl, 'tp': tp, 'size': size
                    }
                else: # Sell
                    sl = entry_price + sl_dist
                    tp = entry_price - (sl_dist * 2.0)
                    position = {
                        'side': -1, 'entry': entry_price, 'sl': sl, 'tp': tp, 'size': size
                    }

        return self._calculate_stats()

    def _close_position(self, ts, price, reason, pos):
        pnl = (price - pos['entry']) * pos['size'] if pos['side'] == 1 else (pos['entry'] - price) * pos['size']
        self.equity += pnl
        self.trades.append({
            'timestamp': ts,
            'pnl': pnl,
            'reason': reason
        })

    def _calculate_stats(self):
        total_return = (self.equity - self.initial_equity) / self.initial_equity * 100
        wins = [t for t in self.trades if t['pnl'] > 0]
        losses = [t for t in self.trades if t['pnl'] <= 0]
        
        win_rate = len(wins) / len(self.trades) * 100 if self.trades else 0
        total_win = sum(t['pnl'] for t in wins)
        total_loss = abs(sum(t['pnl'] for t in losses))
        pf = total_win / total_loss if total_loss > 0 else 0
        
        # Max Drawdown (Simplified)
        # 這裡沒有 equity curve，只回傳最終結果
        
        return {
            'total_return': total_return,
            'profit_factor': pf,
            'win_rate': win_rate,
            'total_trades': len(self.trades),
            'max_dd': 0 # 暫時略過
        }

if __name__ == "__main__":
    # 測試用
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, "data")
    csv_trend = os.path.join(data_dir, "BTC-USDT-USDT_4h.csv")
    csv_entry = os.path.join(data_dir, "BTC-USDT-USDT_15m.csv")
    
    if os.path.exists(csv_trend):
        vbt = VectorBacktester(csv_trend, csv_entry, "4h", "15m", start_date="2024-01-01")
        vbt.calculate_indicators()
        vbt.generate_signals()
        stats = vbt.run_backtest()
        print(stats)
