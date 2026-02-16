# Forex Trading Bot - ICT/SMC Strategy

A professional forex trading bot implementing **Inner Circle Trader (ICT)** and **Smart Money Concepts (SMC)** strategies with flexible confluence requirements.

## 🎯 Features

- **3 Flexible Setup Options** for different market conditions
- **Risk-Adaptive Position Sizing** (full/half based on confirmations)
- **Real-time Market Analysis** via yfinance data feeds
- **Pair-Specific Strategies** optimized for EUR/USD, GBP/USD, and XAU/USD
- **Session-Aware Trading** (London & NY sessions)
- **Web Dashboard** for monitoring signals and performance
- **Comprehensive Logging** for trade analysis

## 📁 Project Structure

```
forex_trading_bot/
├── core/                               # Core trading strategies
│   ├── flexible_ict_strategy.py       # Main flexible 3-option strategy ⭐
│   ├── professional_strategy.py       # Original professional strategy
│   ├── enhanced_smc_strategy.py       # Enhanced SMC implementation
│   ├── smc_strategy.py                # Base SMC strategy
│   ├── ict_analysis.py                # ICT pattern detection
│   ├── advanced_filters.py            # Market filters & session detection
│   ├── enhanced_risk_manager.py       # Position sizing & risk management
│   ├── risk_manager.py                # Base risk manager
│   ├── trade_executor.py              # Trade execution logic
│   └── fibonacci_liquidity.py         # Fibonacci & liquidity tools
│
├── scripts/                            # Executable scripts
│   ├── backtests/                     # All backtest scripts
│   │   ├── backtest_real_data_2024.py
│   │   ├── backtest_realistic_live.py
│   │   ├── run_comprehensive_backtest.py
│   │   └── run_quick_backtest.py
│   ├── tests/                         # All test scripts
│   │   ├── test_mt5_connection.py
│   │   ├── test_webhook_simple.py
│   │   └── test_webhook_realtime.py
│   ├── tradingview_webhook_server.py  # Main webhook server ⭐
│   ├── live_data_poller.py            # Real-time data fetcher ⭐
│   ├── trading_bot.py                 # Legacy trading bot
│   └── live_trading_bot.py            # Live trading implementation
│
├── connectors/                         # Data connectors
│   ├── forex_api.py                   # Forex API connector
│   ├── free_data_connector.py         # Free data sources
│   ├── mt5_connector.py               # MetaTrader 5 connector
│   └── price_feed.py                  # Price feed manager
│
├── database/                           # Database modules
│   ├── journal.py                     # Trade journal
│   ├── trades.py                      # Trade records
│   └── timeseries.py                  # Time series data
│
├── backtesting/                        # Backtesting engine
│   ├── backtest_engine.py             # Main backtesting engine
│   └── data_fetcher.py                # Historical data fetcher
│
├── machine_learning/                   # ML features (future)
│   ├── feature_engineering.py         # Feature extraction
│   └── models/                        # ML models
│
├── utils/                              # Utility modules
│   ├── logger.py                      # Logging configuration
│   ├── config.py                      # Configuration loader
│   └── env_config.py                  # Environment config
│
├── docs/                               # Documentation
│   ├── TRADING_PLAN.md                # Original trading plan
│   ├── DOCKER_SETUP.md                # Docker deployment guide
│   ├── MT5_SETUP.md                   # MetaTrader 5 setup
│   ├── TRADINGVIEW_WEBHOOK_SETUP.md   # TradingView integration
│   └── ALTERNATIVE_BROKERS.md         # Broker alternatives
│
├── static/                             # Web dashboard
│   └── dashboard.html                 # Real-time dashboard UI
│
├── config/                             # Configuration files
│   └── config.json                    # Bot configuration
│
├── logs/                               # Log files (gitignored)
├── data/                               # Data storage (gitignored)
├── start_bot.sh                        # Start the trading bot ⭐
├── stop_bot.sh                         # Stop the trading bot ⭐
├── requirements.txt                    # Python dependencies
├── docker-compose.yml                  # Docker configuration
├── Dockerfile                          # Docker image
├── FLEXIBLE_STRATEGY_GUIDE.md          # Strategy guide (NEW!) ⭐
├── ENHANCED_STRATEGY.md                # Enhanced strategy docs
└── README.md                           # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- pip or conda
- Linux/macOS (Windows via WSL)

### Installation

```bash
# Clone the repository
git clone https://github.com/KirstonKK/forex_trading_bot.git
cd forex_trading_bot

# Install dependencies
pip install -r requirements.txt

# Start the bot
bash start_bot.sh
```

### Endpoints

Once running, access:

- **Dashboard:** http://localhost:5000
- **Health Check:** http://localhost:5000/health
- **Signals:** http://localhost:5000/signals
- **Market Data:** http://localhost:5000/data

## 🎓 Trading Strategy

The bot implements a **flexible 3-option strategy system**:

### Option 1: HTF Bias + Liquidity Sweep + BoS
- ✅ Clear HTF trend (4H or 1H)
- ✅ Liquidity sweep (equal highs/lows or Asian range)
- ✅ Break of Structure in HTF direction
- **Best for:** EUR/USD, GBP/USD London session

### Option 2: HTF Zone + OB + ChoCH
- ✅ Price taps HTF zone (4H/1H)
- ✅ Order Block on 5M aligned with zone
- ✅ Change of Character on LTF
- **Best for:** NY session reversals, Gold

### Option 3: OB + FVG + Fib 79%
- ✅ 5M Order Block
- ✅ Fair Value Gap overlapping OB
- ✅ 79% Fibonacci retracement
- **Best for:** Clean pullbacks, precision entries

### Risk Management

- **3 confirmations** → 1.0% risk (full position)
- **2 confirmations** → 0.5% risk (half position)
- **1 confirmation** → No trade

### Target Risk/Reward
- Minimum: 1:2.5
- Target: 1:3 to 1:5
- Stop Loss: 30-150 pips

## 📊 Supported Pairs

- **EUR/USD** - Priority: Liquidity sweeps + BoS
- **GBP/USD** - Priority: Asian range sweeps
- **XAU/USD (Gold)** - Priority: HTF zones + trend

## 🔧 Configuration

Edit `config/config.json` to customize:

```json
{
  "account_balance": 10000,
  "risk_per_trade": 0.01,
  "max_trades_per_day": 2,
  "symbols": ["EURUSD", "GBPUSD"],
  "sessions": ["london", "newyork"]
}
```

## 📈 Monitoring

### View Signals
```bash
curl -s http://localhost:5000/signals | python3 -m json.tool
```

### Watch Logs
```bash
# Webhook server
tail -f logs/webhook.log

# Data poller
tail -f logs/poller_startup.log
```

### Check System Health
```bash
curl http://localhost:5000/health
```

## 🐳 Docker Deployment

```bash
# Build and run with Docker
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## 📚 Documentation

- **[Flexible Strategy Guide](FLEXIBLE_STRATEGY_GUIDE.md)** - Detailed strategy explanation ⭐
- **[Trading Plan](docs/TRADING_PLAN.md)** - Original ICT trading plan
- **[Docker Setup](docs/DOCKER_SETUP.md)** - Deployment guide
- **[TradingView Integration](docs/TRADINGVIEW_WEBHOOK_SETUP.md)** - Webhook setup

## 🧪 Testing

```bash
# Run unit tests
python -m pytest scripts/tests/

# Test webhook server
python scripts/tests/test_webhook_simple.py

# Test data connection
python scripts/tests/test_mt5_connection.py
```

## 📊 Backtesting

```bash
# Run backtest
python scripts/backtests/backtest_real_data_2024.py

# View results
cat data/latest_backtest.json
```

## ⚠️ Disclaimer

**This bot is for educational purposes only.** Trading forex and CFDs involves substantial risk of loss. Past performance is not indicative of future results. Always:

- Start with a demo account
- Never risk more than you can afford to lose
- Understand the strategy before going live
- Monitor the bot regularly
- Use proper risk management

## 📝 License

This project is licensed under the MIT License - see LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📧 Support

- **Issues:** Open an issue on GitHub
- **Discussions:** Use GitHub Discussions
- **Documentation:** Check the `docs/` folder

## 🔄 Recent Updates

### v2.0.0 - Flexible Strategy Implementation (Jan 2026)
- ✨ Added 3-option flexible strategy system
- ✨ Implemented confirmation-based risk sizing
- ✨ Added pair-specific strategy priorities
- ✨ Enhanced logging with setup type details
- 📚 Created comprehensive strategy guide
- 🐛 Fixed strategy integration issues

### v1.0.0 - Initial Release
- ⚡ Professional ICT/SMC strategy
- 📊 Real-time data via yfinance
- 🌐 Web dashboard
- 📝 Comprehensive logging
- 🐳 Docker support

## 🛠️ Maintenance

### Update Dependencies
```bash
pip install -r requirements.txt --upgrade
```

### Clean Logs
```bash
# Keep last 7 days only
find logs/ -name "*.log" -mtime +7 -delete
```

### Backup Data
```bash
# Backup database and logs
tar -czf backup_$(date +%Y%m%d).tar.gz data/ logs/
```

## 🎯 Roadmap

- [ ] Machine learning signal filtering
- [ ] Multi-timeframe analysis dashboard
- [ ] Telegram notifications
- [ ] Advanced backtesting reports
- [ ] Paper trading mode
- [ ] Risk analyzer tools

---

**Made with ❤️ for ICT traders**
