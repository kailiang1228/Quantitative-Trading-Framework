import pandas as pd
import os
import glob

DATA_DIR = "D:\Lesson_CODE\code\TRADING\Quant_V6_G\data"

def merge_funding_to_ohlcv():
    print("🔄 開始合併數據 (Funding Rate + Open Interest)...")
    
    # 1. 讀取所有 funding 檔案
    funding_files = glob.glob(os.path.join(DATA_DIR, "*_funding.csv"))
    
    for f_path in funding_files:
        symbol_prefix = os.path.basename(f_path).replace("_funding.csv", "")
        print(f"   處理幣種: {symbol_prefix}")
        
        # 讀取 funding rate
        df_funding = pd.read_csv(f_path)
        # 強制使用 int64 避免 Windows 下溢位成 int32 (造成負數時間戳)
        df_funding['timestamp'] = df_funding['timestamp'].astype('int64')
        df_funding = df_funding.sort_values('timestamp')
        
        # 讀取 Open Interest (如果有的話)
        oi_path = os.path.join(DATA_DIR, f"{symbol_prefix}_oi.csv")
        df_oi = None
        if os.path.exists(oi_path):
            print(f"     -> 發現持倉量數據 (OI)")
            df_oi = pd.read_csv(oi_path)
            df_oi['timestamp'] = df_oi['timestamp'].astype('int64')
            df_oi = df_oi.sort_values('timestamp')
        
        # 找出該幣種所有的 OHLCV 檔案
        ohlcv_files = glob.glob(os.path.join(DATA_DIR, f"{symbol_prefix}_*.csv"))
        
        for o_path in ohlcv_files:
            if "_funding" in o_path or "_oi" in o_path: continue
            
            print(f"     -> 合併至 {os.path.basename(o_path)} ...", end="")
            
            df_ohlcv = pd.read_csv(o_path)
            
            # 確保 timestamp 是 int64
            if 'timestamp' not in df_ohlcv.columns and 'datetime' in df_ohlcv.columns:
                 df_ohlcv['timestamp'] = pd.to_datetime(df_ohlcv['datetime']).astype('int64') // 10**6
            
            # 關鍵修正：使用 'int64'
            df_ohlcv['timestamp'] = df_ohlcv['timestamp'].astype('int64')
            
            # 1. 合併 Funding Rate (backward fill)
            df_merged = pd.merge_asof(
                df_ohlcv.sort_values('timestamp'),
                df_funding[['timestamp', 'fundingRate']].sort_values('timestamp'),
                on='timestamp',
                direction='backward'
            )
            
            # 2. 合併 Open Interest (backward fill)
            if df_oi is not None:
                # 選擇要合併的欄位
                oi_cols = ['timestamp', 'openInterestValue']
                if 'openInterestAmount' in df_oi.columns:
                    oi_cols.append('openInterestAmount')
                    
                df_merged = pd.merge_asof(
                    df_merged.sort_values('timestamp'),
                    df_oi[oi_cols].sort_values('timestamp'),
                    on='timestamp',
                    direction='backward'
                )
            
            # 儲存
            df_merged.to_csv(o_path, index=False)
            print(" 完成!")

    print("\n✅ 合併完成！現在您的 K 線檔案中包含 'fundingRate' 與 'openInterestValue' 欄位了。")

if __name__ == "__main__":
    merge_funding_to_ohlcv()
