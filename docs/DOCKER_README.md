# For Developers: Running This In Docker

Just downloaded this repo? Run it instantly without any setup:

```bash
docker-compose up --build
```

That's it! Docker will:

1. ✅ Install Python 3.9
2. ✅ Install all dependencies (TensorFlow, pandas, LightGBM, etc.)
3. ✅ Set up SQLite database
4. ✅ Run full backtests with real market data
5. ✅ Show results in your terminal

**Requirements:**

- Docker Desktop (free, [download here](https://www.docker.com/products/docker-desktop))
- ~500MB disk space
- ~3 minutes first run

## Common Commands

```bash
# Quick backtest (200 days, 2 min)
docker-compose up --build

# Detailed backtest (2 weeks, 5 min)
docker-compose run forex_bot python3 backtests/scripts/backtest_realistic_live.py

# Interactive shell
docker-compose run forex_bot bash

# View trade results
sqlite3 data/live_journal.db "SELECT symbol, direction, entry_price, stop_loss, take_profit FROM trades LIMIT 5;"

# Stop & clean up
docker-compose down
```

## What You're Testing

- **Strategy**: Smart Money Concepts (SMC)
  - BOS (Break of Structure) detection
  - Pullback zone identification
  - Entry zones: FVG, Discount zones, Order blocks
- **Risk Management**:

  - 1% risk per trade
  - 1.5% daily loss limit
  - 3% weekly loss limit
  - 1.5:1 minimum RR ratio

- **Results**: Trade journal with detailed entry/exit analysis

See `DOCKER_SETUP.md` for full documentation.
See `README.md` for strategy details.
