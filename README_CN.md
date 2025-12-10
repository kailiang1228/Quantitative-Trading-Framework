# 📈 Quantitative Trading Framework (量化交易框架)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

這是一個專為 **OKX 永續合約 (USDT-M Futures)** 打造的專業級、模組化量化交易框架。

與一般的腳本不同，本框架的設計核心在於 **生產環境的安全性** 與 **可擴充性**。它解決了真實交易中的複雜問題——如網路不穩定、API 限制、狀態同步以及嚴格的風險控制——讓開發者能專注於策略邏輯本身。

---

## 🌟 核心功能

### 🛡️ 生產級可靠性 (Production-Grade Reliability)
*   **原子化下單 (Atomic Execution)**：利用 OKX 的 `attachAlgoOrds` 功能，將「進場單」、「止盈單 (TP)」與「止損單 (SL)」打包在同一個 API 請求中發送。這徹底消除了因網路中斷導致只有進場卻沒有止損的「裸單」風險。
*   **狀態持久化 (State Persistence)**：機器人會自動將倉位狀態儲存至本地 JSON 資料庫 (`positions_db.json`)。即使程式崩潰或重啟，也能精確恢復之前的交易狀態與進場價格。
*   **穩健的錯誤處理**：內建 API 重試機制與完整的日誌記錄系統。

### ⚡ 高擬真回測 (High-Fidelity Backtesting)
*   **真實成本模擬**：回測引擎並非僅計算理論獲利，而是計入了 **Taker 手續費**、**滑點 (Slippage)** 以及 **資金費率 (Funding Rates)**，提供最接近真實的績效評估。
*   **多策略組合**：支援同時運行多個策略進行組合回測，評估投資組合的表現。
*   **詳細報表**：自動生成權益曲線圖、最大回撤分析與詳細交易日誌。

### 🧩 模組化架構 (Modular Architecture)
*   **邏輯解耦**：策略 (Strategy)、風控 (Risk) 與執行 (Execution) 完全分離。新增策略只需在 `strategies/` 資料夾中新增一個檔案即可。
*   **事件驅動核心**：高效的主循環負責處理數據更新、訊號分發與訂單管理。

### ⚖️ 進階風險管理 (Advanced Risk Management)
*   **動態倉位計算**：根據當前帳戶權益與設定的單筆風險百分比（如 2%）自動計算下單數量。
*   **資金保護**：可設定最大回撤限制與總保證金佔用上限，防止過度槓桿。

---

## 📂 專案結構

```text
Quantitative-Trading-Framework/
├── main.py                  # 🚀 機器人啟動入口
├── config.py                # ⚙️ 全域設定 (風險參數、API、時間級別)
├── exchange_api.py          # 🏦 OKX API 封裝 (REST + 公共數據)
│
├── core/                    # 🧠 核心系統邏輯
│   ├── quant_bot.py         # 主事件循環與策略分發
│   ├── risk_manager.py      # 倉位計算與風控檢查
│   ├── order_manager.py     # 訂單執行與驗證
│   └── persistence.py       # JSON 狀態保存與讀取
│
├── strategies/              # 📈 策略實作
│   ├── supertrend_strategy.py    # 範例：趨勢跟隨策略
│   ├── bollinger_reversion.py    # 範例：均值回歸策略
│   └── ... (可自行擴充)
│
├── backtest/                # 📊 回測引擎
│   ├── composite_backtest.py     # 主回測腳本
│   ├── simple_backtest.py        # 簡易教學版回測
│   └── generate_report.py        # 視覺化報表工具
│
└── data/                    # 💾 數據儲存
    └── positions_db.json    # 活躍倉位狀態 (自動生成)
```

## 🚀 快速開始

### 1. 環境需求
*   Python 3.10 或更高版本
*   OKX 帳戶 (用於模擬或實盤交易)

### 2. 安裝
Clone 專案並安裝依賴套件：
```bash
git clone https://github.com/yourusername/Quantitative-Trading-Framework.git
cd Quantitative-Trading-Framework
pip install -r requirements.txt
```

### 3. 設定
編輯 `config.py` 進行個人化設定。
*   **風險設定**：調整 `RISK_PER_TRADE` (預設 2%) 與槓桿倍數。
*   **API Key**：建議透過環境變數設定 OKX API Key，或在測試時直接寫入檔案。

```python
# config.py 範例
API_KEY = os.getenv("OKX_API_KEY")
IS_SIMULATION = True  # 設為 False 即為實盤
```

### 4. 執行回測
在投入資金前，請務必使用歷史數據驗證策略。
```bash
# 確保 data/ 資料夾中有對應格式的 CSV 數據 (timestamp, open, high, low, close, volume)
python backtest/composite_backtest.py
```

### 5. 啟動機器人
預設以模擬模式啟動。
```bash
python main.py
```

---

## 🧠 內建策略介紹

本框架內建了兩個核心策略範本，旨在作為開發更複雜邏輯的基礎。

### 1. Supertrend Strategy (趨勢跟隨策略)
*   **核心概念**：經典的趨勢跟隨系統，旨在捕捉市場的大型方向性波動。假設一旦趨勢形成，價格沿趨勢方向運行的機率大於反轉。
*   **進場邏輯**：
    *   **做多 (Long)**：當收盤價突破 Supertrend 上軌（轉綠）時進場，代表多頭趨勢確立。
    *   **做空 (Short)**：當收盤價跌破 Supertrend 下軌（轉紅）時進場，代表空頭趨勢確立。
*   **出場邏輯**：
    *   **止損 (Stop Loss)**：動態止損。止損點隨著 Supertrend 線移動，在趨勢延續時鎖定利潤。
    *   **止盈 (Take Profit)**：基於固定的風險回報比 (Risk-Reward Ratio) 計算，例如設定為初始止損距離的 2 倍。

### 2. Bollinger Mean Reversion (布林均值回歸策略)
*   **核心概念**：專為盤整或震盪市場設計的逆勢策略。假設價格具有彈性，在觸及極端水平後會回歸均值 (平均價格)。
*   **進場邏輯**：
    *   **做多 (Long)**：當價格觸及或跌破 **布林通道下軌** 時進場，視為超賣訊號。
    *   **做空 (Short)**：當價格觸及或突破 **布林通道上軌** 時進場，視為超買訊號。
*   **出場邏輯**：
    *   **止盈 (Take Profit)**：設定在 **布林中軌** (移動平均線)，即價格的平衡點。
    *   **止損 (Stop Loss)**：設定在進場軌道外側的一定 ATR (平均真實波幅) 距離，以容忍市場雜訊。

---

## 🛠️ 開發新策略

要新增策略，只需在 `strategies/` 資料夾中建立新的 Python 檔案，並實作 `analyze` 方法。

```python
# strategies/my_custom_strategy.py
class MyCustomStrategy:
    def __init__(self):
        self.name = "MyStrategy"

    def analyze(self, api, symbol):
        # 1. 獲取數據
        # 2. 計算指標
        # 3. 回傳訊號 (Buy/Sell) 或 None
        pass
```

---

## ⚠️ 免責聲明

**使用風險自負。**

本軟體僅供教學與研究用途。加密貨幣交易涉及高度風險，並不適合所有投資者。作者與貢獻者不對使用本軟體造成的任何財務損失負責。在投入真實資金前，請務必在模擬環境中進行充分測試。
