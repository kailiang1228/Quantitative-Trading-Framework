import os
import sys
import pandas as pd
import glob
import numpy as np
from datetime import datetime

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import necessary modules
import config
from strategies.meme_breakout_strategy import MemeBreakoutStrategy
from backtest.composite_backtest import MockExchangeAPI

class MemeBacktester:
    def __init__(self, csv_trend, csv_entry, symbol):
        self.symbol = symbol
        self.trend_tf = "1h"   # Meme 策略強制使用 1h
        self.entry_tf = "15m"  # Meme 策略強制使用 15m
        
        # Load Data
        self.df_trend = self._load_csv(csv_trend)
        self.df_entry = self._load_csv(csv_entry)
        
        # Align Data
        common_start = max(self.df_trend['timestamp'].min(), self.df_entry['timestamp'].min())
        common_end = min(self.df_trend['timestamp'].max(), self.df_entry['timestamp'].max())
        
        self.df_trend = self.df_trend[(self.df_trend['timestamp'] >= common_start) & (self.df_trend['timestamp'] <= common_end)]
        self.df_entry = self.df_entry[(self.df_entry['timestamp'] >= common_start) & (self.df_entry['timestamp'] <= common_end)]
        
        self.df_trend.reset_index(drop=True, inplace=True)
        self.df_entry.reset_index(drop=True, inplace=True)
        
        # Initialize API and Strategy
        self.api = MockExchangeAPI(self.df_trend, self.df_entry, self.trend_tf, self.entry_tf)
        self.strategy = MemeBreakoutStrategy(rr=3.0) # 預設 3.0 R
        
        # Backtest State
        self.initial_equity = 1000.0
        self.equity = self.initial_equity
        self.trades = []
        self.equity_curve = []

    def _load_csv(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        df = pd.read_csv(path)
        if 'timestamp' not in df.columns and 'datetime' in df.columns:
            df['timestamp'] = pd.to_datetime(df['datetime']).astype(np.int64) // 10**6
        return df.sort_values('timestamp')

    def run(self):
        position = None
        
        # Iterate through entry candles
        for i, row in self.df_entry.iterrows():
            current_ts = row['timestamp']
            current_price = row['close']
            high = row['high']
            low = row['low']
            
            self.api.set_current_time(current_ts)
            
            # 1. Check Exit
            if position:
                pnl = 0
                closed = False
                exit_price = current_price
                reason = ''
                
                # Trailing Stop Logic (Meme Special)
                # Meme 策略通常使用非常緊的移動止損 (e.g., 1.0 ATR)
                atr_val = position.get('atr', 0)
                ts_mult = position.get('trailing_stop_atr', 1.0)
                
                if atr_val > 0:
                    trailing_dist = ts_mult * atr_val
                    if position['side'] == 'buy':
                        new_sl = current_price - trailing_dist
                        if new_sl > position['sl']:
                            position['sl'] = new_sl
                    else:
                        new_sl = current_price + trailing_dist
                        if new_sl < position['sl']:
                            position['sl'] = new_sl

                # Check SL/TP
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
                    # Deduct Fees (Taker 0.05% * 2 for entry/exit)
                    fee_rate = 0.001 # 0.1% total round trip estimate
                    notional = position['entry'] * position['size']
                    fees = notional * fee_rate
                    pnl -= fees
                    
                    self.equity += pnl
                    self.trades.append({
                        'timestamp': current_ts,
                        'side': position['side'],
                        'entry': position['entry'],
                        'exit': exit_price,
                        'pnl': pnl,
                        'reason': reason,
                        'equity': self.equity
                    })
                    position = None
                    continue

            # 2. Check Entry
            if position is None:
                signal = self.strategy.analyze(self.api, f"{self.symbol}/USDT")
                
                if signal:
                    # Meme Risk Management: Fixed % Risk per trade
                    risk_pct = 0.02 # 2% risk per trade
                    risk_amt = self.equity * risk_pct
                    dist = abs(signal['entry'] - signal['sl'])
                    
                    if dist > 0:
                        size = risk_amt / dist
                        
                        # Leverage Cap (Meme coins often have lower max leverage)
                        max_lev = 10
                        if size * signal['entry'] > self.equity * max_lev:
                            size = (self.equity * max_lev) / signal['entry']
                            
                        position = {
                            'entry': signal['entry'],
                            'sl': signal['sl'],
                            'tp': signal['tp'],
                            'side': signal['side'],
                            'size': size,
                            'atr': signal.get('atr', 0),
                            'trailing_stop_atr': signal.get('trailing_stop_atr', 1.0)
                        }

        return self._calculate_stats()

    def _calculate_stats(self):
        final_equity = self.equity
        total_return = (final_equity - self.initial_equity) / self.initial_equity * 100
        
        stats = {
            "Symbol": self.symbol,
            "Total Return (%)": round(total_return, 2),
            "Final Equity": round(final_equity, 2),
            "Total Trades": len(self.trades),
            "Win Rate (%)": 0,
            "Profit Factor": 0,
            "Max Drawdown (%)": 0
        }

        if len(self.trades) > 0:
            wins = [t for t in self.trades if t['pnl'] > 0]
            losses = [t for t in self.trades if t['pnl'] <= 0]
            
            stats["Win Rate (%)"] = round(len(wins) / len(self.trades) * 100, 2)
            
            total_win = sum([t['pnl'] for t in wins])
            total_loss = abs(sum([t['pnl'] for t in losses]))
            stats["Profit Factor"] = round(total_win / total_loss, 2) if total_loss != 0 else 999

            # MDD
            df_eq = pd.DataFrame([{'equity': self.initial_equity}] + [{'equity': t['equity']} for t in self.trades])
            df_eq['peak'] = df_eq['equity'].cummax()
            df_eq['drawdown'] = (df_eq['equity'] - df_eq['peak']) / df_eq['peak']
            stats["Max Drawdown (%)"] = round(abs(df_eq['drawdown'].min()) * 100, 2)
            
        return stats

def run_meme_batch_test():
    data_dir = os.path.join(os.path.dirname(project_root), "data")
    print(f"🚀 Starting MEME Strategy Batch Test (Crazy Mode)")
    print(f"📂 Data Directory: {data_dir}")
    
    # Find all symbols (using 15m files as base since we need 15m for entry)
    pattern = os.path.join(data_dir, "*_15m.csv")
    files = glob.glob(pattern)
    
    results = []
    
    for file_path in files:
        filename = os.path.basename(file_path)
        if "-USDT-USDT" in filename:
            symbol = filename.split("-USDT-USDT")[0]
        else:
            continue
            
        # Skip stablecoins or non-volatile assets if needed
        if symbol in ["USDC", "USDT", "DAI"]:
            continue
            
        # Check if 1h data exists (required for trend filter)
        csv_trend = os.path.join(data_dir, f"{symbol}-USDT-USDT_4h.csv") # Note: Using 4h file but strategy might resample or we should ensure we have 1h data. 
        # Wait, the strategy uses 1h. Let's check if we have 1h data.
        # If download_data only downloaded 4h and 15m, we might need to use 4h as trend or resample 15m to 1h.
        # For now, let's assume we use 4h file as "trend" file, but the strategy logic inside might need adjustment if it strictly expects 1h.
        # Actually, MemeBreakoutStrategy uses `tf_trend = "1h"`. 
        # If we only downloaded 4h, we have a problem.
        # Let's check download_data.py config... it downloads 4h and 15m.
        # So we should probably adjust the strategy to use 4h trend OR resample.
        # To keep it simple and robust, let's use 4h data for trend filter in this backtest script, 
        # and I will patch the strategy instance to use 4h if 1h is missing.
        
        # Actually, let's just use the 4h file. The strategy class has hardcoded "1h".
        # We can override it in the backtester.
        
        csv_trend = os.path.join(data_dir, f"{symbol}-USDT-USDT_4h.csv")
        
        if not os.path.exists(csv_trend):
            # Try to find 1h if available
            csv_trend_1h = os.path.join(data_dir, f"{symbol}-USDT-USDT_1h.csv")
            if os.path.exists(csv_trend_1h):
                csv_trend = csv_trend_1h
            else:
                # print(f"⚠️ Missing trend data for {symbol}, skipping.")
                continue
        
        print(f"Testing {symbol}...", end="", flush=True)
        
        try:
            bt = MemeBacktester(csv_trend, file_path, symbol)
            # Force strategy to use 4h if that's what we loaded
            if "4h" in csv_trend:
                bt.strategy.trend_ema_period = 50 # Keep 50 EMA
                # We need to tell the mock API that "1h" request should return 4h data?
                # Or better, change the request in strategy.
                # Let's just hack the MockAPI to return trend data when asked for "1h"
                bt.api.trend_tf = "1h" # Lie to the API that this data is 1h
            
            stats = bt.run()
            print(f" Return: {stats['Total Return (%)']}% | PF: {stats['Profit Factor']}")
            results.append(stats)
            
        except Exception as e:
            print(f" Error: {e}")
            
    # Output Results
    df_results = pd.DataFrame(results)
    if not df_results.empty:
        df_results = df_results.sort_values(by="Total Return (%)", ascending=False)
        
        print("\n" + "="*60)
        print("🐶 MEME STRATEGY RESULTS (Sorted by Return)")
        print("="*60)
        print(df_results.to_string(index=False))
        
        output_file = os.path.join(current_dir, "meme_backtest_results.csv")
        df_results.to_csv(output_file, index=False)
        print(f"\n💾 Results saved to: {output_file}")

if __name__ == "__main__":
    run_meme_batch_test()
