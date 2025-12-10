import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from composite_backtest import CompositeBacktester
from strategies.supertrend_strategy import SupertrendStrategy
from strategies.supertrend_optimized import SupertrendOptimizedStrategy
from strategies.bollinger_reversion import BollingerReversionStrategy
from strategies.breakout_trend import BreakoutTrendStrategy

# Configuration
TREND_TF = "4h"
ENTRY_TF = "1h"
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
COINS = ["ETH", "SOL", "ADA", "BTC", "BNB", "DOGE", "AVAX", "LINK", "LTC", "NEO"]

# Cost/Slippage scenarios
SCENARIOS = [
    {"label": "base", "fee_rate": 0.0005, "slippage": 0.0002},
    {"label": "stress", "fee_rate": 0.0010, "slippage": 0.0005},
]

# Filter thresholds
FILTER_THRESHOLDS = {"profit_factor": 1.2, "trades": 8, "sharpe": 0}

# Rolling window length (years)
ROLLING_YEARS = 3

# Plotting
PLOT_TOP_N = 8              # individual equity plots
PORTFOLIO_TOP_N = 5         # portfolio built from top N (by total_return) in base scenario

# Strategy sets
STRATEGY_SETS = {
    "supertrend": [SupertrendStrategy(rr=3.5)],
    "supertrend_opt": [SupertrendOptimizedStrategy(rr=3.5)],
    "supertrend_opt_bbr": [SupertrendOptimizedStrategy(rr=3.5), BollingerReversionStrategy(rr=1.5)],
    "breakout": [BreakoutTrendStrategy(rr=2.0)],
}

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_dir = os.path.join(os.path.dirname(project_root), "data")


def run_single_backtest(coin, year, set_name, strat_list, scenario):
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    csv_trend = os.path.join(data_dir, f"{coin}-USDT-USDT_{TREND_TF}.csv")
    csv_entry = os.path.join(data_dir, f"{coin}-USDT-USDT_{ENTRY_TF}.csv")

    if not (os.path.exists(csv_trend) and os.path.exists(csv_entry)):
        print(f"[SKIP] Missing data for {coin} {year}")
        return None, None

    bt = CompositeBacktester(
        csv_trend,
        csv_entry,
        trend_tf=TREND_TF,
        entry_tf=ENTRY_TF,
        start_date=start_date,
        end_date=end_date,
        strategies=strat_list,
        fee_rate=scenario["fee_rate"],
        slippage=scenario["slippage"],
    )
    stats = bt.run(plot=False)
    return stats, bt.equity_curve


def plot_equity_curve(equity_curve, out_path, title):
    if not equity_curve:
        return
    df_eq = pd.DataFrame(equity_curve)
    df_eq["datetime"] = pd.to_datetime(df_eq["timestamp"], unit="ms")
    df_eq.set_index("datetime", inplace=True)
    df_eq["peak"] = df_eq["equity"].cummax()
    df_eq["drawdown"] = (df_eq["equity"] - df_eq["peak"]) / df_eq["peak"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), gridspec_kw={"height_ratios": [2, 1]})
    ax1.plot(df_eq.index, df_eq["equity"], label="Equity", color="#1f77b4")
    ax1.set_title(title)
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    ax2.fill_between(df_eq.index, df_eq["drawdown"], 0, color="#d62728", alpha=0.3)
    ax2.set_title("Drawdown")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path)
    plt.close(fig)


def aggregate_rolling(df, window):
    rows = []
    df_sorted = df.sort_values(["coin", "strategy_set", "year"])
    for (coin, strat), g in df_sorted.groupby(["coin", "strategy_set"]):
        years = sorted(g["year"].unique())
        for i in range(len(years) - window + 1):
            win_years = years[i : i + window]
            sub = g[g["year"].isin(win_years)]
            if sub.empty:
                continue
            geom = np.prod(1 + sub["total_return"].values / 100) - 1
            trades = sub["trades"].sum()
            pf = np.average(sub["profit_factor"], weights=sub["trades"]) if trades > 0 else 0
            sharpe = np.average(sub["sharpe"], weights=sub["trades"]) if trades > 0 else 0
            rows.append({
                "coin": coin,
                "strategy_set": strat,
                "years": f"{win_years[0]}-{win_years[-1]}",
                "total_return_pct": geom * 100,
                "profit_factor": pf,
                "sharpe": sharpe,
                "trades": trades,
            })
    return pd.DataFrame(rows)


def build_portfolio_equity(eq_curves, candidates, initial_equity=1000):
    series_list = []
    for key in candidates:
        curve = eq_curves.get(key)
        if not curve:
            continue
        df = pd.DataFrame(curve)
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.drop_duplicates(subset=["datetime"], keep="last")
        df.set_index("datetime", inplace=True)
        start_val = df["equity"].iloc[0]
        df["norm"] = df["equity"] / start_val
        series_list.append(df[["norm"]])
    if not series_list:
        return None
    all_idx = series_list[0].index
    for s in series_list[1:]:
        all_idx = all_idx.union(s.index)
    aligned = [s.reindex(all_idx).ffill() for s in series_list]
    combo = pd.concat(aligned, axis=1)
    combo.columns = [f"c{i}" for i in range(len(series_list))]
    combo["portfolio_equity"] = combo.mean(axis=1) * initial_equity
    combo.reset_index(inplace=True)
    combo.rename(columns={"datetime": "timestamp"}, inplace=True)
    return combo


def main():
    results = []
    equity_store = {}

    for scenario in SCENARIOS:
        label = scenario["label"]
        print(f"===== Scenario: {label} | fee {scenario['fee_rate']} | slippage {scenario['slippage']} =====")
        for coin in COINS:
            for year in YEARS:
                for set_name, strat_list in STRATEGY_SETS.items():
                    try:
                        stats, eq_curve = run_single_backtest(coin, year, set_name, strat_list, scenario)
                        if stats is None:
                            continue
                        results.append({
                            "scenario": label,
                            "coin": coin,
                            "year": year,
                            "strategy_set": set_name,
                            "total_return": stats.get("total_return"),
                            "profit_factor": stats.get("profit_factor"),
                            "win_rate": stats.get("win_rate"),
                            "max_dd_pct": stats.get("max_dd", 0) * 100,
                            "sharpe": stats.get("sharpe_ratio"),
                            "trades": stats.get("total_trades"),
                        })
                        equity_store[(label, coin, year, set_name)] = eq_curve
                    except Exception as e:
                        print(f"[ERROR] {coin} {year} {set_name} ({label}): {e}")
                        continue

    if not results:
        print("❌ No results generated. Check data files and configuration.")
        return

    out_dir = os.path.dirname(__file__)
    df = pd.DataFrame(results)
    out_path = os.path.join(out_dir, "multi_backtest_results.csv")
    df.to_csv(out_path, index=False)
    print(f"✅ Saved results to {out_path}")

    for scenario in SCENARIOS:
        label = scenario["label"]
        df_s = df[df["scenario"] == label]
        mask = (
            (df_s["profit_factor"] > FILTER_THRESHOLDS["profit_factor"])
            & (df_s["trades"] >= FILTER_THRESHOLDS["trades"])
            & (df_s["sharpe"] > FILTER_THRESHOLDS["sharpe"])
        )
        filtered = df_s[mask].copy().sort_values(["coin", "year", "strategy_set"])
        filtered_path = os.path.join(out_dir, f"multi_backtest_filtered_{label}.csv")
        filtered.to_csv(filtered_path, index=False)
        print(f"✅ Saved filtered results to {filtered_path} ({len(filtered)} rows)")
        if not filtered.empty:
            cols = ["coin", "year", "strategy_set", "total_return", "profit_factor", "sharpe", "trades", "max_dd_pct"]
            print(f"Filtered overview ({label}):")
            print(filtered[cols].to_string(index=False))
        else:
            print(f"⚠️ Scenario {label}: no rows matched filter.")

        rolling_df = aggregate_rolling(df_s, ROLLING_YEARS)
        if not rolling_df.empty:
            roll_path = os.path.join(out_dir, f"multi_backtest_rolling_{label}.csv")
            rolling_df.to_csv(roll_path, index=False)
            print(f"✅ Saved rolling stats to {roll_path}")

    plot_dir = os.path.join(out_dir, "plots")
    os.makedirs(plot_dir, exist_ok=True)
    base_df = df[df["scenario"] == "base"].copy()
    top_for_plot = base_df.sort_values("total_return", ascending=False).head(PLOT_TOP_N)
    for _, row in top_for_plot.iterrows():
        key = ("base", row["coin"], row["year"], row["strategy_set"])
        curve = equity_store.get(key)
        if not curve:
            continue
        fname = f"plot_{row['coin']}_{row['year']}_{row['strategy_set']}.png"
        plot_equity_curve(curve, os.path.join(plot_dir, fname), f"{row['coin']} {row['year']} {row['strategy_set']} (base)")

    filtered_base_path = os.path.join(out_dir, "multi_backtest_filtered_base.csv")
    filtered_base = pd.read_csv(filtered_base_path) if os.path.exists(filtered_base_path) else pd.DataFrame()
    if not filtered_base.empty:
        filtered_base = filtered_base.sort_values("total_return", ascending=False).head(PORTFOLIO_TOP_N)
        candidate_keys = [("base", r["coin"], r["year"], r["strategy_set"]) for _, r in filtered_base.iterrows()]
        portfolio_df = build_portfolio_equity(equity_store, candidate_keys)
        if portfolio_df is not None:
            port_path = os.path.join(out_dir, "portfolio_equity_base.csv")
            portfolio_df.to_csv(port_path, index=False)
            print(f"✅ Saved portfolio equity to {port_path}")
            fig, ax = plt.subplots(figsize=(11, 5))
            dt = pd.to_datetime(portfolio_df["timestamp"])
            ax.plot(dt, portfolio_df["portfolio_equity"], label="Portfolio (eq-weight)")
            ax.set_title("Portfolio Equity (base top selections)")
            ax.grid(True, alpha=0.3)
            ax.legend()
            plt.tight_layout()
            port_plot_path = os.path.join(plot_dir, "portfolio_base.png")
            plt.savefig(port_plot_path)
            plt.close(fig)
            print(f"✅ Saved portfolio plot to {port_plot_path}")
        else:
            print("⚠️ Portfolio build skipped (no equity curves).")
    else:
        print("⚠️ No filtered base rows; portfolio not built.")


if __name__ == "__main__":
    main()
