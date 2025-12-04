# backtest/advanced_backtest.py
# 機構級回測系統 (含資金費率過濾、手續費、限價單模擬)

import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

# 路徑設定
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import config
from strategies.multi_timeframe_trend import MultiTimeframeTrendStrategy
from strategies.breakout_trend import BreakoutTrendStrategy
from strategies.bollinger_reversion import BollingerReversionStrategy

class AdvancedExchangeAPI:
    """
    進階模擬交易所 API
    支援：
    1. OHLCV 數據
    2. 歷史資金費率 (Funding Rate)
    """
    def __init__(self, df_trend, df_entry, df_funding, trend_tf, entry_tf):
        self.df_trend = df_trend
        self.df_entry = df_entry
        self.df_funding = df_funding
        self.trend_tf = trend_tf
        self.entry_tf = entry_tf
        
        # 轉 numpy 加速
        self.ts_trend = self.df_trend['timestamp'].values
        self.ts_entry = self.df_entry['timestamp'].values
        
        if self.df_funding is not None:
            self.ts_funding = self.df_funding['timestamp'].values
            self.rates_funding = self.df_funding['fundingRate'].values
        else:
            self.ts_funding = None
        
        self.current_time = None 

    def set_current_time(self, timestamp):
        self.current_time = timestamp

    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        if timeframe == self.trend_tf:
            df = self.df_trend
            ts_arr = self.ts_trend
        else:
            df = self.df_entry
            ts_arr = self.ts_entry
        
        idx = np.searchsorted(ts_arr, self.current_time, side='right')
        start_idx = max(0, idx - limit)
        recent_data = df.iloc[start_idx:idx]
        
        if recent_data.empty:
            return []
        return recent_data[['timestamp', 'open', 'high', 'low', 'close', 'volume']].values.tolist()

    def fetch_funding_rate(self, symbol):
        """
        回傳當前時間點「最近」的資金費率
        """
        if self.ts_funding is None:
            return 0.0
            
        # 找到 current_time 之前最近的一個 funding rate
        idx = np.searchsorted(self.ts_funding, self.current_time, side='right')
        if idx > 0:
            return self.rates_funding[idx-1]
        return 0.0
    
    def fetch_ticker(self, symbol):
        idx = np.searchsorted(self.ts_entry, self.current_time, side='right')
        if idx > 0:
            price = self.df_entry.iloc[idx-1]['close']
        else:
            price = 0
        return {'last': price}

class AdvancedBacktester:
    def __init__(self, symbol, trend_tf, entry_tf, start_date, initial_equity=1000.0, commission=0.0005):
        self.symbol = symbol
        self.trend_tf = trend_tf
        self.entry_tf = entry_tf
        self.initial_equity = initial_equity
        self.commission = commission  # 手續費 (預設萬5)
        
        # 設定 Config
        config.TIMEFRAMES["trend"] = trend_tf
        config.TIMEFRAMES["entry"] = entry_tf
        
        # 載入數據
        self._load_data(start_date)
        
        # 初始化策略
        self.strategy = MultiTimeframeTrendStrategy()
        # self.strategy = BreakoutTrendStrategy()
        # self.strategy = BollingerReversionStrategy()
        
        self.trades = []
        self.equity_curve = []
        self.equity = initial_equity
        
        # 統計變數
        self.missed_trades = 0  # 紀錄因限價單未成交的次數

    def _load_data(self, start_date):
        data_dir = os.path.join(project_root, "data")
        
        # 檔名處理
        safe_symbol = self.symbol.replace("/", "-") + "-USDT" # e.g. BTC-USDT-USDT
        csv_trend = os.path.join(data_dir, f"{safe_symbol}_{self.trend_tf}.csv")
        csv_entry = os.path.join(data_dir, f"{safe_symbol}_{self.entry_tf}.csv")
        csv_funding = os.path.join(data_dir, f"{safe_symbol}_funding.csv")
        
        print(f"📊 讀取數據: {self.symbol}")
        self.df_trend = self._read_csv(csv_trend, start_date)
        self.df_entry = self._read_csv(csv_entry, start_date)
        
        if os.path.exists(csv_funding):
            print("   ✅ 發現資金費率數據，啟用過濾功能")
            self.df_funding = self._read_csv(csv_funding, start_date)
        else:
            print("   ⚠️ 未發現資金費率數據，將使用預設值 0")
            self.df_funding = None
            
        # 對齊時間
        common_start = max(self.df_trend['timestamp'].min(), self.df_entry['timestamp'].min())
        self.df_trend = self.df_trend[self.df_trend['timestamp'] >= common_start]
        self.df_entry = self.df_entry[self.df_entry['timestamp'] >= common_start]
        
        self.api = AdvancedExchangeAPI(self.df_trend, self.df_entry, self.df_funding, self.trend_tf, self.entry_tf)

    def _read_csv(self, path, start_date):
        if not os.path.exists(path):
            raise FileNotFoundError(f"找不到檔案: {path}")
        df = pd.read_csv(path)
        if 'timestamp' not in df.columns and 'datetime' in df.columns:
            df['timestamp'] = pd.to_datetime(df['datetime']).astype(np.int64) // 10**6
        
        start_ts = pd.to_datetime(start_date).timestamp() * 1000
        df = df[df['timestamp'] >= start_ts]
        return df.sort_values('timestamp').reset_index(drop=True)

    def run(self):
        print(f"\n🚀 開始機構級回測 (Limit Order + Fees + Funding Filter)...")
        
        position = None
        pending_order = None  # 掛單 (Limit Order)
        
        total_candles = len(self.df_entry)
        
        for i in range(total_candles - 1): # 留最後一根避免 index out of bounds
            row = self.df_entry.iloc[i]
            next_row = self.df_entry.iloc[i+1] # 用下一根 K 線來判斷成交
            
            current_ts = row['timestamp']
            self.api.set_current_time(current_ts)
            
            # ------------------------------------------
            # 1. 處理掛單 (Limit Order Execution)
            # ------------------------------------------
            if pending_order:
                # 檢查下一根 K 線是否吃到掛單
                # 買單：Next Low <= Limit Price
                # 賣單：Next High >= Limit Price
                
                is_filled = False
                fill_price = pending_order['price']
                
                if pending_order['side'] == 'buy':
                    if next_row['low'] <= fill_price:
                        is_filled = True
                else: # sell
                    if next_row['high'] >= fill_price:
                        is_filled = True
                
                if is_filled:
                    # 成交！建立倉位
                    # 扣除手續費 (Entry Fee)
                    cost = fill_price * pending_order['size'] * self.commission
                    self.equity -= cost
                    
                    position = {
                        'entry': fill_price,
                        'sl': pending_order['sl'],
                        'tp': pending_order['tp'],
                        'side': pending_order['side'],
                        'size': pending_order['size'],
                        'atr': pending_order['atr'],
                        'entry_ts': next_row['timestamp']
                    }
                    pending_order = None # 掛單移除
                else:
                    # 掛單未成交，過期取消 (Missed Trade)
                    # 這裡假設掛單只掛一根 K 線，沒吃到就撤單 (這是常見的策略邏輯)
                    self.missed_trades += 1
                    pending_order = None

            # ------------------------------------------
            # 2. 處理持倉 (Position Management)
            # ------------------------------------------
            if position:
                # 檢查出場 (SL/TP)
                # 使用 next_row 的 High/Low 來判斷是否觸發
                
                exit_price = None
                reason = ''
                
                # 移動止損邏輯 (簡化版)
                ts_mult = 3.0
                if position['atr'] > 0:
                    if position['side'] == 'buy':
                        new_sl = row['close'] - (position['atr'] * ts_mult)
                        if new_sl > position['sl']: position['sl'] = new_sl
                    else:
                        new_sl = row['close'] + (position['atr'] * ts_mult)
                        if new_sl < position['sl']: position['sl'] = new_sl

                # 檢查是否觸發 SL/TP (在下一根 K 線內)
                if position['side'] == 'buy':
                    if next_row['low'] <= position['sl']:
                        exit_price = position['sl'] # 假設滑點嚴重，這裡其實可以模擬更差的價格
                        reason = 'SL'
                    elif next_row['high'] >= position['tp']:
                        exit_price = position['tp']
                        reason = 'TP'
                else:
                    if next_row['high'] >= position['sl']:
                        exit_price = position['sl']
                        reason = 'SL'
                    elif next_row['low'] <= position['tp']:
                        exit_price = position['tp']
                        reason = 'TP'
                
                if exit_price:
                    # 計算損益
                    if position['side'] == 'buy':
                        pnl = (exit_price - position['entry']) * position['size']
                    else:
                        pnl = (position['entry'] - exit_price) * position['size']
                    
                    # 扣除手續費 (Exit Fee)
                    exit_cost = exit_price * position['size'] * self.commission
                    pnl -= exit_cost
                    
                    self.equity += pnl
                    self.trades.append({
                        'entry_ts': position['entry_ts'],
                        'exit_ts': next_row['timestamp'],
                        'side': position['side'],
                        'entry': position['entry'],
                        'exit': exit_price,
                        'pnl': pnl,
                        'reason': reason,
                        'equity': self.equity
                    })
                    position = None
            
            # ------------------------------------------
            # 3. 尋找新機會 (Signal Generation)
            # ------------------------------------------
            if position is None and pending_order is None:
                signal = self.strategy.analyze(self.api, self.symbol)
                
                if signal:
                    # 資金管理
                    risk_amt = self.equity * 0.02
                    dist = abs(signal['entry'] - signal['sl'])
                    if dist > 0:
                        size = risk_amt / dist
                        # 槓桿限制 3x
                        if size * signal['entry'] > self.equity * 3:
                            size = (self.equity * 3) / signal['entry']
                        
                        # 發送限價掛單 (Limit Order)
                        # 掛在當前 K 線的 Close 價 (假設我們在收盤瞬間掛單)
                        pending_order = {
                            'price': row['close'], # Limit Price
                            'sl': signal['sl'],
                            'tp': signal['tp'],
                            'side': signal['side'],
                            'size': size,
                            'atr': signal['atr']
                        }

            # 記錄權益曲線
            self.equity_curve.append({'timestamp': current_ts, 'equity': self.equity})

        self._print_stats()

    def _print_stats(self):
        final_equity = self.equity
        ret = (final_equity - self.initial_equity) / self.initial_equity * 100
        
        print("\n" + "="*40)
        print(f"📊 機構級回測報告: {self.symbol}")
        print("="*40)
        print(f"策略: {self.strategy.name}")
        print(f"週期: {self.trend_tf} / {self.entry_tf}")
        print(f"初始: {self.initial_equity:.2f} U")
        print(f"最終: {final_equity:.2f} U")
        print(f"報酬: {ret:.2f}%")
        print(f"交易次數: {len(self.trades)}")
        print(f"錯過交易 (Limit未成交): {self.missed_trades}")
        
        if self.trades:
            wins = [t for t in self.trades if t['pnl'] > 0]
            win_rate = len(wins) / len(self.trades) * 100
            print(f"勝率: {win_rate:.2f}%")
            
            # 畫圖
            df_eq = pd.DataFrame(self.equity_curve)
            df_eq['datetime'] = pd.to_datetime(df_eq['timestamp'], unit='ms')
            df_eq.set_index('datetime', inplace=True)
            df_eq['equity'].plot(title=f"Advanced Backtest: {self.symbol}", figsize=(10, 6))
            plt.show()

if __name__ == "__main__":
    # 測試用
    bt = AdvancedBacktester(
        symbol="BTC/USDT",
        trend_tf="4h",
        entry_tf="15m",
        start_date="2023-01-01"
    )
    bt.run()
