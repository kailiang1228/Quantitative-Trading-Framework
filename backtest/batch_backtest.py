import os
import sys
import pandas as pd
import glob
from datetime import datetime

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backtest.composite_backtest import CompositeBacktester
import config

def run_batch_backtest():
    # Setup
    data_dir = os.path.join(os.path.dirname(project_root), "data")
    trend_tf = "1h"   # 改為 1h 趨勢 (更靈敏，適合高頻)
    entry_tf = "15m"
    start_date = "2023-01-01"
    end_date = "2024-12-31"
    
    print(f"🚀 Starting Batch Backtest")
    print(f"📅 Period: {start_date} to {end_date}")
    print(f"📂 Data Directory: {data_dir}")
    
    # Find all symbols based on 4h files
    pattern = os.path.join(data_dir, f"*_{trend_tf}.csv")
    files = glob.glob(pattern)
    
    results = []
    
    for file_path in files:
        filename = os.path.basename(file_path)
        # Extract symbol (assuming format SYMBOL-USDT-USDT_4h.csv)
        if "-USDT-USDT" in filename:
            symbol = filename.split("-USDT-USDT")[0]
        else:
            continue
            
        print(f"\nTesting {symbol}...")
        
        # Construct paths
        csv_trend = os.path.join(data_dir, f"{symbol}-USDT-USDT_{trend_tf}.csv")
        csv_entry = os.path.join(data_dir, f"{symbol}-USDT-USDT_{entry_tf}.csv")
        
        if not os.path.exists(csv_entry):
            print(f"⚠️ Missing entry data for {symbol}, skipping.")
            continue
            
        try:
            # Set global symbol for strategy logic if needed
            # (CompositeBacktester sets config.TIMEFRAMES but maybe not SYMBOL in config)
            # We can patch the global SYMBOL in composite_backtest if it uses it
            import backtest.composite_backtest as cb
            cb.SYMBOL = symbol
            
            bt = CompositeBacktester(
                csv_trend, 
                csv_entry, 
                trend_tf=trend_tf, 
                entry_tf=entry_tf,
                start_date=start_date,
                end_date=end_date,
                initial_equity=1000.0
            )
            
            # Run without plotting to save time/resources
            stats = bt.run(plot=False)
            
            results.append({
                "Symbol": symbol,
                "Total Return (%)": round(stats['total_return'], 2),
                "Profit Factor": round(stats['profit_factor'], 2),
                "Win Rate (%)": round(stats['win_rate'], 2),
                "Max Drawdown (%)": round(stats['max_dd'] * 100, 2),
                "Total Trades": stats['total_trades'],
                "Final Equity": round(stats['final_equity'], 2),
                "Sharpe Ratio": round(stats['sharpe_ratio'], 2)
            })
            
        except Exception as e:
            print(f"❌ Error testing {symbol}: {e}")
            
    # Create DataFrame and Sort
    df_results = pd.DataFrame(results)
    if not df_results.empty:
        df_results = df_results.sort_values(by="Profit Factor", ascending=False)
        
        print("\n" + "="*60)
        print("🏆 BATCH BACKTEST RESULTS (Sorted by Profit Factor)")
        print("="*60)
        print(df_results.to_string(index=False))
        
        # Save to CSV
        output_file = os.path.join(current_dir, "batch_backtest_results.csv")
        df_results.to_csv(output_file, index=False)
        print(f"\n💾 Results saved to: {output_file}")
        
        # Recommendation
        print("\n💡 RECOMMENDATIONS (White List):")
        good_symbols = df_results[df_results["Profit Factor"] > 1.3]["Symbol"].tolist()
        print(f"✅ Strong Buy (PF > 1.3): {', '.join(good_symbols)}")
        
        watch_symbols = df_results[(df_results["Profit Factor"] >= 1.1) & (df_results["Profit Factor"] <= 1.3)]["Symbol"].tolist()
        print(f"👀 Watch List (1.1 <= PF <= 1.3): {', '.join(watch_symbols)}")
        
        avoid_symbols = df_results[df_results["Profit Factor"] < 1.1]["Symbol"].tolist()
        print(f"❌ Avoid (PF < 1.1): {', '.join(avoid_symbols)}")
        
    else:
        print("No results generated.")

if __name__ == "__main__":
    run_batch_backtest()
