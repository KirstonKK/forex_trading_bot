"""
News Event Filter
Pauses trading during high-impact economic events and bank holidays.
Bank holidays = reduced liquidity = wider spreads = higher risk of false signals.
"""

import requests
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple
import json
import os


# ──────────────────────────────────────────────────────────────
# US / UK / EU bank holidays that reduce forex liquidity
# Forex markets technically stay open, but spreads widen and
# institutional flow drops significantly. We treat these as
# "reduced liquidity" days and skip signal generation.
# ──────────────────────────────────────────────────────────────
BANK_HOLIDAYS = {
    # ===== 2026 =====
    # US holidays
    date(2026, 1, 1):   {"name": "New Year's Day",        "region": "US/UK/EU"},
    date(2026, 1, 19):  {"name": "Martin Luther King Jr. Day", "region": "US"},
    date(2026, 2, 16):  {"name": "Presidents' Day",       "region": "US"},
    date(2026, 4, 3):   {"name": "Good Friday",           "region": "US/UK/EU"},
    date(2026, 5, 25):  {"name": "Memorial Day",          "region": "US"},
    date(2026, 7, 3):   {"name": "Independence Day (observed)", "region": "US"},
    date(2026, 9, 7):   {"name": "Labor Day",             "region": "US"},
    date(2026, 11, 26): {"name": "Thanksgiving Day",      "region": "US"},
    date(2026, 11, 27): {"name": "Black Friday (half day)", "region": "US"},
    date(2026, 12, 25): {"name": "Christmas Day",         "region": "US/UK/EU"},
    # UK holidays
    date(2026, 4, 6):   {"name": "Easter Monday",         "region": "UK/EU"},
    date(2026, 5, 4):   {"name": "Early May Bank Holiday", "region": "UK"},
    date(2026, 5, 25):  {"name": "Spring Bank Holiday",   "region": "UK"},  # same as Memorial Day
    date(2026, 8, 31):  {"name": "Summer Bank Holiday",   "region": "UK"},
    date(2026, 12, 26): {"name": "Boxing Day",            "region": "UK"},
    date(2026, 12, 28): {"name": "Boxing Day (substitute)", "region": "UK"},
    # EU holidays (ECB closed)
    date(2026, 1, 6):   {"name": "Epiphany (parts of EU)", "region": "EU"},
    date(2026, 5, 1):   {"name": "Labour Day",            "region": "EU"},

    # ===== 2027 =====
    date(2027, 1, 1):   {"name": "New Year's Day",        "region": "US/UK/EU"},
    date(2027, 1, 18):  {"name": "Martin Luther King Jr. Day", "region": "US"},
    date(2027, 2, 15):  {"name": "Presidents' Day",       "region": "US"},
    date(2027, 3, 26):  {"name": "Good Friday",           "region": "US/UK/EU"},
    date(2027, 3, 29):  {"name": "Easter Monday",         "region": "UK/EU"},
    date(2027, 5, 3):   {"name": "Early May Bank Holiday", "region": "UK"},
    date(2027, 5, 31):  {"name": "Memorial Day / Spring Bank Holiday", "region": "US/UK"},
    date(2027, 7, 5):   {"name": "Independence Day (observed)", "region": "US"},
    date(2027, 9, 6):   {"name": "Labor Day",             "region": "US"},
    date(2027, 11, 25): {"name": "Thanksgiving Day",      "region": "US"},
    date(2027, 11, 26): {"name": "Black Friday (half day)", "region": "US"},
    date(2027, 12, 25): {"name": "Christmas Day",         "region": "US/UK/EU"},
    date(2027, 12, 27): {"name": "Boxing Day (substitute)", "region": "UK"},
}


def is_bank_holiday(check_date: date = None) -> Tuple[bool, Optional[str]]:
    """
    Check if a given date is a bank holiday that reduces forex liquidity.

    Returns:
        (is_holiday: bool, holiday_name: str or None)
    """
    if check_date is None:
        check_date = date.today()

    # Accept datetime objects too
    if isinstance(check_date, datetime):
        check_date = check_date.date()

    holiday = BANK_HOLIDAYS.get(check_date)
    if holiday:
        return True, f"{holiday['name']} ({holiday['region']})"
    return False, None


def is_reduced_liquidity_day(check_date: date = None) -> Tuple[bool, Optional[str]]:
    """
    Broader check: bank holiday OR day before/after major holidays
    (Dec 24, Dec 31, day after Thanksgiving already covered).
    """
    is_hol, name = is_bank_holiday(check_date)
    if is_hol:
        return True, f"🏦 Bank Holiday: {name}"

    if check_date is None:
        check_date = date.today()
    if isinstance(check_date, datetime):
        check_date = check_date.date()

    # Dec 24 and Dec 31 are half-days with very thin liquidity
    if check_date.month == 12 and check_date.day in (24, 31):
        return True, "🏦 Holiday Eve — thin liquidity expected"

    return False, None


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
        self.cache_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "news_cache.json")
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
        Define major scheduled events manually.
        Only block trading for CONFIRMED high-impact events,
        not every Thursday/Wednesday "just in case".
        
        FOMC meets ~8 times/year, ECB ~8 times, BOE ~8 times.
        These DON'T happen every week, so marking them HIGH every
        Thursday/Wednesday was blocking trades unnecessarily.
        """
        now = datetime.utcnow()
        events = []
        
        weekday = now.weekday()  # 0=Monday, 4=Friday
        
        # NFP - First Friday of month at 13:30 UTC (very predictable)
        if weekday == 4 and now.day <= 7:
            events.append({
                'time': now.replace(hour=13, minute=30, second=0),
                'name': 'Non-Farm Payrolls',
                'currency': 'USD',
                'impact': 'HIGH'
            })
        
        # Mark recurring events as MEDIUM so they don't block trading.
        # Without a real calendar API, we can't know which specific
        # Thursday/Wednesday actually has a central bank decision.
        
        # FOMC Wednesdays (roughly every 6 weeks — NOT every week)
        if weekday == 2:
            events.append({
                'time': now.replace(hour=19, minute=0, second=0),
                'name': 'FOMC Meeting (possible)',
                'currency': 'USD',
                'impact': 'MEDIUM'
            })
        
        # ECB Thursdays (roughly every 6 weeks — NOT every week)
        if weekday == 3:
            events.append({
                'time': now.replace(hour=12, minute=45, second=0),
                'name': 'ECB Rate Decision (possible)',
                'currency': 'EUR',
                'impact': 'MEDIUM'
            })
        
        # BOE Thursdays (roughly every 6 weeks — NOT every week)
        if weekday == 3:
            events.append({
                'time': now.replace(hour=12, minute=0, second=0),
                'name': 'BOE Rate Decision (possible)',
                'currency': 'GBP',
                'impact': 'MEDIUM'
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
