# backtest/composite_backtest.py
# 組合策略回測系統 (模擬真實 Bot 行為)
# 同時運行 Trend, Breakout, Reversion 策略，並依優先順序執行

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
from config import TIMEFRAMES, REWARD_RATIO

# 引入所有策略
from strategies.multi_timeframe_trend import MultiTimeframeTrendStrategy
from strategies.breakout_trend import BreakoutTrendStrategy
from strategies.bollinger_reversion import BollingerReversionStrategy
from strategies.supertrend_strategy import SupertrendStrategy
from core.regime_detector import RegimeDetector, MarketRegime

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

class CompositeBacktester:
    def __init__(self, csv_trend, csv_entry, trend_tf, entry_tf, start_date=None, end_date=None, initial_equity=1000.0, fee_rate=0.0005, slippage=0.0002):
        self.trend_tf = trend_tf
        self.entry_tf = entry_tf
        self.fee_rate = fee_rate      # 0.05% (Taker)
        self.slippage = slippage      # 0.02% (滑點)
        self.avg_funding_rate = 0.0001 # 0.01% per 8h (平均資金費率)
        
        # 動態修改 config 中的 TIMEFRAMES
        config.TIMEFRAMES["trend"] = trend_tf
        config.TIMEFRAMES["entry"] = entry_tf

        # ---------------------------------------------------
        # 初始化所有策略 (模擬 QuantBot)
        # ---------------------------------------------------
        self.strategies = [
            # MultiTimeframeTrendStrategy(),     # 1. 趨勢回調 (主) - 暫時停用
            # BreakoutTrendStrategy(rr=REWARD_RATIO),  # 2. 波動率突破 (表現不佳，停用)
            SupertrendStrategy(rr=REWARD_RATIO), # 3. 超級趨勢 (優化版 - 核心策略)
            BollingerReversionStrategy(rr=REWARD_RATIO), # 4. 趨勢回調 (優化版 - 輔助策略)
        ]
        self.regime_detector = RegimeDetector()

        self.trades = []
        self.equity_curve = [] 
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
        common_start = max(self.df_trend['timestamp'].min(), self.df_entry['timestamp'].min())
        common_end = min(self.df_trend['timestamp'].max(), self.df_entry['timestamp'].max())
        
        self.df_trend = self.df_trend[(self.df_trend['timestamp'] >= common_start) & (self.df_trend['timestamp'] <= common_end)]
        self.df_entry = self.df_entry[(self.df_entry['timestamp'] >= common_start) & (self.df_entry['timestamp'] <= common_end)]
        
        self.df_trend.reset_index(drop=True, inplace=True)
        self.df_entry.reset_index(drop=True, inplace=True)
        
        self.api = MockExchangeAPI(self.df_trend, self.df_entry, trend_tf, entry_tf)
        print(f"✅ 資料準備完成 | 區間: {len(self.df_entry)} 根 K線")

    def _load_csv(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"找不到檔案: {path}")
        df = pd.read_csv(path)
        if 'timestamp' not in df.columns and 'datetime' in df.columns:
            df['timestamp'] = pd.to_datetime(df['datetime']).astype(np.int64) // 10**6
        return df.sort_values('timestamp')

    def run(self, plot=True):
        print("\n🚀 開始組合策略回測...")
        
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
                
                # 移動止損 (Trailing Stop)
                atr_val = position.get('atr', 0)
                if atr_val > 0:
                    # 讀取策略設定的移動止損參數，若無則預設 2.0
                    ts_mult = position.get('trailing_stop_atr', 2.0)
                    trailing_dist = ts_mult * atr_val
                    
                    if position['side'] == 'buy':
                        new_sl = current_price - trailing_dist
                        if new_sl > position['sl']:
                            position['sl'] = new_sl
                    else:
                        new_sl = current_price + trailing_dist
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
                    # Apply Slippage to Exit
                    # Buy position closing (Sell): Price decreases (worse)
                    # Sell position closing (Buy): Price increases (worse)
                    real_exit_price = exit_price
                    if position['side'] == 'buy':
                        real_exit_price = real_exit_price * (1 - self.slippage)
                    else:
                        real_exit_price = real_exit_price * (1 + self.slippage)

                    # Fee Calculation
                    entry_fee = position['entry'] * position['size'] * self.fee_rate
                    exit_fee = real_exit_price * position['size'] * self.fee_rate
                    
                    # Funding Fee Calculation
                    # Duration in hours
                    duration_ms = current_ts - position['entry_ts']
                    duration_hours = duration_ms / (1000 * 3600)
                    funding_intervals = duration_hours / 8
                    funding_fee = (position['entry'] * position['size']) * self.avg_funding_rate * funding_intervals
                    
                    total_fee = entry_fee + exit_fee + funding_fee
                    
                    # PnL Calculation using real_exit_price
                    if position['side'] == 'buy':
                        gross_pnl = (real_exit_price - position['entry']) * position['size']
                    else:
                        gross_pnl = (position['entry'] - real_exit_price) * position['size']

                    net_pnl = gross_pnl - total_fee
                    self.equity += net_pnl
                    
                    self.trades.append({
                        'timestamp': current_ts,
                        'symbol': SYMBOL + '/USDT' if 'SYMBOL' in globals() else 'Unknown',
                        'side': position['side'],
                        'entry': position['entry'],
                        'exit': real_exit_price,
                        'pnl': net_pnl,  # 記錄淨損益
                        'gross_pnl': gross_pnl, # 記錄毛損益
                        'fee': total_fee, # 記錄手續費 (含資金費)
                        'reason': reason,
                        'equity': self.equity,
                        'strategy': position.get('strategy', 'Unknown')
                    })
                    position = None
                    continue 
            
            # 2. 檢查進場 (模擬 QuantBot 的 check_signals)
            if position is None:
                # 依序詢問每個策略
                signal = None
                for strat in self.strategies:
                    # 取得全域變數 SYMBOL，若無則預設 SOL
                    sym = globals().get('SYMBOL', 'SOL')
                    s = strat.analyze(self.api, f"{sym}/USDT")
                    if s:
                        signal = s
                        break # 找到訊號就跳出，不再問下一個策略
                
                if signal:
                    risk_pct = 0.02
                    risk_amt = self.equity * risk_pct
                    dist = abs(signal['entry'] - signal['sl'])
                    
                    if dist > 0:
                        size = risk_amt / dist
                        # 槓桿限制 (模擬)
                        if size * signal['entry'] > self.equity * 5:
                            size = (self.equity * 5) / signal['entry']
                        
                        # Apply Slippage to Entry
                        # Buy: Price increases (worse)
                        # Sell: Price decreases (worse)
                        entry_price = signal['entry']
                        if signal['side'] == 'buy':
                            entry_price = entry_price * (1 + self.slippage)
                        else:
                            entry_price = entry_price * (1 - self.slippage)

                        position = {
                            'entry': entry_price,
                            'entry_ts': current_ts, # Record entry time for funding calc
                            'sl': signal['sl'],
                            'tp': signal['tp'],
                            'side': signal['side'],
                            'size': size,
                            'atr': signal.get('atr', 0),
                            'strategy': signal.get('strategy', 'Unknown'),
                            'trailing_stop_atr': signal.get('trailing_stop_atr', 2.0)
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
            "sortino_ratio": 0,
            "strategy_breakdown": {}
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

            # 策略分佈統計
            strat_names = set([t['strategy'] for t in self.trades])
            for name in strat_names:
                strat_trades = [t for t in self.trades if t['strategy'] == name]
                strat_wins = [t for t in strat_trades if t['pnl'] > 0]
                win_rate = len(strat_wins) / len(strat_trades) * 100 if strat_trades else 0
                pnl = sum([t['pnl'] for t in strat_trades])
                stats["strategy_breakdown"][name] = {
                    "count": len(strat_trades),
                    "win_rate": win_rate,
                    "pnl": pnl
                }

        # 計算最大回撤 & Sharpe/Sortino
        if self.equity_curve:
            df_eq = pd.DataFrame(self.equity_curve)
            df_eq['datetime'] = pd.to_datetime(df_eq['timestamp'], unit='ms')
            df_eq.set_index('datetime', inplace=True)
            
            df_eq['peak'] = df_eq['equity'].cummax()
            df_eq['drawdown'] = (df_eq['equity'] - df_eq['peak']) / df_eq['peak']
            stats["max_dd"] = abs(df_eq['drawdown'].min())

            daily_returns = df_eq['equity'].resample('D').last().pct_change().dropna()
            if len(daily_returns) > 1 and daily_returns.std() != 0:
                stats["sharpe_ratio"] = daily_returns.mean() / daily_returns.std() * np.sqrt(365)
                downside_returns = daily_returns[daily_returns < 0]
                if len(downside_returns) > 0 and downside_returns.std() != 0:
                    stats["sortino_ratio"] = daily_returns.mean() / downside_returns.std() * np.sqrt(365)
        
        return stats

    def _print_stats(self, stats):
        print("\n" + "="*40)
        print(f"📊 {SYMBOL}組合策略回測結果 (Composite)")
        print("="*40)
        print(f"時間級別: 趨勢 {self.trend_tf} / 進場 {self.entry_tf}")
        print("-" * 40)
        print(f"初始資金: {stats['initial_equity']:.2f} U")
        print(f"最終權益: {stats['final_equity']:.2f} U")
        print(f"總報酬率: {stats['total_return']:.2f}%")
        print(f"總交易次數: {stats['total_trades']}")
        print(f"勝率: {stats['win_rate']:.2f}%")
        print(f"獲利因子 (PF): {stats['profit_factor']:.2f}")
        print(f"最大回撤 (MDD): {stats['max_dd']*100:.2f}%")
        print(f"夏普比率: {stats['sharpe_ratio']:.2f}")
        print("-" * 40)
        print("📌 各策略表現:")
        for name, data in stats["strategy_breakdown"].items():
            print(f"  - {name}: {data['count']} 筆, 勝率 {data['win_rate']:.1f}%, PnL: {data['pnl']:.2f} U")

    def _plot_results(self, stats):
        if not self.equity_curve:
            return

        df_eq = pd.DataFrame(self.equity_curve)
        df_eq['datetime'] = pd.to_datetime(df_eq['timestamp'], unit='ms')
        df_eq.set_index('datetime', inplace=True)
        
        df_eq['peak'] = df_eq['equity'].cummax()
        df_eq['drawdown'] = (df_eq['equity'] - df_eq['peak']) / df_eq['peak']
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), gridspec_kw={'height_ratios': [2, 1]})
        plt.subplots_adjust(right=0.75)
        
        ax1.plot(df_eq.index, df_eq['equity'], label='Equity', color='#1f77b4')
        ax1.set_title('Composite Strategy Equity Curve', fontsize=14)
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # 準備統計數據文字
        textstr = '\n'.join((
            f"Total Return: {stats['total_return']:.2f}%",
            f"Win Rate: {stats['win_rate']:.2f}%",
            f"Profit Factor: {stats['profit_factor']:.2f}",
            f"Max Drawdown: {stats['max_dd']*100:.2f}%",
            f"Trades: {stats['total_trades']}",
            "----------------",
            "Breakdown:",
        ))
        for name, data in stats["strategy_breakdown"].items():
            textstr += f"\n{name[:10]}..: {data['count']} ({data['win_rate']:.0f}%)"
        
        props = dict(boxstyle='round', facecolor='white', alpha=0.8, edgecolor='gray')
        fig.text(0.77, 0.60, textstr, fontsize=11, verticalalignment='top', bbox=props)

        ax2.fill_between(df_eq.index, df_eq['drawdown'], 0, color='#d62728', alpha=0.3)
        ax2.set_title('Drawdown (%)')
        ax2.grid(True, alpha=0.3)
        
        output_file = "backtest_result_composite.png"
        plt.savefig(output_file)
        print(f"📊 圖表已儲存至 {output_file}")

if __name__ == "__main__":
    # ==========================================
    # ⚙️ 使用者設定區
    # ==========================================
    SYMBOL = "BTC"
    TREND_TIMEFRAME = "4h"   
    ENTRY_TIMEFRAME = "15m"   
    START_DATE = "2023-01-01"
    END_DATE = None
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # data_dir is in the parent of project_root (TRADING/data)
    data_dir = os.path.join(os.path.dirname(project_root), "data")
    
    csv_trend = os.path.join(data_dir, f"{SYMBOL}-USDT-USDT_{TREND_TIMEFRAME}.csv")
    csv_entry = os.path.join(data_dir, f"{SYMBOL}-USDT-USDT_{ENTRY_TIMEFRAME}.csv")
    
    if os.path.exists(csv_trend) and os.path.exists(csv_entry):
        bt = CompositeBacktester(
            csv_trend, 
            csv_entry, 
            trend_tf=TREND_TIMEFRAME, 
            entry_tf=ENTRY_TIMEFRAME,
            start_date=START_DATE,
            end_date=END_DATE
        )
        bt.run()
    else:
        print(f"❌ 找不到 CSV 檔案: {csv_trend}")
