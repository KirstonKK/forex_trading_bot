# Flexible ICT Trading Strategy Guide

## Overview
The bot now uses a **flexible 3-option strategy system** that reduces the need for perfect confluence while maintaining high win rates. Each option focuses on different market conditions.

---

## 🎯 Three Setup Options

### Option 1: HTF Bias + Liquidity Sweep + BoS
**Best for:** EU/GU London session, trending markets

**Requirements:**
- ✅ Clear HTF trend (4H or 1H)
- ✅ Liquidity sweep (equal highs/lows taken OR Asian high/low swept)
- ✅ BoS (Break of Structure) in direction of HTF trend

**Why it works:**
- HTF gives you directional bias
- Liquidity sweep provides entry justification
- BoS confirms real institutional displacement

**When to use:**
- EURUSD & GBPUSD during London session
- Gold during strong trend continuation
- When markets respect higher timeframes

---

### Option 2: HTF Zone + OB + ChoCH
**Best for:** NY session reversals, continuation setups

**Requirements:**
- ✅ Price taps a HTF zone (4H or 1H supply/demand)
- ✅ Order Block on 5M aligned with HTF zone
- ✅ ChoCH (Change of Character) on LTF

**Why it works:**
- HTF zone = institutional interest area
- Order Block = precise execution level
- ChoCH = momentum shift confirmation

**Bonus (not required):**
- Liquidity sweep adds confidence

**When to use:**
- NY session price reactions
- Gold bouncing from 30M zones
- Reversal opportunities at key levels

---

### Option 3: OB + FVG + Fib 79%
**Best for:** Clean pullbacks, precision entries

**Requirements:**
- ✅ 5M Order Block
- ✅ Fair Value Gap (FVG) overlapping the OB
- ✅ 79% Fibonacci retracement

**Why it works:**
- FVG = price inefficiency
- Fib 79% = discount/premium pricing
- OB = smart money footprint

**Bonus (not required):**
- HTF bias adds confidence (reduce risk if unclear)

**When to use:**
- Clean pullback setups
- Low-spread sessions (London/NY open)
- When price respects Fibonacci levels

---

## 💰 Risk Management System

### Confirmation-Based Risk Sizing

**3 Confirmations = FULL RISK (1.0%)**
- All requirements met
- Maximum confidence
- Full position size

**2 Confirmations = HALF RISK (0.5%)**
- Core requirements met
- Reduced confidence
- 50% position size

**1 Confirmation = NO TRADE**
- Insufficient setup
- Wait for better opportunity

### Example:
```
Option 1 Setup:
✅ HTF Bias
✅ Liquidity Sweep  
✅ BoS
= 3 confirmations → Trade with 1% risk

Option 2 Setup:
✅ HTF Zone
✅ Order Block
❌ ChoCH (not present)
= 2 confirmations → Trade with 0.5% risk

Option 3 Setup:
✅ Order Block
❌ FVG (not overlapping)
❌ Fib (not aligned)
= 1 confirmation → NO TRADE
```

---

## 📊 Pair-Specific Priority

### EUR/USD & GBP/USD
**Priority Order:**
1. Liquidity sweep (Asian high/low)
2. BoS / ChoCH
3. OB alignment

**Key Rule:**
- If Asian range sweep + BoS shows, enter even without Fib

**Best Sessions:**
- London open (8-10 AM GMT)
- London/NY overlap (12-2 PM GMT)

### XAU/USD (Gold)
**Priority Order:**
1. HTF trend (4H)
2. 30M zone reaction
3. LTF ChoCH or BoS

**Key Rule:**
- Gold respects trend + zones more than Fibonacci
- Focus on Option 2 (HTF Zone + OB + ChoCH)

**Best Sessions:**
- London open
- NY session for reversals

---

## 🔍 How the Bot Analyzes

### For EUR/USD and GBP/USD:
1. **First try:** Option 1 (HTF + Liquidity + BoS)
2. **Second try:** Option 2 (HTF Zone + OB + ChoCH)
3. **Third try:** Option 3 (OB + FVG + Fib)

### For XAU/USD (Gold):
1. **First try:** Option 2 (HTF Zone + OB + ChoCH)
2. **Second try:** Option 1 (HTF + Liquidity + BoS)
3. **Third try:** Option 3 (OB + FVG + Fib)

---

## 📈 Signal Output Format

When a signal is detected, you'll see:

```
🎯 SIGNAL DETECTED FOR EURUSD!
   Setup: HTF_LIQUIDITY_BOS
   Confirmations: HTF_BIAS, LIQUIDITY_SWEEP, BOS (3/3)
   Type: long
   Entry: 1.17450
   Stop Loss: 1.17200
   Take Profit: 1.18200
   Risk/Reward: 1:3.0
   Risk Size: 100.0% (Full=True)
   Confidence: 0.85
```

**Understanding the output:**
- **Setup Type:** Which option triggered
- **Confirmations:** What conditions were met
- **Risk Size:** 100% = full risk, 50% = half risk
- **Confidence:** 0.60-0.95 (higher = more confluence)

---

## ⚙️ System Configuration

### Current Settings:
- **Max trades per day:** 2
- **Risk per trade:** 1% (full) or 0.5% (half)
- **Min Risk/Reward:** 1:2.5
- **Target Risk/Reward:** 1:3 to 1:5
- **Stop Loss range:** 30-150 pips

### Trading Sessions:
- **Active:** London (8 AM - 12 PM GMT), NY (12 PM - 4 PM GMT)
- **Avoided:** Asian session (low volatility)

---

## 🎓 Strategy Philosophy

### Why This Approach Works:

1. **Flexible but Disciplined**
   - Not hyper-focused on ALL confluences
   - Each option has core requirements
   - Bonus factors increase confidence

2. **Risk-Adapted**
   - More confirmations = more risk
   - Fewer confirmations = less risk
   - Never trade with just 1 confirmation

3. **Market-Adaptive**
   - Different options for different conditions
   - Pair-specific priorities
   - Session-aware

4. **Realistic**
   - Acknowledges that perfect setups are rare
   - Allows quality trades with 2-3 confirmations
   - Maintains selectivity (no forced trades)

---

## 📝 Quick Reference

### Minimum Requirements by Option:

| Option | Core | Bonus |
|--------|------|-------|
| **Option 1** | HTF + Liq + BoS | Fib, Asian sweep |
| **Option 2** | Zone + OB + ChoCH | Liq sweep, HTF bias |
| **Option 3** | OB + FVG + Fib | HTF bias |

### Risk Decision Tree:
```
3 confirmations → 1.0% risk → TRADE
2 confirmations → 0.5% risk → TRADE
1 confirmation → 0.0% risk → WAIT
0 confirmations → NO SETUP
```

---

## 🚀 Next Steps

1. **Monitor for 24-48 hours** to see signal frequency
2. **Check log output** when signals trigger
3. **Adjust if needed** based on market conditions
4. **Track results** to validate approach

### To check current signals:
```bash
curl -s http://localhost:5000/signals | python3 -m json.tool
```

### To view live logs:
```bash
tail -f logs/webhook.log
```

---

## 📞 Support

If signals are too frequent: Increase minimum confirmation count
If signals are too rare: Review option priorities for your pairs
If quality is low: Adjust confidence thresholds

**System is designed to be selective - no signals is better than bad signals!**
