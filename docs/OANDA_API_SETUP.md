# OANDA REST API Setup (Works on macOS!)

## Why OANDA REST API Instead of MT5?

The MetaTrader5 Python library only works on **Windows/Linux** - it doesn't work on macOS. However, OANDA provides a REST API that works on **any platform** including macOS.

## Your OANDA Credentials

You have MT5 credentials:
- **Login**: 1600073321
- **Password**: qbH0Gt4z2Ou#61
- **Server**: OANDA_Global-Demo-1

## Getting OANDA API Access

### Step 1: Login to OANDA Web Platform

Go to: https://www.oanda.com/account/login

Use your credentials:
- Username: (your email or username)
- Password: qbH0Gt4z2Ou#61

### Step 2: Navigate to API Access

1. Click on your **account name** (top right)
2. Select **"Manage API Access"** or **"Manage Funds"** → **"API Access"**
3. If using demo account, make sure you're on the **fxTrade Practice** platform

### Step 3: Generate Personal Access Token

1. Click **"Generate"** or **"Create Token"**
2. Give it a name (e.g., "Trading Bot")
3. **Copy and save the token** - you won't see it again!
4. Note your **Account ID** (format: `101-004-XXXXXXXX-001`)

### Step 4: Create .env File

Create a file called `.env` in your project root:

```bash
# OANDA API Credentials
OANDA_ACCOUNT_ID=101-004-XXXXXXXX-001  # Replace with your actual account ID
OANDA_API_TOKEN=your_token_here         # Replace with your generated token
OANDA_ENVIRONMENT=practice              # Use "practice" for demo, "live" for real

# Trading Settings
RISK_PER_TRADE=0.01
MAX_TRADES_PER_DAY=2
POLL_INTERVAL=300
```

## Testing the Connection

Run this command to test:

```bash
python3 scripts/test_oanda_connection.py
```

## Trading with OANDA API

The bot will automatically use OANDA REST API when you:

1. Set the environment variables above
2. Run the bot: `python3 scripts/live_trading_bot_oanda.py`

## Benefits of OANDA REST API

✅ Works on macOS (and any platform)
✅ No MT5 terminal installation needed
✅ Direct API access - faster execution
✅ Better for automated trading
✅ More reliable connection

## MT5 vs REST API Comparison

| Feature | MT5 Python | OANDA REST API |
|---------|-----------|----------------|
| **macOS Support** | ❌ No | ✅ Yes |
| **Installation** | Requires MT5 terminal | Just Python requests |
| **Speed** | Good | Excellent |
| **Automation** | Limited | Full control |
| **Historical Data** | Via MT5 | Direct from API |

## Quick Start Commands

```bash
# 1. Test connection
python3 scripts/test_oanda_connection.py

# 2. Fetch live market data
python3 scripts/fetch_oanda_data.py

# 3. Run simulation with real OANDA data
python3 scripts/test_bot_simulation.py

# 4. Start live trading (when ready)
python3 scripts/live_trading_bot_oanda.py
```

## Important Notes

1. **Practice Account**: Your current credentials are for a demo account - perfect for testing!
2. **API Rate Limits**: OANDA allows up to 120 requests/second (more than enough)
3. **Data Accuracy**: REST API provides the same data as MT5
4. **Execution**: Orders execute directly through OANDA's servers

## Troubleshooting

### Can't Find API Access Page?
- Make sure you're logged into **fxTrade Practice** (not regular fxTrade)
- Look under "Manage Funds" → "API Access"

### Token Not Working?
- Make sure you copied the full token
- Check you're using the correct account ID
- Verify you're using "practice" environment for demo accounts

### Need Help?
- OANDA API Docs: https://developer.oanda.com/rest-live-v20/introduction/
- Support: https://www.oanda.com/contact-us/

---

**Next Steps**: Follow the steps above to get your OANDA API token, then we can test the connection and start trading on macOS! 🚀
