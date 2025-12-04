
import ccxt
import pandas as pd
import time
import os
from datetime import datetime, timedelta

# 引入 ExchangeAPI 以使用其篩選邏輯
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from exchange_api import ExchangeAPI

# ==========================================
# 設定區
# ==========================================
# 是否自動抓取前 N 大成交量幣種
AUTO_TOP_N = False
TOP_N_LIMIT = 20

# 手動指定清單 (如果 AUTO_TOP_N = False，則只下載這些)
MANUAL_SYMBOLS = [
    # "BTC/USDT:USDT",
    # "ETH/USDT:USDT",
    # "SOL/USDT:USDT",
    "DOGE/USDT:USDT",
    "XRP/USDT:USDT",
    "BNB/USDT:USDT",
    "AVAX/USDT:USDT",
    "LINK/USDT:USDT",
    "ADA/USDT:USDT",
    "TRX/USDT:USDT",
    "XLM/USDT:USDT",
    "CRO/USDT:USDT",
    "LTC/USDT:USDT",
    "INJ/USDT:USDT",
    "NEO/USDT:USDT",
    # "CRV/USDT:USDT",
    # "SUSHI/USDT:USDT",
    # "ID/USDT:USDT",
    # "THETA/USDT:USDT",
]

# 黑名單 (即使在前 20 名也不下載)
BLACKLIST = [
    "USDC/USDT:USDT",
    "BUSD/USDT:USDT",
    "DAI/USDT:USDT",
    "LUNA/USDT:USDT", # 舉例
]

# 設定不同時框的起始年份
# 格式: "時框": 起始年份
TIMEFRAME_CONFIG = {
    "1d": 2022,
    "4h": 2022,
    "1h": 2022,
    "15m": 2022,
    "5m": 2022
}

# 存檔目錄
DATA_DIR = "data"

# ==========================================

def get_symbols():
    if not AUTO_TOP_N:
        return MANUAL_SYMBOLS
    
    print(f"🔍 正在從 OKX 獲取成交量前 {TOP_N_LIMIT} 大幣種...")
    try:
        api = ExchangeAPI()
        top_symbols = api.get_top_volume_symbols(limit=TOP_N_LIMIT)
        
        # 過濾黑名單
        final_symbols = [s for s in top_symbols if s not in BLACKLIST]
        
        # 確保手動清單裡的重要幣種也在裡面 (Optional)
        for s in MANUAL_SYMBOLS[:3]: # 確保 BTC, ETH, SOL 在裡面
            if s not in final_symbols:
                final_symbols.append(s)
        
        print(f"✅ 最終下載清單 ({len(final_symbols)}): {final_symbols}")
        return final_symbols
    except Exception as e:
        print(f"❌ 獲取失敗，使用預設清單: {e}")
        return MANUAL_SYMBOLS

def get_start_timestamp(year):
    """回傳指定年份 1月1日 的毫秒時間戳"""
    dt = datetime(year, 1, 1)
    return int(dt.timestamp() * 1000)

def download_funding_rates(exchange, symbol, start_ts, end_ts):
    """下載資金費率歷史"""
    print(f"   💰 下載資金費率 (Funding Rate)...", end="", flush=True)
    all_funding = []
    since = start_ts
    
    while True:
        try:
            # OKX funding rate history usually returns 100 items
            funding_rates = exchange.fetch_funding_rate_history(symbol, since=since, limit=100)
            
            if not funding_rates:
                break
                
            all_funding.extend(funding_rates)
            
            last_ts = funding_rates[-1]['timestamp']
            since = last_ts + 1
            
            if last_ts >= end_ts:
                break
                
            time.sleep(0.05)
            
            if len(funding_rates) < 100:
                break
                
        except Exception as e:
            print(f" [Error: {e}]", end="")
            time.sleep(2)
            continue
            
    if all_funding:
        df = pd.DataFrame(all_funding)
        # Keep relevant columns: timestamp, fundingRate, datetime
        # Some exchanges return 'info' which is a dict, we don't need it
        if 'info' in df.columns:
            del df['info']
            
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.drop_duplicates(subset=['timestamp'])
        return df
    return pd.DataFrame()

def download_open_interest(exchange, symbol, start_ts, end_ts):
    """
    下載持倉量 (Open Interest)
    注意: OKX 公開 API 通常只提供最近 3 個月 (或更短) 的 OI 歷史數據。
    如果請求的時間範圍太早，會回傳 'Illegal time range'。
    因此這裡預設只抓取最近 90 天。
    """
    print(f"   📊 下載持倉量 (Open Interest)...", end="", flush=True)
    
    # 自動調整起始時間為最近 90 天 (約 3 個月)
    # 避免 'Illegal time range' 錯誤
    three_months_ms = 90 * 24 * 60 * 60 * 1000
    adjusted_start = max(start_ts, end_ts - three_months_ms)
    
    if adjusted_start > start_ts:
        print(f" (調整為最近 3 個月以符合 API 限制)", end="")
        
    all_oi = []
    since = adjusted_start
    
    retry_count = 0
    
    while True:
        try:
            # OKX OI history
            oi_data = exchange.fetch_open_interest_history(symbol, since=since, limit=100)
            
            if not oi_data:
                break
                
            all_oi.extend(oi_data)
            
            last_ts = oi_data[-1]['timestamp']
            since = last_ts + 1
            
            if last_ts >= end_ts:
                break
                
            time.sleep(0.05)
            
            if len(oi_data) < 100:
                break
            
            retry_count = 0 # 重置重試計數
                
        except Exception as e:
            error_msg = str(e)
            if "Illegal time range" in error_msg:
                print(f" [API 限制: 時間範圍無效，停止下載]", end="")
                break
            
            print(f" [Error: {e}]", end="")
            retry_count += 1
            if retry_count > 3:
                print(" [多次失敗，跳過]", end="")
                break
            time.sleep(2)
            continue
            
    if all_oi:
        df = pd.DataFrame(all_oi)
        # Keep relevant columns
        cols_to_keep = ['timestamp', 'openInterestValue', 'datetime']
        # Some versions might have openInterestAmount
        if 'openInterestAmount' in df.columns:
            cols_to_keep.append('openInterestAmount')
            
        df = df[cols_to_keep]
        df = df.drop_duplicates(subset=['timestamp'])
        return df
    return pd.DataFrame()

def download_all():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    print("正在初始化 OKX 連線...")
    exchange = ccxt.okx({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    
    now = exchange.milliseconds()
    
    print(f"準備下載數據...")
    print(f"包含 K 線、資金費率 (Funding Rate) 與 持倉量 (Open Interest)")

    target_symbols = get_symbols()

    for symbol in target_symbols:
        print(f"📊 正在處理 {symbol} ...")
        safe_symbol_name = symbol.replace('/', '-').replace(':', '-')
        
        # 1. 下載 K 線數據
        for tf, start_year in TIMEFRAME_CONFIG.items():
            start_ts = get_start_timestamp(start_year)
            print(f"   📥 下載 {tf} K線 (從 {start_year}年)...", end="", flush=True)
            
            all_ohlcv = []
            since = start_ts
            count = 0
            
            while True:
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=100)
                    
                    # 如果抓不到數據 (可能是該幣種當時還沒發行)
                    if not ohlcv:
                        # 如果已經超過現在時間，就結束
                        if since > now:
                            break
                        
                        # 如果還沒超過現在，可能是還沒發行，往後跳 1 個月試試看
                        # print(f" [跳過空窗] ", end="", flush=True)
                        since += 30 * 24 * 60 * 60 * 1000 # +30 days
                        time.sleep(0.1)
                        continue

                    all_ohlcv.extend(ohlcv)
                    last_ts = ohlcv[-1][0]
                    since = last_ts + 1
                    if last_ts >= now: break
                    
                    count += 1
                    if count % 10 == 0: print(".", end="", flush=True)
                    time.sleep(0.05)
                    # if len(ohlcv) < 100: break # 移除這行，因為有時候中間會有缺漏，不代表結束
                except Exception as e:
                    print(f"x", end="")
                    time.sleep(1)
                    continue
            
            if all_ohlcv:
                df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df = df.drop_duplicates(subset=['timestamp'])
                
                filename = f"{safe_symbol_name}_{tf}.csv"
                filepath = os.path.join(DATA_DIR, filename)
                df.to_csv(filepath, index=False)
                print(f" 完成! ({len(df)} 筆)")
            else:
                print(" 無數據")

        # 2. 下載資金費率 & 持倉量 (統一從最早的年份開始)
        min_year = min(TIMEFRAME_CONFIG.values())
        start_ts_funding = get_start_timestamp(min_year)
        
        # Funding Rate
        df_funding = download_funding_rates(exchange, symbol, start_ts_funding, now)
        if not df_funding.empty:
            filename = f"{safe_symbol_name}_funding.csv"
            filepath = os.path.join(DATA_DIR, filename)
            df_funding.to_csv(filepath, index=False)
            print(f"   💰 資金費率下載完成! ({len(df_funding)} 筆) -> {filename}")
        else:
            print("   ⚠️ 無資金費率數據")

        # Open Interest
        df_oi = download_open_interest(exchange, symbol, start_ts_funding, now)
        if not df_oi.empty:
            filename = f"{safe_symbol_name}_oi.csv"
            filepath = os.path.join(DATA_DIR, filename)
            df_oi.to_csv(filepath, index=False)
            print(f"   📊 持倉量下載完成! ({len(df_oi)} 筆) -> {filename}")
        else:
            print("   ⚠️ 無持倉量數據")
        
        print("-" * 40)

    print("\n✅ 所有下載任務完成！")
    print(f"檔案已儲存於 {os.path.abspath(DATA_DIR)}")

if __name__ == "__main__":
    download_all()
