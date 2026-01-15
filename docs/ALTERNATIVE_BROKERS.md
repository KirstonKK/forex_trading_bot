# Alternative Forex Brokers with Free API Access

Since OANDA requires payment for prop firm challenges, here are alternative brokers with **free demo accounts and REST APIs** that work on macOS.

## 1. Alpaca (FREE - Recommended for Starting)

### ✅ Pros
- **100% FREE** API access
- No paid challenges or subscriptions
- Easy setup - get API key in 5 minutes
- Paper trading (demo) unlimited
- Well-documented API
- Works on macOS/Windows/Linux

### ❌ Cons
- **NO FOREX** - Only stocks and crypto
- US markets only
- Not ideal for forex-specific strategies

### Quick Setup
```bash
# 1. Sign up: https://alpaca.markets
# 2. Generate API keys (paper trading)
# 3. Install SDK
pip install alpaca-trade-api

# 4. Test connection
from alpaca_trade_api import REST
api = REST('API_KEY', 'SECRET_KEY', base_url='https://paper-api.alpaca.markets')
account = api.get_account()
print(f"Buying Power: ${account.buying_power}")
```

**Best For**: Testing your bot logic with real API before moving to forex

---

## 2. Interactive Brokers (IB) - FREE API

### ✅ Pros
- **FREE** paper trading account
- Real forex pairs (EUR/USD, GBP/USD, etc.)
- Professional-grade platform
- Low spreads
- REST API + TWS API

### ❌ Cons
- Complex setup (requires TWS/IB Gateway installation)
- API learning curve is steeper
- Need to keep TWS running (like MT5)
- $10,000 minimum for live account (but paper is free)

### Quick Setup
```bash
# 1. Open paper trading account: https://www.interactivebrokers.com
# 2. Download TWS or IB Gateway
# 3. Install Python API
pip install ibapi

# 4. Enable API in TWS settings
# 5. Connect via Socket
```

**Best For**: Serious traders ready for professional platform

---

## 3. Forex.com / FXCM - REST API (FREE Demo)

### ✅ Pros
- Real forex broker
- Free demo accounts
- REST API available
- Good spreads
- Supports MT5 too

### ❌ Cons
- API documentation not as good as others
- May require live account for full API access
- Regional restrictions

### Setup
```bash
# Check availability in your region
# Sign up for demo: https://www.forex.com
# API docs: https://docs.forex.com
```

---

## 4. Dukascopy - JForex API (FREE)

### ✅ Pros
- Swiss bank - very reliable
- Free demo account
- JForex API (Java-based)
- Can bridge to Python

### ❌ Cons
- Java-based (not native Python)
- More complex integration
- Smaller community

---

## 5. IG Markets - REST API (FREE Demo)

### ✅ Pros
- Large UK-based broker
- Free demo account
- Good REST API
- Supports forex, indices, commodities

### ❌ Cons
- Regional restrictions (not in US)
- Limited API rate limits on demo

### Setup
```bash
# 1. Sign up: https://www.ig.com/uk/demo-account
# 2. Get API key from account settings
# 3. Install lightstreamer for real-time data
pip install ig-markets-api-python-library
```

---

## 6. MetaTrader 5 Brokers (Windows VPS Solution)

### Option A: Use Windows VPS
- Rent Windows VPS ($5-15/month)
- Install MT5 terminal
- Run your Python bot on VPS
- Connect from anywhere

**VPS Providers**:
- Vultr: $5/month
- DigitalOcean: $6/month  
- AWS Lightsail: $5/month

### Option B: Wine on macOS (Complex)
Not recommended - very unstable

---

## 🏆 Recommended Path

### For Learning & Testing (This Week)
1. **Alpaca** - Get your bot working with their free API
2. Test all your strategy logic
3. Verify risk management works
4. Debug any issues

### For Forex Trading (Next Week)
1. **Interactive Brokers** paper account (free)
2. Or rent **Windows VPS** for $5/month + use any MT5 broker
3. Or **IG Markets** if in UK/EU

---

## Cost Comparison

| Broker | Demo Account | API Access | Monthly Cost | Best For |
|--------|-------------|------------|--------------|----------|
| **Alpaca** | ✅ Free | ✅ Free | $0 | Testing bot logic |
| **Interactive Brokers** | ✅ Free | ✅ Free | $0 | Serious forex trading |
| **IG Markets** | ✅ Free | ✅ Free | $0 | UK/EU traders |
| **MT5 + VPS** | ✅ Free demo | ✅ Free | $5-15 VPS | Any MT5 broker |
| **OANDA (Challenge)** | ❌ Paid | ✅ Free | $100-500 | Prop firms only |

---

## Quick Decision Tree

```
Do you want forex pairs?
├─ NO → Use Alpaca (easiest, free)
│
└─ YES → Are you in US?
    ├─ YES → Interactive Brokers (free paper account)
    │
    └─ NO → Are you in UK/EU?
        ├─ YES → IG Markets (free demo)
        │
        └─ NO → Rent VPS + Use MT5 broker ($5/month)
```

---

## Next Steps

**Option 1: Start with Alpaca (Recommended)**
```bash
# Takes 10 minutes to get trading
1. Sign up at alpaca.markets
2. Get paper trading API keys
3. Run: pip install alpaca-trade-api
4. Test your bot with stocks
5. Once confident, move to forex broker
```

**Option 2: Interactive Brokers (Forex Ready)**
```bash
# Takes 30 minutes to setup
1. Open paper account at interactivebrokers.com
2. Download TWS or IB Gateway
3. Enable API in settings
4. Run: pip install ibapi
5. Start trading forex pairs
```

**Option 3: Windows VPS + MT5 ($5/month)**
```bash
# Takes 1 hour to setup
1. Rent Windows VPS (Vultr/DigitalOcean)
2. Install MT5 terminal
3. Open demo account with any broker
4. Upload your bot to VPS
5. Run 24/7
```

---

## My Recommendation

**Start with Interactive Brokers paper account** because:
- ✅ Free forever
- ✅ Real forex pairs
- ✅ Professional platform
- ✅ No VPS needed (runs on macOS via TWS)
- ✅ Can go live when ready ($10k minimum)

Or if you want **dead simple**:
- Use Alpaca to test your bot logic (10 min setup)
- Then move to IB for actual forex trading

**Avoid** OANDA challenges unless you want prop firm funding.

---

Want me to create connectors for any of these brokers?
