# Live Trading Setup - Data Sources

## 📊 Data Source Priority

### PRIMARY: TradingView Webhooks ✅
**Recommended for live trading**
- Real exchange data (most accurate)
- Updates on every candle close
- No API limits or rate limiting
- Works 24/7 when market is open

**Setup Required:**
1. Webhook server running (automatic with `./start_bot.sh`)
2. ngrok tunnel for public URL
3. TradingView alert configured

See: [TRADINGVIEW_WEBHOOK_SETUP.md](docs/TRADINGVIEW_WEBHOOK_SETUP.md)

### FALLBACK: yfinance Polling ⚠️
**Backup only - use when TradingView not configured**
- Polls every 5 seconds
- Subject to API outages (like now)
- Less accurate than exchange data
- May have delays

**Automatic Behavior:**
- Poller checks if TradingView data is recent
- If TradingView active → poller goes into monitoring mode
- If TradingView stale → poller activates yfinance fallback

---

## 🚀 For Monday Morning Trading

### Option 1: TradingView (RECOMMENDED)

```bash
# 1. Start webhook server
./start_bot.sh

# 2. Expose to internet (one-time setup)
ngrok http 5000

# 3. Copy the ngrok URL (e.g., https://abc123.ngrok.io)

# 4. In TradingView:
#    - Create alert on your chart
#    - Set webhook URL: https://abc123.ngrok.io/webhook
#    - Set to trigger on candle close
#    - Message body:
{
  "secret": "your_secret_key_here",
  "symbol": "EURUSD",
  "timeframe": "1h",
  "close": {{close}},
  "open": {{open}},
  "high": {{high}},
  "low": {{low}},
  "volume": {{volume}},
  "timestamp": {{time}}
}
```

### Option 2: yfinance Only (Fallback)

```bash
# Just run the bot - poller will activate automatically
./start_bot.sh

# If yfinance is working, data will flow
# If yfinance is broken, bot will wait for TradingView
```

---

## ✅ Verification

Check what data source is active:

```bash
# Check server status
curl http://localhost:5000/health

# View current data
curl http://localhost:5000/data

# View active signals
curl http://localhost:5000/signals
```

Dashboard: http://localhost:5000

---

## 🎯 What Happens Monday

**With TradingView configured:**
1. Market opens Sunday 5pm EST
2. TradingView sends data on candle closes
3. Bot analyzes ICT patterns
4. Signals logged + sent to Telegram
5. No manual intervention needed ✅

**Without TradingView (yfinance fallback):**
1. Poller attempts to fetch from yfinance
2. If yfinance working → bot runs normally
3. If yfinance broken → bot waits for data
4. Manual TradingView setup recommended

---

## 💡 Recommendation

**Set up TradingView webhooks this weekend** so you're ready for Monday. Takes 10 minutes and provides the most reliable data feed.
