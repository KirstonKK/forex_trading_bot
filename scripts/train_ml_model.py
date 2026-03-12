#!/usr/bin/env python3
"""
Train the ML Risk Model from historical trade data.

Reads completed trades from active_signals.json (detailed signal data)
and trade_history.json, builds training features, and trains the model.

Usage:
    python scripts/train_ml_model.py
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from machine_learning.ml_risk_model import MLRiskModel, ML_DIR, TRAINING_DATA_FILE


def load_signals():
    """Load all completed signals from active_signals.json."""
    signals_file = Path(__file__).parent.parent / 'data' / 'active_signals.json'
    if not signals_file.exists():
        print("ERROR: active_signals.json not found")
        return {}
    with open(signals_file) as f:
        return json.load(f)


def load_trade_history():
    """Load trade history for cross-reference."""
    history_file = Path(__file__).parent.parent / 'data' / 'trade_history.json'
    if not history_file.exists():
        return []
    with open(history_file) as f:
        return json.load(f)


def extract_training_features(signal: dict) -> dict:
    """
    Extract ML features from a completed signal.
    Maps the rich signal data to the FeatureExtractor schema.
    """
    confirmations = signal.get('confirmations', [])
    conf_count = len(confirmations)
    
    # Normalize confirmation count (1-8 range observed)
    norm_conf = min(conf_count, 8) / 8.0
    
    # Setup type encoding
    setup_types = {
        'HTF_LIQUIDITY_BOS': 0.0,
        'HTF_ZONE_OB_CHOCH': 0.2,
        'OB_FVG_FIB': 0.4,
        'LIQ_SWEEP_ENGULF': 0.6,
        'ICT_SWEEP_CONFIRM': 0.8,
        'ZONE_OB_FIB_SWEEP': 1.0,
    }
    setup_val = setup_types.get(signal.get('setup_type', ''), 0.5)
    
    # Boolean features from confirmations
    conf_str = ' '.join(confirmations)
    has_choch = 1.0 if 'CHOCH' in conf_str else 0.0
    has_bos = 1.0 if signal.get('has_bos', False) or 'BOS' in conf_str else 0.0
    has_fvg = 1.0 if 'FVG' in conf_str else 0.0
    has_ob = 1.0 if 'OB' in conf_str else 0.0
    has_liq_sweep = 1.0 if signal.get('has_liquidity_sweep', False) else 0.0
    
    # SL distance in pips
    entry = signal.get('entry_price', 0)
    sl = signal.get('stop_loss', 0)
    symbol = signal.get('symbol', '')
    if entry and sl:
        sl_distance = abs(entry - sl)
        multiplier = 10 if 'XAU' in symbol else 10000
        sl_pips = sl_distance * multiplier
        norm_sl = min(sl_pips, 100) / 100.0
    else:
        norm_sl = 0.5
    
    # HTF alignment
    htf_trend = signal.get('htf_trend', 'none')
    direction = signal.get('direction', '')
    htf_aligned = 0.0
    if (htf_trend == 'bearish' and direction == 'short') or \
       (htf_trend == 'bullish' and direction == 'long'):
        htf_aligned = 1.0
    elif htf_trend in ('none', 'ranging'):
        htf_aligned = 0.3  # Neutral — not aligned but not conflicting
    # else: 0.0 = counter-trend
    
    # Time features
    detected_at = signal.get('detected_at', '')
    hour = 12
    day_of_week = 2
    session_val = 0.33
    if detected_at:
        try:
            dt = datetime.fromisoformat(detected_at.replace('+00:00', '').replace('Z', ''))
            hour = dt.hour
            day_of_week = dt.weekday()
            
            # Session classification
            if 8 <= hour < 12:
                session_val = 0.0  # London
            elif 13 <= hour < 17:
                session_val = 0.33  # NY
            elif 12 <= hour < 13:
                session_val = 0.67  # Overlap
            else:
                session_val = 1.0  # Off-session
        except:
            pass
    
    # Session open hours
    session_start = 8
    hours_active = max(0, min(8, hour - session_start)) / 8.0
    
    # Fib confluence
    has_fib = 1.0 if signal.get('has_fib_confluence', False) else 0.0
    
    # Asian sweep
    asian_sweep = 1.0 if signal.get('asian_sweep', False) else 0.0
    
    # Risk/Reward
    rr = signal.get('risk_reward', 2.0)
    
    # Confidence from strategy
    strategy_confidence = signal.get('confidence', 0.85)
    
    # Symbol encoding (for pair-specific performance tracking)
    symbol_map = {'EUR_USD': 0.0, 'GBP_USD': 0.5, 'XAU_USD': 1.0}
    symbol_val = symbol_map.get(symbol, 0.5)
    
    # ML risk multiplier from previous scoring (if available)
    ml_conf = signal.get('ml_confidence', 70) / 100.0
    
    features = {
        'confirmation_count': norm_conf,
        'setup_type': setup_val,
        'has_choch': has_choch,
        'has_bos': has_bos,
        'has_fvg': has_fvg,
        'has_ob': has_ob,
        'has_liquidity_sweep': has_liq_sweep,
        'fvg_size_pct': 0.5,  # Not available in signal data
        'ob_strength': 0.5,   # Not available in signal data
        'distance_to_sl_pips': norm_sl,
        'atr_normalized': 0.5,  # Not available
        'session': session_val,
        'trend_strength': htf_aligned,  # Use alignment as proxy
        'hours_since_session_open': hours_active,
        'day_of_week': min(day_of_week, 4) / 4.0,
        'htf_bias_aligned': htf_aligned,
        'htf_in_zone': 1.0 if 'HTF_ZONE' in conf_str else 0.0,
        'mtf_alignment_score': htf_aligned * 0.8 + has_bos * 0.2,
        'pair_win_rate_10': 0.5,  # Will be computed below
        'hour_win_rate': 0.5,     # Will be computed below
        'setup_type_win_rate': 0.5,  # Will be computed below
        'streak': 0.5,  # Neutral
    }
    
    return features


def compute_rolling_stats(signals_list: list) -> dict:
    """Compute rolling win rates by pair, hour, setup type."""
    pair_history = defaultdict(list)
    hour_history = defaultdict(list)
    setup_history = defaultdict(list)
    
    for sig in signals_list:
        outcome = 1 if sig.get('status') == 'win' else 0
        symbol = sig.get('symbol', '')
        setup = sig.get('setup_type', '')
        
        detected_at = sig.get('detected_at', '')
        hour = 12
        if detected_at:
            try:
                dt = datetime.fromisoformat(detected_at.replace('+00:00', '').replace('Z', ''))
                hour = dt.hour
            except:
                pass
        
        pair_history[symbol].append(outcome)
        hour_history[hour].append(outcome)
        setup_history[setup].append(outcome)
    
    return {
        'pair': {k: sum(v)/len(v) if v else 0.5 for k, v in pair_history.items()},
        'hour': {k: sum(v)/len(v) if v else 0.5 for k, v in hour_history.items()},
        'setup': {k: sum(v)/len(v) if v else 0.5 for k, v in setup_history.items()},
    }


def main():
    print("=" * 60)
    print("ML RISK MODEL TRAINING")
    print("=" * 60)
    
    # Load data
    signals = load_signals()
    trade_history = load_trade_history()
    
    # Filter to completed trades only (win/loss)
    completed = {k: v for k, v in signals.items() 
                 if v.get('status') in ('win', 'loss')}
    
    print(f"\nData loaded:")
    print(f"  Total signals: {len(signals)}")
    print(f"  Completed (win/loss): {len(completed)}")
    print(f"  Trade history records: {len(trade_history)}")
    
    if len(completed) < 10:
        print("\nERROR: Need at least 10 completed trades to train.")
        return
    
    # Sort by timestamp for rolling stats
    sorted_signals = sorted(completed.values(), key=lambda x: x.get('timestamp', 0))
    
    # Compute rolling statistics
    rolling_stats = compute_rolling_stats(sorted_signals)
    
    print(f"\nRolling stats computed:")
    for pair, wr in rolling_stats['pair'].items():
        print(f"  {pair}: {wr*100:.1f}% WR")
    for setup, wr in rolling_stats['setup'].items():
        print(f"  {setup}: {wr*100:.1f}% WR")
    
    # Build training data
    training_data = []
    wins = 0
    losses = 0
    
    # Process in chronological order for rolling context
    pair_recent = defaultdict(list)  # Last 10 trades per pair
    streak = 0
    
    for signal in sorted_signals:
        outcome = signal.get('status', '')
        symbol = signal.get('symbol', '')
        setup = signal.get('setup_type', '')
        pips = signal.get('pips_result', 0)
        
        # Extract features
        features = extract_training_features(signal)
        
        # Inject rolling stats
        features['pair_win_rate_10'] = rolling_stats['pair'].get(symbol, 0.5)
        features['setup_type_win_rate'] = rolling_stats['setup'].get(setup, 0.5)
        
        detected_at = signal.get('detected_at', '')
        hour = 12
        if detected_at:
            try:
                dt = datetime.fromisoformat(detected_at.replace('+00:00', '').replace('Z', ''))
                hour = dt.hour
            except:
                pass
        features['hour_win_rate'] = rolling_stats['hour'].get(hour, 0.5)
        
        # Streak
        norm_streak = max(-5, min(5, streak))
        features['streak'] = (norm_streak + 5) / 10.0
        
        # Update streak
        if outcome == 'win':
            streak = max(0, streak) + 1
            wins += 1
        else:
            streak = min(0, streak) - 1
            losses += 1
        
        sample = {
            'timestamp': signal.get('detected_at', ''),
            'features': features,
            'outcome': outcome,
            'pips': pips,
            'symbol': symbol,
            'setup_type': setup,
        }
        training_data.append(sample)
    
    print(f"\nTraining data prepared:")
    print(f"  Samples: {len(training_data)}")
    print(f"  Wins: {wins}, Losses: {losses}")
    print(f"  Win rate: {wins/len(training_data)*100:.1f}%")
    
    # Save training data
    ML_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRAINING_DATA_FILE, 'w') as f:
        json.dump(training_data, f, indent=2)
    print(f"\n  Saved training data to {TRAINING_DATA_FILE}")
    
    # Train the model
    model = MLRiskModel()
    model.training_data = training_data
    model.min_training_samples = 10  # Lower threshold for training
    
    metrics = model.train()
    print(f"\nTraining results:")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    if metrics.get('status') != 'trained':
        print("\nTraining did not complete successfully. Aborting diagnostics.")
        return
    
    # Test the model using TRAINING FEATURES directly. This validates
    # the trained scorer irrespective of underlying model type.
    print(f"\n--- Score Distribution on Training Data ---")
    import numpy as np
    
    feature_names = sorted([
        'confirmation_count', 'setup_type', 'has_choch', 'has_bos', 'has_fvg',
        'has_ob', 'has_liquidity_sweep', 'fvg_size_pct', 'ob_strength',
        'distance_to_sl_pips', 'atr_normalized', 'session', 'trend_strength',
        'hours_since_session_open', 'day_of_week', 'htf_bias_aligned',
        'htf_in_zone', 'mtf_alignment_score', 'pair_win_rate_10',
        'hour_win_rate', 'setup_type_win_rate', 'streak'
    ])
    
    score_buckets = {'skip (0-39)': {'total': 0, 'wins': 0},
                     'quarter (40-49)': {'total': 0, 'wins': 0},
                     'half (50-59)': {'total': 0, 'wins': 0},
                     'three_quarter (60-74)': {'total': 0, 'wins': 0},
                     'full (75-100)': {'total': 0, 'wins': 0}}
    correct = 0
    total = 0
    
    for sample in training_data:
        vec = np.array([sample['features'].get(fn, 0.5) for fn in feature_names], dtype=float).reshape(1, -1)
        proba = float(model._predict_proba(vec)[0])
        conf = int(proba * 100)
        
        if conf < 40:
            bucket = 'skip (0-39)'
        elif conf < 50:
            bucket = 'quarter (40-49)'
        elif conf < 60:
            bucket = 'half (50-59)'
        elif conf < 75:
            bucket = 'three_quarter (60-74)'
        else:
            bucket = 'full (75-100)'
        
        score_buckets[bucket]['total'] += 1
        if sample['outcome'] == 'win':
            score_buckets[bucket]['wins'] += 1
        
        predicted_win = conf >= 50
        actual_win = sample['outcome'] == 'win'
        if predicted_win == actual_win:
            correct += 1
        total += 1
    
    for bucket, data in score_buckets.items():
        if data['total'] > 0:
            wr = data['wins'] / data['total'] * 100
            print(f"  {bucket}: {data['total']} trades ({wr:.0f}% actual WR)")
        else:
            print(f"  {bucket}: 0 trades")
    
    print(f"\n  Classification accuracy: {correct/total*100:.1f}%")
    
    # Show model stats
    stats = model.get_model_stats()
    print(f"\nModel stats:")
    for k, v in stats.items():
        if k == 'by_symbol':
            for sym, data in v.items():
                wr = data['wins'] / data['total'] * 100 if data['total'] > 0 else 0
                print(f"  {sym}: {data['wins']}/{data['total']} ({wr:.1f}% WR)")
        elif isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")
    
    print(f"\n{'='*60}")
    print("ML MODEL TRAINED AND SAVED SUCCESSFULLY")
    print(f"  Model file: {ML_DIR / 'risk_model.pkl'}")
    print(f"  Training data: {TRAINING_DATA_FILE}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
