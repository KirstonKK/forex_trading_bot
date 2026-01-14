# MT5 Setup Guide - Forex Trading Bot

## Quick Start (5 minutes)

You already have MT5 credentials! Follow these steps to get the bot running:

```bash
# 1. Set environment variables (macOS/Linux)
export MT5_LOGIN=1600072829
export MT5_PASSWORD='6I#bgaWJhj#CT8k'
export MT5_SERVER='OANDA_Global-Demo-1'

# Or create a .env file (recommended)
cat > .env << EOF
MT5_LOGIN=1600072829
MT5_PASSWORD=6I#bgaWJhj#CT8k
MT5_SERVER=OANDA_Global-Demo-1
EOF

# 2. Install dependencies
pip install -r requirements.txt

# 3. Test connection
python3 test_mt5_connection.py

# 4. Start live bot (paper trading)
python3 live_trading_bot.py
```

## Prerequisites

### 1. MetaTrader5 Terminal (Required)

You need the **MT5 desktop application running** on your computer:

- Download: [MetaTrader5 Installer](https://www.metatrader5.com/en/download)
- Install on macOS/Windows/Linux
- **Keep it running** while the bot is trading
- The bot communicates with MT5 via the MetaTrader5 Python library

### 2. Your MT5 Account (Already Have It!)

- Login: `1600072829`
- Password: `6I#bgaWJhj#CT8k`
- Server: `OANDA_Global-Demo-1`
- This is a **paper trading account** (demo) - no real money at risk

### 3. Python Packages

Already in `requirements.txt`. Install with:

```bash
pip install -r requirements.txt
```

Key packages:

- `MetaTrader5>=5.0.45` - Python interface to MT5
- `numpy`, `pandas` - Data handling
- `tensorflow`, `lightgbm` - ML models
- `influxdb-client` - Time series database (optional)

## Configuration

### Environment Variables

Set these three variables:

| Variable       | Value                  | Example               |
| -------------- | ---------------------- | --------------------- |
| `MT5_LOGIN`    | Your MT5 account login | `1600072829`          |
| `MT5_PASSWORD` | Your MT5 password      | `6I#bgaWJhj#CT8k`     |
| `MT5_SERVER`   | Your MT5 server name   | `OANDA_Global-Demo-1` |

**Option A: Shell Environment (Temporary)**

```bash
export MT5_LOGIN=1600072829
export MT5_PASSWORD='6I#bgaWJhj#CT8k'
export MT5_SERVER='OANDA_Global-Demo-1'
```

**Option B: .env File (Persistent)**

```bash
# Create .env in the bot directory
cat > .env << EOF
MT5_LOGIN=1600072829
MT5_PASSWORD=6I#bgaWJhj#CT8k
MT5_SERVER=OANDA_Global-Demo-1
EOF

# Now you don't need to export variables - they load automatically
```

**Option C: macOS ~/.zshrc (Permanent)**

```bash
echo "export MT5_LOGIN=1600072829" >> ~/.zshrc
echo "export MT5_PASSWORD='6I#bgaWJhj#CT8k'" >> ~/.zshrc
echo "export MT5_SERVER='OANDA_Global-Demo-1'" >> ~/.zshrc
source ~/.zshrc
```

## Testing Connection

Before running the live bot, validate everything works:

```bash
python3 test_mt5_connection.py
```

This runs 7 tests:

1. ✓ Credentials validation
2. ✓ MT5 connection
3. ✓ Account balance
4. ✓ Live price quotes (EURUSD, GBPUSD, XAUUSD)
5. ✓ Candlestick data (M5 timeframe)
6. ✓ SMC strategy analysis
7. ✓ Risk manager calculation

Expected output:

```
============================================================
TEST SUMMARY
============================================================
✓ PASS: Credentials
✓ PASS: MT5 Connection
✓ PASS: Account Balance
✓ PASS: Live Prices
✓ PASS: Candlestick Data
✓ PASS: SMC Strategy
✓ PASS: Risk Manager
============================================================

✓ All tests passed! You're ready to run the live bot:
  python3 live_trading_bot.py
```

## Running the Live Bot

```bash
python3 live_trading_bot.py
```

The bot will:

- Connect to your MT5 account
- Poll for market data every 5 minutes
- Analyze EURUSD, GBPUSD, XAUUSD for SMC signals
- Automatically place trades when signals detected
- Monitor open positions
- Log all trades to `data/live_journal.db`

### Console Output Example

```
============================================================
LIVE TRADING BOT - MT5 EDITION
============================================================
Symbols: ['EURUSD', 'GBPUSD', 'XAUUSD']
Poll Interval: 300s
Press Ctrl+C to stop
============================================================

2026-01-14 14:30:15 - Analysis - INFO - --- Iteration 1 (14:30:15) ---
Account Balance: $50,000.00

[14:30:15] Open Positions:
  EURUSD: BUY 0.32 @ 1.08500 (+$320.00)
============================================================
```

## Bot Features

### Trading Strategy

- **SMC Patterns**: Break of Structure → Pullback → Entry
- **Entry Zones**: FVG, Discount Zones, Order Blocks
- **Risk/Reward**: Minimum 1.5:1 ratio

### Risk Management

- **Per Trade Risk**: 1% of account ($500 on $50k)
- **Daily Loss Limit**: 1.5% max daily drawdown
- **Weekly Loss Limit**: 3% max weekly drawdown
- **Max Trades**: 1 per symbol (no overlapping)

### Monitoring

- Real-time balance display
- Open position tracking
- P&L calculation per trade
- Trade journal with SMC details

## Troubleshooting

### Error: "MT5 initialize failed"

```
Solution:
- Download and install MetaTrader5 from metatrader5.com
- Open the MT5 application
- Keep it running while bot trades
```

### Error: "MT5 login failed"

```
Solution:
- Check credentials are correct (case sensitive)
- Verify server name matches exactly
- Ensure account exists on that server
- Reset password if unsure
```

### Error: "No such symbol: EURUSD"

```
Solution:
- Open MT5 terminal
- Check which symbols are available on your server
- Edit symbols in live_trading_bot.py if needed
- Some servers use "EURUSD" others use "EURUSD.m" or similar
```

### Error: "Cannot get price for symbol"

```
Solution:
- Verify symbol is available on your MT5 server
- Check market is open (not weekend)
- Ensure market data is enabled in MT5 settings
```

### Bot Not Finding Signals

```
Note:
- Signals are RARE (good for reducing false trades)
- SMC patterns need perfect confluence
- Check trade journal for signal attempts
- Adjust signal strength filters if needed
- Run backtests first to validate strategy
```

## Advanced Configuration

### Edit Symbols

In `live_trading_bot.py`, line 290:

```python
bot = LiveTradingBot(
    login=login,
    password=password,
    server=server,
    symbols=['EURUSD', 'GBPUSD', 'XAUUSD'],  # ← Change here
    poll_interval=300  # 5 minutes
)
```

### Change Poll Interval

Smaller = More frequent checks (uses more API calls)

```python
poll_interval=60   # Check every 1 minute
poll_interval=300  # Check every 5 minutes (default)
poll_interval=900  # Check every 15 minutes
```

### Adjust Risk Per Trade

In `live_trading_bot.py`, line 39:

```python
self.risk_manager = EnhancedRiskManager(
    account_balance=account_balance,
    risk_per_trade=0.01,  # ← 1% per trade (0.005 = 0.5%)
    daily_loss_limit=0.015,  # 1.5%
    weekly_loss_limit=0.03   # 3%
)
```

## Viewing Trade History

All trades are logged to SQLite database:

```bash
# View trades in terminal
sqlite3 data/live_journal.db "SELECT * FROM trades LIMIT 10;"

# Or use Python
python3 -c "
import sqlite3
db = sqlite3.connect('data/live_journal.db')
cursor = db.cursor()
cursor.execute('SELECT symbol, direction, entry_price, stop_loss, take_profit, entry_time FROM trades ORDER BY entry_time DESC LIMIT 5')
for row in cursor:
    print(row)
"
```

## Important Notes

⚠️ **Paper Trading (Demo)**

- Your account is **paper trading** (simulated money)
- No real money at risk
- Exact same execution and spreads as live
- Good for testing before real trading

⚠️ **Always Monitor**

- Bot should not run unattended
- Watch for connection drops
- Monitor account balance
- Check trade journal daily

⚠️ **System Requirements**

- MT5 terminal must stay running
- Stable internet connection
- Computer cannot sleep while bot runs
- Recommend: Run on VPS or dedicated machine for 24/7 trading

⚠️ **Strategy Disclaimer**

- Past performance ≠ future results
- Back tested on synthetic data (unrealistic)
- Real market conditions vary
- Use strict risk management

## Next Steps

1. ✅ Set environment variables (done)
2. ✅ Install dependencies: `pip install -r requirements.txt`
3. ✅ Test connection: `python3 test_mt5_connection.py`
4. ✅ Run bot: `python3 live_trading_bot.py`
5. ✅ Monitor trades (first 24 hours)
6. ✅ Review trade journal
7. ✅ Optimize parameters based on results
8. (Optional) Go live with real money

## Support

- **MT5 API**: https://www.mql5.com/en/articles/6157
- **Python Library**: https://github.com/khramkov/MT5-Python
- **MT5 API**: https://www.mql5.com/en/articles/6157
- **Strategy Help**: SMC (Smart Money Concepts) educational resources

## Files Modified

- `connectors/mt5_connector.py` - New: MT5 API wrapper
- `live_trading_bot.py` - Updated: Now uses MT5 instead of Oanda
- `test_mt5_connection.py` - Updated: MT5-specific tests
- `requirements.txt` - Confirms MetaTrader5 is included

Happy trading! 🚀
