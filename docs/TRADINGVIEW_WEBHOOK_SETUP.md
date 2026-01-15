# TradingView Webhook Setup Guide

Complete guide to connect TradingView alerts to your trading bot.

## What This Does

- TradingView monitors the market 24/7
- When your strategy conditions are met, TradingView sends a webhook
- Your bot receives the signal and executes the trade automatically
- No need to watch charts or manually click buttons!

## Step 1: Install Dependencies

```bash
pip3 install flask ngrok
```

## Step 2: Start the Webhook Server

```bash
# In simulation mode (recommended for testing)
python3 scripts/tradingview_webhook_server.py

# Or with OANDA (if you have API credentials)
export OANDA_ACCOUNT_ID="your_account_id"
export OANDA_API_TOKEN="your_api_token"
export OANDA_ENVIRONMENT="practice"
export BROKER="oanda"
python3 scripts/tradingview_webhook_server.py
```

The server will start on `http://localhost:5000`

## Step 3: Expose Server to Internet with ngrok

TradingView needs a public URL to send webhooks. Use ngrok:

```bash
# Install ngrok (one-time)
brew install ngrok

# Start ngrok tunnel
ngrok http 5000
```

You'll see output like:

```
Forwarding https://abc123.ngrok.io -> http://localhost:5000
```

**Copy the HTTPS URL** (e.g., `https://abc123.ngrok.io`)

## Step 4: Set Up TradingView Alert

### 4.1 Create Your Strategy/Indicator

1. Open TradingView
2. Add your strategy or indicators to the chart
3. Test it manually to verify it works

### 4.2 Create Alert

1. Click **Alert** button (clock icon) or press `Alt + A`
2. Set alert conditions (e.g., "RSI crosses above 30")
3. In **Webhook URL**, paste: `https://abc123.ngrok.io/webhook`
4. In **Alert Message**, use this JSON format:

#### For BUY Signal:

```json
{
  "secret": "your_secret_key_here",
  "action": "buy",
  "symbol": "EUR_USD",
  "price": {{close}},
  "stop_loss": {{low}},
  "take_profit": {{close}} + ({{close}} - {{low}}) * 3,
  "risk_pct": 1.0
}
```

#### For SELL Signal:

```json
{
  "secret": "your_secret_key_here",
  "action": "sell",
  "symbol": "EUR_USD",
  "price": {{close}},
  "stop_loss": {{high}},
  "take_profit": {{close}} - ({{high}} - {{close}}) * 3,
  "risk_pct": 1.0
}
```

#### For CLOSE Signal:

```json
{
  "secret": "your_secret_key_here",
  "action": "close",
  "symbol": "EUR_USD"
}
```

### 4.3 TradingView Variables

TradingView automatically replaces these placeholders:

- `{{close}}` - Current close price
- `{{open}}` - Current open price
- `{{high}}` - Current high
- `{{low}}` - Current low
- `{{volume}}` - Current volume
- `{{ticker}}` - Symbol name

### 4.4 Set Alert Options

- **Condition**: Your strategy condition
- **Options**: "Once Per Bar Close" (recommended)
- **Expiration**: "Open-ended" (never expires)
- **Alert actions**: ✓ Webhook URL

Click **Create**

## Step 5: Test the Webhook

### Test with curl (before using TradingView):

```bash
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "your_secret_key_here",
    "action": "buy",
    "symbol": "EUR_USD",
    "price": 1.1234,
    "stop_loss": 1.1200,
    "take_profit": 1.1300,
    "risk_pct": 1.0
  }'
```

Expected response:

```json
{
  "status": "success",
  "ticket": 123456,
  "action": "buy",
  "symbol": "EUR_USD",
  "price": 1.1234,
  "stop_loss": 1.12,
  "take_profit": 1.13,
  "size": 0.5,
  "risk": "$100.00"
}
```

### Check Health:

```bash
curl http://localhost:5000/health
```

### View Positions:

```bash
curl http://localhost:5000/positions
```

### View Account:

```bash
curl http://localhost:5000/account
```

## Security Settings

### Change Webhook Secret

**Important:** Change the default secret!

```bash
export WEBHOOK_SECRET="my_super_secret_key_12345"
python3 scripts/tradingview_webhook_server.py
```

Update your TradingView alert message to use the same secret.

## Example TradingView Strategy

Here's a simple Pine Script strategy that sends webhooks:

```pine
//@version=5
strategy("Webhook Strategy", overlay=true)

// Strategy logic
rsi = ta.rsi(close, 14)
buySignal = ta.crossover(rsi, 30)
sellSignal = ta.crossunder(rsi, 70)

// Execute trades
if (buySignal)
    strategy.entry("Buy", strategy.long)
    alert('{"secret":"your_secret_key_here","action":"buy","symbol":"EUR_USD","price":' + str.tostring(close) + ',"stop_loss":' + str.tostring(low[1]) + ',"take_profit":' + str.tostring(close + (close - low[1]) * 3) + ',"risk_pct":1.0}', alert.freq_once_per_bar_close)

if (sellSignal)
    strategy.close("Buy")
    alert('{"secret":"your_secret_key_here","action":"close","symbol":"EUR_USD"}', alert.freq_once_per_bar_close)
```

## Supported Symbol Formats

- **Forex**: `EUR_USD`, `GBP_USD`, `USD_JPY`
- **Gold**: `XAU_USD`, `GOLD`
- **OANDA format**: `EUR_USD` (use underscores)

Make sure your TradingView symbol matches the broker format!

## Monitoring

### Check Logs

```bash
tail -f logs/webhook.log
```

### Server Output

The server prints all received webhooks and trade executions to console.

## Production Setup

For 24/7 operation:

### Option 1: Run on VPS

1. Deploy to a cloud server (AWS, DigitalOcean, etc.)
2. Use a proper domain with SSL certificate
3. Run server with systemd or supervisor

### Option 2: Use ngrok Paid Plan

- Get a permanent subdomain
- No need to update TradingView URL
- More stable connection

### Option 3: Heroku/Railway

- Deploy as a web service
- Auto-scaling and monitoring included
- Free tier available

## Troubleshooting

### Webhook Not Receiving

1. Check ngrok is running: `ngrok http 5000`
2. Verify HTTPS URL in TradingView (not HTTP)
3. Check webhook secret matches
4. View ngrok dashboard: http://localhost:4040

### Trade Not Executing

1. Check server logs: `logs/webhook.log`
2. Verify symbol format matches broker
3. Check account balance and risk limits
4. Test with curl first

### Invalid Secret Error

- Secret in TradingView alert must match `WEBHOOK_SECRET`
- Default is `your_secret_key_here` (change this!)

## Next Steps

1. Start server in simulation mode
2. Test with curl
3. Create TradingView alert
4. Monitor first few signals
5. Once confident, switch to live broker (OANDA)

## Support

- Logs: `logs/webhook.log`
- Server health: `http://localhost:5000/health`
- ngrok dashboard: `http://localhost:4040`
