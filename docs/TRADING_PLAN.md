# Trading Plan Implementation

## Strategy Overview

This bot implements a complete ICT (Inner Circle Trader) / SMC (Smart Money Concepts) strategy with strict entry rules and risk management.

## Trading Rules

### 1. Higher Timeframe Structure (4H/1H)

- **Always start** by checking 4H or 1H timeframe
- Determine if market is **BULLISH**, **BEARISH**, or **RANGING**
- Only trade with the trend (no trades in ranging markets)

### 2. Order Block Selection (5-Minute)

- Mark order blocks on **5-minute timeframe**
- Order Block = Last opposing candle before strong move
  - Bullish OB: Last bearish candle before bullish rally
  - Bearish OB: Last bullish candle before bearish drop
- **Must align with higher timeframe zones**

### 3. Fibonacci Confluence

- Use **79% Fibonacci retracement** level
- Order block must overlap with 79% Fib level
- Adds confluence to the selected zone

### 4. Fair Value Gaps (FVG) & Breaker Blocks

- Detect 3-candle imbalances (FVG)
- Price can fill FVG without mitigating your OB
- Watch for breaker block zones as reaction areas

### 5. Market Structure Confirmation

- Wait for **Break of Structure (BoS)**
- Wait for **Change of Character (ChoCH)**
- Both required before entry

### 6. Liquidity Check

- Look for **equal highs** and **equal lows** (liquidity pools)
- If present, wait for market to sweep both sides
- Enter after liquidity is taken

### 7. Pair-Specific Rules

#### EURUSD & GBPUSD (EU & GU):

- Watch for sweep of **Asian session high or low**
- Entry after sweep taps into your selected zone
- Applies to most currency pairs

#### Gold (XAUUSD):

- **Trade strictly with the trend**
- Use **30-minute timeframe** for zone selection
- Ensure 30M zones align with 4H zones

### 8. Final Rule

**If all above conditions are NOT met → NO TRADE**

## Risk Management

### Risk-to-Reward (RR)

- Target: **1:3 to 1:5** RR per trade
- Typical target: **1:4** RR
- Once daily target achieved → **STOP trading**

### Trade Limits

- **Maximum 2 valid trades per day**
- Both can be taken during London or NY session
- If target reached in London → **No trades in NY**

### Take Profit (TP) Levels

- Previous Day's Low (PDL) or High (PDH)
- Asian Session Low or High
- Fair Value Gaps (FVG) aligned with Order Blocks
- Liquidity pools (equal highs/lows)

### Stop Loss (SL) Rules

- Place SL **above/below the 30-minute zone** selected
- SL must be between **50 – 120 points**
- **Do NOT enter** trades with SL > 150 points
- Do not move stops prematurely
- Only adjust SL to secure profits once trade has moved **70% toward TP**

## Trade Entry Checklist

Before entering any trade, verify:

- [ ] HTF Structure confirmed (4H/1H trend)
- [ ] Order Block marked on 5M timeframe
- [ ] OB aligns with HTF zone
- [ ] 79% Fib confluence present
- [ ] FVG/Breaker blocks identified
- [ ] Break of Structure (BoS) confirmed
- [ ] Change of Character (ChoCH) confirmed
- [ ] Liquidity swept (if equal highs/lows present)
- [ ] Pair-specific rules met:
  - [ ] EU/GU: Asian session sweep
  - [ ] XAUUSD: 30M zone aligned with 4H
- [ ] SL between 50-120 points
- [ ] RR ratio ≥ 1:3
- [ ] Less than 2 trades taken today
- [ ] Daily target not yet reached

**If ANY checkbox is unchecked → NO TRADE**

## Session Guidelines

### London Session (08:00-12:00 GMT)

- Primary trading window
- High volatility and liquidity
- Best for EU/GU pairs

### NY Session (13:00-17:00 GMT)

- Secondary trading window
- Only if London target not met
- Overlap with London (13:00-16:00) is ideal

### Asian Session (00:00-08:00 GMT)

- **DO NOT TRADE** during Asian session
- Use for identifying highs/lows for sweep setups
- Mark liquidity levels for London/NY

## Implementation in Bot

The bot implements this strategy through:

1. **Multi-Timeframe Analysis**: Fetches 4H/1H for trend + 5M for entry
2. **Order Block Detection**: Identifies OBs on 5M timeframe
3. **Fibonacci Calculator**: Computes 79% retracement levels
4. **FVG Detection**: Finds 3-candle imbalances
5. **BoS/ChoCH Confirmation**: Validates market structure shifts
6. **Liquidity Detection**: Identifies equal highs/lows
7. **Risk Management**: Enforces SL/TP rules, daily limits
8. **Pair-Specific Logic**: Different rules for EU/GU vs XAUUSD

## Code Location

- **Strategy**: `core/enhanced_smc_strategy.py`
- **Risk Manager**: `core/enhanced_risk_manager.py`
- **Live Trading**: `scripts/live_trading_bot.py`

## Testing

To test the strategy:

```bash
# Simulation mode (without MT5)
python3 scripts/test_bot_simulation.py

# Backtest mode
python3 backtests/scripts/backtest_realistic_live.py

# Live trading (requires MT5 terminal on Windows/VPS)
python3 scripts/live_trading_bot.py
```

## Important Notes

1. **Discipline is key** - Do not deviate from the rules
2. **Quality over quantity** - 2 high-quality trades > 10 mediocre trades
3. **Protect capital** - Stop trading after 2 losses in a day
4. **Journal every trade** - Review and learn from each trade
5. **Respect the market** - If conditions aren't met, stay out

## Account Requirements

- **Minimum Balance**: $10,000 (for 1% risk per trade = $100)
- **Leverage**: 1:100 or higher
- **Broker**: MT5-compatible (Exness, OANDA, etc.)
- **Spread**: Low spread broker recommended (< 1 pip for EU/GU)

---

_This trading plan is implemented in the Enhanced SMC Strategy module._
