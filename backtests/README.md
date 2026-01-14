# Backtesting Suite

This directory contains backtest scripts and results for the SMC trading strategy.

## Scripts

### `scripts/run_quick_backtest.py`

Fast backtest with **sample/synthetic data** (no internet required).

- Generates 14,400 candles (200 days × 3 symbols)
- No external dependencies
- Completes in seconds

```bash
cd backtests/scripts && python3 run_quick_backtest.py
```

### `scripts/backtest_live_minimal.py`

Minimal **live data backtest** (2 weeks only).

- Fetches actual forex data from Yahoo Finance
- Tests strategy on real market data
- Minimal resource usage

```bash
cd backtests/scripts && python3 backtest_live_minimal.py
```

### `scripts/backtest_runner.py`

Full **customizable backtest** runner.

- Supports any date range
- Live data from yfinance
- Configurable symbols

```bash
cd backtests/scripts && python3 backtest_runner.py --live
```

## Results

Backtest results are saved to:

- **Journal DB**: `../../data/backtest_journal.db`
  - Individual trades with entry/exit details
  - P&L tracking
  - Pattern statistics

## Configuration

Edit backtest parameters in scripts:

- `account_balance`: Starting capital
- `risk_per_trade`: Risk percentage per trade
- `symbols`: Trading pairs to backtest
- `max_trades_per_day`: Trade frequency limit

## Sample Results

Latest backtest (14,400 candles, 200 days):

- **Total Trades**: 1,113
- **Win Rate**: 87.3%
- **Profit Factor**: 7.48
- **Return**: 152.89%
- **Max Drawdown**: 0.34%
