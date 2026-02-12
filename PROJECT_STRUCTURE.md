# Forex Trading Bot - Project Structure

## 📁 Directory Organization

```
forex_trading_bot/
├── 📄 README.md                      # Main documentation
├── 📄 requirements.txt               # Python dependencies
├── 📄 start_bot.sh                   # Start the bot
├── 📄 stop_bot.sh                    # Stop the bot
│
├── 📂 core/                          # Core trading logic
│   ├── flexible_ict_strategy.py     # Main ICT strategy (3 setups)
│   ├── professional_strategy.py      # Alternative strategy
│   ├── enhanced_smc_strategy.py      # SMC implementation
│   ├── smc_strategy.py               # Base SMC
│   ├── ict_analysis.py               # ICT pattern detection
│   ├── advanced_filters.py           # Market filters & sessions
│   ├── enhanced_risk_manager.py      # Risk management
│   ├── risk_manager.py               # Base risk manager
│   ├── trade_executor.py             # Trade execution
│   └── fibonacci_liquidity.py        # Fibonacci tools
│
├── 📂 scripts/                       # Executable scripts
│   ├── tradingview_webhook_server.py # 🎯 Main server (port 5000)
│   ├── live_data_poller.py          # 🎯 Real-time data fetcher
│   ├── trading_bot.py                # Legacy bot
│   └── live_trading_bot.py           # Live implementation
│
├── 📂 connectors/                    # Data source connectors
│   ├── forex_api.py                  # Forex API
│   ├── free_data_connector.py        # Free data sources
│   ├── mt5_connector.py              # MetaTrader 5
│   └── price_feed.py                 # Price feed manager
│
├── 📂 integrations/                  # External integrations
│   ├── telegram_bot.py               # Telegram notifications
│   ├── news_filter.py                # Economic calendar filter
│   ├── daily_report.py               # Daily performance reports
│   ├── weekly_report.py              # Weekly summaries
│   ├── trade_tracker.py              # Performance tracking
│   └── ab_testing.py                 # Strategy A/B testing
│
├── 📂 database/                      # Data persistence
│   ├── journal.py                    # Trade journal
│   ├── trades.py                     # Trade records
│   └── timeseries.py                 # Time series data
│
├── 📂 backtesting/                   # Backtesting engine
│   ├── backtest_engine.py            # Main engine
│   └── data_fetcher.py               # Historical data
│
├── 📂 machine_learning/              # ML features
│   ├── feature_engineering.py        # Feature extraction
│   └── ml_risk_model.py              # Risk scoring model
│
├── 📂 utils/                         # Utilities
│   ├── logger.py                     # Logging config
│   ├── config.py                     # Configuration loader
│   └── env_config.py                 # Environment variables
│
├── 📂 tests/                         # Test files
│   ├── backtests/                    # Backtest scripts
│   │   ├── run_comprehensive_backtest.py
│   │   └── run_simple_backtest.py
│   ├── webhooks/                     # Webhook tests
│   │   ├── test_webhook_realtime.py
│   │   ├── test_webhook_quick.py
│   │   └── test_webhook_simple.py
│   └── test_mt5_connection.py        # MT5 tests
│
├── 📂 deployment/                    # Deployment files
│   ├── jarvis-bot.service            # Systemd service
│   ├── jarvis-trading-bot.service    # Alt service
│   ├── jarvis-webhook.service        # Webhook service
│   ├── install_docker.sh             # Docker setup
│   ├── Dockerfile                    # Docker image
│   └── docker-compose.yml            # Docker compose
│
├── 📂 docs/                          # Documentation
│   ├── TRADING_PLAN.md               # Trading plan
│   ├── DOCKER_SETUP.md               # Docker guide
│   ├── MT5_SETUP.md                  # MT5 setup
│   ├── TRADINGVIEW_WEBHOOK_SETUP.md  # TradingView guide
│   └── ALTERNATIVE_BROKERS.md        # Broker options
│
├── 📂 static/                        # Web dashboard
│   └── dashboard.html                # Real-time UI
│
├── 📂 config/                        # Configuration
│   └── config.json                   # Bot settings
│
├── 📂 logs/                          # Log files (gitignored)
│   ├── webhook.log                   # Webhook server logs
│   ├── poller.log                    # Data poller logs
│   └── backtest_output.log           # Backtest results
│
└── 📂 data/                          # Data storage (gitignored)
    ├── market_data.json              # Live market data
    └── active_signals.json           # Current signals
```

## 🎯 Key Files

### Running the Bot
- **`start_bot.sh`** - Main startup script
- **`scripts/tradingview_webhook_server.py`** - Webhook server (always running)
- **`scripts/live_data_poller.py`** - Data fetcher (always running)

### Strategy
- **`core/flexible_ict_strategy.py`** - Main trading strategy (1321 lines)
- **`core/enhanced_risk_manager.py`** - Risk management

### Testing
- **`tests/backtests/run_comprehensive_backtest.py`** - Full backtest
- **`tests/webhooks/test_webhook_realtime.py`** - Webhook testing

### Configuration
- **`config/config.json`** - Bot configuration
- **`requirements.txt`** - Python dependencies

## 📊 Data Flow

```
yfinance → live_data_poller.py → webhook_server → flexible_ict_strategy → signals → Telegram
```

## 🚀 Quick Start

```bash
# Start the bot
./start_bot.sh

# Check status
curl http://localhost:5000/health

# View signals
curl http://localhost:5000/signals

# Stop the bot
./stop_bot.sh
```

## 📝 Notes

- All test files moved to `tests/` directory
- Deployment files organized in `deployment/`
- Core logic unchanged, only file locations
- All imports remain valid
