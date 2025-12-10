import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Data from the user's prompt
data_base = [
    {"coin": "ADA", "year": 2024, "strategy_set": "supertrend", "total_return": 23.064176, "profit_factor": 1.957583, "sharpe": 1.559412, "trades": 34, "max_dd_pct": 6.948232},
    {"coin": "ADA", "year": 2024, "strategy_set": "supertrend_opt", "total_return": 12.224992, "profit_factor": 1.428345, "sharpe": 0.807366, "trades": 27, "max_dd_pct": 9.433015},
    {"coin": "AVAX", "year": 2022, "strategy_set": "supertrend", "total_return": 9.058794, "profit_factor": 1.237868, "sharpe": 0.685735, "trades": 39, "max_dd_pct": 12.616781},
    {"coin": "AVAX", "year": 2022, "strategy_set": "supertrend_opt", "total_return": 19.276543, "profit_factor": 1.727537, "sharpe": 1.312744, "trades": 24, "max_dd_pct": 12.728202},
    {"coin": "AVAX", "year": 2022, "strategy_set": "supertrend_opt_bbr", "total_return": 24.137800, "profit_factor": 1.637963, "sharpe": 1.407279, "trades": 37, "max_dd_pct": 15.826876},
    {"coin": "AVAX", "year": 2024, "strategy_set": "supertrend_opt", "total_return": 9.797716, "profit_factor": 1.405811, "sharpe": 0.719601, "trades": 23, "max_dd_pct": 9.509099},
    {"coin": "AVAX", "year": 2025, "strategy_set": "supertrend", "total_return": 9.369451, "profit_factor": 1.331560, "sharpe": 1.073892, "trades": 35, "max_dd_pct": 8.087200},
    {"coin": "BTC", "year": 2020, "strategy_set": "breakout", "total_return": 26.705843, "profit_factor": 1.333492, "sharpe": 1.169929, "trades": 99, "max_dd_pct": 9.525508},
    {"coin": "BTC", "year": 2022, "strategy_set": "breakout", "total_return": 23.881480, "profit_factor": 1.400505, "sharpe": 1.153227, "trades": 74, "max_dd_pct": 15.087068},
    {"coin": "BTC", "year": 2024, "strategy_set": "breakout", "total_return": 26.489855, "profit_factor": 1.293464, "sharpe": 1.064082, "trades": 97, "max_dd_pct": 20.357161},
    {"coin": "BTC", "year": 2024, "strategy_set": "supertrend_opt", "total_return": 1.749204, "profit_factor": 1.205935, "sharpe": 0.246778, "trades": 9, "max_dd_pct": 8.952066},
    {"coin": "BTC", "year": 2025, "strategy_set": "breakout", "total_return": 49.521761, "profit_factor": 1.647252, "sharpe": 2.021517, "trades": 82, "max_dd_pct": 13.257986},
    {"coin": "DOGE", "year": 2022, "strategy_set": "supertrend_opt", "total_return": 25.103847, "profit_factor": 2.740457, "sharpe": 1.624030, "trades": 15, "max_dd_pct": 8.649983},
    {"coin": "DOGE", "year": 2022, "strategy_set": "supertrend_opt_bbr", "total_return": 31.884201, "profit_factor": 2.373248, "sharpe": 1.827263, "trades": 24, "max_dd_pct": 8.045726},
    {"coin": "ETH", "year": 2020, "strategy_set": "breakout", "total_return": 27.938332, "profit_factor": 1.370585, "sharpe": 1.190692, "trades": 90, "max_dd_pct": 14.305740},
    {"coin": "ETH", "year": 2021, "strategy_set": "breakout", "total_return": 20.476359, "profit_factor": 1.350421, "sharpe": 0.902734, "trades": 75, "max_dd_pct": 25.812868},
    {"coin": "ETH", "year": 2022, "strategy_set": "breakout", "total_return": 43.781690, "profit_factor": 1.714189, "sharpe": 1.693063, "trades": 77, "max_dd_pct": 11.402210},
    {"coin": "ETH", "year": 2023, "strategy_set": "breakout", "total_return": 89.102838, "profit_factor": 2.295146, "sharpe": 2.463759, "trades": 80, "max_dd_pct": 9.417598},
    {"coin": "ETH", "year": 2023, "strategy_set": "supertrend", "total_return": 2.183939, "profit_factor": 1.201283, "sharpe": 0.269918, "trades": 11, "max_dd_pct": 15.421199},
    {"coin": "ETH", "year": 2023, "strategy_set": "supertrend_opt_bbr", "total_return": 4.174578, "profit_factor": 1.245220, "sharpe": 0.388346, "trades": 15, "max_dd_pct": 21.503893},
    {"coin": "ETH", "year": 2024, "strategy_set": "breakout", "total_return": 25.415711, "profit_factor": 1.436993, "sharpe": 1.229965, "trades": 77, "max_dd_pct": 9.372425},
    {"coin": "ETH", "year": 2024, "strategy_set": "supertrend", "total_return": 4.025572, "profit_factor": 1.829099, "sharpe": 0.634939, "trades": 9, "max_dd_pct": 4.275497},
    {"coin": "ETH", "year": 2024, "strategy_set": "supertrend_opt_bbr", "total_return": 14.327283, "profit_factor": 2.095337, "sharpe": 1.252144, "trades": 16, "max_dd_pct": 5.287511},
    {"coin": "ETH", "year": 2025, "strategy_set": "breakout", "total_return": 27.646862, "profit_factor": 1.387380, "sharpe": 1.206559, "trades": 85, "max_dd_pct": 17.596440},
    {"coin": "ETH", "year": 2025, "strategy_set": "supertrend_opt_bbr", "total_return": 6.853761, "profit_factor": 1.777701, "sharpe": 0.764049, "trades": 12, "max_dd_pct": 6.392017},
    {"coin": "LINK", "year": 2025, "strategy_set": "supertrend", "total_return": 27.604678, "profit_factor": 2.198500, "sharpe": 2.064883, "trades": 25, "max_dd_pct": 10.515438},
    {"coin": "LINK", "year": 2025, "strategy_set": "supertrend_opt", "total_return": 16.501822, "profit_factor": 1.692037, "sharpe": 1.034763, "trades": 19, "max_dd_pct": 8.744131},
    {"coin": "LINK", "year": 2025, "strategy_set": "supertrend_opt_bbr", "total_return": 13.972869, "profit_factor": 1.390918, "sharpe": 0.841646, "trades": 32, "max_dd_pct": 10.403504},
    {"coin": "LTC", "year": 2023, "strategy_set": "supertrend", "total_return": 5.931615, "profit_factor": 1.212886, "sharpe": 0.461021, "trades": 33, "max_dd_pct": 9.881764},
    {"coin": "SOL", "year": 2024, "strategy_set": "supertrend_opt", "total_return": 7.119004, "profit_factor": 1.300335, "sharpe": 0.569688, "trades": 22, "max_dd_pct": 14.033711},
    {"coin": "SOL", "year": 2025, "strategy_set": "supertrend", "total_return": 27.733757, "profit_factor": 1.782958, "sharpe": 1.524345, "trades": 38, "max_dd_pct": 9.477451},
    {"coin": "SOL", "year": 2025, "strategy_set": "supertrend_opt", "total_return": 12.037131, "profit_factor": 1.347531, "sharpe": 0.765360, "trades": 29, "max_dd_pct": 15.218106}
]

df = pd.DataFrame(data_base)

# Create output directory
output_dir = r"D:\Lesson_CODE\code\TRADING\Quant_V6_G\backtest\plots"
os.makedirs(output_dir, exist_ok=True)

# 1. Save CSV
csv_path = os.path.join(output_dir, "backtest_summary_readable.csv")
df.to_csv(csv_path, index=False)
print(f"Saved CSV to {csv_path}")

# 2. Create Visualization
# We want to show Profit Factor and Total Return for the best strategy per coin/year
# Filter to get the best strategy per coin (based on Sharpe or Total Return)
# Let's pick the best strategy for each coin based on average Sharpe across years
best_strategies = df.groupby(['coin', 'strategy_set'])['sharpe'].mean().reset_index()
best_strategies = best_strategies.sort_values(['coin', 'sharpe'], ascending=[True, False])
best_strategies = best_strategies.drop_duplicates(subset=['coin'], keep='first')

# Filter original df to only include these best strategies
df_best = df.merge(best_strategies[['coin', 'strategy_set']], on=['coin', 'strategy_set'])

# Plot 1: Total Return by Coin & Year (Best Strategy)
plt.figure(figsize=(12, 6))
sns.barplot(data=df_best, x='coin', y='total_return', hue='year', palette='viridis')
plt.title('Total Return (%) by Coin (Best Strategy)')
plt.ylabel('Total Return (%)')
plt.xlabel('Coin')
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "total_return_summary.png"))
plt.close()

# Plot 2: Profit Factor vs Sharpe (Scatter)
plt.figure(figsize=(10, 6))
sns.scatterplot(data=df, x='profit_factor', y='sharpe', hue='coin', style='strategy_set', s=100)
plt.title('Profit Factor vs Sharpe Ratio (All Strategies)')
plt.axvline(x=1.2, color='r', linestyle='--', label='Min PF 1.2')
plt.axhline(y=1.0, color='g', linestyle='--', label='Min Sharpe 1.0')
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig(os.path.join(output_dir, "risk_reward_scatter.png"))
plt.close()

print("Charts generated successfully.")
