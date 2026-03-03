#!/usr/bin/env python3
"""
Signal TP/SL Hit Analysis
Analyzes whether generated signals are hitting Take Profit or Stop Loss levels.
"""

import json
from collections import defaultdict
from datetime import datetime

TRADE_HISTORY = "/home/vanhansen53/forex_trading_bot/data/trade_history.json"
ACTIVE_SIGNALS = "/home/vanhansen53/forex_trading_bot/data/active_signals.json"

def load_data():
    with open(TRADE_HISTORY) as f:
        trades = json.load(f)
    with open(ACTIVE_SIGNALS) as f:
        signals = json.load(f)
    return trades, signals

def analyze():
    trades, signals = load_data()
    
    # --- Filter resolved trades from active_signals (has exit_price) ---
    resolved_signals = {}
    for sid, s in signals.items():
        if s.get("status") in ("win", "loss", "expired"):
            resolved_signals[sid] = s

    # Combine: trade_history is the canonical list of filled trades
    # active_signals has ALL signals including cancelled/expired/unfilled
    
    print("=" * 80)
    print("  FOREX TRADING BOT — TP/SL HIT ANALYSIS")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    # ===== SECTION 1: Overall Stats from trade_history (filled trades only) =====
    total = len(trades)
    wins = [t for t in trades if t["status"] == "win"]
    losses = [t for t in trades if t["status"] == "loss"]
    expired = [t for t in trades if t["status"] == "expired"]
    
    print(f"\n{'─' * 80}")
    print("  1. FILLED TRADE OUTCOMES (trade_history.json)")
    print(f"{'─' * 80}")
    print(f"  Total filled trades:  {total}")
    print(f"  TP Hit (wins):        {len(wins)}  ({len(wins)/total*100:.1f}%)")
    print(f"  SL Hit (losses):      {len(losses)}  ({len(losses)/total*100:.1f}%)")
    print(f"  Expired:              {len(expired)}  ({len(expired)/total*100:.1f}%)")
    
    # ===== SECTION 2: All Signal Statuses (including unfilled) =====
    all_statuses = defaultdict(int)
    for sid, s in signals.items():
        all_statuses[s["status"]] += 1
    
    total_signals = len(signals)
    print(f"\n{'─' * 80}")
    print("  2. ALL SIGNAL STATUSES (active_signals.json)")
    print(f"{'─' * 80}")
    print(f"  Total signals generated:  {total_signals}")
    for status, count in sorted(all_statuses.items(), key=lambda x: -x[1]):
        pct = count / total_signals * 100
        bar = "█" * int(pct / 2)
        print(f"    {status:12s}  {count:3d}  ({pct:5.1f}%)  {bar}")
    
    # Unfilled entries
    unfilled = [s for s in signals.values() if s.get("entry_filled") == False]
    cancelled = [s for s in signals.values() if s["status"] == "cancelled"]
    expired_sigs = [s for s in signals.values() if s["status"] == "expired"]
    
    filled_count = len([s for s in signals.values() if s["status"] in ("win", "loss")])
    print(f"\n  Signals that got filled & resolved: {filled_count} / {total_signals} ({filled_count/total_signals*100:.1f}%)")
    print(f"  Never filled (limit not reached):   {len(unfilled)}")
    print(f"  Cancelled before market open:       {len(cancelled)}")
    
    # ===== SECTION 3: Win Rate by Symbol =====
    print(f"\n{'─' * 80}")
    print("  3. WIN RATE BY SYMBOL")
    print(f"{'─' * 80}")
    
    by_symbol = defaultdict(lambda: {"wins": 0, "losses": 0, "expired": 0, "total_pips": 0.0})
    for t in trades:
        sym = t["symbol"]
        if t["status"] == "win":
            by_symbol[sym]["wins"] += 1
        elif t["status"] == "loss":
            by_symbol[sym]["losses"] += 1
        else:
            by_symbol[sym]["expired"] += 1
        by_symbol[sym]["total_pips"] += t.get("pips_result", 0)
    
    print(f"  {'Symbol':<12} {'Trades':>7} {'Wins':>6} {'Losses':>7} {'Win%':>7} {'Net Pips':>10}")
    print(f"  {'─'*12} {'─'*7} {'─'*6} {'─'*7} {'─'*7} {'─'*10}")
    for sym in sorted(by_symbol.keys()):
        d = by_symbol[sym]
        total_sym = d["wins"] + d["losses"] + d["expired"]
        wr = d["wins"] / (d["wins"] + d["losses"]) * 100 if (d["wins"] + d["losses"]) > 0 else 0
        print(f"  {sym:<12} {total_sym:>7} {d['wins']:>6} {d['losses']:>7} {wr:>6.1f}% {d['total_pips']:>+10.1f}")
    
    # ===== SECTION 4: Win Rate by Setup Type =====
    print(f"\n{'─' * 80}")
    print("  4. WIN RATE BY SETUP TYPE")
    print(f"{'─' * 80}")
    
    by_setup = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pips": 0.0, "rr_list": []})
    for t in trades:
        st = t.get("setup_type", "UNKNOWN")
        if t["status"] == "win":
            by_setup[st]["wins"] += 1
        elif t["status"] == "loss":
            by_setup[st]["losses"] += 1
        by_setup[st]["total_pips"] += t.get("pips_result", 0)
        if t.get("rr_achieved"):
            by_setup[st]["rr_list"].append(t["rr_achieved"])
    
    print(f"  {'Setup Type':<25} {'Trades':>7} {'Wins':>6} {'Losses':>7} {'Win%':>7} {'Avg RR':>8} {'Net Pips':>10}")
    print(f"  {'─'*25} {'─'*7} {'─'*6} {'─'*7} {'─'*7} {'─'*8} {'─'*10}")
    for st in sorted(by_setup.keys(), key=lambda k: -(by_setup[k]["wins"] + by_setup[k]["losses"])):
        d = by_setup[st]
        total_st = d["wins"] + d["losses"]
        wr = d["wins"] / total_st * 100 if total_st > 0 else 0
        avg_rr = sum(d["rr_list"]) / len(d["rr_list"]) if d["rr_list"] else 0
        print(f"  {st:<25} {total_st:>7} {d['wins']:>6} {d['losses']:>7} {wr:>6.1f}% {avg_rr:>+8.2f} {d['total_pips']:>+10.1f}")
    
    # ===== SECTION 5: Win Rate by Direction =====
    print(f"\n{'─' * 80}")
    print("  5. WIN RATE BY DIRECTION")
    print(f"{'─' * 80}")
    
    by_dir = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pips": 0.0})
    for t in trades:
        d_key = t["direction"]
        if t["status"] == "win":
            by_dir[d_key]["wins"] += 1
        elif t["status"] == "loss":
            by_dir[d_key]["losses"] += 1
        by_dir[d_key]["total_pips"] += t.get("pips_result", 0)
    
    for d_key in sorted(by_dir.keys()):
        d = by_dir[d_key]
        total_d = d["wins"] + d["losses"]
        wr = d["wins"] / total_d * 100 if total_d > 0 else 0
        print(f"  {d_key.upper():<8}  Trades: {total_d}  Wins: {d['wins']}  Losses: {d['losses']}  Win%: {wr:.1f}%  Net Pips: {d['total_pips']:+.1f}")
    
    # ===== SECTION 6: RR Analysis =====
    print(f"\n{'─' * 80}")
    print("  6. RISK-REWARD ANALYSIS")
    print(f"{'─' * 80}")
    
    target_rrs = [t.get("rr_achieved", 0) for t in trades if t["status"] == "win"]
    if target_rrs:
        print(f"  Avg RR on wins:       {sum(target_rrs)/len(target_rrs):.2f}")
        print(f"  Min RR on wins:       {min(target_rrs):.2f}")
        print(f"  Max RR on wins:       {max(target_rrs):.2f}")
    
    all_rr = [t.get("rr_achieved", 0) for t in trades if t["status"] in ("win", "loss")]
    if all_rr:
        print(f"  Avg RR (all trades):  {sum(all_rr)/len(all_rr):.2f}")
    
    # Expected value calc
    wl_trades = [t for t in trades if t["status"] in ("win", "loss")]
    if wl_trades:
        win_rate = len(wins) / len(wl_trades)
        avg_win_rr = sum(target_rrs) / len(target_rrs) if target_rrs else 0
        avg_loss_rr = 1.0  # all losses exit at SL = -1R
        ev = (win_rate * avg_win_rr) - ((1 - win_rate) * avg_loss_rr)
        print(f"\n  Win Rate:             {win_rate*100:.1f}%")
        print(f"  Avg Win (R):          +{avg_win_rr:.2f}R")
        print(f"  Avg Loss (R):         -1.00R")
        print(f"  Expected Value (R):   {ev:+.3f}R per trade")
        if ev > 0:
            print(f"  >> POSITIVE EDGE:     System has positive expectancy")
        else:
            print(f"  >> NEGATIVE EDGE:     System is losing money on average")
    
    # ===== SECTION 7: TP vs SL Exit Verification =====
    print(f"\n{'─' * 80}")
    print("  7. EXIT PRICE VERIFICATION (Did price actually hit TP/SL?)")
    print(f"{'─' * 80}")
    
    tp_match = 0
    sl_match = 0
    tp_mismatch = 0
    sl_mismatch = 0
    
    for t in trades:
        if t["status"] == "win":
            if abs(t["exit_price"] - t["take_profit"]) < 0.001:
                tp_match += 1
            else:
                tp_mismatch += 1
                # print(f"    TP MISMATCH: {t['signal_id']} exit={t['exit_price']:.5f} vs tp={t['take_profit']:.5f}")
        elif t["status"] == "loss":
            if abs(t["exit_price"] - t["stop_loss"]) < 0.5:  # wider tolerance for XAU
                sl_match += 1
            else:
                sl_mismatch += 1
                # print(f"    SL MISMATCH: {t['signal_id']} exit={t['exit_price']:.5f} vs sl={t['stop_loss']:.5f}")
    
    print(f"  Wins exiting at exact TP:     {tp_match}/{len(wins)} ({tp_match/len(wins)*100:.0f}%)")
    print(f"  Wins NOT at exact TP:         {tp_mismatch}/{len(wins)}")
    print(f"  Losses exiting at exact SL:   {sl_match}/{len(losses)} ({sl_match/len(losses)*100:.0f}%)")
    print(f"  Losses NOT at exact SL:       {sl_mismatch}/{len(losses)}")
    
    # ===== SECTION 8: Time to Hit TP vs SL =====
    print(f"\n{'─' * 80}")
    print("  8. TIME-TO-EXIT ANALYSIS")
    print(f"{'─' * 80}")
    
    win_durations = []
    loss_durations = []
    
    for t in trades:
        try:
            entry_str = t["entry_time"]
            exit_str = t["exit_time"]
            # Parse entry
            if "T" in entry_str:
                entry_dt = datetime.fromisoformat(entry_str.replace("Z", "+00:00"))
            else:
                entry_dt = datetime.strptime(entry_str, "%Y-%m-%d %H:%M:%S")
            # Parse exit  
            exit_dt = datetime.fromisoformat(exit_str.replace("Z", "+00:00"))
            # Remove tz for comparison if mixed
            entry_dt = entry_dt.replace(tzinfo=None)
            exit_dt = exit_dt.replace(tzinfo=None)
            
            duration_hrs = (exit_dt - entry_dt).total_seconds() / 3600
            if duration_hrs < 0:
                continue
                
            if t["status"] == "win":
                win_durations.append(duration_hrs)
            elif t["status"] == "loss":
                loss_durations.append(duration_hrs)
        except Exception:
            continue
    
    if win_durations:
        print(f"  Avg time to TP:    {sum(win_durations)/len(win_durations):.1f} hours")
        print(f"  Fastest TP hit:    {min(win_durations):.2f} hours")
        print(f"  Slowest TP hit:    {max(win_durations):.1f} hours")
    if loss_durations:
        print(f"  Avg time to SL:    {sum(loss_durations)/len(loss_durations):.1f} hours")
        print(f"  Fastest SL hit:    {min(loss_durations):.2f} hours")
        print(f"  Slowest SL hit:    {max(loss_durations):.1f} hours")
    
    if win_durations and loss_durations:
        avg_win_t = sum(win_durations) / len(win_durations)
        avg_loss_t = sum(loss_durations) / len(loss_durations)
        if avg_loss_t < avg_win_t:
            print(f"\n  >> WARNING: SL is hit faster ({avg_loss_t:.1f}h) than TP ({avg_win_t:.1f}h)")
            print(f"     This suggests price moves against entries before reversing.")
        else:
            print(f"\n  >> GOOD: TP is hit faster ({avg_win_t:.1f}h) than SL ({avg_loss_t:.1f}h)")

    # ===== SECTION 9: Consecutive Patterns =====
    print(f"\n{'─' * 80}")
    print("  9. STREAK ANALYSIS")
    print(f"{'─' * 80}")
    
    max_win_streak = 0
    max_loss_streak = 0
    cur_win = 0
    cur_loss = 0
    
    for t in trades:
        if t["status"] == "win":
            cur_win += 1
            cur_loss = 0
            max_win_streak = max(max_win_streak, cur_win)
        elif t["status"] == "loss":
            cur_loss += 1
            cur_win = 0
            max_loss_streak = max(max_loss_streak, cur_loss)
        else:
            cur_win = 0
            cur_loss = 0
    
    print(f"  Max consecutive wins:   {max_win_streak}")
    print(f"  Max consecutive losses: {max_loss_streak}")
    
    # ===== SECTION 10: Daily Performance =====
    print(f"\n{'─' * 80}")
    print("  10. PERFORMANCE BY DATE")
    print(f"{'─' * 80}")
    
    by_date = defaultdict(lambda: {"wins": 0, "losses": 0, "pips": 0.0})
    for t in trades:
        date_str = t["entry_time"][:10]
        if t["status"] == "win":
            by_date[date_str]["wins"] += 1
        elif t["status"] == "loss":
            by_date[date_str]["losses"] += 1
        by_date[date_str]["pips"] += t.get("pips_result", 0)
    
    print(f"  {'Date':<12} {'W':>3} {'L':>3} {'Win%':>7} {'Pips':>10} {'Visual':>20}")
    print(f"  {'─'*12} {'─'*3} {'─'*3} {'─'*7} {'─'*10} {'─'*20}")
    for date in sorted(by_date.keys()):
        d = by_date[date]
        total_d = d["wins"] + d["losses"]
        wr = d["wins"] / total_d * 100 if total_d > 0 else 0
        bar = "+" * d["wins"] + "-" * d["losses"]
        print(f"  {date:<12} {d['wins']:>3} {d['losses']:>3} {wr:>6.1f}% {d['pips']:>+10.1f}  {bar}")
    
    # ===== SECTION 11: Confidence Analysis =====
    print(f"\n{'─' * 80}")
    print("  11. WIN RATE BY CONFIDENCE LEVEL")
    print(f"{'─' * 80}")
    
    by_conf = defaultdict(lambda: {"wins": 0, "losses": 0})
    for t in trades:
        conf = t.get("confidence", 0)
        bucket = f"{conf:.2f}"
        if t["status"] == "win":
            by_conf[bucket]["wins"] += 1
        elif t["status"] == "loss":
            by_conf[bucket]["losses"] += 1
    
    for conf in sorted(by_conf.keys()):
        d = by_conf[conf]
        total_c = d["wins"] + d["losses"]
        wr = d["wins"] / total_c * 100 if total_c > 0 else 0
        print(f"  Conf={conf}  Trades: {total_c:>3}  Win%: {wr:>5.1f}%  W:{d['wins']} L:{d['losses']}")

    # ===== SUMMARY =====
    print(f"\n{'=' * 80}")
    print("  SUMMARY & KEY FINDINGS")
    print(f"{'=' * 80}")
    
    wl_count = len(wins) + len(losses)
    overall_wr = len(wins) / wl_count * 100 if wl_count > 0 else 0
    total_pips = sum(t.get("pips_result", 0) for t in trades)
    
    print(f"""
  Overall Win Rate:     {overall_wr:.1f}% ({len(wins)}W / {len(losses)}L out of {wl_count} resolved)
  Total Net Pips:       {total_pips:+.1f}
  
  KEY OBSERVATIONS:
  """)
    
    # Check if all wins exit at TP and all losses at SL
    print(f"  1. EXIT ACCURACY: {tp_match}/{len(wins)} wins exit at exact TP price,")
    print(f"     {sl_match}/{len(losses)} losses exit at exact SL price.")
    if tp_match == len(wins) and sl_match == len(losses):
        print(f"     -> Trades are binary: they always hit either TP or SL exactly.")
        print(f"     -> No partial TPs or early manual exits detected.")
    
    # Check if profitable
    if ev > 0:
        print(f"\n  2. EDGE: Expected value of {ev:+.3f}R per trade is POSITIVE.")
        print(f"     Avg win of {avg_win_rr:.2f}R compensates for {(1-win_rate)*100:.1f}% loss rate.")
    else:
        print(f"\n  2. EDGE: Expected value of {ev:+.3f}R per trade is NEGATIVE.")
        print(f"     {overall_wr:.0f}% win rate with avg {avg_win_rr:.2f}R wins is NOT enough")
        print(f"     to cover the {100-overall_wr:.0f}% of trades hitting SL at -1R.")
        need_wr = 1 / (1 + avg_win_rr)
        print(f"     Need at least {need_wr*100:.1f}% win rate at {avg_win_rr:.2f}R to break even.")
    
    # Speed analysis
    if win_durations and loss_durations:
        avg_wt = sum(win_durations)/len(win_durations)
        avg_lt = sum(loss_durations)/len(loss_durations)
        if avg_lt < avg_wt:
            print(f"\n  3. ENTRY TIMING: SL is hit in avg {avg_lt:.1f}h vs TP in {avg_wt:.1f}h.")
            print(f"     Entries may be too early — price moves against before going to target.")
        else:
            print(f"\n  3. ENTRY TIMING: TP reached faster ({avg_wt:.1f}h) than SL ({avg_lt:.1f}h) - GOOD.")
    
    # Biggest problem areas
    worst_setup = min(by_setup.items(), key=lambda x: x[1]["total_pips"])
    best_setup = max(by_setup.items(), key=lambda x: x[1]["total_pips"])
    print(f"\n  4. BEST SETUP:  {best_setup[0]} ({best_setup[1]['total_pips']:+.0f} pips)")
    print(f"     WORST SETUP: {worst_setup[0]} ({worst_setup[1]['total_pips']:+.0f} pips)")
    
    worst_sym = min(by_symbol.items(), key=lambda x: x[1]["total_pips"])
    best_sym = max(by_symbol.items(), key=lambda x: x[1]["total_pips"])
    print(f"\n  5. BEST SYMBOL:  {best_sym[0]} ({best_sym[1]['total_pips']:+.0f} pips)")
    print(f"     WORST SYMBOL: {worst_sym[0]} ({worst_sym[1]['total_pips']:+.0f} pips)")

    print(f"\n{'=' * 80}")


if __name__ == "__main__":
    analyze()
