"""
Forex-specific Knowledge Graph Schema for PulseGraph
Defines currencies, central banks, and economic events for forex trading.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import os

try:
    from neo4j import GraphDatabase, Driver
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    Driver = None


class CurrencyType(Enum):
    """Major forex currencies."""
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"
    JPY = "JPY"
    AUD = "AUD"
    CHF = "CHF"
    CAD = "CAD"
    NZD = "NZD"


class CentralBank(Enum):
    """Major central banks."""
    ECB = "European Central Bank"
    FED = "Federal Reserve"
    BOE = "Bank of England"
    BOJ = "Bank of Japan"
    RBA = "Reserve Bank of Australia"
    SNB = "Swiss National Bank"
    BOC = "Bank of Canada"
    RBNZ = "Reserve Bank of New Zealand"


class EventImpact(Enum):
    """Economic event impact level."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ForexEvent:
    """Forex economic event."""
    id: str
    event_type: str  # rate_decision, employment, inflation, gdp, speech
    currency: str
    central_bank: Optional[str]
    scheduled_at: datetime
    impact: EventImpact
    title: str
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None


@dataclass
class CurrencySentiment:
    """Sentiment data for a currency pair."""
    pair: str  # e.g., "EURUSD"
    score: float  # -1.0 (bearish) to 1.0 (bullish)
    volume: int  # Number of sources analyzed
    sources: List[str]
    last_updated: datetime
    confidence: float


@dataclass
class SentimentSource:
    """Source of sentiment data."""
    url: str
    title: str
    source_type: str  # news, social, analyst
    published_at: datetime
    sentiment_score: float
    currency_mentions: List[str]


# Forex-specific Cypher queries
FOREX_SCHEMA_CYPHER = """
// Currency nodes
CREATE CONSTRAINT currency_id IF NOT EXISTS FOR (c:Currency) REQUIRE c.id IS UNIQUE;

// Central Bank nodes  
CREATE CONSTRAINT central_bank_id IF NOT EXISTS FOR (cb:CentralBank) REQUIRE cb.id IS UNIQUE;

// Forex Event nodes
CREATE CONSTRAINT forex_event_id IF NOT EXISTS FOR (e:ForexEvent) REQUIRE e.id IS UNIQUE;

// Currency Pair nodes
CREATE CONSTRAINT pair_id IF NOT EXISTS FOR (p:CurrencyPair) REQUIRE p.id IS UNIQUE;

// Sentiment Signal nodes
CREATE CONSTRAINT sentiment_id IF NOT EXISTS FOR (s:SentimentSignal) REQUIRE s.id IS UNIQUE;

// Source Document nodes
CREATE CONSTRAINT source_id IF NOT EXISTS FOR (src:Source) REQUIRE src.id IS UNIQUE;
"""


class ForexKnowledgeGraph:
    """Manages the forex-specific knowledge graph."""
    
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        """Initialize connection to Neo4j."""
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self._driver: Optional[Driver] = None
        self._connected = False
        
    @property
    def is_available(self) -> bool:
        """Check if Neo4j connection is available."""
        return NEO4J_AVAILABLE and self._connected
    
    def connect(self) -> bool:
        """Establish connection to Neo4j."""
        if not NEO4J_AVAILABLE:
            return False
        
        try:
            self._driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password)
            )
            # Test connection
            with self._driver.session() as session:
                session.run("RETURN 1")
            self._connected = True
            return True
        except Exception as e:
            print(f"Neo4j connection failed: {e}")
            self._connected = False
            return False
    
    def close(self):
        """Close the database connection."""
        if self._driver:
            self._driver.close()
            self._connected = False
    
    def ensure_schema(self) -> bool:
        """Create schema constraints and indexes."""
        if not self.is_available:
            return False
        
        try:
            with self._driver.session() as session:
                for statement in FOREX_SCHEMA_CYPHER.strip().split(';'):
                    statement = statement.strip()
                    if statement:
                        session.run(statement)
            return True
        except Exception as e:
            print(f"Schema creation failed: {e}")
            return False
    
    def seed_currencies(self) -> bool:
        """Seed the graph with major forex currencies and central banks."""
        if not self.is_available:
            return False
        
        currencies = [
            ("EUR", "Euro", "ECB"),
            ("USD", "US Dollar", "FED"),
            ("GBP", "British Pound", "BOE"),
            ("JPY", "Japanese Yen", "BOJ"),
            ("AUD", "Australian Dollar", "RBA"),
            ("CHF", "Swiss Franc", "SNB"),
            ("CAD", "Canadian Dollar", "BOC"),
        ]
        
        pairs = [
            ("EURUSD", "EUR", "USD"),
            ("GBPUSD", "GBP", "USD"),
            ("USDJPY", "USD", "JPY"),
            ("AUDUSD", "AUD", "USD"),
            ("USDCHF", "USD", "CHF"),
            ("USDCAD", "USD", "CAD"),
            ("EURGBP", "EUR", "GBP"),
        ]
        
        central_banks = [
            ("ECB", "European Central Bank", "EUR"),
            ("FED", "Federal Reserve", "USD"),
            ("BOE", "Bank of England", "GBP"),
            ("BOJ", "Bank of Japan", "JPY"),
            ("RBA", "Reserve Bank of Australia", "AUD"),
            ("SNB", "Swiss National Bank", "CHF"),
            ("BOC", "Bank of Canada", "CAD"),
        ]
        
        try:
            with self._driver.session() as session:
                # Create currencies
                for code, name, cb in currencies:
                    session.run(
                        """
                        MERGE (c:Currency {id: $code})
                        SET c.name = $name, c.central_bank = $cb
                        """,
                        code=code, name=name, cb=cb
                    )
                
                # Create pairs
                for pair_id, base, quote in pairs:
                    session.run(
                        """
                        MERGE (p:CurrencyPair {id: $pair_id})
                        SET p.base = $base, p.quote = $quote
                        WITH p
                        MATCH (b:Currency {id: $base})
                        MATCH (q:Currency {id: $quote})
                        MERGE (p)-[:BASE]->(b)
                        MERGE (p)-[:QUOTE]->(q)
                        """,
                        pair_id=pair_id, base=base, quote=quote
                    )
                
                # Create central banks
                for cb_id, name, currency in central_banks:
                    session.run(
                        """
                        MERGE (cb:CentralBank {id: $cb_id})
                        SET cb.name = $name
                        WITH cb
                        MATCH (c:Currency {id: $currency})
                        MERGE (cb)-[:CONTROLS]->(c)
                        """,
                        cb_id=cb_id, name=name, currency=currency
                    )
                
            return True
        except Exception as e:
            print(f"Seeding failed: {e}")
            return False
    
    def upsert_sentiment(self, pair: str, score: float, volume: int = 1, 
                         sources: List[str] = None) -> bool:
        """Insert or update sentiment for a currency pair."""
        if not self.is_available:
            return False
        
        try:
            with self._driver.session() as session:
                session.run(
                    """
                    MATCH (p:CurrencyPair {id: $pair})
                    MERGE (s:SentimentSignal {id: $signal_id})
                    SET s.score = $score,
                        s.volume = $volume,
                        s.sources = $sources,
                        s.updated_at = datetime()
                    MERGE (s)-[:ABOUT]->(p)
                    """,
                    pair=pair,
                    signal_id=f"{pair}_sentiment_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                    score=score,
                    volume=volume,
                    sources=sources or []
                )
            return True
        except Exception as e:
            print(f"Upsert sentiment failed: {e}")
            return False
    
    def get_pair_sentiment(self, pair: str) -> Optional[CurrencySentiment]:
        """Get latest sentiment for a currency pair."""
        if not self.is_available:
            return None
        
        try:
            with self._driver.session() as session:
                result = session.run(
                    """
                    MATCH (s:SentimentSignal)-[:ABOUT]->(p:CurrencyPair {id: $pair})
                    RETURN s.score AS score, s.volume AS volume, 
                           s.sources AS sources, s.updated_at AS updated_at
                    ORDER BY s.updated_at DESC
                    LIMIT 1
                    """,
                    pair=pair
                )
                record = result.single()
                if record:
                    return CurrencySentiment(
                        pair=pair,
                        score=record["score"],
                        volume=record["volume"],
                        sources=record["sources"] or [],
                        last_updated=record["updated_at"],
                        confidence=min(record["volume"] / 10, 1.0)  # More sources = higher confidence
                    )
            return None
        except Exception as e:
            print(f"Get sentiment failed: {e}")
            return None
    
    def upsert_forex_event(self, event: ForexEvent) -> bool:
        """Insert or update a forex economic event."""
        if not self.is_available:
            return False
        
        try:
            with self._driver.session() as session:
                session.run(
                    """
                    MERGE (e:ForexEvent {id: $id})
                    SET e.event_type = $event_type,
                        e.currency = $currency,
                        e.central_bank = $central_bank,
                        e.scheduled_at = datetime($scheduled_at),
                        e.impact = $impact,
                        e.title = $title,
                        e.actual = $actual,
                        e.forecast = $forecast,
                        e.previous = $previous
                    WITH e
                    MATCH (c:Currency {id: $currency})
                    MERGE (e)-[:AFFECTS]->(c)
                    """,
                    id=event.id,
                    event_type=event.event_type,
                    currency=event.currency,
                    central_bank=event.central_bank,
                    scheduled_at=event.scheduled_at.isoformat(),
                    impact=event.impact.value,
                    title=event.title,
                    actual=event.actual,
                    forecast=event.forecast,
                    previous=event.previous
                )
            return True
        except Exception as e:
            print(f"Upsert event failed: {e}")
            return False
    
    def get_upcoming_events(self, currency: str = None, 
                            hours_ahead: int = 24) -> List[ForexEvent]:
        """Get upcoming economic events."""
        if not self.is_available:
            return []
        
        try:
            with self._driver.session() as session:
                if currency:
                    result = session.run(
                        """
                        MATCH (e:ForexEvent)-[:AFFECTS]->(c:Currency {id: $currency})
                        WHERE e.scheduled_at >= datetime() 
                          AND e.scheduled_at <= datetime() + duration({hours: $hours})
                        RETURN e
                        ORDER BY e.scheduled_at ASC
                        """,
                        currency=currency, hours=hours_ahead
                    )
                else:
                    result = session.run(
                        """
                        MATCH (e:ForexEvent)
                        WHERE e.scheduled_at >= datetime() 
                          AND e.scheduled_at <= datetime() + duration({hours: $hours})
                        RETURN e
                        ORDER BY e.scheduled_at ASC
                        """,
                        hours=hours_ahead
                    )
                
                events = []
                for record in result:
                    e = record["e"]
                    events.append(ForexEvent(
                        id=e["id"],
                        event_type=e["event_type"],
                        currency=e["currency"],
                        central_bank=e.get("central_bank"),
                        scheduled_at=e["scheduled_at"],
                        impact=EventImpact(e["impact"]),
                        title=e["title"],
                        actual=e.get("actual"),
                        forecast=e.get("forecast"),
                        previous=e.get("previous")
                    ))
                return events
        except Exception as e:
            print(f"Get events failed: {e}")
            return []
