# 📈 Quant_V6_G — Institutional-Grade High-Frequency Trading System

**Quant_V6_G** is an **Institutional-Grade High-Frequency Trading System (HFT-Lite)** designed for **OKX Perpetual Futures (USDT-M)**.
This system has been rigorously validated through "Real-Cost Backtesting," deeply optimized for **0.05% Taker Fees** and **Slippage**, focusing on generating Alpha through high-frequency swing strategies even after deducting trading costs.

> **中文說明 (Chinese Version)**: Please refer to [README_CN.md](README_CN.md) for the traditional Chinese documentation.

---

## 🚀 Core Advantages (核心優勢)

### ⚡ High Frequency & Low Latency (高頻與低延遲)
*   **1H Trend + 15m Entry**: Compared to traditional 4H strategies, this system reacts 4x faster, capturing intraday medium-term swings.
*   **HFT Parameter Tuning**: Optimized Supertrend (10, 3.0) and Bollinger (2.0 Std) parameters ensure rapid position building when volatility arrives.

### 🛡️ Real-Cost Defense (真實成本防禦)
To combat the two killers of HFT—**Fees** and **False Breakouts**—the system includes multiple filtering mechanisms:
*   **Dead Market Filter**: Forcefully stops trading when Bollinger Bandwidth < 2% to avoid fee erosion in stagnant markets.
*   **Candle Body Filter**: Filters out Doji and long wicks to prevent false breakouts; only full-bodied candles trigger signals.
*   **Funding Rate Protection**: Automatically calculates Funding Fees during holding periods to avoid holding high-fee positions for too long.

### 🧠 Adaptive Regime Detection (自適應市場感知)
The system features a built-in `RegimeDetector` module that analyzes market entropy in real-time:
*   **Trending**: Activates **Supertrend** strategy when ADX > 20 and volatility expands.
*   **Ranging**: Switches to **Bollinger Reversion** strategy when ADX < 20 and Bandwidth converges.

---

## 🧱 System Architecture (系統架構)

Modular design ensures high scalability and maintainability:

```text
Quant_V6_G/
├── main.py                  # 🚀 System Entry Point
├── config.py                # ⚙️ Configuration (VIP Rates, Risk)
├── exchange_api.py          # 🏦 OKX API Wrapper (OI/Funding)
│
├── core/                    # 🧠 Core Layer
│   ├── quant_bot.py         # Main Loop (Strategy Dispatcher)
│   ├── regime_detector.py   # Market Regime Analysis
│   ├── risk_manager.py      # Risk Engine (Position Sizing)
│   └── order_manager.py     # Order Execution (OCO / Ghost Order Cleaning)
│
├── strategies/              # 📈 Strategy Library
│   ├── supertrend_strategy.py    # [Trend] HFT Supertrend (10, 3.0)
│   ├── bollinger_reversion.py    # [MeanRev] Dynamic Bollinger (w/ Dead Market Filter)
│   └── meme_breakout_strategy.py # [Alpha] Meme Coin Breakout
│
├── backtest/                # 🧪 Backtest Lab
│   ├── batch_backtest.py    # Batch Backtest (Real Fee/Slippage Sim)
│   └── composite_backtest.py# Composite Strategy Engine
│
└── utils/                   # 🛠️ Utilities
    ├── trade_recorder.py    # CSV Audit Logging
    └── logger_util.py       # Telegram Real-time Alerts
```

---

## 📈 Strategy Logic (策略邏輯)

### 1. Supertrend Strategy (Trend Legion)
*   **Logic**: 1H for major trend (EMA 50), 15m Supertrend (10, 3.0) for entry.
*   **Filters**:
    *   **ADX > 20**: Ensures momentum exists.
    *   **Candle Body > 0.3 ATR**: Rejects false breakouts.
*   **Target**: BTC, ETH, SOL, and other major coins with strong trends.

### 2. Bollinger Reversion (Reversion Legion)
*   **Logic**: Deep pullback trading aligned with the major trend (1H EMA). Long when price touches the lower Bollinger Band (2.0 Std) in an uptrend.
*   **Filters**:
    *   **Bandwidth > 2%**: Rejects dead markets.
    *   **RSI < 30 / > 70**: Confirms extreme sentiment.
*   **Target**: Slow bull markets with upward oscillation.

### 3. Meme Breakout (Special Forces)
*   **Logic**: Designed for high-volatility coins like DOGE, PEPE.
*   **Condition**: Keltner Channel Breakout + Volume Explosion (> 2.0x Avg Vol).
*   **Risk Control**: Tight Stop Loss (1.5 ATR), aiming for 10x returns.

---

## ⚙️ Installation & Deployment (安裝與部署)

### 1. Environment Setup
Ensure Python 3.8+ is installed, then install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Data Preparation
The system relies on historical data for backtesting and analysis:
```bash
# 1. Download OHLCV, Funding Rates, Open Interest (Auto-fetches Top 20)
python download_data.py
```

### 3. Configuration
Copy `config_template.py` to `config.py` and fill in your OKX API credentials and risk settings:

```bash
cp config_template.py config.py
```

```python
# config.py

# 1. API Settings
OKX_API_KEY = "your_api_key"
OKX_SECRET = "your_secret"
OKX_PASSWORD = "your_password"
USE_TESTNET = False  # Recommended: True for simulation first

# 2. Risk Settings
RISK_PER_TRADE = 0.02      # 2% Risk per trade
MAX_TOTAL_MARGIN_RATIO = 0.6 # Max Total Margin 60%
```

### 4. Launch Bot
```bash
python main.py
```

---

## 🧪 Backtesting System (回測系統)

This system includes the industry's strictest backtesting module, rejecting "Happy Path Simulations":

### Batch Backtest
Simulates real market friction costs to verify if the strategy remains profitable after fees.
*   **Fee Rate**: 0.05% (Taker)
*   **Slippage**: 0.02%
*   **Funding**: Dynamic Calculation

```bash
python Quant_V6_G/backtest/batch_backtest.py
```
*Results are automatically sorted into `batch_backtest_results.csv`. Coins with PF > 1.1 are recommended for the whitelist.*

---

## ⚠️ Disclaimer (免責聲明)

This software is for educational and research purposes only. Cryptocurrency trading involves high risk and may result in the total loss of funds.
**The developer is not responsible for any profits or losses generated by using this system.** Please ensure you fully test on a Testnet before trading with real capital.

