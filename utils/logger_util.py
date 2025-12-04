# utils/logger_util.py
# =========================
# 功能：
# 1. 統一 Log 格式（含 timestamp）
# 2. 將所有 log 寫入 logs/bot.log
# 3. Telegram 通知（依 config 控制）
# =========================

import logging
import sys
import requests
from datetime import datetime

from utils.file_logger import write_log_to_file

from config import (
    TG_BOT_TOKEN,
    TG_CHAT_ID,
    ENABLE_TG_NOTIFICATIONS,
    NOTIFY_ORDER_PLACED,
    NOTIFY_ORDER_FILLED,
    NOTIFY_ORDER_CANCELED,
    NOTIFY_POSITION_CLOSED,
    NOTIFY_ERRORS,
    NOTIFY_HEARTBEAT,
    LOG_LEVEL,
)

# =========================
# 基本 logger 設定
# =========================

def setup_logger():
    logger = logging.getLogger("QuantBot")
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # 避免加到重複 handler
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

logger = setup_logger()

# =========================
#  統一 Log 出口
# =========================

def log(msg):
    text = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [LOG] {msg}"
    print(text)
    write_log_to_file(text)

def log_error(msg):
    text = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] {msg}"
    print(text)
    write_log_to_file(text)

# =========================
# Telegram 發送底層
# =========================

def send_telegram_message(text: str, message_type: str = "info") -> bool:
    if not ENABLE_TG_NOTIFICATIONS:
        return False

    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return False

    # 判斷是否要送
    if message_type == "order_placed" and not NOTIFY_ORDER_PLACED:
        return True
    if message_type == "order_filled" and not NOTIFY_ORDER_FILLED:
        return True
    if message_type == "order_canceled" and not NOTIFY_ORDER_CANCELED:
        return True
    if message_type == "position_closed" and not NOTIFY_POSITION_CLOSED:
        return True
    if message_type == "error" and not NOTIFY_ERRORS:
        return True
    if message_type == "heartbeat" and not NOTIFY_HEARTBEAT:
        return True

    emoji_map = {
        "order_placed": "🟡",
        "order_filled": "🟢",
        "order_canceled": "🔴",
        "position_closed": "🔵",
        "error": "🚨",
        "heartbeat": "💓",
        "info": "ℹ️",
        "position_report": "📊",
    }
    emoji = emoji_map.get(message_type, "ℹ️")

    payload = {
        "chat_id": TG_CHAT_ID,
        "text": f"{emoji} {text}",
        "parse_mode": "HTML",
    }

    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            data=payload,
            timeout=10,
        )
        if res.status_code != 200:
            logger.error(f"Telegram 發送失敗: {res.text}")
            return False
        return True

    except Exception as e:
        logger.error(f"Telegram 連線失敗: {e}")
        return False

# =========================
# 上層通知封裝
# =========================

def notify_order_placed(symbol, side, qty, price, sl, tp, strategy):
    msg = f"""
<b>📈 新訂單已提交</b>

🏷️ <b>標的:</b> {symbol}
🎯 <b>方向:</b> {side.upper()}
📊 <b>數量:</b> {qty:.6f}
💰 <b>價格:</b> {price:.2f}
🛡️ <b>止損:</b> {sl:.2f}
🎯 <b>止盈:</b> {tp:.2f}
🤖 <b>策略:</b> {strategy}
⏰ <b>時間:</b> {datetime.now().strftime('%H:%M:%S')}
"""
    send_telegram_message(msg, "order_placed")
    log(f"下單: {symbol} {side} {qty:.6f} @ {price:.2f}")


def notify_order_filled(symbol, side, qty, price, pnl=0.0):
    pnl_text = f"📈 盈虧: {pnl:.2f}" if pnl != 0 else ""
    msg = f"""
<b>✅ 訂單已成交</b>

🏷️ <b>標的:</b> {symbol}
🎯 <b>方向:</b> {side.upper()}
📊 <b>數量:</b> {qty:.6f}
💰 <b>成交價:</b> {price:.2f}
{pnl_text}
⏰ <b>時間:</b> {datetime.now().strftime('%H:%M:%S')}
"""
    send_telegram_message(msg, "order_filled")
    log(f"成交: {symbol} {side} {qty:.6f} @ {price:.2f}")


def notify_position_closed(symbol, side, qty, entry_price, exit_price, pnl, duration):
    pnl_emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"

    msg = f"""
<b>🎯 倉位已平倉</b>

🏷️ <b>標的:</b> {symbol}
🎯 <b>方向:</b> {side.upper()}
📊 <b>數量:</b> {qty:.6f}
💰 <b>入場:</b> {entry_price:.2f}
💰 <b>出場:</b> {exit_price:.2f}
{pnl_emoji} <b>盈虧:</b> {pnl:.2f}
⏳ <b>持倉時間:</b> {duration}
⏰ <b>時間:</b> {datetime.now().strftime('%H:%M:%S')}
"""
    send_telegram_message(msg, "position_closed")
    log(f"平倉: {symbol} PnL={pnl:.2f}")


def notify_error(error_msg, context=""):
    msg = f"""
<b>🚨 系統錯誤</b>

📝 <b>錯誤:</b> {error_msg}
🔧 <b>Context:</b> {context}
⏰ <b>時間:</b> {datetime.now().strftime('%H:%M:%S')}
"""
    send_telegram_message(msg, "error")
    log_error(f"{error_msg} | {context}")


def notify_position_report(positions, total_equity, total_pnl, open_orders=0):
    if not positions:
        msg = f"""
<b>📊 倉位報告 - 無持倉</b>

💰 <b>總權益:</b> {total_equity:.2f}
📈 <b>浮動盈虧:</b> {total_pnl:.2f}
🔄 <b>掛單數:</b> {open_orders}
⏰ <b>時間:</b> {datetime.now().strftime('%H:%M:%S')}
"""
    else:
        parts = []
        for symbol, pos in positions.items():
            pnl = pos.get("unrealized_pnl", 0.0)
            emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
            parts.append(
                f"""🏷️ <b>{symbol}</b>
   📊 數量: {pos.get('size', 0):.6f}
   💰 入場: {pos.get('entry_price', 0):.2f}
   💰 現價: {pos.get('current_price', 0):.2f}
   {emoji} 浮盈虧: {pnl:.2f}
"""
            )

        body = "\n".join(parts)
        msg = f"""
<b>📊 倉位報告</b>

{body}
💰 <b>總權益:</b> {total_equity:.2f}
📈 <b>浮動盈虧:</b> {total_pnl:.2f}
🔄 <b>掛單數:</b> {open_orders}
⏰ <b>時間:</b> {datetime.now().strftime('%H:%M:%S')}
"""

    send_telegram_message(msg, "position_report")
    log("倉位報告已發送")


def notify_heartbeat(bot_status, uptime, total_trades, win_rate):
    msg = f"""
<b>💓 系統心跳</b>

🟢 <b>狀態:</b> {bot_status}
⏰ <b>運行時間:</b> {uptime}
📊 <b>累積交易數:</b> {total_trades}
📈 <b>勝率:</b> {win_rate:.1f}%
🕒 <b>時間:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    send_telegram_message(msg, "heartbeat")
    log("心跳已發送")
