import json
import os
import time
from utils.logger_util import log

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "positions_db.json")

def load_positions():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        log(f"讀取倉位資料庫失敗: {e}")
        return {}

def save_positions(positions):
    try:
        # Convert positions dict to serializable format if needed
        # Assuming positions dict is already JSON serializable
        with open(DB_FILE, "w") as f:
            json.dump(positions, f, indent=4)
    except Exception as e:
        log(f"儲存倉位資料庫失敗: {e}")

def update_position_entry_time(symbol, entry_time):
    positions = load_positions()
    if symbol not in positions:
        positions[symbol] = {}
    positions[symbol]["entry_time"] = entry_time
    save_positions(positions)

def get_position_entry_time(symbol):
    positions = load_positions()
    return positions.get(symbol, {}).get("entry_time")

def remove_position(symbol):
    positions = load_positions()
    if symbol in positions:
        del positions[symbol]
        save_positions(positions)
