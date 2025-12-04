# backtest/simple_backtest.py
# 專業版回測系統 (含視覺化、效能優化、訓練/測試集切分、夏普比率)

import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# 將上層目錄加入 path 以便 import strategies
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 引入 config 並允許動態修改
import config
from config import TIMEFRAMES

# 引入您的策略
from strategies.multi_timeframe_trend import MultiTimeframeTrendStrategy
from strategies.breakout_trend import BreakoutTrendStrategy
from strategies.bollinger_reversion import BollingerReversionStrategy

class MockExchangeAPI:
    """
    模擬交易所 API (通用版)
    支援動態時間級別，使用 numpy searchsorted 加速查找
    """
    def __init__(self, df_trend, df_entry, trend_tf, entry_tf):
        self.df_trend = df_trend
        self.df_entry = df_entry
        self.trend_tf = trend_tf
        self.entry_tf = entry_tf
        
        # 預先轉成 numpy array 加速查找
        self.ts_trend = self.df_trend['timestamp'].values
        self.ts_entry = self.df_entry['timestamp'].values
        
        self.current_time = None 
        self.funding_rate = 0.0001 

    def set_current_time(self, timestamp):
        self.current_time = timestamp

    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        # 根據請求的時間級別回傳對應的資料
        if timeframe == self.trend_tf:
            df = self.df_trend
            ts_arr = self.ts_trend
        elif timeframe == self.entry_tf:
            df = self.df_entry
            ts_arr = self.ts_entry
        else:
            # 如果請求了未知的時間級別，預設回傳 entry 級別 (避免報錯)
            df = self.df_entry
            ts_arr = self.ts_entry
        
        # 使用二分搜尋找到 current_time 的位置 (右邊界)
        idx = np.searchsorted(ts_arr, self.current_time, side='right')
        
        # 取出前 limit 筆
        start_idx = max(0, idx - limit)
        recent_data = df.iloc[start_idx:idx]
        
        if recent_data.empty:
            return []
            
        # 轉成 list of list
        return recent_data[['timestamp', 'open', 'high', 'low', 'close', 'volume']].values.tolist()

    def fetch_funding_rate(self, symbol):
        return self.funding_rate
    
    def fetch_ticker(self, symbol):
        # 回傳當前 entry 級別的收盤價
        idx = np.searchsorted(self.ts_entry, self.current_time, side='right')
        if idx > 0:
            price = self.df_entry.iloc[idx-1]['close']
        else:
            price = 0
        return {'last': price}

class Backtester:
    def __init__(self, csv_trend, csv_entry, trend_tf, entry_tf, start_date=None, end_date=None, initial_equity=1000.0, strategy_class=None):
        self.trend_tf = trend_tf
        self.entry_tf = entry_tf
        
        # 動態修改 config 中的 TIMEFRAMES，讓策略讀到正確的時間級別
        config.TIMEFRAMES["trend"] = trend_tf
        config.TIMEFRAMES["entry"] = entry_tf
        # print(f"⚙️  策略時間級別已設定: 趨勢={trend_tf}, 進場={entry_tf}")

        # ---------------------------------------------------
        # 策略選擇區
        # ---------------------------------------------------
        if strategy_class:
            self.strategy = strategy_class()
        else:
            # self.strategy = MultiTimeframeTrendStrategy()
            # self.strategy = BreakoutTrendStrategy()
            self.strategy = BollingerReversionStrategy()

        self.trades = []
        self.equity_curve = [] # 記錄 [timestamp, equity]
        self.initial_equity = initial_equity
        self.equity = initial_equity
        
        print(f"📊 正在讀取數據...\n  Trend ({trend_tf}): {csv_trend}\n  Entry ({entry_tf}): {csv_entry}")
        self.df_trend = self._load_csv(csv_trend)
        self.df_entry = self._load_csv(csv_entry)
        
        # 時間過濾
        if start_date:
            start_ts = pd.to_datetime(start_date).timestamp() * 1000
            self.df_trend = self.df_trend[self.df_trend['timestamp'] >= start_ts]
            self.df_entry = self.df_entry[self.df_entry['timestamp'] >= start_ts]
            
        if end_date:
            end_ts = pd.to_datetime(end_date).timestamp() * 1000
            self.df_trend = self.df_trend[self.df_trend['timestamp'] <= end_ts]
            self.df_entry = self.df_entry[self.df_entry['timestamp'] <= end_ts]

        # 對齊時間
        if self.df_trend.empty or self.df_entry.empty:
            raise ValueError("❌ 選定的時間範圍內沒有數據！請檢查日期或重新下載數據。")

        common_start = max(self.df_trend['timestamp'].min(), self.df_entry['timestamp'].min())
        common_end = min(self.df_trend['timestamp'].max(), self.df_entry['timestamp'].max())
        
        self.df_trend = self.df_trend[(self.df_trend['timestamp'] >= common_start) & (self.df_trend['timestamp'] <= common_end)]
        self.df_entry = self.df_entry[(self.df_entry['timestamp'] >= common_start) & (self.df_entry['timestamp'] <= common_end)]
        
        self.df_trend.reset_index(drop=True, inplace=True)
        self.df_entry.reset_index(drop=True, inplace=True)
        
        self.api = MockExchangeAPI(self.df_trend, self.df_entry, trend_tf, entry_tf)
        print(f"✅ 資料準備完成 | 區間: {len(self.df_entry)} 根 K線")
        print(f"📅 時間範圍: {pd.to_datetime(common_start, unit='ms')} ~ {pd.to_datetime(common_end, unit='ms')}")

    def _load_csv(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"找不到檔案: {path}")
        df = pd.read_csv(path)
        if 'timestamp' not in df.columns and 'datetime' in df.columns:
            df['timestamp'] = pd.to_datetime(df['datetime']).astype(np.int64) // 10**6
        return df.sort_values('timestamp')

    def run(self, plot=True):
        # print("\n🚀 開始回測...")
        
        position = None 
        total_candles = len(self.df_entry)
        check_interval = max(1, total_candles // 10)
        
        for i, row in self.df_entry.iterrows():
            if i % check_interval == 0:
                print(f"   進度: {i/total_candles*100:.0f}%")
                
            current_ts = row['timestamp']
            current_price = row['close']
            high = row['high']
            low = row['low']
            
            self.api.set_current_time(current_ts)
            
            # 計算浮動盈虧
            unrealized_pnl = 0
            if position:
                if position['side'] == 'buy':
                    unrealized_pnl = (current_price - position['entry']) * position['size']
                else:
                    unrealized_pnl = (position['entry'] - current_price) * position['size']
            
            self.equity_curve.append({
                'timestamp': current_ts,
                'equity': self.equity + unrealized_pnl
            })
            
            # 1. 檢查出場
            if position:
                pnl = 0
                closed = False
                exit_price = current_price
                reason = ''
                
                # ---------------------------------------------------
                # [優化] 移動止損 (Trailing Stop) 邏輯
                # ---------------------------------------------------
                USE_TRAILING_STOP = True
                
                if USE_TRAILING_STOP:
                    # ATR Trailing Stop (Chandelier Exit)
                    atr_val = position.get('atr', 0)
                    if atr_val > 0:
                        # 讀取策略設定的移動止損參數，若無則預設 2.0
                        ts_mult = position.get('trailing_stop_atr', 2.0)
                        trailing_dist = ts_mult * atr_val
                        
                        if position['side'] == 'buy':
                            new_sl = current_price - trailing_dist
                            # 只能往上移，不能往下移
                            if new_sl > position['sl']:
                                position['sl'] = new_sl
                        else:
                            new_sl = current_price + trailing_dist
                            # 只能往下移，不能往上移
                            if new_sl < position['sl']:
                                position['sl'] = new_sl

                if position['side'] == 'buy':
                    if low <= position['sl']: 
                        exit_price = position['sl']
                        pnl = (exit_price - position['entry']) * position['size']
                        closed = True
                        reason = 'SL'
                    elif high >= position['tp']: 
                        exit_price = position['tp']
                        pnl = (exit_price - position['entry']) * position['size']
                        closed = True
                        reason = 'TP'
                        
                elif position['side'] == 'sell':
                    if high >= position['sl']: 
                        exit_price = position['sl']
                        pnl = (position['entry'] - exit_price) * position['size']
                        closed = True
                        reason = 'SL'
                    elif low <= position['tp']: 
                        exit_price = position['tp']
                        pnl = (position['entry'] - exit_price) * position['size']
                        closed = True
                        reason = 'TP'
                
                if closed:
                    self.equity += pnl
                    self.trades.append({
                        'timestamp': current_ts,
                        'symbol': 'BTC/USDT',
                        'side': position['side'],
                        'entry': position['entry'],
                        'exit': exit_price,
                        'pnl': pnl,
                        'reason': reason,
                        'equity': self.equity
                    })
                    position = None
                    continue 
            
            # 2. 檢查進場
            if position is None:
                signal = self.strategy.analyze(self.api, "BTC/USDT")
                
                if signal:
                    risk_pct = 0.02
                    risk_amt = self.equity * risk_pct
                    dist = abs(signal['entry'] - signal['sl'])
                    
                    if dist > 0:
                        size = risk_amt / dist
                        if size * signal['entry'] > self.equity * 3:
                            size = (self.equity * 3) / signal['entry']
                        
                        position = {
                            'entry': signal['entry'],
                            'sl': signal['sl'],
                            'tp': signal['tp'],
                            'side': signal['side'],
                            'size': size,
                            'atr': signal.get('atr', 0)
                        }

        self.stats = self._calculate_stats()
        if plot:
            self._print_stats(self.stats)
            self._plot_results(self.stats)
        return self.stats

    def _calculate_stats(self):
        final_equity = self.equity
        total_return = (final_equity - self.initial_equity) / self.initial_equity * 100
        
        stats = {
            "initial_equity": self.initial_equity,
            "final_equity": final_equity,
            "total_return": total_return,
            "total_trades": len(self.trades),
            "win_rate": 0,
            "profit_factor": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "max_dd": 0,
            "sharpe_ratio": 0,
            "sortino_ratio": 0
        }

        if len(self.trades) > 0:
            wins = [t for t in self.trades if t['pnl'] > 0]
            losses = [t for t in self.trades if t['pnl'] <= 0]
            
            stats["win_rate"] = len(wins) / len(self.trades) * 100
            stats["avg_win"] = np.mean([t['pnl'] for t in wins]) if wins else 0
            stats["avg_loss"] = np.mean([t['pnl'] for t in losses]) if losses else 0
            
            total_win = sum([t['pnl'] for t in wins])
            total_loss = abs(sum([t['pnl'] for t in losses]))
            stats["profit_factor"] = total_win / total_loss if total_loss != 0 else float('inf')

        # 計算最大回撤 & Sharpe/Sortino
        if self.equity_curve:
            df_eq = pd.DataFrame(self.equity_curve)
            df_eq['datetime'] = pd.to_datetime(df_eq['timestamp'], unit='ms')
            df_eq.set_index('datetime', inplace=True)
            
            # Max Drawdown
            df_eq['peak'] = df_eq['equity'].cummax()
            df_eq['drawdown'] = (df_eq['equity'] - df_eq['peak']) / df_eq['peak']
            stats["max_dd"] = abs(df_eq['drawdown'].min())

            # Sharpe & Sortino (以日為單位)
            daily_returns = df_eq['equity'].resample('D').last().pct_change().dropna()
            if len(daily_returns) > 1 and daily_returns.std() != 0:
                # 假設無風險利率為 0
                stats["sharpe_ratio"] = daily_returns.mean() / daily_returns.std() * np.sqrt(365)
                
                downside_returns = daily_returns[daily_returns < 0]
                if len(downside_returns) > 0 and downside_returns.std() != 0:
                    stats["sortino_ratio"] = daily_returns.mean() / downside_returns.std() * np.sqrt(365)
        
        return stats

    def _print_stats(self, stats):
        print("\n" + "="*40)
        print("📊 回測結果統計")
        print("="*40)
        print(f"策略名稱: {self.strategy.__class__.__name__}")
        print(f"時間級別: 趨勢 {self.trend_tf} / 進場 {self.entry_tf}")
        print("-" * 40)
        print(f"初始資金: {stats['initial_equity']:.2f} U")
        print(f"最終權益: {stats['final_equity']:.2f} U")
        print(f"總報酬率: {stats['total_return']:.2f}%")
        print(f"總交易次數: {stats['total_trades']}")
        print(f"勝率: {stats['win_rate']:.2f}%")
        print(f"獲利因子 (PF): {stats['profit_factor']:.2f}")
        print(f"平均獲利: {stats['avg_win']:.2f} U")
        print(f"平均虧損: {stats['avg_loss']:.2f} U")
        print(f"最大回撤 (MDD): {stats['max_dd']*100:.2f}%")
        print(f"夏普比率 (Sharpe): {stats['sharpe_ratio']:.2f}")
        print(f"索提諾比率 (Sortino): {stats['sortino_ratio']:.2f}")

    def _plot_results(self, stats):
        if not self.equity_curve:
            return

        df_eq = pd.DataFrame(self.equity_curve)
        df_eq['datetime'] = pd.to_datetime(df_eq['timestamp'], unit='ms')
        df_eq.set_index('datetime', inplace=True)
        
        df_eq['peak'] = df_eq['equity'].cummax()
        df_eq['drawdown'] = (df_eq['equity'] - df_eq['peak']) / df_eq['peak']
        
        # 調整圖表佈局，右邊留白給文字框
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), gridspec_kw={'height_ratios': [2, 1]})
        plt.subplots_adjust(right=0.75)
        
        # 上圖：權益曲線
        ax1.plot(df_eq.index, df_eq['equity'], label='Equity', color='#1f77b4', linewidth=1.5)
        ax1.set_title('Backtest Equity Curve', fontsize=14, fontweight='bold')
        ax1.set_ylabel('USDT', fontsize=12)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper left')
        
        # 準備統計數據文字
        strategy_name = self.strategy.__class__.__name__
        textstr = '\n'.join((
            f"Strategy: {strategy_name}",
            f"Trend TF: {self.trend_tf}",
            f"Entry TF: {self.entry_tf}",
            f"------------------------",
            f"Total Return: {stats['total_return']:.2f}%",
            f"Win Rate: {stats['win_rate']:.2f}%",
            f"Profit Factor: {stats['profit_factor']:.2f}",
            f"Max Drawdown: {stats['max_dd']*100:.2f}%",
            f"Sharpe Ratio: {stats['sharpe_ratio']:.2f}",
            f"Sortino Ratio: {stats['sortino_ratio']:.2f}",
            f"Trades: {stats['total_trades']}"
        ))
        
        # 放置文字框 (放在圖表右側空白處)
        props = dict(boxstyle='round', facecolor='white', alpha=0.8, edgecolor='gray')
        fig.text(0.77, 0.60, textstr, fontsize=11, verticalalignment='top', bbox=props)

        # 下圖：回撤
        ax2.fill_between(df_eq.index, df_eq['drawdown'], 0, color='#d62728', alpha=0.3, label='Drawdown')
        ax2.set_title('Drawdown (%)', fontsize=12)
        ax2.set_ylabel('Drawdown', fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        plt.show()

if __name__ == "__main__":
    # ==========================================
    # ⚙️ 使用者設定區 (在這裡切換時間級別)
    # ==========================================
    TREND_TIMEFRAME = "1d"   # 趨勢判斷 (建議 4h 或 1d)
    ENTRY_TIMEFRAME = "4h"   # 進場點位 (建議 1h 或 15m)
    
    # 設定回測區間
    # START_DATE = "2022-01-01"
    # END_DATE = "2024-06-30"

    # START_DATE = "2022-01-01"
    # END_DATE = "2023-01-01"

    START_DATE = "2023-01-01"
    END_DATE = None

    # START_DATE = "2024-01-01" # 測試今年
    # END_DATE = None           # 到最新
    
    # ==========================================
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, "data")
    
    # 自動組建檔名
    csv_trend = os.path.join(data_dir, f"BTC-USDT-USDT_{TREND_TIMEFRAME}.csv")
    csv_entry = os.path.join(data_dir, f"BTC-USDT-USDT_{ENTRY_TIMEFRAME}.csv")
    
    print(f"📂 預期資料路徑:\n  {csv_trend}\n  {csv_entry}")
    
    if os.path.exists(csv_trend) and os.path.exists(csv_entry):
        bt = Backtester(
            csv_trend, 
            csv_entry, 
            trend_tf=TREND_TIMEFRAME, 
            entry_tf=ENTRY_TIMEFRAME,
            start_date=START_DATE,
            end_date=END_DATE
        )
        bt.run()
    else:
        print(f"❌ 找不到 CSV 檔案，請先執行 download_data.py 並確認已下載 {TREND_TIMEFRAME} 和 {ENTRY_TIMEFRAME} 的資料。")
