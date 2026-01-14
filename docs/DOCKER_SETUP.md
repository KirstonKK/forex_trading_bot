# Docker Setup - Forex Trading Bot Developer Edition

**Share this entire repository with other developers.** They can run everything in Docker without any setup!

## Prerequisites

- Docker Desktop installed ([download here](https://www.docker.com/products/docker-desktop))
- ~2GB disk space
- ~5 minutes first run, <30 seconds subsequent runs

## Quick Start (30 seconds)

```bash
# Clone or download the repo, then:
cd forex_trading_bot

# Build and run backtests
docker-compose up --build

# View results in terminal output
```

That's it! No Python installation, no dependencies, nothing. Docker handles everything.

## What's Inside

- ✅ Python 3.9 environment
- ✅ All ML/data science libraries (TensorFlow, LightGBM, pandas)
- ✅ SQLite for trade journals
- ✅ Complete backtesting framework
- ✅ SMC strategy implementation
- ✅ Risk management system

## Common Commands

### Run Quick Backtest (200 days, 2 minutes)

```bash
docker-compose up --build
```

### Run Realistic Backtest (2 weeks, 5 minutes)

```bash
docker-compose run forex_bot python3 backtests/scripts/backtest_realistic_live.py
```

### Run All Backtests

```bash
docker-compose run forex_bot python3 backtests/scripts/backtest_runner.py
```

### Interactive Shell (Debug Mode)

```bash
docker-compose run forex_bot bash
# Now you're inside the container
python3 -c "from core.smc_strategy import SMCStrategy; print('SMC loaded!')"
```

### Check Trade Results

```bash
# View trades from latest backtest
sqlite3 data/live_journal.db "SELECT * FROM trades ORDER BY entry_time DESC LIMIT 10;"

# Or with Docker:
docker-compose exec forex_bot sqlite3 data/live_journal.db "SELECT symbol, direction, entry_price, stop_loss, take_profit FROM trades LIMIT 5;"
```

### View Real-Time Logs

```bash
docker-compose logs -f
```

## Files Explained

```
├── Dockerfile              # Linux Python 3.9 environment
├── docker-compose.yml      # Docker configuration
├── .dockerignore          # Files to exclude from image
├── requirements.txt       # Python dependencies
│
├── core/                  # Strategy & risk management
│   ├── smc_strategy.py    # SMC pattern recognition
│   └── enhanced_risk_manager.py
│
├── backtesting/           # Backtest framework
│   ├── backtest_engine.py
│   ├── data_fetcher.py
│   └── scripts/
│       ├── run_quick_backtest.py   # ← Main entry point
│       ├── backtest_realistic_live.py
│       └── backtest_runner.py
│
├── machine_learning/      # ML models
│   ├── feature_engineering.py
│   └── models/
│       ├── lstm_price_predictor.py
│       └── trade_predictor.py
│
├── database/              # Data persistence
│   ├── journal.py
│   ├── timeseries.py
│   └── trades.py
│
└── data/                  # Output directory (auto-created)
    └── live_journal.db    # Trade history
```

## Development Workflow

### For Single Dev Modifications:

1. **Edit code** (e.g., change SMC parameters)

   ```bash
   # Edit core/smc_strategy.py locally
   vim core/smc_strategy.py
   ```

2. **Rebuild and test**

   ```bash
   docker-compose up --build
   ```

3. **Check results**
   ```bash
   sqlite3 data/live_journal.db "SELECT COUNT(*) FROM trades;"
   ```

### For Team Collaboration:

1. **Share via Git**

   ```bash
   git add .
   git commit -m "Updated SMC signal strength filter"
   git push
   ```

2. **Team member pulls and runs**

   ```bash
   git pull
   docker-compose up --build
   ```

3. **Compare results** (trade journals are in `data/`)
   ```bash
   sqlite3 data/live_journal.db "SELECT * FROM trades;"
   ```

## Performance Benchmarks

| Test                | Duration            | Trades Generated | Docker Time |
| ------------------- | ------------------- | ---------------- | ----------- |
| Quick (200 days)    | 2 min               | 50-100           | 2 min       |
| Realistic (2 weeks) | 1.5 hours simulated | 10-50            | 5 min       |
| Full (1 year)       | 6 hours simulated   | 100-300          | 15 min      |

## Troubleshooting

### "Cannot find image"

```bash
docker-compose down -v  # Clean up
docker-compose up --build  # Rebuild
```

### "Permission denied /app/data"

```bash
chmod -R 755 data/
docker-compose up --build
```

### "Out of disk space"

```bash
docker system prune -a  # Clean unused images
docker-compose up --build
```

### "Python module not found"

```bash
# Rebuild to ensure dependencies are fresh
docker-compose down -v
docker-compose up --build
```

## Testing Different Strategies

### Test SMC with stricter signal filters:

```bash
# Edit core/smc_strategy.py (change signal_strength_threshold = 0.75)
vim core/smc_strategy.py

# Rebuild and test
docker-compose up --build
```

### Test different timeframes:

```bash
# Edit backtests/scripts/run_quick_backtest.py
vim backtests/scripts/run_quick_backtest.py

# Change: timeframe = "M5" to "H1" or "D1"
# Rebuild and run
docker-compose up --build
```

## Advanced: Custom Backtests

Run with your own parameters:

```bash
docker-compose run forex_bot python3 << 'EOF'
from backtesting.backtest_engine import BacktestEngine
from core.smc_strategy import SMCStrategy
from core.enhanced_risk_manager import EnhancedRiskManager

# Your custom test
engine = BacktestEngine(
    initial_balance=50000,
    strategy=SMCStrategy(),
    risk_manager=EnhancedRiskManager(0.01),
    symbols=['EURUSD', 'GBPUSD'],
)

results = engine.run(days=100)
print(f"Win Rate: {results['win_rate']:.2%}")
print(f"Total P&L: ${results['total_pnl']:.2f}")
EOF
```

## Cleanup

```bash
# Stop containers
docker-compose down

# Remove all data (⚠️ be careful!)
docker-compose down -v

# Remove image completely
docker rmi forex_trading_bot:latest

# Clean all Docker resources
docker system prune -a
```

## What's NOT Included (Live Trading)

This Docker image is for **backtesting only**. For live trading, you need:

- **MetaTrader5** (Windows/Linux only, not in Docker)
- **VPS** (to run MT5 24/7)
- **Actual API credentials**

See `MT5_SETUP.md` for live trading setup.

## Tips for Teams

### Share Strategy Improvements

```bash
# Save your backtest results
cp data/live_journal.db data/backtest_results_$(date +%Y%m%d).db

# Commit to git
git add data/backtest_results_*.db
git commit -m "SMC backtest results with 0.75 signal threshold"
git push
```

### Compare Strategies

```bash
# Team member downloads and runs
git pull
docker-compose up --build

# Compare with their results
sqlite3 data/backtest_results_20260114.db "SELECT COUNT(*) as total_trades, SUM(CASE WHEN status='closed_win' THEN 1 ELSE 0 END) as wins FROM trades;"
sqlite3 data/live_journal.db "SELECT COUNT(*) as total_trades, SUM(CASE WHEN status='closed_win' THEN 1 ELSE 0 END) as wins FROM trades;"
```

## Support

- **Docker Issues**: Check [Docker Docs](https://docs.docker.com/)
- **Python Errors**: Check bot logs with `docker-compose logs -f`
- **Strategy Questions**: See `README.md` for strategy explanation
- **Code Help**: See inline comments in `core/smc_strategy.py`

---

**Happy backtesting!** 📊🚀
