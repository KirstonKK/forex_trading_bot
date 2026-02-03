"""
News Event Filter
Pauses trading during high-impact economic events
"""

import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import os

class NewsFilter:
    """Filter to pause trading around high-impact news events"""
    
    # Major economic events that move EUR, GBP, USD, XAU
    HIGH_IMPACT_EVENTS = [
        # USD Events
        "Non-Farm Payrolls", "NFP", "Nonfarm Payrolls",
        "FOMC", "Federal Reserve", "Fed Chair", "Fed Interest Rate",
        "CPI", "Consumer Price Index", "Core CPI",
        "PPI", "Producer Price Index",
        "GDP", "Gross Domestic Product",
        "Unemployment Rate", "Jobless Claims", "Initial Claims",
        "Retail Sales", "Core Retail Sales",
        "ISM Manufacturing", "ISM Services", "ISM PMI",
        "ADP Employment", "ADP Non-Farm",
        "Trade Balance", "Current Account",
        "Durable Goods", "Core Durable Goods",
        "Treasury", "10-Year Auction",
        
        # EUR Events
        "ECB", "European Central Bank", "ECB Rate", "Lagarde",
        "German GDP", "German CPI", "German ZEW",
        "Eurozone CPI", "Eurozone GDP", "Euro Zone",
        "German Manufacturing PMI", "German Services PMI",
        "French CPI", "French GDP",
        "EU Employment", "EU Trade Balance",
        
        # GBP Events
        "BOE", "Bank of England", "MPC", "BOE Rate",
        "UK GDP", "UK CPI", "UK Retail Sales",
        "UK Employment", "UK Unemployment",
        "UK Manufacturing PMI", "UK Services PMI",
        "UK Trade Balance", "UK Current Account",
        "Claimant Count", "Average Earnings",
        
        # Gold Events
        "Gold Demand", "COMEX", "Physical Gold",
        "Safe Haven", "Inflation Expectations"
    ]
    
    # Currencies we trade
    RELEVANT_CURRENCIES = ["USD", "EUR", "GBP", "XAU", "GOLD"]
    
    def __init__(self, buffer_minutes: int = 30):
        """
        Initialize news filter
        
        Args:
            buffer_minutes: Minutes before/after news to pause trading
        """
        self.buffer_minutes = buffer_minutes
        self.cached_events: List[Dict] = []
        self.cache_file = "/home/juujuaddy/forex_trading_bot/data/news_cache.json"
        self.last_fetch = None
        self._load_cache()
    
    def _load_cache(self):
        """Load cached events from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self.cached_events = data.get('events', [])
                    self.last_fetch = datetime.fromisoformat(data.get('last_fetch', '2000-01-01'))
        except Exception as e:
            print(f"[News] Cache load error: {e}")
            self.cached_events = []
    
    def _save_cache(self):
        """Save events to cache file"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump({
                    'events': self.cached_events,
                    'last_fetch': datetime.utcnow().isoformat()
                }, f, indent=2)
        except Exception as e:
            print(f"[News] Cache save error: {e}")
    
    def fetch_economic_calendar(self) -> List[Dict]:
        """
        Fetch today's economic events
        Uses free APIs to get economic calendar data
        """
        # Only fetch once per hour
        if self.last_fetch and (datetime.utcnow() - self.last_fetch).seconds < 3600:
            return self.cached_events
        
        events = []
        
        # Method 1: Try Forex Factory scraping (simplified)
        try:
            events = self._fetch_manual_schedule()
        except Exception as e:
            print(f"[News] Manual schedule error: {e}")
        
        if events:
            self.cached_events = events
            self.last_fetch = datetime.utcnow()
            self._save_cache()
        
        return events
    
    def _fetch_manual_schedule(self) -> List[Dict]:
        """
        Define major scheduled events manually
        These are the key events that move markets
        """
        # Weekly recurring events (approximate times UTC)
        now = datetime.utcnow()
        events = []
        
        # NFP - First Friday of month at 13:30 UTC
        # FOMC - Usually Wed at 19:00 UTC (8 meetings per year)
        # ECB Rate Decision - Usually Thursday at 12:45 UTC
        # BOE Rate Decision - Usually Thursday at 12:00 UTC
        
        # For now, define key times to avoid
        # These are approximate and should be updated with live data
        
        weekday = now.weekday()  # 0=Monday, 4=Friday
        
        # Check if first Friday of month (NFP day)
        if weekday == 4 and now.day <= 7:
            events.append({
                'time': now.replace(hour=13, minute=30, second=0),
                'name': 'Non-Farm Payrolls',
                'currency': 'USD',
                'impact': 'HIGH'
            })
        
        # FOMC Wednesdays (roughly every 6 weeks)
        if weekday == 2:
            events.append({
                'time': now.replace(hour=19, minute=0, second=0),
                'name': 'FOMC Meeting (possible)',
                'currency': 'USD',
                'impact': 'HIGH'
            })
        
        # ECB Thursdays
        if weekday == 3:
            events.append({
                'time': now.replace(hour=12, minute=45, second=0),
                'name': 'ECB Rate Decision (possible)',
                'currency': 'EUR',
                'impact': 'HIGH'
            })
        
        # BOE Thursdays
        if weekday == 3:
            events.append({
                'time': now.replace(hour=12, minute=0, second=0),
                'name': 'BOE Rate Decision (possible)',
                'currency': 'GBP',
                'impact': 'HIGH'
            })
        
        # Daily CPI/PPI releases (typically 13:30 UTC for US)
        events.append({
            'time': now.replace(hour=13, minute=30, second=0),
            'name': 'US Economic Data Release',
            'currency': 'USD',
            'impact': 'MEDIUM'
        })
        
        # London Open economic releases (08:00-09:00 UTC)
        events.append({
            'time': now.replace(hour=8, minute=30, second=0),
            'name': 'European Economic Data',
            'currency': 'EUR',
            'impact': 'MEDIUM'
        })
        
        return events
    
    def is_news_blackout(self, symbol: str = None) -> tuple:
        """
        Check if we're in a news blackout period
        
        Args:
            symbol: Optional symbol to check (EURUSD, GBPUSD, XAUUSD)
        
        Returns:
            (is_blackout: bool, reason: str or None)
        """
        now = datetime.utcnow()
        events = self.fetch_economic_calendar()
        
        # Determine which currencies to check
        check_currencies = self.RELEVANT_CURRENCIES.copy()
        if symbol:
            if "EUR" in symbol:
                check_currencies = ["EUR", "USD"]
            elif "GBP" in symbol:
                check_currencies = ["GBP", "USD"]
            elif "XAU" in symbol or "GOLD" in symbol:
                check_currencies = ["XAU", "GOLD", "USD"]
        
        for event in events:
            event_time = event.get('time')
            if isinstance(event_time, str):
                event_time = datetime.fromisoformat(event_time)
            
            event_currency = event.get('currency', '').upper()
            event_impact = event.get('impact', 'MEDIUM').upper()
            
            # Skip if not relevant currency
            relevant = any(curr in check_currencies for curr in [event_currency])
            if not relevant:
                continue
            
            # Only block for HIGH impact events
            if event_impact != 'HIGH':
                continue
            
            # Check if within buffer window
            time_diff = abs((now - event_time).total_seconds() / 60)
            
            if time_diff <= self.buffer_minutes:
                event_name = event.get('name', 'Economic Event')
                return (True, f"⚠️ NEWS BLACKOUT: {event_name} ({event_currency}) - {self.buffer_minutes}min buffer")
        
        return (False, None)
    
    def get_upcoming_events(self, hours: int = 24) -> List[Dict]:
        """Get upcoming high-impact events"""
        now = datetime.utcnow()
        events = self.fetch_economic_calendar()
        
        upcoming = []
        for event in events:
            event_time = event.get('time')
            if isinstance(event_time, str):
                event_time = datetime.fromisoformat(event_time)
            
            # Check if in future and within hours window
            if event_time > now and (event_time - now).total_seconds() < hours * 3600:
                event['time_str'] = event_time.strftime('%H:%M UTC')
                upcoming.append(event)
        
        return sorted(upcoming, key=lambda x: x['time'])
    
    def format_news_report(self) -> str:
        """Format upcoming news for Telegram report"""
        events = self.get_upcoming_events(24)
        
        if not events:
            return "📅 No major news events in next 24h"
        
        lines = ["📅 *Upcoming High-Impact News:*"]
        for event in events[:5]:  # Top 5
            impact_emoji = "🔴" if event.get('impact') == 'HIGH' else "🟡"
            lines.append(f"{impact_emoji} {event['time_str']} - {event['name']} ({event['currency']})")
        
        return "\n".join(lines)


# Singleton instance
_news_filter = None

def get_news_filter() -> NewsFilter:
    """Get or create news filter singleton"""
    global _news_filter
    if _news_filter is None:
        _news_filter = NewsFilter(buffer_minutes=30)
    return _news_filter


def is_news_blackout(symbol: str = None) -> tuple:
    """Convenience function to check news blackout"""
    return get_news_filter().is_news_blackout(symbol)


if __name__ == "__main__":
    # Test the news filter
    nf = NewsFilter()
    
    print("=== News Filter Test ===")
    print(f"Is blackout: {nf.is_news_blackout()}")
    print(f"\nUpcoming events:")
    for event in nf.get_upcoming_events(24):
        print(f"  - {event['time_str']}: {event['name']} ({event['currency']})")
    print(f"\n{nf.format_news_report()}")
