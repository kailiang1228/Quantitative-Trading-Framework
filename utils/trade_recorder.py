# utils/trade_recorder.py
import os
import csv
from datetime import datetime

# 使用絕對路徑，確保 csv 永遠寫在程式所在的 logs 資料夾下
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(TRADES_DIR, exist_ok=True)

TRADES_PATH = os.path.join(TRADES_DIR, "trades.csv")

HEADERS = [
    "datetime",
    "timestamp",
    "symbol",
    "side",
    "strategy",
    "entry_price",
    "exit_price",
    "qty",
    "pnl_usdt",
    "pnl_pct",
    "rr",
    "duration_sec",
    "equity_before",
    "equity_after",
    "sl",
    "tp",
    "leverage",
]


def _ensure_header():
    if not os.path.exists(TRADES_PATH):
        with open(TRADES_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)


def record_trade(
    *,
    timestamp: float,
    symbol: str,
    side: str,
    entry: float,
    exit: float,
    qty: float,
    pnl: float,
    pnl_pct: float,
    rr: float,
    strategy: str,
    duration_sec: float,
    equity_before: float,
    equity_after: float,
    sl: float,
    tp: float,
    leverage: float,
):
    """
    將每筆平倉寫入 trades.csv
    """
    _ensure_header()
    dt = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    row = [
        dt,
        f"{timestamp:.3f}",
        symbol,
        side,
        f"{strategy}",
        f"{entry:.4f}",
        f"{exit:.4f}",
        f"{qty:.6f}",
        f"{pnl:.4f}",
        f"{pnl_pct:.4f}",
        f"{rr:.4f}",
        f"{duration_sec:.1f}",
        f"{equity_before:.4f}",
        f"{equity_after:.4f}",
        f"{sl:.4f}",
        f"{tp:.4f}",
        f"{leverage:.2f}",
    ]

    try:
        with open(TRADES_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)
    except Exception:
        # 寫檔失敗就忽略，不要炸掉 bot
        pass
