# core/quant_bot.py
# 主控：QuantBot
# 會使用：
# - ExchangeAPI
# - MultiTimeframeTrendStrategy（趨勢 + 回調）
# - BreakoutTrendStrategy（趨勢 + 突破）
# - RiskManager / OrderManager / PositionManager
# - Telegram 通知（啟動 / 倉位報告 / 心跳）

import time
from datetime import datetime, timedelta

from exchange_api import ExchangeAPI
from strategies.multi_timeframe_trend import MultiTimeframeTrendStrategy
from strategies.breakout_trend import BreakoutTrendStrategy
from strategies.bollinger_reversion import BollingerReversionStrategy
from core.position_manager import PositionManager
from core.risk_manager import RiskManager
from core.order_manager import OrderManager
from core.regime_detector import RegimeDetector, MarketRegime  # [新增]
from utils.logger_util import (
    log,
    log_error,
    notify_position_report,
    notify_heartbeat,
    send_telegram_message,
)
from config import (
    SYMBOLS,
    AUTO_SYMBOL_SELECTION, # [新增]
    MAX_CONCURRENT_TRADES,
    POSITION_REPORT_INTERVAL,
    HEARTBEAT_INTERVAL,
    REWARD_RATIO,
)


class QuantBot:
    def __init__(self):
        # 交易所 API
        self.api = ExchangeAPI()
        
        # [新增] 自動選幣邏輯
        self.symbols = SYMBOLS
        if AUTO_SYMBOL_SELECTION:
            top_symbols = self.api.get_top_volume_symbols(limit=20)
            if top_symbols:
                self.symbols = top_symbols
                # 更新 config 中的 SYMBOLS 以便其他模組使用 (雖然這不是好習慣，但為了相容性)
                import config
                config.SYMBOLS = top_symbols

        # 風控 / 倉位 / 下單管理
        self.position_manager = PositionManager()
        self.risk_manager = RiskManager(self.api)
        self.order_manager = OrderManager(self.position_manager, self.api)
        self.regime_detector = RegimeDetector()  # [新增] 市場狀態偵測器

        # ======================================================
        # 策略列表
        #   - 給 main.py 用：self.strategies["trend"] / ["breakout"]
        #   - 給舊的 run()/check_signals 用：self.strategy_sequence 依序嘗試
        # ======================================================
        self.strategies = {
            "trend": MultiTimeframeTrendStrategy(),     # 主策略：趨勢 + 回調
            "breakout": BreakoutTrendStrategy(rr=REWARD_RATIO),  # 第二策略：趨勢 + 突破
            "reversion": BollingerReversionStrategy(rr=REWARD_RATIO), # [新增] 第三策略：震盪回歸
        }
        self.strategy_sequence = [
            self.strategies["trend"],
            self.strategies["breakout"],
            self.strategies["reversion"],
        ]

        # 時序控制
        self.last_sync = 0.0
        self.sync_interval = 30  # 每 30 秒同步一次持倉
        self.last_position_report = 0.0
        self.last_heartbeat = 0.0

        # 統計
        self.start_time = time.time()
        self.total_trades = 0
        self.winning_trades = 0

    # ========= 對外：啟動 ==========

    def run(self):
        """主循環：永遠 while True 直到 KeyboardInterrupt"""
        log("🚀 QuantBot 啟動")
        self.send_startup_message()

        while True:
            try:
                now = time.time()

                # 1) 定期同步持倉（含檢查平倉）
                if now - self.last_sync >= self.sync_interval:
                    self.sync_positions()
                    self.order_manager.clean_ghost_orders(self.api)
                    self.last_sync = now

                # 2) 檢查掛單是否視為「成交」並發訊（目前是假成交邏輯）
                filled = self.order_manager.check_order_fills(self.api)
                if filled > 0:
                    log(f"檢測到 {filled} 筆掛單視為成交")

                # 3) 檢查策略訊號並可能下單
                log("\n" + "─" * 50)
                log("📌 市場掃描 / 趨勢分析")
                log("─" * 50)
                self.check_signals()

                # 4) 定期發倉位報告
                if now - self.last_position_report >= POSITION_REPORT_INTERVAL:
                    self.send_position_report()
                    self.last_position_report = now

                # 5) 定期發心跳
                if now - self.last_heartbeat >= HEARTBEAT_INTERVAL:
                    self.send_heartbeat()
                    self.last_heartbeat = now

                # 6) 簡單健康檢查（回撤警告）
                self.health_check()

                time.sleep(10)

            except KeyboardInterrupt:
                log("🛑 使用者手動停止")
                break
            except Exception as e:
                log_error(f"主循環錯誤: {e}")
                time.sleep(30)

    # ========= 啟動 / 報告 / 心跳 ==========

    def send_startup_message(self):
        """啟動時送一則 TG 訊息（如果有設定）"""
        msg = f"""
<b>🚀 量化交易機器人已啟動</b>

📊 監控標的 ({len(self.symbols)}): {", ".join(self.symbols[:5])}...
🤖 策略:
  - MultiTimeframeTrend (趨勢 + 回調)
  - BreakoutTrend (趨勢 + 突破)
⏰ 啟動時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

<i>系統運行中，將定期回報倉位與健康狀態...</i>
"""
        send_telegram_message(msg, "info")

    def send_position_report(self):
        """呼叫 PositionManager 統計資料後，推送倉位報告"""
        try:
            report = self.position_manager.get_position_report_data(self.api)
            notify_position_report(
                positions=report["positions"],
                total_equity=report["total_equity"],
                total_pnl=report["total_pnl"],
                open_orders=report["open_orders_count"],
            )
        except Exception as e:
            log_error(f"發送倉位報告失敗: {e}")

    def send_heartbeat(self):
        """每小時送一次系統狀態"""
        try:
            uptime_seconds = int(time.time() - self.start_time)
            uptime_str = str(timedelta(seconds=uptime_seconds))
            win_rate = (
                (self.winning_trades / self.total_trades * 100.0)
                if self.total_trades > 0
                else 0.0
            )
            notify_heartbeat(
                bot_status="正常運行",
                uptime=uptime_str,
                total_trades=self.total_trades,
                win_rate=win_rate,
            )
        except Exception as e:
            log_error(f"發送心跳失敗: {e}")

    # ========= 持倉同步 / 健康檢查 ==========

    def sync_positions(self):
        """
        從交易所抓最新持倉，更新 PositionManager，
        並將實際權益更新到 RiskManager（風控用）。
        """
        try:
            self.position_manager.sync_from_exchange(self.api)
            equity = self.api.get_equity()
            self.risk_manager.update_equity(equity)
        except Exception as e:
            log_error(f"同步倉位失敗: {e}")

    # ------------------------------------------------------------
    # 自動清理 ghost OCO（主單不存在，但 TP/SL 還在）
    # ------------------------------------------------------------
    # def _clean_ghost_orders(self):
    #     (已移至 OrderManager.clean_ghost_orders)
    #     pass


    def health_check(self):
        """
        簡單健康檢查：例如權益低於某門檻可以 log 警告。
        真正停機邏輯可以之後再加。
        """
        try:
            equity = self.api.get_equity()
            log(f"💰 當前權益: {equity:.2f}")
        except Exception as e:
            log_error(f"健康檢查失敗: {e}")

    # ========= 核心：策略 + 下單 ==========

    def manage_running_positions(self):
        """
        [新增] 監控持倉：
        1. 如果獲利超過 1% (或 1R)，將止損移至入場價 (保本)
        2. 如果獲利超過 2% (或 2R)，啟動移動止損 (Trailing Stop)
        """
        for symbol, pos in self.position_manager.positions.items():
            if abs(pos["size"]) == 0:
                continue

            try:
                # 取得當前價格
                ticker = self.api.fetch_ticker(symbol)
                current_price = ticker["last"]
                entry_price = pos["entry_price"]
                side = pos["side"]
                
                # 計算未實現盈虧 %
                if side == "long":
                    pnl_pct = (current_price - entry_price) / entry_price
                else:
                    pnl_pct = (entry_price - current_price) / entry_price

                # ----------------------------------------------------
                # 策略 1: 自動保本 (Auto Break-Even)
                # 當獲利 > 1% 時，嘗試把 SL 改到 Entry
                # ----------------------------------------------------
                if pnl_pct > 0.01:
                    # 檢查是否已經移過 SL (避免重複 API call)
                    # 這裡簡單用 "sl" 欄位判斷，如果 SL 已經在 Entry 附近就不動
                    current_sl = pos.get("sl", 0)
                    
                    # 判斷是否需要移動
                    need_move = False
                    new_sl = entry_price
                    
                    if side == "long":
                        # 多單：如果 SL < Entry，且價格 > Entry * 1.01，則移到 Entry
                        if current_sl < entry_price * 0.999: 
                            need_move = True
                    else:
                        # 空單：如果 SL > Entry，且價格 < Entry * 0.99，則移到 Entry
                        if current_sl > entry_price * 1.001:
                            need_move = True
                            
                    if need_move:
                        log(f"💰 {symbol} 獲利 > 1%，移動止損至保本位 {entry_price}")
                        # 尋找該 symbol 的 Algo 訂單 (SL)
                        algos = self.api.fetch_open_algo_orders(symbol)
                        for algo in algos:
                            # 簡單判斷：如果是 OCO 或 Stop Loss
                            if algo.get("ordType") in ["oco", "conditional", "trigger"]:
                                algo_id = algo["algoId"]
                                success = self.api.amend_order(symbol, algo_id, new_trigger_price=new_sl)
                                if success:
                                    pos["sl"] = new_sl # 更新本地 SL 記錄
                                break

            except Exception as e:
                log_error(f"管理持倉失敗 {symbol}: {e}")

    def check_signals(self):
        """對每個 symbol 跑所有策略，找到合格訊號就下單。"""
        
        # [新增] 檢查現有倉位是否需要「移動止損」或「保本」
        self.manage_running_positions()

        # 目前持倉數量
        open_positions = self.position_manager.get_open_positions_count()
        if open_positions >= MAX_CONCURRENT_TRADES:
            # 已滿倉，不再開新單
            return

        for symbol in self.symbols: # [修改] 使用 self.symbols
            log(f"🔍 掃描: {symbol}")
            try:
                # 這個 symbol 已有倉位就不開新單（避免同幣多單堆疊）
                if not self.position_manager.can_open_position(symbol):
                    continue

                # ----------------------------------------------------
                # [新增] 市場狀態判斷 (Regime Detection)
                # ----------------------------------------------------
                # 抓取 1h 數據進行判斷
                ohlcv_1h = self.api.fetch_ohlcv(symbol, "1h", limit=50)
                regime = self.regime_detector.detect_regime(ohlcv_1h)
                
                # 根據狀態篩選策略
                # [修改] 使用者要求開啟所有策略，僅做 Log 提示
                active_strategies = self.strategy_sequence
                
                if regime == MarketRegime.TRENDING:
                    log(f"   👉 Regime: TRENDING (Running ALL strategies)")
                elif regime == MarketRegime.RANGING:
                    log(f"   👉 Regime: RANGING (Running ALL strategies)")
                else:
                    log(f"   👉 Regime: UNCERTAIN (Running ALL strategies)")

                signal = None
                # 依序跑策略：有訊號就用那個
                for strat in active_strategies:
                    s = strat.analyze(self.api, symbol)
                    if s is not None:
                        signal = s
                        break

                if signal is None:
                    continue

                # 交給 RiskManager 做檢查（波動率 / SLTP 合理性）
                if not self.risk_manager.validate_signal(symbol, signal):
                    continue

                # [新增] 檢查總帳戶風險 (Global Risk Check)
                # 獲取當前所有持倉的保證金佔用
                current_total_margin = self.position_manager.get_total_margin_used(self.api)
                is_safe, msg = self.risk_manager.check_global_risk(open_positions, current_total_margin)
                
                if not is_safe:
                    log(f"⚠️ {symbol} 風控攔截: {msg}")
                    continue

                # 真正執行下單
                self.execute_trade(symbol, signal)

            except Exception as e:
                log_error(f"檢查訊號失敗 {symbol}: {e}")

    def execute_trade(self, symbol, signal):
        """從 signal -> 算倉位大小 -> 下 OCO 單 -> 更新 PositionManager"""
        try:
            entry = signal["entry"]
            sl = signal["sl"]
            side = signal["side"]  # 'buy' / 'sell'

            qty, msg = self.risk_manager.calculate_position_size(
                symbol, entry, sl, side
            )
            if qty <= 0:
                log(f"⚠️ {symbol} 倉位計算失敗: {msg}")
                return

            success = self.order_manager.place_trend_order(symbol, signal, qty)
            if not success:
                log(f"❌ {symbol} 下單失敗")
                return

            log(f"✅ {symbol} 交易執行成功（策略: {signal.get('strategy', 'Unknown')}）")

            # 對 PositionManager 標記「已開倉」
            # 這邊把 'buy'/'sell' 轉成 'long'/'short'
            pos_side = "long" if side == "buy" else "short"
            
            # 獲取當前權益，用於記錄
            current_equity = self.api.get_equity()
            self.position_manager.mark_position_opened(symbol, qty, entry, pos_side, current_equity)

            self.total_trades += 1

        except Exception as e:
            log_error(f"執行交易失敗 {symbol}: {e}")
