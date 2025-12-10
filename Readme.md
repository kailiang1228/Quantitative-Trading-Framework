# 📈 Quantitative Trading Framework

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A professional, modular, and event-driven quantitative trading framework engineered for **OKX Perpetual Futures (USDT-M)**.

Unlike simple scripts, this framework is built with **production safety** and **extensibility** in mind. It handles the complexities of real-world trading—such as network instability, exchange API quirks, and strict risk management—allowing you to focus purely on strategy logic.

> **中文說明 (Chinese Version)**: Please refer to [README_CN.md](README_CN.md).

---

## 🌟 Key Features

### 🛡️ Production-Grade Reliability
*   **Atomic Order Execution**: Utilizes OKX's `attachAlgoOrds` to place Entry, Take-Profit (TP), and Stop-Loss (SL) orders in a single API call. This eliminates the risk of "naked positions" caused by network failures between requests.
*   **State Persistence**: Automatically saves position state to a local JSON database (`positions_db.json`). The bot can be restarted at any time without losing track of active trades or entry prices.
*   **Robust Error Handling**: Built-in retry mechanisms and comprehensive logging for API interactions.

### ⚡ High-Fidelity Backtesting
*   **Real-Cost Simulation**: Backtesting engine accounts for **Taker Fees**, **Slippage**, and **Funding Rates**, providing realistic performance metrics rather than theoretical gains.
*   **Multi-Strategy Support**: Run multiple strategies simultaneously in a composite backtest to evaluate portfolio performance.
*   **Detailed Reporting**: Generates equity curves, drawdown analysis, and trade logs.

### 🧩 Modular Architecture
*   **Decoupled Logic**: Strategies, Risk Management, and Execution are separated. Adding a new strategy is as simple as adding a file to the `strategies/` folder.
*   **Event-Driven Core**: The main loop efficiently handles data fetching, signal generation, and order management.

### ⚖️ Advanced Risk Management
*   **Dynamic Position Sizing**: Calculates trade size based on account equity and configured risk percentage per trade.
*   **Capital Protection**: Configurable maximum drawdown limits and margin ratio caps.

---

## 📂 Project Structure

```text
Quantitative-Trading-Framework/
├── main.py                  # 🚀 Entry point for the trading bot
├── config.py                # ⚙️ Global configuration (Risk, API, Timeframes)
├── exchange_api.py          # 🏦 Wrapper for OKX API (REST + Public Data)
│
├── core/                    # 🧠 Core System Logic
│   ├── quant_bot.py         # Main event loop & strategy dispatcher
│   ├── risk_manager.py      # Position sizing & risk checks
│   ├── order_manager.py     # Order execution & verification
│   └── persistence.py       # JSON-based state saving/loading
│
├── strategies/              # 📈 Strategy Implementation
│   ├── supertrend_strategy.py    # Example: Trend Following
│   ├── bollinger_reversion.py    # Example: Mean Reversion
│   └── ... (Add your own)
│
├── backtest/                # 📊 Backtesting Engine
│   ├── composite_backtest.py     # Main backtesting script
│   ├── simple_backtest.py        # Simplified version for learning
│   └── generate_report.py        # Visualization tools
│
└── data/                    # 💾 Data Storage
    └── positions_db.json    # Active position state (auto-generated)
```

## 🚀 Getting Started

### 1. Prerequisites
*   Python 3.10 or higher
*   An OKX account (for live/simulation trading)

### 2. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/yourusername/Quantitative-Trading-Framework.git
cd Quantitative-Trading-Framework
pip install -r requirements.txt
```

### 3. Configuration
Edit `config.py` to set your preferences.
*   **Risk Settings**: Adjust `RISK_PER_TRADE` (default 2%) and `LEVERAGE`.
*   **API Keys**: Set your OKX API keys via environment variables (Recommended) or directly in the file for testing.

```python
# Example in config.py
API_KEY = os.getenv("OKX_API_KEY")
IS_SIMULATION = True  # Set to False for real trading
```

### 4. Running Backtests
Validate your strategy with historical data before going live.
```bash
# Ensure you have CSV data in the data/ folder (format: timestamp, open, high, low, close, volume)
python backtest/composite_backtest.py
```

### 5. Running the Bot
Start the bot in simulation mode (default) or live mode.
```bash
python main.py
```

---

## 🧠 Included Strategies

The framework comes with two core strategy templates to get you started. These are designed to be simple yet effective foundations for more complex logic.

### 1. Supertrend Strategy (Trend Following)
*   **Concept**: A classic trend-following system designed to capture large directional moves in the market. It assumes that once a trend is established, it is more likely to continue than to reverse.
*   **Entry Logic**:
    *   **Long**: Enters when the price closes **above** the Supertrend line, indicating a bullish trend reversal.
    *   **Short**: Enters when the price closes **below** the Supertrend line, indicating a bearish trend reversal.
*   **Exit Logic**:
    *   **Stop Loss**: Dynamic. The Stop Loss trails along the Supertrend line itself, locking in profits as the trend progresses.
    *   **Take Profit**: Calculated based on a fixed Risk-Reward Ratio (e.g., 2:1) relative to the initial stop loss distance.

### 2. Bollinger Mean Reversion (Oscillator)
*   **Concept**: A counter-trend strategy designed for ranging or sideways markets. It assumes that prices are elastic and will revert to the mean (average) after hitting extreme levels.
*   **Entry Logic**:
    *   **Long**: Enters when the price touches or breaks below the **Lower Bollinger Band**, indicating an oversold condition.
    *   **Short**: Enters when the price touches or breaks above the **Upper Bollinger Band**, indicating an overbought condition.
*   **Exit Logic**:
    *   **Take Profit**: Placed at the **Middle Band** (Moving Average), representing the equilibrium price.
    *   **Stop Loss**: Placed at a multiple of ATR (Average True Range) beyond the entry band to allow for market noise.

---

## 🛠️ Developing New Strategies

To create a new strategy, add a Python file in `strategies/` and implement the `analyze` method.

```python
# strategies/my_custom_strategy.py
class MyCustomStrategy:
    def __init__(self):
        self.name = "MyStrategy"

    def analyze(self, api, symbol):
        # 1. Fetch data
        # 2. Calculate indicators
        # 3. Return signal (Buy/Sell) or None
        pass
```

---

## ⚠️ Disclaimer

**USE AT YOUR OWN RISK.**

This software is for educational and research purposes only. Cryptocurrency trading involves substantial risk of loss and is not suitable for every investor. The authors and contributors are not responsible for any financial losses incurred through the use of this software. Always test thoroughly in simulation mode before risking real capital.
