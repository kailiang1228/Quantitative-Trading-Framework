# ============================================================
# order_manager.py  v1.1  — 完整 A 版
# ============================================================

import time
from utils.logger_util import (
    log, log_error,
    notify_order_placed,
    notify_order_filled,
    notify_error
)


class OrderManager:

    def __init__(self, position_monitor, api):
        self.api = api
        self.position_monitor = position_monitor

        # 用來避免重複開倉
        self.pending_orders = {}          # symbol → {info}
        self.symbol_pending = set()       # symbol list
        self.symbol_error_cooldown = {}   # symbol → timestamp
        self.MARGIN_ERROR_COOLDOWN = 60   # 保證金不足時 冷卻 60 秒

    # ============================================================
    # 主入口：由策略呼叫下單
    # ============================================================
    def place_trend_order(self, symbol, signal, qty):
        side = signal["side"]
        entry = signal["entry"]
        sl = signal["sl"]
        tp = signal["tp"]
        strategy = signal.get("strategy", "Trend")

        now = time.time()

        # --------------------------------------------------------
        # ① 有持倉 → 不能再開
        # --------------------------------------------------------
        if symbol in self.position_monitor.symbol_has_open_pos:
            log(f"⛔ {symbol} 已有持倉，略過新訊號")
            return False

        # --------------------------------------------------------
        # ② 有 pending → 不能再開
        # --------------------------------------------------------
        if symbol in self.symbol_pending:
            log(f"⛔ {symbol} 已有 pending 訂單，略過新訊號")
            return False

        # --------------------------------------------------------
        # ②-2 雙重確認：API 查詢是否有掛單 (防止重複 TPSL)
        # --------------------------------------------------------
        if self.api.has_open_orders(symbol):
            log(f"⛔ {symbol} 交易所已有掛單 (Limit/OCO)，略過新訊號")
            # 同步更新本地狀態，避免下次還要查 API
            self.symbol_pending.add(symbol)
            return False

        # --------------------------------------------------------
        # ③ 剛剛收到 51008 保證金不足 → 冷卻
        # --------------------------------------------------------
        if symbol in self.symbol_error_cooldown:
            if now < self.symbol_error_cooldown[symbol]:
                remain = int(self.symbol_error_cooldown[symbol] - now)
                log(f"⛔ {symbol} 冷卻中（剩 {remain}s），略過新訊號")
                return False

        # --------------------------------------------------------
        # Step 1. 下單通知（準備下單）
        # --------------------------------------------------------
        notify_order_placed(
            symbol=symbol, side=side, qty=qty,
            price=entry, sl=sl, tp=tp, strategy=strategy
        )

        # --------------------------------------------------------
        # Step 2. 主單 + OCO
        # --------------------------------------------------------
        success = self.api.place_order_oco(
            symbol=symbol,
            side=side,
            qty=qty,
            limit_price=entry,
            tp=tp,
            sl=sl,
            strategy_tag=strategy
        )

        # --------------------------------------------------------
        # Step 3. 主單或 OCO 失敗 → 記錄，冷卻 60 秒
        # --------------------------------------------------------
        if not success:
            log_error(f"❌ {symbol} 主單/OCO 失敗 → 進入冷卻 60 秒")

            # 51008（保證金不足）觸發後加入 cooldown
            self.symbol_error_cooldown[symbol] = time.time() + self.MARGIN_ERROR_COOLDOWN
            return False

        # --------------------------------------------------------
        # Step 4. 全部成功 → 加入 pending
        # --------------------------------------------------------
        self.pending_orders[symbol] = {
            "side": side,
            "qty": qty,
            "entry_price": entry,
            "timestamp": time.time()
        }

        self.symbol_pending.add(symbol)

        log(f"✅ {symbol} 訂單提交成功（等待成交）")

        return True

    # ============================================================
    # 成交檢查：倉位出現 → 當作成交
    # ============================================================
    def check_order_fills(self, api):
        filled_count = 0

        positions = api.fetch_positions()
        open_symbols = {p.get("symbol") for p in positions}

        now = time.time()
        timeout_sec = 600

        for symbol, info in list(self.pending_orders.items()):

            # ---------------------------------------------
            # 成交 → 發通知 + 移除 pending
            # ---------------------------------------------
            if symbol in open_symbols:
                notify_order_filled(
                    symbol=symbol,
                    side=info["side"],
                    qty=info["qty"],
                    price=info["entry_price"]
                )

                del self.pending_orders[symbol]
                self.symbol_pending.discard(symbol)
                filled_count += 1
                continue

            # ---------------------------------------------
            # pending 超時（10 分鐘）→ 當作 miss
            # ---------------------------------------------
            if now - info["timestamp"] > timeout_sec:
                log(f"⏱ {symbol} pending 超時，清除")
                del self.pending_orders[symbol]
                self.symbol_pending.discard(symbol)

        return filled_count

    # ============================================================
    # 清理 Ghost Orders (本地有 pending，但交易所沒單也沒倉位)
    # ============================================================
    def clean_ghost_orders(self, api):
        """
        檢查 pending_orders 中的訂單：
        1. 如果在 positions 裡 -> check_order_fills 會處理 (視為成交)
        2. 如果在 open_orders 裡 -> 正常掛單中
        3. 都不在 -> 訂單可能被取消或拒絕 -> 移除 pending
        """
        if not self.pending_orders:
            return

        try:
            # 獲取交易所當前掛單
            open_orders = api.fetch_open_orders()
            open_order_symbols = {o['symbol'] for o in open_orders}
            
            # 獲取交易所當前倉位
            positions = api.fetch_positions()
            position_symbols = {p['symbol'] for p in positions}

            # 檢查每一個 pending order
            for symbol in list(self.pending_orders.keys()):
                # Case 1: 已成交 (有倉位) -> check_order_fills 會處理，這裡跳過
                if symbol in position_symbols:
                    continue
                
                # Case 2: 掛單中 (有 Open Order) -> 正常
                if symbol in open_order_symbols:
                    continue
                
                # Case 3: 既沒倉位也沒掛單 -> Ghost Order
                log(f"🧹 清除 Ghost Order: {symbol} (交易所無掛單且無倉位)")
                del self.pending_orders[symbol]
                self.symbol_pending.discard(symbol)

        except Exception as e:
            log_error(f"❌ 清理 Ghost Orders 失敗: {e}")

    # ============================================================
    # 供 QuantBot 呼叫：檢查是否允許開新倉
    # ============================================================
    def can_open(self, symbol):
        now = time.time()

        if symbol in self.position_monitor.symbol_has_open_pos:
            return False
        if symbol in self.symbol_pending:
            return False
        if symbol in self.symbol_error_cooldown and now < self.symbol_error_cooldown[symbol]:
            return False

        return True
