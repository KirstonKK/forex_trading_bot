# Forex Trading Bot - SMC Strategy

Pure forex trading bot implementing Smart Money Concepts (SMC) methodology with **live MT5 trading integration**. Built with modular architecture for backtesting, paper trading, and live deployment.

## Quick Start - Live Trading

```bash
# 1. Set up MT5 account credentials
# See: MT5_SETUP.md

# 2. Install dependencies
pip install -r requirements.txt

# 3. Test connection
python3 test_mt5_connection.py

# 4. Run live bot (paper trading)
python3 live_trading_bot.py
```

## Architecture

```
core/
  ├── smc_strategy.py           # SMC pattern: BOS, pullback, entry zones
  ├── enhanced_risk_manager.py  # Risk rules: 1% per trade, daily/weekly limits
  └── trade_executor.py         # Trade lifecycle management

connectors/
  ├── mt5_connector.py          # MT5 API for live data + execution
  ├── forex_api.py              # Generic broker interface
  └── price_feed.py             # Real-time price feeds

database/
  ├── journal.py                # Trade journal with SMC patterns
  ├── timeseries.py             # InfluxDB time series
  └── trades.py                 # Trade history

backtesting/
  ├── backtest_engine.py        # Full backtest engine
  └── data_fetcher.py           # Historical data + synthetic generation

machine_learning/
  ├── feature_engineering.py    # Trade feature extraction
  └── models/
      ├── trade_predictor.py    # LightGBM outcome prediction
      └── lstm_price_predictor.py # LSTM price forecasting

live_trading_bot.py            # Main live trading bot
trading_bot.py                 # Demo/testing orchestrator
```

## Core Strategy: Smart Money Concepts (SMC)

**Pattern**: BOS → Pullback → Entry at High-Probability Zones

- **BOS (Break of Structure)**: Price breaks above previous high or below previous low
- **Pullback Zone**: Retracement after BOS before continuation
- **Entry Zones**:
  - **FVG** (Fair Value Gap): Unfilled price imbalances
  - **Discount Zone**: Retracement 25-75% of move
  - **Order Blocks**: Institutional reversal levels

**Risk Management Rules**:

- Risk per trade: **1%** of account ($100 on $10k)
- Daily loss limit: **1.5%** ($150 on $10k)
- Weekly loss limit: **3%** ($300 on $10k)
- RR minimum: **1.5:1** (profit target 2.0x risk)
- Max trades/day: **2**
- Sessions: London (08:00-17:00 UTC) + NY (13:00-22:00 UTC)

## Features

✅ **Live Trading via MT5**

- Real-time candlestick data
- Market order execution
- Automated stop loss + take profit
- Paper trading (risk-free testing)

✅ **Comprehensive Backtesting**

- 100+ trades per backtest
- Realistic synthetic data generation
- Complete P&L analysis and drawdown metrics
- Trade journal logging with SMC patterns

✅ **Machine Learning**

- LightGBM: Trade outcome prediction
- LSTM: Price sequence forecasting
- Feature engineering from trades

✅ **Trade Journal**

- SQLite persistence
- Pattern tracking (BOS strength, pullback confidence)
- Daily/weekly statistics
- Export capabilities

## Usage

### Live Trading (Paper)

```bash
# 1. Set environment variables with MT5 credentials
export MT5_LOGIN=your_login
export MT5_PASSWORD=your_password
export MT5_SERVER=your_server_name

# Or create a .env file
cat > .env << EOF
MT5_LOGIN=your_login
MT5_PASSWORD=your_password
MT5_SERVER=your_server_name
EOF

# 2. Run bot
python3 live_trading_bot.py
```

### Backtesting

```bash
# Quick sample data backtest (200 days)
cd backtests/scripts
python3 run_quick_backtest.py

# Realistic live data backtest (2 weeks)
python3 backtest_realistic_live.py

# Custom backtest with parameters
python3 backtest_runner.py --symbols EURUSD GBPUSD --days 100
```

### Testing

```bash
# Test Oanda API connection
python3 test_mt5_connection.py

# Test strategy on live prices (demo)
python3 trading_bot.py
```

## Database

- **SQLite**: Trade history, journal, performance metrics
- **InfluxDB** (optional): Time series candlestick + indicator data
- **Files**: backtests/results/ for test artifacts

## Configuration

See `config/config.json` for default settings:

- Account size: $10,000
- Risk per trade: 1%
- Trading pairs: EURUSD, GBPUSD, XAUUSD
- Symbols and timeframes

## Performance

**Backtest Results** (200-day sample data):

- Trades: 1,151
- Win Rate: 89.8%
- Return: ~1500%+ (note: synthetic data unrealistic)
- Max Drawdown: 32.88%

⚠️ _Synthetic data results not realistic - live trading required for validation_

**Live Paper Trading** (recommended):

- Run 24-48 hours first
- Verify signals match strategy rules
- Check journal in `data/live_journal.db`
- Monitor trades in MT5 terminal

## Files

| File                     | Purpose                             |
| ------------------------ | ----------------------------------- |
| `MT5_SETUP.md`           | Step-by-step MT5 account setup      |
| `live_trading_bot.py`    | Main live trading entry point       |
| `test_mt5_connection.py` | Validate MT5 setup before trading   |
| `backtests/README.md`    | Backtesting documentation           |
| `data/`                  | Trade journals and backtest results |

## Requirements

- Python 3.9+
- requests (Oanda API)
- numpy, pandas (analysis)
- tensorflow, lightgbm (ML models)
- sqlite3 (trades database)

## Next Steps

1. ✓ Create MT5 account with credentials (already have)
2. ✓ Set up environment variables (MT5_SETUP.md)
3. ✓ Run `test_mt5_connection.py` (validate)
4. ✓ Start `live_trading_bot.py` (paper trading)
5. ✓ Monitor in MT5 terminal
6. ✓ Review trade journal daily
7. Once profitable: Switch to live (change credentials)

## Important Notes

⚠️ **Always test with paper trading first**

- No real money at risk
- Exact same execution and spreads
- Simulated balance

⚠️ **Strategy disclaimer**

- Back tested results may not reflect live performance
- Past performance ≠ future results
- Market conditions vary
- Use strict risk management

⚠️ **Rate limits**

- Oanda: ~120 requests/min
- Bot respects limits with 5-min polling interval

## Support

- **MT5 API**: https://www.mql5.com/en/articles/6157
- **Python Library**: https://github.com/khramkov/MT5-Python
- **Strategy Help**: SMC (Smart Money Concepts) educational resources
