````markdown
# 📈 Quant_V6_G — Institutional-Grade High-Frequency Trading System

**Quant_V6_G** 是一套專為 **OKX 永續合約 (USDT-M Futures)** 設計的 **機構級高頻量化交易系統 (HFT-Lite)**。
本系統經過嚴格的「真實成本回測」驗證，針對 **0.05% Taker Fee** 與 **滑點** 進行了深度優化，專注於在扣除交易成本後仍能創造 Alpha 的高頻波段策略。

---

## 🚀 核心優勢 (Core Advantages)

### ⚡ 高頻與低延遲 (High Frequency & Low Latency)
*   **1H 趨勢 + 15m 進場**：相比傳統 4H 策略，本系統反應速度快 4 倍，能捕捉日內中型波段。
*   **高頻參數調校**：Supertrend (10, 3.0) 與 Bollinger (2.0 Std) 參數組，確保在波動來臨時能迅速建倉。

### 🛡️ 真實成本防禦 (Real-Cost Defense)
針對高頻交易的兩大殺手——**手續費**與**假突破**，內建多重過濾機制：
*   **死魚盤過濾 (Dead Market Filter)**：當布林通道寬度 < 2% 時，強制停止交易，避免在無波動行情中被手續費磨損。
*   **實體 K 線過濾 (Candle Body Filter)**：過濾十字星 (Doji) 與長影線造成的假突破，只有實體飽滿的 K 線才能觸發訊號。
*   **資金費率保護**：自動計算持倉期間的 Funding Fee，避免長期持有高費率倉位。

### 🧠 自適應市場感知 (Adaptive Regime Detection)
系統內建 `RegimeDetector` 模組，實時分析市場熵值：
*   **Trending (趨勢狀態)**：當 ADX > 20 且波動率擴大時，啟動 **Supertrend** 策略。
*   **Ranging (盤整狀態)**：當 ADX < 20 且 Bandwidth 收斂時，切換至 **Bollinger Reversion** 策略。

---

## 🧱 系統架構 (System Architecture)

採用模組化設計，確保高擴充性與維護性：

```text
Quant_V6_G/
├── main.py                  # 🚀 系統入口
├── config.py                # ⚙️ 參數配置 (含 VIP 費率設定)
├── exchange_api.py          # 🏦 OKX API 封裝 (含 OI/Funding 獲取)
│
├── core/                    # 🧠 核心層
│   ├── quant_bot.py         # 主控循環 (Strategy Dispatcher)
│   ├── regime_detector.py   # 市場狀態判斷
│   ├── risk_manager.py      # 風控引擎 (Size Calculation)
│   └── order_manager.py     # 訂單執行 (OCO / Ghost Order Cleaning)
│
├── strategies/              # 📈 策略庫
│   ├── supertrend_strategy.py    # [Trend] 高頻超級趨勢 (10, 3.0)
│   ├── bollinger_reversion.py    # [MeanRev] 動態布林回調 (含死魚盤過濾)
│   └── meme_breakout_strategy.py # [Alpha] 瘋狗流突破 (針對 Meme 幣)
│
├── backtest/                # 🧪 回測實驗室
│   ├── batch_backtest.py    # 批量回測 (含真實手續費/滑點模擬)
│   └── composite_backtest.py# 組合策略回測引擎
│
└── utils/                   # 🛠️ 工具層
    ├── trade_recorder.py    # CSV 精確審計
    └── logger_util.py       # Telegram 實時推播
```

---

## 📈 策略邏輯 (Strategy Logic)

### 1. Supertrend Strategy (趨勢軍團)
*   **邏輯**：1H 判斷大趨勢 (EMA 50)，15m Supertrend (10, 3.0) 尋找進場點。
*   **濾網**：
    *   **ADX > 20**：確保有動能。
    *   **Candle Body > 0.3 ATR**：拒絕假突破。
*   **適用**：BTC, ETH, SOL 等主流幣的單邊行情。

### 2. Bollinger Reversion (回調軍團)
*   **邏輯**：順大勢 (1H EMA) 的深回調交易。在上升趨勢中，價格觸及布林下軌 (2.0 Std) 時做多。
*   **濾網**：
    *   **Bandwidth > 2%**：拒絕死魚盤。
    *   **RSI < 30 / > 70**：確認極端情緒。
*   **適用**：震盪向上的慢牛行情。

### 3. Meme Breakout (特種部隊)
*   **邏輯**：專為 DOGE, PEPE 等高波動幣設計。
*   **條件**：Keltner Channel 突破 + 成交量爆發 (> 2.0倍均量)。
*   **風控**：極窄止損 (1.5 ATR)，追求 10x 爆擊。

---

## ⚙️ 安裝與部署 (Installation)

### 1. 環境準備
確保已安裝 Python 3.8+，並安裝依賴套件：
```bash
pip install -r requirements.txt
```

### 2. 數據準備 (Data Preparation)
本系統依賴完整的歷史數據進行回測與分析：
```bash
# 1. 下載 K 線、資金費率、持倉量 (自動抓取 Top 20 熱門幣種)
python download_data.py
```

### 3. 設定 Config
將 `config_template.py` 複製為 `config.py`，並填入您的 OKX API 資訊與風控設定：

```bash
cp config_template.py config.py
```

```python
# config.py

# 1. API 設定
OKX_API_KEY = "your_api_key"
OKX_SECRET = "your_secret"
OKX_PASSWORD = "your_password"
USE_TESTNET = False  # 建議先用 True 模擬

# 2. 風控設定
RISK_PER_TRADE = 0.02      # 單筆風險 2%
MAX_TOTAL_MARGIN_RATIO = 0.6 # 總倉位上限 60%
```

### 4. 啟動機器人
```bash
python main.py
```

---

## 🧪 回測系統 (Backtesting)

本系統包含業界最嚴格的回測模組，拒絕「快樂模擬」：

### 批量回測 (Batch Backtest)
模擬真實市場摩擦成本，驗證策略在扣除手續費後是否仍能獲利。
*   **Fee Rate**: 0.05% (Taker)
*   **Slippage**: 0.02% (滑點)
*   **Funding**: 動態計算

```bash
python Quant_V6_G/backtest/batch_backtest.py
```
*輸出結果將自動排序並生成 `batch_backtest_results.csv`，推薦 PF > 1.1 的幣種加入白名單。*

---

## ⚠️ 免責聲明 (Disclaimer)

本軟體僅供教育與研究用途。加密貨幣交易具有極高風險，可能導致資金全額損失。
**使用本系統產生的任何盈虧，開發者概不負責。** 請務必在模擬盤 (Testnet) 充分測試後再投入實盤。

````