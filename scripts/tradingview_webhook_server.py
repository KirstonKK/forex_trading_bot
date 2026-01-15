"""
TradingView Webhook Server
Receives real-time market data from TradingView and runs your ICT/SMC strategy.
NO BROKER CONNECTION - Pure analysis and logging.

How it works:
1. TradingView monitors market 24/7 with real exchange data
2. Sends webhook with current price data every bar close
3. Bot runs your enhanced SMC strategy on the data
4. Logs trading signals (no actual trades executed)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from datetime import datetime
import logging
import json
from typing import Dict, List

# Import strategy only (no broker connectors)
from core.enhanced_smc_strategy import EnhancedSMCStrategy
from core.enhanced_risk_manager import EnhancedRiskManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/webhook.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configuration
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'your_secret_key_here')
ACCOUNT_BALANCE = 10000.0

# Store market data in memory
market_data = {}

# Initialize strategy
strategy = EnhancedSMCStrategy()

# Initialize risk manager
risk_manager = EnhancedRiskManager(
    account_balance=ACCOUNT_BALANCE,
    risk_per_trade=1.0,
    max_daily_loss=4.0,
    max_trades_per_day=2
)


@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Receive market data from TradingView and analyze with your strategy.
    
    Expected JSON from TradingView:
    {
        "secret": "your_secret_key_here",
        "symbol": "EURUSD",
        "timeframe": "5M",
        "time": 1234567890,
        "open": 1.1234,
        "high": 1.1245,
        "low": 1.1220,
        "close": 1.1240,
        "volume": 1000
    }
    """
    try:
        # Get JSON data
        data = request.get_json()
        
        if not data:
            logger.error("No JSON data received")
            return jsonify({'error': 'No data provided'}), 400
        
        logger.info(f"Market data received: {data.get('symbol')} @ {data.get('close')}")
        
        # Verify secret
        if data.get('secret') != WEBHOOK_SECRET:
            logger.error("Invalid webhook secret")
            return jsonify({'error': 'Invalid secret'}), 401
        
        # Extract candle data
        symbol = data.get('symbol', '').replace('/', '_')  # Convert EURUSD to EUR_USD
        if len(symbol) == 6:
            symbol = f"{symbol[:3]}_{symbol[3:]}"
        
        timeframe = data.get('timeframe', '5M')
        
        # Store candle data
        if symbol not in market_data:
            market_data[symbol] = {
                '4H': {'time': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []},
                '1H': {'time': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []},
                '5M': {'time': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []}
            }
        
        # Add new candle
        if timeframe in market_data[symbol]:
            candles = market_data[symbol][timeframe]
            candles['time'].append(int(data.get('time', datetime.now().timestamp())))
            candles['open'].append(float(data.get('open', 0)))
            candles['high'].append(float(data.get('high', 0)))
            candles['low'].append(float(data.get('low', 0)))
            candles['close'].append(float(data.get('close', 0)))
            candles['volume'].append(int(data.get('volume', 0)))
            
            # Keep last 100 candles only
            for key in candles:
                if len(candles[key]) > 100:
                    candles[key] = candles[key][-100:]
        
        # Check if we have enough data to analyze
        if (len(market_data[symbol].get('4H', {}).get('close', [])) >= 50 and
            len(market_data[symbol].get('1H', {}).get('close', [])) >= 50 and
            len(market_data[symbol].get('5M', {}).get('close', [])) >= 50):
            
            # Run strategy analysis
            current_price = data.get('close', 0)
            signal = strategy.generate_signal(
                symbol=symbol,
                candles_4h=market_data[symbol]['4H'],
                candles_1h=market_data[symbol]['1H'],
                candles_5m=market_data[symbol]['5M'],
                current_price=current_price
            )
            
            if signal:
                logger.info(f"\n🎯 SIGNAL DETECTED FOR {symbol}!")
                logger.info(f"   Type: {signal['type']}")
                logger.info(f"   Entry: {signal['entry']:.5f}")
                logger.info(f"   Stop Loss: {signal['stop_loss']:.5f}")
                logger.info(f"   Take Profit: {signal['take_profit']:.5f}")
                logger.info(f"   Risk/Reward: 1:{signal['risk_reward']:.2f}")
                logger.info(f"   Reason: {signal.get('reason', 'SMC setup')}")
                
                return jsonify({
                    'status': 'signal_detected',
                    'signal': signal,
                    'message': f'{signal["type"]} signal for {symbol}'
                }), 200
            else:
                return jsonify({
                    'status': 'no_signal',
                    'message': f'No setup for {symbol} at {current_price:.5f}'
                }), 200
        else:
            return jsonify({
                'status': 'collecting_data',
                'message': f'Need more data for {symbol}',
                'candles': {
                    '4H': len(market_data[symbol].get('4H', {}).get('close', [])),
                    '1H': len(market_data[symbol].get('1H', {}).get('close', [])),
                    '5M': len(market_data[symbol].get('5M', {}).get('close', []))
                }
            }), 200
            
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'running',
        'mode': 'analysis_only',
        'symbols_tracked': list(market_data.keys()),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/data', methods=['GET'])
def get_data():
    """Get stored market data."""
    symbol = request.args.get('symbol', None)
    if symbol:
        return jsonify({
            'status': 'success',
            'symbol': symbol,
            'data': market_data.get(symbol, {})
        })
    else:
        return jsonify({
            'status': 'success',
            'symbols': list(market_data.keys()),
            'data': market_data
        })


@app.route('/signals', methods=['GET'])
def get_signals():
    """Get latest signals for all tracked symbols."""
    signals = {}
    for symbol, data in market_data.items():
        if (len(data.get('4H', {}).get('close', [])) >= 50 and
            len(data.get('1H', {}).get('close', [])) >= 50 and
            len(data.get('5M', {}).get('close', [])) >= 50):
            
            current_price = data['5M']['close'][-1]
            signal = strategy.generate_signal(
                symbol=symbol,
                candles_4h=data['4H'],
                candles_1h=data['1H'],
                candles_5m=data['5M'],
                current_price=current_price
            )
            signals[symbol] = signal if signal else {'status': 'no_setup'}
    
    return jsonify({
        'status': 'success',
        'signals': signals
    })


if __name__ == '__main__':
    PORT = 8080
    
    print("\n" + "="*70)
    print("TRADINGVIEW STRATEGY ANALYZER")
    print("="*70)
    print("Mode: ANALYSIS ONLY (No broker, no real trades)")
    print(f"Webhook Secret: {WEBHOOK_SECRET}")
    print(f"\nServer starting on http://localhost:{PORT}")
    print("\nEndpoints:")
    print("  POST /webhook  - Receive TradingView market data")
    print("  GET  /health   - Health check")
    print("  GET  /data     - View collected market data")
    print("  GET  /signals  - Check current strategy signals")
    print("\nTo connect TradingView:")
    print("  1. Install ngrok: brew install ngrok")
    print(f"  2. Run: ngrok http {PORT}")
    print("  3. Copy HTTPS URL (e.g., https://abc123.ngrok.io)")
    print("  4. In TradingView, create alert with webhook:")
    print(f"     https://abc123.ngrok.io/webhook")
    print("\n📊 Your strategy will analyze real TradingView data")
    print("   Signals will be logged (no trades executed)")
    print("="*70 + "\n")
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Run server
    app.run(host='0.0.0.0', port=PORT, debug=False)
