import sys
import os
import pandas as pd
# from tabulate import tabulate  # 如果沒有安裝 tabulate，我會用簡單的 print 格式

# 設定路徑以便 import
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backtest.simple_backtest import Backtester
from strategies.multi_timeframe_trend import MultiTimeframeTrendStrategy
from strategies.breakout_trend import BreakoutTrendStrategy
from strategies.bollinger_reversion import BollingerReversionStrategy

def run_batch():
    # 1. 定義要測試的策略
    strategies = [
        ("MultiTF_Trend", MultiTimeframeTrendStrategy),
        ("Breakout", BreakoutTrendStrategy),
        ("Bollinger_Rev", BollingerReversionStrategy)
    ]

    # 2. 定義要測試的時間級別組合 (Trend, Entry)
    timeframe_pairs = [
        ("1d", "4h"),
        ("4h", "1h"),
        ("1d", "1h"),
        ("1h", "15m"),
        ("4h", "15m"),
        ("1h", "5m"),
        ("15m", "5m")
    ]

    # 設定資料目錄
    data_dir = os.path.join(project_root, "data")
    
    results = []

    print(f"{'Strategy':<15} | {'TF (Trend/Entry)':<15} | {'Return %':<10} | {'PF':<6} | {'Win Rate %':<10} | {'Trades':<6} | {'Max DD %':<10}")
    print("-" * 90)

    for strat_name, strat_class in strategies:
        for trend_tf, entry_tf in timeframe_pairs:
            
            # 建構檔案路徑
            csv_trend = os.path.join(data_dir, f"BTC-USDT-USDT_{trend_tf}.csv")
            csv_entry = os.path.join(data_dir, f"BTC-USDT-USDT_{entry_tf}.csv")

            # 檢查檔案是否存在
            if not os.path.exists(csv_trend) or not os.path.exists(csv_entry):
                # print(f"⚠️  Missing data for {trend_tf}/{entry_tf}, skipping...")
                continue

            try:
                # 初始化回測 (不畫圖 plot=False)
                # 這裡我們使用 2023-01-01 到 2023-12-31 作為樣本外測試 (或者用全區間)
                # 用戶說 "跑..." 沒指定區間，我們先跑 2023 全年當作驗證，或者跑最近一年
                # 為了快速得到結果，我們先跑 2024-01-01 至今
                
                bt = Backtester(
                    csv_trend, 
                    csv_entry, 
                    trend_tf=trend_tf, 
                    entry_tf=entry_tf,
                    start_date="2024-01-01", # 預設跑今年
                    end_date=None,
                    strategy_class=strat_class
                )
                
                stats = bt.run(plot=False)
                
                # 收集結果
                res = {
                    "Strategy": strat_name,
                    "Timeframe": f"{trend_tf}/{entry_tf}",
                    "Return": stats['total_return'],
                    "PF": stats['profit_factor'],
                    "WinRate": stats['win_rate'],
                    "Trades": stats['total_trades'],
                    "MaxDD": stats['max_dd'] * 100
                }
                results.append(res)

                # 即時印出
                print(f"{strat_name:<15} | {trend_tf}/{entry_tf:<15} | {stats['total_return']:>9.2f}% | {stats['profit_factor']:>6.2f} | {stats['win_rate']:>9.2f}% | {stats['total_trades']:>6} | {stats['max_dd']*100:>9.2f}%")

            except Exception as e:
                print(f"❌ Error running {strat_name} on {trend_tf}/{entry_tf}: {e}")

    # 最終可以存成 CSV
    if results:
        df_res = pd.DataFrame(results)
        output_path = os.path.join(current_dir, "batch_results.csv")
        df_res.to_csv(output_path, index=False)
        print(f"\n✅ Batch test complete. Results saved to {output_path}")
    else:
        print("\n❌ No results generated. Check data files.")

if __name__ == "__main__":
    run_batch()
