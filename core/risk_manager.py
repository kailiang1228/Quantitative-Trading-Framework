# ============================================================
# core/risk_manager.py    （強化註解＋安全升級版）
#
# RiskManager 功能總覽：
# ------------------------------------------------------------
# 1) 每單最大可承受虧損（固定用「帳戶淨值的一定比例」）
# 2) 每單倉位計算：qty = allowed_risk / stop_loss_distance
# 3) 最大名義價值限制（避免單筆下太大 → 爆倉）
# 4) 最小名義價值限制（避免觸發交易所最低金額錯誤）
# 5) 信號基本驗證：entry/sl/tp/atr 是否合理
# 6) 統一 log 格式，且錯誤不會讓程式崩掉
# ============================================================

from config import (
    TOTAL_EQUITY,
    MAX_MARGIN_RATIO,
    MAX_TOTAL_MARGIN_RATIO,  # [新增]
    RISK_PER_TRADE,
    RISK_TIERS,              # [新增]
    FIXED_RISK_USDT,
    MIN_NOTIONAL,
    LEVERAGE
)
from utils.logger_util import (
    log,
    log_error,
    notify_position_report,
    notify_heartbeat,
    send_telegram_message,
)


class RiskManager:
    """
    你的整個系統的「核心安全守門員」  
    避免：
      - 下到 0.003 ETH（名義價值太小 → 直接不下單）
      - 停損距離太小或太大（ATR 異常）
      - 無限放大槓桿（名義價值防爆倉）
      - 訊號值為 0 或負值（拒絕下單）
      - [新增] 總保證金過高（防止爆倉）
      - [新增] 針對小幣自動降倉（Risk Tiers）
    """

    # ------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------
    def __init__(self, api):
        self.api = api
        # equity 會在 QuantBot 中被動態更新（依交易所實際權益）
        self.equity = TOTAL_EQUITY

    # ------------------------------------------------------------
    # 由 QuantBot 更新 equity
    # ------------------------------------------------------------
    def update_equity(self, equity):
        """
        QuantBot 每次同步倉位後會呼叫  
        讓風控永遠用「最新的權益」來計算每筆下單大小
        """
        self.equity = max(float(equity), 0.0)

    # ------------------------------------------------------------
    # [新增] 檢查總帳戶風險 (Global Risk Check)
    # ------------------------------------------------------------
    def check_global_risk(self, current_positions_count, current_total_margin_used):
        """
        在下單前檢查：
        1. 總保證金是否已超過 MAX_TOTAL_MARGIN_RATIO
        """
        if self.equity <= 0:
            return False, "權益為 0"

        # 檢查總保證金佔比
        margin_ratio = current_total_margin_used / self.equity
        if margin_ratio >= MAX_TOTAL_MARGIN_RATIO:
            return False, f"總保證金佔比過高 ({margin_ratio*100:.1f}% >= {MAX_TOTAL_MARGIN_RATIO*100}%)"

        return True, "OK"

    # ------------------------------------------------------------
    # 訊號基本驗證（entry/sl/tp 是否正常）
    # ------------------------------------------------------------
    def validate_signal(self, symbol, signal):
        entry = signal.get("entry", 0)
        sl = signal.get("sl", 0)
        tp = signal.get("tp", 0)
        atr = signal.get("atr", 0)

        # --------------------------
        # 價格異常
        # --------------------------
        if entry <= 0 or sl <= 0 or tp <= 0:
            log(f"⚠️ {symbol} 訊號異常：entry/sl/tp <= 0")
            return False

        # --------------------------
        # ATR 過大（極端波動 → 直接跳過）
        # --------------------------
        if atr > entry * 0.05:
            log(f"⚠️ {symbol} 波動過大 ATR={atr:.4f} (>5%) → 跳過")
            return False

        return True

    # ------------------------------------------------------------
    # 核心：計算每單倉位大小
    # ------------------------------------------------------------
    def calculate_position_size(self, symbol, entry_price, stop_loss, side):
        """
        計算 qty：
        --------------------------------------------------------
        1) 先以「帳戶淨值 * RISK_PER_TRADE」當作最大允許虧損
        2) [新增] 應用 RISK_TIERS 權重 (小幣倉位打折)
        3) qty_base = allowed_risk / |entry - stop_loss|
        4) 再檢查：
           - 保證金是否超過 MAX_MARGIN_RATIO * equity
           - 名義價值是否低於交易所最低 MIN_NOTIONAL
           - 最後再「反算實際風險」，確保 <= equity * RISK_PER_TRADE
        --------------------------------------------------------
        """

        try:
            # ====================================================
            # 1) 計算停損距離（每 1 單位要虧多少 USDT）
            # ====================================================
            risk_per_unit = abs(entry_price - stop_loss)
            
            # [新增] 最小止損距離檢查 (防止止損太近導致倉位過大)
            # 設定為價格的 0.4% (例如 BTC 90000 -> 最小止損 360U)
            # 如果策略給的止損太近，強制用這個距離來算倉位，避免開太大
            min_sl_dist = entry_price * 0.004
            
            if risk_per_unit < min_sl_dist:
                log(f"⚠️ {symbol} 止損距離過近 ({risk_per_unit:.2f} < {min_sl_dist:.2f}) -> 強制使用最小距離 {min_sl_dist:.2f} 計算倉位")
                risk_per_unit = min_sl_dist

            if risk_per_unit <= 0:
                return 0, "止損價格錯誤（距離 <= 0）"

            if self.equity <= 0:
                return 0, "權益為 0，無法下單"

            # ====================================================
            # 2) 設定「本單最大允許虧損」
            #    → 這裡直接按「帳戶淨值 * RISK_PER_TRADE」
            # ====================================================
            allowed_risk_ratio = max(float(RISK_PER_TRADE), 0.0)
            # 強制上一個 safety cap（避免 config 不小心設太大）
            if allowed_risk_ratio > 0.10:
                allowed_risk_ratio = 0.10

            # [新增] 應用 Risk Tier 權重
            # 如果是 BTC/ETH -> 1.0, SOL -> 0.85, 其他 -> 0.6
            tier_multiplier = RISK_TIERS.get(symbol, RISK_TIERS.get("DEFAULT", 0.6))
            allowed_risk_ratio *= tier_multiplier
            
            allowed_risk = self.equity * allowed_risk_ratio

            # （保留小帳 FIXED_RISK_USDT 功能：如果你之後想限制小帳）
            if FIXED_RISK_USDT is not None and self.equity <= 500:
                allowed_risk = min(allowed_risk, float(FIXED_RISK_USDT))

            # ====================================================
            # 3) 以「風險公式」算出理論 max qty
            # ====================================================
            base_qty = allowed_risk / risk_per_unit  # 核心公式

            # ====================================================
            # 4) 保證金限制（Margin Cap）
            #    Margin = (Qty * Entry) / Leverage
            #    Max Margin = Equity * MAX_MARGIN_RATIO
            #    => Max Notional = Max Margin * Leverage
            # ====================================================
            leverage = LEVERAGE.get(symbol, LEVERAGE.get("DEFAULT", 5)) # [修改] 支援 DEFAULT
            max_margin_allowed = self.equity * MAX_MARGIN_RATIO
            max_notional_allowed = max_margin_allowed * leverage

            notional = entry_price * base_qty
            if notional > max_notional_allowed:
                # 倉位太大 → 按比例縮小
                scale = max_notional_allowed / max(notional, 1e-9)
                base_qty *= scale
                log(f"📦 {symbol} 倉位因保證金過大 (> {MAX_MARGIN_RATIO*100}%) 已縮小")

            # ====================================================
            # 5) 檢查最小名義價值（避免下太小）
            # ====================================================
            min_notional = MIN_NOTIONAL.get(symbol, MIN_NOTIONAL.get("DEFAULT", 6.0)) # [修改] 支援 DEFAULT

            if base_qty * entry_price < min_notional:
                return 0, f"名義價值過小 (< {min_notional}U) → 跳過"

            # ====================================================
            # 6) 精度處理（交給 ccxt）
            # ====================================================
            precise_qty = self.api.exchange.amount_to_precision(symbol, base_qty)
            qty = float(precise_qty)

            if qty <= 0:
                return 0, "精度處理後 qty==0"

            # ====================================================
            # 7) 反算「實際最大虧損」，再做一次 safety cap
            # ====================================================
            actual_risk = risk_per_unit * qty
            max_risk_allowed = self.equity * allowed_risk_ratio

            if actual_risk > max_risk_allowed:
                # 再縮一小段，保證實際虧損 <= 允許比例
                scale = max_risk_allowed / actual_risk
                qty *= scale
                precise_qty = self.api.exchange.amount_to_precision(symbol, qty)
                qty = float(precise_qty)
                actual_risk = risk_per_unit * qty

            # 名義價值重新計算
            final_notional = qty * entry_price

            # 再次檢查最小名義價值
            if final_notional < min_notional:
                return 0, f"名義價值過小 (< {min_notional}U)（縮小後）→ 跳過"

            # ====================================================
            # 8) Log（便於你在 Telegram 看到倉位大小）
            # ====================================================
            risk_pct = (actual_risk / self.equity * 100.0) if self.equity > 0 else 0.0
            margin_est = final_notional / leverage if leverage > 0 else final_notional
            margin_pct = (margin_est / self.equity * 100.0) if self.equity > 0 else 0.0

            log(
                f"💰 {symbol} 倉位計算 (Tier={tier_multiplier}): "
                f"qty={qty:.6f}, "
                f"notional={final_notional:.2f}U, "
                f"理論最大虧損={actual_risk:.2f}U ({risk_pct:.2f}%), "
                f"保證金≈{margin_est:.2f}U ({margin_pct:.2f}%)"
            )

            return qty, "成功"

        except Exception as e:
            return 0, f"倉位計算錯誤: {e}"
