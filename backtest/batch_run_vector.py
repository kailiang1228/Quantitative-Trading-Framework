import sys
import os
import pandas as pd

# 設定路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backtest.vector_backtest import VectorBacktester

def run_multi_coin_batch():
    # 1. 定義要測試的幣種
    coins = ["BTC", "ETH", "SOL"]
    
    # 2. 定義要測試的時間級別組合
    timeframe_pairs = [
        ("1d", "4h"),
        ("4h", "1h"),
        ("1h", "15m"),
        ("4h", "15m"),
        ("1h", "5m")
    ]

    data_dir = os.path.join(project_root, "data")
    results = []

    print(f"{'Coin':<6} | {'TF (Trend/Entry)':<15} | {'Return %':<10} | {'PF':<6} | {'Win Rate %':<10} | {'Trades':<6}")
    print("-" * 70)

    for coin in coins:
        for trend_tf, entry_tf in timeframe_pairs:
            # 建構檔案路徑 (注意檔名格式)
            # 假設檔名是 BTC-USDT-USDT_1h.csv
            csv_trend = os.path.join(data_dir, f"{coin}-USDT-USDT_{trend_tf}.csv")
            csv_entry = os.path.join(data_dir, f"{coin}-USDT-USDT_{entry_tf}.csv")

            if not os.path.exists(csv_trend) or not os.path.exists(csv_entry):
                continue

            try:
                # 使用向量化回測
                vbt = VectorBacktester(
                    csv_trend, 
                    csv_entry, 
                    trend_tf=trend_tf, 
                    entry_tf=entry_tf,
                    start_date="2024-01-01"
                )
                
                vbt.calculate_indicators()
                vbt.generate_signals()
                stats = vbt.run_backtest()
                
                res = {
                    "Coin": coin,
                    "Timeframe": f"{trend_tf}/{entry_tf}",
                    "Return": stats['total_return'],
                    "PF": stats['profit_factor'],
                    "WinRate": stats['win_rate'],
                    "Trades": stats['total_trades']
                }
                results.append(res)

                print(f"{coin:<6} | {trend_tf}/{entry_tf:<15} | {stats['total_return']:>9.2f}% | {stats['profit_factor']:>6.2f} | {stats['win_rate']:>9.2f}% | {stats['total_trades']:>6}")

            except Exception as e:
                print(f"❌ Error {coin} {trend_tf}/{entry_tf}: {e}")

    if results:
        df_res = pd.DataFrame(results)
        output_path = os.path.join(current_dir, "multi_coin_results.csv")
        df_res.to_csv(output_path, index=False)
        print(f"\n✅ Multi-coin test complete. Saved to {output_path}")

if __name__ == "__main__":
    run_multi_coin_batch()
