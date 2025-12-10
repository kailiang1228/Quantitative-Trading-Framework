# ============================================================
# position_manager.py (強化版)
#
# 功能：
#   - 從交易所同步持倉（加入 ghost position 抗干擾）
#   - 偵測「倉位被平」並發送通知
#   - 生成倉位報表給 QuantBot
#   - 避免 ghost/錯誤資料造成重複開倉
#   - 提供 can_open_position / mark_position_opened
#
# 核心精神：
#   ✨ "交易所是真相，本地只是 cache（要保護但不能相信100%）"
# ============================================================

import time
from datetime import datetime
from utils.logger_util import log, notify_position_closed
from utils.trade_recorder import record_trade
from config import POSITION_REPORT_INTERVAL
from core.persistence import save_positions, load_positions, remove_position # [新增] 持久化模組

class PositionManager:
    """
    管理所有倉位資訊，核心功能：
        1. 每次 sync 依交易所結果更新本地 positions
        2. 偵測「剛剛被平倉」的 symbol → Telegram 通知
        3. 本地 positions ≠ pending orders → 修正
        4. 可問：某 symbol 是否能再開倉
        5. 提供倉位狀態給報表
    """

    def __init__(self):
        # 結構：
        # {
        #   "BTC/USDT:USDT": {
        #       "size": 0.012,
        #       "entry_price": 90000,
        #       "current_price": 91000,
        #       "side": "long",
        #       "unrealized_pnl": 12.5,
        #       "leverage": 5,
        #       "entry_time": 1710000000
        #   },
        #   ...
        # }
        self.positions = {}
        
        # [新增] 嘗試從 DB 載入上次的倉位狀態 (主要是為了 entry_time)
        saved_positions = load_positions()
        if saved_positions:
            self.positions = saved_positions
            log(f"📥 已從資料庫恢復 {len(self.positions)} 筆倉位狀態")

        self.position_history = []
        self.last_position_report = 0

        # 修正 ghost position 用
        self._last_sync_positions_raw = []
        self._ghost_protect_buffer = {}   # symbol → last valid pos
        self._ghost_warning_count = 0     # [新增] 連續空值計數器

        # 這兩個是 v1.1 新增，用來防止重複下單
        self.symbol_has_open_pos = set()     # 有倉位的 symbol
        self.symbol_has_pending = set()      # 有 pending order / OCO 的 symbol

        # 權益需要你在外面更新後塞進來
        self.last_equity = None

    # ------------------------------------------------------------
    # 核心：同步交易所倉位
    # ------------------------------------------------------------
    def sync_from_exchange(self, api):
        try:
            raw_positions = api.fetch_positions()

            # 防止 ghost：如果本次 raw 空，但上一輪不是空 → 視為 API glitch
            # 修改邏輯：連續 3 次都回傳空值，才認定是真的平倉了
            if raw_positions == [] and self._last_sync_positions_raw != []:
                self._ghost_warning_count += 1
                if self._ghost_warning_count < 3:
                    log(f"⚠️ API 倉位回傳空值（疑似 ghost），忽略這次同步 ({self._ghost_warning_count}/3)")
                    return
                else:
                    log("ℹ️ 連續 3 次回傳空值，確認倉位已清空")
            else:
                # 如果有資料，或者本來就沒資料，重置計數器
                self._ghost_warning_count = 0

            self._last_sync_positions_raw = raw_positions

            current_positions = {}

            for pos in raw_positions:
                symbol = pos.get("symbol")
                size = self._parse_position_size(pos)

                if symbol is None or size == 0:
                    continue

                entry_price = float(pos.get("entryPrice", 0))
                cur_price = float(
                    pos.get("markPrice")
                    or pos.get("lastPrice")
                    or entry_price
                )
                side = "long" if size > 0 else "short"
                unreal = float(pos.get("unrealizedPnl", 0))
                lev = float(pos.get("leverage", 1))

                # 保留 entry_time（若本地已有）
                # [修正] 優先使用 DB/Memory 中的 entry_time，否則使用 API 的 ctime (若有)，最後才用 now
                # OKX API position 包含 cTime (creation time in ms)
                api_ctime = float(pos.get("cTime", 0)) / 1000.0
                
                existing_entry_time = self.positions.get(symbol, {}).get("entry_time")
                
                if existing_entry_time:
                    entry_time = existing_entry_time
                elif api_ctime > 0:
                    entry_time = api_ctime
                else:
                    entry_time = time.time()
                
                # [修正] 優先使用 API 回傳的 side，否則才用 size 正負判斷
                # ExchangeAPI.fetch_positions 已經處理好 side ("long"/"short")
                api_side = pos.get("side")
                if api_side in ["long", "short"]:
                    side = api_side
                else:
                    side = "long" if size > 0 else "short"

                contract_size = float(pos.get("contractSize", 1.0))

                current_positions[symbol] = {
                    "size": size,
                    "contract_size": contract_size,
                    "entry_price": entry_price,
                    "current_price": cur_price,
                    "side": side,
                    "unrealized_pnl": unreal,
                    "leverage": lev,
                    "entry_time": entry_time,
                }

                # ghost 保護：更新最新有效資料
                self._ghost_protect_buffer[symbol] = current_positions[symbol]

            # 2. 偵測平倉
            self.sync_positions(current_positions)

            # 3. 更新緩存
            self.positions = current_positions
            
            # [新增] 將最新狀態寫入 DB
            save_positions(self.positions)

            log(f"📊 倉位同步完成：{len(self.positions)} 筆倉位")

        except Exception as e:
            log(f"⚠️ 倉位同步錯誤: {e}")

    # 這個在外面同步 OKX 倉位後呼叫，把最新 positions 傳進來
    def sync_positions(self, new_positions: dict):
        """
        new_positions: {symbol: {...}}
        """
        # 先找出哪些倉位被關閉
        closed = []

        for symbol, old_pos in self.positions.items():
            if symbol not in new_positions:
                closed.append((symbol, old_pos))

        # 更新目前持倉
        self.positions = new_positions

        # 更新 symbol_has_open_pos
        self.symbol_has_open_pos = set(new_positions.keys())

        # 通知所有被關閉的倉位
        for symbol, pos_info in closed:
            self._notify_position_closed(symbol, pos_info)

    # ------------------------------------------------------------
    # 平倉通知 + 寫 trade log（v1.1）
    # ------------------------------------------------------------
    def _notify_position_closed(self, symbol, pos):
        try:
            entry = float(pos.get("entry_price", 0) or 0)
            size = abs(float(pos.get("size", 0) or 0))
            contract_size = float(pos.get("contract_size", 1.0))
            side = pos.get("side", "unknown")
            entry_time = float(pos.get("entry_time", time.time()))
            strategy = pos.get("strategy", "unknown")
            sl = float(pos.get("sl", 0) or 0)
            tp = float(pos.get("tp", 0) or 0)
            leverage = float(pos.get("leverage", 0) or 0)

            # 盡量使用 current_price 當出場價，沒有就用 close_price
            exit_price = float(
                pos.get("close_price", pos.get("current_price", entry)) or entry
            )

            # 損益 (需乘上 contract_size)
            if side == "long":
                pnl = (exit_price - entry) * size * contract_size
            else:
                pnl = (entry - exit_price) * size * contract_size

            # 損益百分比（以 entry 價計）
            pnl_pct = (exit_price - entry) / entry * (1 if side == "long" else -1)

            # 持倉時間
            duration = time.time() - entry_time
            h = int(duration // 3600)
            m = int((duration % 3600) // 60)
            duration_str = f"{h}h {m}m"

            # 發 Telegram + log
            notify_position_closed(
                symbol=symbol,
                side=side,
                qty=size,
                entry_price=entry,
                exit_price=exit_price,
                pnl=pnl,
                duration=duration_str,
            )

            self.position_history.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "size": size,
                    "entry_price": entry,
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "entry_time": entry_time,
                    "exit_time": time.time(),
                    "duration": duration_str,
                    "strategy": strategy,
                    "sl": sl,
                    "tp": tp,
                    "leverage": leverage,
                }
            )

            # --------- v1.1：寫入 trades.csv ---------
            equity_before = pos.get("equity_before")
            if equity_before is None:
                equity_before = self.last_equity or 0
            
            equity_after = equity_before + pnl
            self.last_equity = equity_after

            record_trade(
                timestamp=time.time(),
                symbol=symbol,
                side=side,
                entry=entry,
                exit=exit_price,
                qty=size,
                pnl=pnl,
                pnl_pct=pnl_pct,
                rr=pnl / pos.get("max_loss_usdt", 1) if pos.get("max_loss_usdt") else 0,
                strategy=strategy,
                duration_sec=duration,
                equity_before=equity_before,
                equity_after=equity_after,
                sl=sl,
                tp=tp,
                leverage=leverage,
            )
            # ----------------------------------------

            # 倉位關掉 → 解除 pending / open 標記
            if symbol in self.symbol_has_open_pos:
                self.symbol_has_open_pos.remove(symbol)
            if symbol in self.symbol_has_pending:
                self.symbol_has_pending.remove(symbol)

            log(f"📤 平倉完成: {symbol} | PnL={pnl:.2f}")

        except Exception as e:
            log(f"❌ 平倉通知失敗 {symbol}: {e}")


    # ------------------------------------------------------------
    # 給 Telegram 倉位報表
    # ------------------------------------------------------------
    def get_position_report_data(self, api):
        try:
            total_equity = api.get_equity()
            total_pnl = 0

            for symbol, pos in self.positions.items():

                ticker = api.fetch_ticker(symbol)
                cur = float(ticker.get("last", pos["current_price"]))

                pos["current_price"] = cur

                size = abs(pos["size"])
                entry_price = pos["entry_price"]
                contract_size = float(pos.get("contract_size", 1.0))

                if pos["side"] == "long":
                    unreal = (cur - entry_price) * size * contract_size
                else:
                    unreal = (entry_price - cur) * size * contract_size

                pos["unrealized_pnl"] = unreal
                total_pnl += unreal

            return {
                "positions": self.positions,
                "total_equity": total_equity,
                "total_pnl": total_pnl,
                "open_orders_count": 0,
            }

        except Exception as e:
            log(f"⚠️ 倉位報告生成失敗: {e}")
            return {
                "positions": {},
                "total_equity": 0,
                "total_pnl": 0,
                "open_orders_count": 0,
            }

    # ------------------------------------------------------------
    # 判斷是否可開新倉
    # ------------------------------------------------------------
    def can_open_position(self, symbol):
        pos = self.positions.get(symbol)
        return pos is None or abs(pos["size"]) == 0

    # ------------------------------------------------------------
    # 標記剛開倉（僅本地，不代表交易所已成交）
    # ------------------------------------------------------------
    def mark_position_opened(self, symbol, qty, entry_price, side, equity=None):
        size = qty if side == "buy" else -qty
        self.positions[symbol] = {
            "size": size,
            "entry_price": entry_price,
            "side": "long" if size > 0 else "short",
            "entry_time": time.time(),
            "current_price": entry_price,
            "unrealized_pnl": 0,
            "equity_before": equity,  # 記錄開倉時的權益
        }

    # ------------------------------------------------------------
    # 計算有多少 symbol 有倉位
    # ------------------------------------------------------------
    def get_open_positions_count(self):
        return sum(1 for pos in self.positions.values() if abs(pos["size"]) > 0)

    # ------------------------------------------------------------
    # 工具：解析 ccxt position size
    # ------------------------------------------------------------
    def _parse_position_size(self, pos):
        for key in ("contracts", "positionAmt", "size"):
            if key in pos:
                try:
                    return float(pos[key])
                except:
                    continue
        return 0

    # ------------------------------------------------------------
    # 計算有多少 symbol 有倉位
    # ------------------------------------------------------------
    def get_open_positions_count(self):
        return sum(1 for pos in self.positions.values() if abs(pos["size"]) > 0)

    # ------------------------------------------------------------
    # 工具：解析 ccxt position size
    # ------------------------------------------------------------
    def _parse_position_size(self, pos):
        for key in ("contracts", "positionAmt", "size"):
            if key in pos:
                try:
                    return float(pos[key])
                except:
                    continue
        return 0

    # ------------------------------------------------------------
    # 計算總保證金佔用 (RiskManager 用)
    # ------------------------------------------------------------
    def get_total_margin_used(self, api=None):
        """
        計算目前所有持倉佔用的保證金總額 (USDT)
        Margin = (Size * ContractSize * EntryPrice) / Leverage
        """
        total_margin = 0.0
        for symbol, pos in self.positions.items():
            size = abs(float(pos.get("size", 0)))
            if size == 0:
                continue
                
            entry_price = float(pos.get("entry_price", 0))
            leverage = float(pos.get("leverage", 1))
            contract_size = float(pos.get("contract_size", 1.0))
            
            if leverage <= 0: leverage = 1
            
            position_value = size * contract_size * entry_price
            margin = position_value / leverage
            total_margin += margin
            
        return total_margin

    # ------------------------------------------------------------
    # 是否該送一輪倉位報告給主程式（簡易版）
    #   - main.py 用：if position_manager.should_send_position_report(): ...
    # ------------------------------------------------------------
    def should_send_position_report(self):
        """
        回傳 True 表示「這一輪可以送一次報告」，
        並更新內部的 last_position_report 時間。
        """
        now = time.time()
        if now - self.last_position_report >= POSITION_REPORT_INTERVAL:
            self.last_position_report = now
            return True
        return False
