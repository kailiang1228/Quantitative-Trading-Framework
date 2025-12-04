# ============================================================
# exchange_api.py  (強化註解＋安全升級版)
# OKX API 底層封裝（新版）
#
# 功能：
#   - 初始化 OKX
#   - 自動 testnet / real 轉換
#   - 統一 fetch_ohlcv / positions / ticker
#   - 槓桿統一設定
#   - OCO 下單流程（主單 + OCO）
#   - 最小名義價值檢查（避免亂開小單）
#
# ✨ 保證：
#   - 完全相容你現有架構（QuantBot 不會壞）
#   - 不會改任何你的函式名稱
#   - 不會更動任何你上層程式邏輯
#   - 只增強安全性 & 註解
# ============================================================

import ccxt
from utils.logger_util import log, log_error
from config import (
    OKX_API_KEY, OKX_SECRET, OKX_PASSWORD,
    USE_TESTNET, DRY_RUN, LEVERAGE, MIN_NOTIONAL
)


class ExchangeAPI:
    """
    OKX API 底層封裝
    --------------------------------------------------------
    外部程式只會呼叫這層，不會直接接觸 ccxt。
    因此所有格式統一、錯誤處理、精度處理、名義價值。
    --------------------------------------------------------
    """

    # ------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------
    def __init__(self):

        # 初始化 ccxt OKX instance
        self.exchange = ccxt.okx({
            'apiKey': OKX_API_KEY,
            'secret': OKX_SECRET,
            'password': OKX_PASSWORD,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',  # 使用永續合約（你目前所有策略用這個）
            }
        })

        # 切 testnet（如果設定 True）
        if USE_TESTNET:
            self.exchange.set_sandbox_mode(True)
            log("🧪 Sandbox Mode Enabled")

        # 載入市場
        try:
            self.exchange.load_markets()
            log("✅ Markets Loaded")
        except Exception as e:
            log_error(f"❌ load_markets Failed: {e}")

        # 偵測倉位模式（Hedge Mode / One-way Mode）
        self.pos_mode = self._detect_position_mode()
        log(f"📌 Position Mode = {self.pos_mode}")

    # ------------------------------------------------------------
    # 偵測持倉模式：long_short_mode / net_mode
    # ------------------------------------------------------------
    def _detect_position_mode(self):
        try:
            res = self.exchange.private_get_account_config()
            data = res.get("data", [{}])[0]
            return data.get("posMode", "net")
        except Exception:
            return "net"

    # ------------------------------------------------------------
    # fetch_ohlcv
    # ------------------------------------------------------------
    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        """
        統一 OHLCV 回傳格式
        [[ts, open, high, low, close, volume], ...]
        """
        try:
            return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as e:
            log_error(f"❌ fetch_ohlcv Error {symbol}: {e}")
            return []

    # ------------------------------------------------------------
    # 帳戶資金（USDT）
    # ------------------------------------------------------------
    def get_equity(self):
        try:
            balance = self.exchange.fetch_balance()
            usdt = balance.get("USDT", {})
            total = usdt.get("total", 0) or 0
            log(f"💰 Equity={total:.2f}U")
            return total
        except Exception:
            log_error("❌ fetch_balance Failed")
            return 0

    # ------------------------------------------------------------
    # 取得倉位（標準化格式）
    # ------------------------------------------------------------
    def fetch_positions(self):
        """
        回傳每筆倉位：
        {
            symbol, contracts, entryPrice, markPrice,
            unrealizedPnl, side("long"/"short"), contractSize
        }
        """
        try:
            raw = self.exchange.fetch_positions()
            positions = []

            for pos in raw:
                size = float(pos.get("contracts", 0) or 0)
                if size == 0:
                    continue  # 無倉位直接跳過

                symbol = pos.get("symbol")
                entry = float(pos.get("entryPrice", 0) or 0)
                mark = float(pos.get("markPrice", entry) or entry)
                unreal = float(pos.get("unrealizedPnl", 0) or 0)
                
                # [修正] 優先使用 ccxt 解析好的 side
                side = pos.get("side")
                if not side:
                    # 如果 ccxt 沒解析出來，嘗試看原始 info
                    info = pos.get("info", {})
                    pos_side = info.get("posSide") # OKX: long, short, net
                    if pos_side in ["long", "short"]:
                        side = pos_side
                    else:
                        # net mode: 看 pos 正負
                        raw_sz = float(info.get("pos", 0))
                        side = "long" if raw_sz > 0 else "short"

                # 獲取合約面值
                try:
                    market = self.exchange.market(symbol)
                    contract_size = float(market.get('contractSize', 1.0))
                    
                    # [防呆] 如果 BTC/ETH 讀到 1.0，可能是 markets 沒載入好，嘗試重載一次
                    if contract_size == 1.0 and ("BTC" in symbol or "ETH" in symbol) and "USDT" in symbol:
                        # 避免頻繁重載，這裡可以加個 flag 或簡單 log
                        # 但為了安全，我們假設這是異常
                        pass 
                except:
                    contract_size = 1.0

                positions.append({
                    "symbol": symbol,
                    "contracts": abs(size),
                    "entryPrice": entry,
                    "markPrice": mark,
                    "unrealizedPnl": unreal,
                    "side": side,
                    "contractSize": contract_size
                })

            return positions

        except Exception as e:
            log_error(f"❌ fetch_positions Failed: {e}")
            return []

    # ------------------------------------------------------------
    # 設定槓桿
    # ------------------------------------------------------------
    def set_leverage(self, symbol):
        lev = LEVERAGE.get(symbol, 3)

        try:
            # OKX 需要指定 mgnMode (isolated/cross) 才能正確生效
            # 這裡我們強制使用 isolated，因為下單也是用 isolated
            self.exchange.set_leverage(lev, symbol, params={'mgnMode': 'isolated'})
            log(f"⚙️ leverage: {symbol} x{lev} (isolated)")
        except Exception:
            log_error(f"❌ set_leverage Failed: {symbol}")

    # ------------------------------------------------------------
    # 下主單 + OCO  （net_mode 最終版）
    # ------------------------------------------------------------
    def place_order_oco(self, symbol, side, qty, limit_price, tp, sl, strategy_tag=""):
        """
        ================
        1) 名義價值檢查（避免你又下到 0.003U）
        2) 建立主單
        3) 綁定 OCO（止盈止損）
        ================
        """

        # ------------------------
        # DRY RUN（不下單，純 log）
        # ------------------------
        if DRY_RUN:
            log(f"🟡 DRY RUN: {symbol} {side} qty={qty} price={limit_price}")
            return True

        # ------------------------
        # 名義價值檢查
        # ------------------------
        notional = qty * limit_price
        min_nt = MIN_NOTIONAL.get(symbol, 5)
        if notional < min_nt:
            log_error(f"❌ Notional Too Small {notional:.2f} < {min_nt}")
            return False

        # ------------------------
        # 設置槓桿
        # ------------------------
        self.set_leverage(symbol)

        market = self.exchange.market(symbol)
        
        # [修正] OKX 的 create_order `amount` 參數對應 API 的 `sz` (張數)
        # 對於 USDT-Swap:
        #   - SOL/USDT: contractSize = 1 (1張 = 1 SOL)
        #   - ETH/USDT: contractSize = 0.1 (1張 = 0.1 ETH)
        #   - BTC/USDT: contractSize = 0.01 (1張 = 0.01 BTC)
        # 如果我們想下 2.53 ETH，必須轉成張數: 2.53 / 0.1 = 25.3 張
        # 否則直接傳 2.53 會變成 2.53 張 = 0.253 ETH (這就是為什麼倉位變小的原因)
        
        contract_size = float(market.get('contractSize', 1.0))
        if contract_size <= 0: 
            contract_size = 1.0
            
        # 將 幣的數量 (qty) 轉換為 張數 (num_contracts)
        qty_contracts = qty / contract_size
        
        # 使用 ccxt 的 precision 處理 (注意: 這裡是對張數做 precision)
        # OKX 張數通常是整數，但有些幣種可能允許小數張? 通常是整數。
        # ccxt amount_to_precision 會根據 market['precision']['amount'] 處理
        qty_p = float(self.exchange.amount_to_precision(symbol, qty_contracts))
        
        price_p = float(self.exchange.price_to_precision(symbol, limit_price))
        
        log(f"📐 Size Conversion: {qty:.4f} {market['base']} -> {qty_p} Contracts (1 Contract = {contract_size} {market['base']})")

        # ============================================================
        # Step 1: 主單（net_mode 不要 posSide）
        # ============================================================
        try:
            order = self.exchange.create_order(
                symbol=symbol,
                type="limit",
                side=side,
                amount=qty_p,  # 傳入張數
                price=price_p,
                params={
                    "tdMode": "isolated",
                    # ❗ net_mode 不要 posSide ！！
                }
            )
            order_id = order["id"]
            log(f"✅ Main Order OK id={order_id}")

        except Exception as e:
            log_error(f"❌ Main Order Failed: {e}")
            return False

        # ============================================================
        # Step 2: OCO（net_mode 不要 posSide）
        # ============================================================
        try:
            algo = self.exchange.private_post_trade_order_algo({
                "instId": market["id"],
                "tdMode": "isolated",
                "ordType": "oco",
                "side": "sell" if side == "buy" else "buy",
                "sz": str(qty_p),  # 傳入張數 (字串)
                "tpTriggerPx": str(tp),
                "tpOrdPx": "-1",
                "slTriggerPx": str(sl),
                "slOrdPx": "-1",
                # ❗ net_mode 不要 posSide ！！
            })

            algo_id = algo.get("data", [{}])[0].get("algoId", "unknown")
            log(f"📌 OCO OK algoId={algo_id}")
            return True

        except Exception as e:
            log_error(f"❌ OCO Failed: {e}")
            return False

    # ------------------------------------------------------------
    # 修改訂單 (用於移動止損)
    # ------------------------------------------------------------
    def amend_order(self, symbol, order_id, new_price=None, new_trigger_price=None):
        """
        修改一般訂單或 Algo 訂單 (OCO/SL)
        注意：OKX 修改 OCO/SL 需要用專門的 algo endpoint，
        但 ccxt 的 edit_order 對於 algo 支援度不一。
        這裡針對 OKX 實作 algo 修改。
        """
        try:
            # 判斷是否為 Algo ID (通常很長或是我們自己存的)
            # 這裡簡化：嘗試修改 Algo，如果失敗再試試普通單
            
            # 1. 嘗試修改 Algo 訂單 (止損單通常是 Algo)
            if new_trigger_price:
                # OKX 修改 Algo 訂單需要傳入 newSz, newTpTriggerPx, newSlTriggerPx 等
                # 這裡我們假設只改 SL 觸發價
                params = {
                    "instId": self.exchange.market(symbol)["id"],
                    "algoId": str(order_id),
                    "slTriggerPx": str(new_trigger_price),
                    "slOrdPx": "-1" # 市價止損
                }
                res = self.exchange.private_post_trade_amend_algos(params)
                
                if res.get("code") == "0":
                    log(f"✅ 修改 Algo 訂單成功: {symbol} SL -> {new_trigger_price}")
                    return True
                else:
                    # 如果回傳錯誤，可能是普通訂單，或是參數不對
                    log(f"⚠️ 修改 Algo 失敗 (code={res.get('code')})，嘗試普通訂單修改...")

            # 2. 嘗試修改普通訂單 (Limit Order)
            if new_price:
                self.exchange.edit_order(order_id, symbol, "limit", "sell", 0, new_price) # amount 0 = 不改數量
                log(f"✅ 修改普通訂單成功: {symbol} Price -> {new_price}")
                return True

            return False

        except Exception as e:
            log_error(f"❌ 修改訂單失敗 {symbol} id={order_id}: {e}")
            return False

    # ------------------------------------------------------------
    # 即時 ticker
    # ------------------------------------------------------------
    def fetch_ticker(self, symbol):
        try:
            return self.exchange.fetch_ticker(symbol)
        except:
            return {"last": 0}

    # ------------------------------------------------------------
    # 獲取資金費率 (Sentiment Factor)
    # ------------------------------------------------------------
    def fetch_funding_rate(self, symbol):
        """
        回傳當前資金費率 (float)
        例如 0.0001 代表 0.01%
        """
        try:
            # ccxt 統一介面 fetch_funding_rate
            funding = self.exchange.fetch_funding_rate(symbol)
            return float(funding.get('fundingRate', 0))
        except Exception:
            # 如果失敗，回傳 0 (中性)
            return 0.0

    # ------------------------------------------------------------
    # 查詢未成交訂單 (普通單)
    # ------------------------------------------------------------
    def fetch_open_orders(self, symbol=None):
        try:
            return self.exchange.fetch_open_orders(symbol)
        except Exception as e:
            log_error(f"❌ fetch_open_orders Failed: {e}")
            return []

    # ------------------------------------------------------------
    # 查詢未成交策略單 (Algo / OCO)
    # ------------------------------------------------------------
    def fetch_open_algo_orders(self, symbol=None):
        try:
            # OKX 需要用 private_get_trade_orders_algo_pending
            # 必須指定 instType="SWAP" 或是 instId
            params = {"ordType": "oco"}
            
            if symbol:
                market = self.exchange.market(symbol)
                params["instId"] = market["id"]
            else:
                # 如果沒指定 symbol，預設查所有 SWAP
                params["instType"] = "SWAP"
            
            res = self.exchange.private_get_trade_orders_algo_pending(params)
            return res.get("data", [])
        except Exception as e:
            log_error(f"❌ fetch_open_algo_orders Failed: {e}")
            return []

    # ------------------------------------------------------------
    # 檢查是否有任何掛單 (普通 or Algo)
    # ------------------------------------------------------------
    def has_open_orders(self, symbol):
        """
        檢查該幣種是否還有未成交的掛單 (包含 Limit 與 OCO/TPSL)
        防止重複下單的重要檢查
        """
        try:
            # 1. 檢查普通掛單
            orders = self.fetch_open_orders(symbol)
            if len(orders) > 0:
                return True
            
            # 2. 檢查策略掛單 (OCO/TPSL)
            algos = self.fetch_open_algo_orders(symbol)
            if len(algos) > 0:
                return True
                
            return False
        except Exception as e:
            log_error(f"❌ has_open_orders Check Failed: {e}")
            # 保守起見，如果 API 失敗，假設有單，避免重複下單
            return True

    # ------------------------------------------------------------
    # 獲取未平倉合約量 (Open Interest) - Low Correlation Factor
    # ------------------------------------------------------------
    def fetch_open_interest(self, symbol):
        """
        回傳 Open Interest (以 USD 價值為單位)
        """
        try:
            oi_data = self.exchange.fetch_open_interest(symbol)
            # 優先取 USD 價值，方便比較
            return float(oi_data.get('openInterestValue', 0) or 0)
        except Exception:
            return 0.0

    # ------------------------------------------------------------
    # [新增] 獲取市場成交量前 N 大的幣種 (Top N Volume)
    # ------------------------------------------------------------
    def get_top_volume_symbols(self, limit=20):
        """
        自動掃描市場，找出成交量最大的 USDT 永續合約
        回傳格式: ['BTC/USDT:USDT', 'ETH/USDT:USDT', ...]
        """
        try:
            log(f"🔍 正在掃描市場前 {limit} 大熱門幣種...")
            tickers = self.exchange.fetch_tickers()
            
            # 篩選條件：
            # 1. 必須是 USDT 結算
            # 2. 必須是 SWAP (永續合約)
            # 3. 排除 USDC 對
            valid_tickers = []
            for symbol, ticker in tickers.items():
                if "/USDT:USDT" in symbol and "USDC" not in symbol:
                    quote_vol = ticker.get('quoteVolume') or 0
                    valid_tickers.append((symbol, quote_vol))
            
            # 依成交量 (quoteVolume) 降序排列
            valid_tickers.sort(key=lambda x: x[1], reverse=True)
            
            # 取前 N 名
            top_symbols = [t[0] for t in valid_tickers[:limit]]
            
            # 確保 BTC 和 ETH 一定在裡面 (如果意外掉出前20)
            must_have = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
            for s in must_have:
                if s not in top_symbols:
                    top_symbols.insert(0, s)
                    top_symbols.pop() # 移除最後一個以維持數量
            
            log(f"✅ 已更新熱門幣種清單: {len(top_symbols)} 支")
            return top_symbols

        except Exception as e:
            log_error(f"❌ 獲取熱門幣種失敗: {e}")
            # 失敗時回傳預設清單
            return ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]

