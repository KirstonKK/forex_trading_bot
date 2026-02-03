"""
Forex Sentiment Advisor - Advisory System using PulseGraph
Provides market sentiment information without affecting trade decisions.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from enum import Enum
import os
import json
import logging

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

from .forex_schema import (
    ForexKnowledgeGraph, 
    CurrencySentiment, 
    ForexEvent,
    EventImpact
)

logger = logging.getLogger(__name__)


class SentimentBias(Enum):
    """Market sentiment bias."""
    STRONGLY_BULLISH = "strongly_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONGLY_BEARISH = "strongly_bearish"


@dataclass
class AdvisorySignal:
    """Advisory signal (does NOT affect trade decisions)."""
    pair: str
    bias: SentimentBias
    score: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    summary: str
    sources_count: int
    upcoming_events: List[Dict[str, Any]]
    warnings: List[str]
    generated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pair": self.pair,
            "bias": self.bias.value,
            "score": round(self.score, 3),
            "confidence": round(self.confidence, 2),
            "summary": self.summary,
            "sources_count": self.sources_count,
            "upcoming_events": self.upcoming_events,
            "warnings": self.warnings,
            "generated_at": self.generated_at.isoformat()
        }


@dataclass
class MarketContext:
    """Current market context for advisory display."""
    pairs: Dict[str, AdvisorySignal]
    high_impact_events: List[Dict[str, Any]]
    market_summary: str
    updated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pairs": {k: v.to_dict() for k, v in self.pairs.items()},
            "high_impact_events": self.high_impact_events,
            "market_summary": self.market_summary,
            "updated_at": self.updated_at.isoformat()
        }


class ForexSentimentAdvisor:
    """
    Advisory sentiment system using PulseGraph.
    Provides market context WITHOUT affecting trade decisions.
    """
    
    SUPPORTED_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    
    def __init__(self, neo4j_uri: str = None, openai_api_key: str = None):
        """Initialize the advisor."""
        self.graph = ForexKnowledgeGraph(uri=neo4j_uri)
        self._openai_client = None
        self._openai_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._cache: Dict[str, AdvisorySignal] = {}
        self._cache_ttl = timedelta(minutes=15)
        self._last_cache_update: Optional[datetime] = None
        self._initialized = False
        
        # Fallback sentiment (used when Neo4j/OpenAI not available)
        self._fallback_sentiment: Dict[str, float] = {
            "EURUSD": 0.0,
            "GBPUSD": 0.0,
            "USDJPY": 0.0,
            "AUDUSD": 0.0
        }
    
    @property
    def is_available(self) -> bool:
        """Check if the advisor is fully operational."""
        return self._initialized and self.graph.is_available
    
    @property
    def is_degraded(self) -> bool:
        """Check if running in degraded mode (no Neo4j but still functional)."""
        return self._initialized and not self.graph.is_available
    
    def initialize(self) -> Tuple[bool, str]:
        """
        Initialize connections and schema.
        Returns (success, message).
        """
        messages = []
        
        # Try Neo4j connection
        if self.graph.connect():
            self.graph.ensure_schema()
            self.graph.seed_currencies()
            messages.append("Neo4j connected, schema ready")
        else:
            messages.append("Neo4j unavailable - running in degraded mode")
        
        # Try OpenAI connection
        if OPENAI_AVAILABLE and self._openai_key:
            try:
                self._openai_client = OpenAI(api_key=self._openai_key)
                messages.append("OpenAI connected")
            except Exception as e:
                messages.append(f"OpenAI unavailable: {e}")
        else:
            messages.append("OpenAI not configured")
        
        self._initialized = True
        return True, "; ".join(messages)
    
    def shutdown(self):
        """Clean up resources."""
        self.graph.close()
        self._initialized = False
    
    def _score_to_bias(self, score: float) -> SentimentBias:
        """Convert numeric score to sentiment bias."""
        if score >= 0.5:
            return SentimentBias.STRONGLY_BULLISH
        elif score >= 0.2:
            return SentimentBias.BULLISH
        elif score <= -0.5:
            return SentimentBias.STRONGLY_BEARISH
        elif score <= -0.2:
            return SentimentBias.BEARISH
        else:
            return SentimentBias.NEUTRAL
    
    def _generate_summary(self, pair: str, score: float, 
                          events: List[ForexEvent]) -> str:
        """Generate a human-readable summary."""
        base, quote = pair[:3], pair[3:]
        bias = self._score_to_bias(score)
        
        bias_text = {
            SentimentBias.STRONGLY_BULLISH: f"Strong bullish sentiment for {base} vs {quote}",
            SentimentBias.BULLISH: f"Mild bullish sentiment for {base} vs {quote}",
            SentimentBias.NEUTRAL: f"Neutral sentiment for {pair}",
            SentimentBias.BEARISH: f"Mild bearish sentiment for {base} vs {quote}",
            SentimentBias.STRONGLY_BEARISH: f"Strong bearish sentiment for {base} vs {quote}"
        }
        
        summary = bias_text.get(bias, f"Sentiment for {pair}")
        
        if events:
            high_impact = [e for e in events if e.impact == EventImpact.HIGH]
            if high_impact:
                summary += f". ⚠️ {len(high_impact)} high-impact events upcoming"
        
        return summary
    
    def _generate_warnings(self, pair: str, events: List[ForexEvent]) -> List[str]:
        """Generate warnings for the pair."""
        warnings = []
        
        # Check for high-impact events
        high_impact = [e for e in events if e.impact == EventImpact.HIGH]
        for event in high_impact[:3]:  # Max 3 warnings
            warnings.append(f"⚠️ {event.title} at {event.scheduled_at.strftime('%H:%M UTC')}")
        
        return warnings
    
    def get_advisory(self, pair: str) -> AdvisorySignal:
        """
        Get advisory signal for a currency pair.
        This is ADVISORY ONLY - does not affect trade decisions.
        """
        pair = pair.upper().replace("_", "").replace("/", "")
        
        # Check cache
        if pair in self._cache:
            cached = self._cache[pair]
            if datetime.now(timezone.utc) - cached.generated_at < self._cache_ttl:
                return cached
        
        # Get sentiment from graph or use fallback
        sentiment = None
        if self.graph.is_available:
            sentiment = self.graph.get_pair_sentiment(pair)
        
        if sentiment:
            score = sentiment.score
            confidence = sentiment.confidence
            sources_count = sentiment.volume
        else:
            # Fallback: neutral sentiment
            score = self._fallback_sentiment.get(pair, 0.0)
            confidence = 0.3  # Low confidence for fallback
            sources_count = 0
        
        # Get upcoming events
        base_currency = pair[:3]
        quote_currency = pair[3:]
        events = []
        
        if self.graph.is_available:
            events.extend(self.graph.get_upcoming_events(base_currency, hours_ahead=24))
            events.extend(self.graph.get_upcoming_events(quote_currency, hours_ahead=24))
        
        # Sort events by time
        events.sort(key=lambda e: e.scheduled_at)
        
        # Format events for output
        upcoming_events = [
            {
                "title": e.title,
                "currency": e.currency,
                "impact": e.impact.value,
                "scheduled_at": e.scheduled_at.isoformat()
            }
            for e in events[:5]  # Max 5 events
        ]
        
        # Generate summary and warnings
        summary = self._generate_summary(pair, score, events)
        warnings = self._generate_warnings(pair, events)
        
        advisory = AdvisorySignal(
            pair=pair,
            bias=self._score_to_bias(score),
            score=score,
            confidence=confidence,
            summary=summary,
            sources_count=sources_count,
            upcoming_events=upcoming_events,
            warnings=warnings,
            generated_at=datetime.now(timezone.utc)
        )
        
        # Cache the result
        self._cache[pair] = advisory
        
        return advisory
    
    def get_market_context(self) -> MarketContext:
        """
        Get full market context for all supported pairs.
        ADVISORY ONLY - for display purposes.
        """
        pairs = {}
        all_events = []
        
        for pair in self.SUPPORTED_PAIRS:
            advisory = self.get_advisory(pair)
            pairs[pair] = advisory
            all_events.extend(advisory.upcoming_events)
        
        # Filter high-impact events
        high_impact_events = [
            e for e in all_events 
            if e.get("impact") == "high"
        ]
        
        # Deduplicate by title
        seen = set()
        unique_events = []
        for e in high_impact_events:
            if e["title"] not in seen:
                seen.add(e["title"])
                unique_events.append(e)
        
        # Generate market summary
        bullish_pairs = [p for p, a in pairs.items() if a.score > 0.2]
        bearish_pairs = [p for p, a in pairs.items() if a.score < -0.2]
        
        if not bullish_pairs and not bearish_pairs:
            market_summary = "Market sentiment is mixed/neutral across major pairs"
        elif len(bullish_pairs) > len(bearish_pairs):
            market_summary = f"Bullish bias: {', '.join(bullish_pairs)}"
        else:
            market_summary = f"Bearish bias: {', '.join(bearish_pairs)}"
        
        if unique_events:
            market_summary += f" | {len(unique_events)} high-impact events ahead"
        
        return MarketContext(
            pairs=pairs,
            high_impact_events=unique_events[:10],
            market_summary=market_summary,
            updated_at=datetime.now(timezone.utc)
        )
    
    def update_sentiment_from_news(self, pair: str, headlines: List[str]) -> bool:
        """
        Update sentiment based on news headlines (requires OpenAI).
        Returns True if successful.
        """
        if not self._openai_client:
            logger.warning("OpenAI not available for sentiment analysis")
            return False
        
        try:
            base, quote = pair[:3], pair[3:]
            
            prompt = f"""Analyze the following forex news headlines for {pair} ({base} vs {quote}).
Rate the overall sentiment from -1.0 (very bearish for {base}) to 1.0 (very bullish for {base}).

Headlines:
{chr(10).join(f'- {h}' for h in headlines[:10])}

Respond with only a JSON object:
{{"score": <float>, "reasoning": "<brief explanation>"}}
"""
            
            response = self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a forex market sentiment analyst."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            content = response.choices[0].message.content.strip()
            # Parse JSON response
            result = json.loads(content)
            score = float(result.get("score", 0.0))
            score = max(-1.0, min(1.0, score))  # Clamp to valid range
            
            # Update graph
            if self.graph.is_available:
                self.graph.upsert_sentiment(
                    pair=pair,
                    score=score,
                    volume=len(headlines),
                    sources=headlines[:5]
                )
            
            # Update fallback
            self._fallback_sentiment[pair] = score
            
            # Clear cache
            if pair in self._cache:
                del self._cache[pair]
            
            logger.info(f"Updated {pair} sentiment: {score:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Sentiment update failed: {e}")
            return False
    
    def format_for_dashboard(self) -> str:
        """Format market context as HTML for dashboard display."""
        context = self.get_market_context()
        
        html = """
<div class="market-sentiment">
    <h3>📊 Market Sentiment Advisory</h3>
    <p class="advisory-note">ℹ️ Advisory only - does not affect trade decisions</p>
    <p class="summary">{summary}</p>
    <div class="pairs-grid">
""".format(summary=context.market_summary)
        
        for pair, signal in context.pairs.items():
            bias_class = "neutral"
            if signal.score > 0.2:
                bias_class = "bullish"
            elif signal.score < -0.2:
                bias_class = "bearish"
            
            bias_icon = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(bias_class, "⚪")
            
            html += f"""
        <div class="pair-card {bias_class}">
            <div class="pair-name">{bias_icon} {pair}</div>
            <div class="pair-score">Score: {signal.score:+.2f}</div>
            <div class="pair-bias">{signal.bias.value.replace('_', ' ').title()}</div>
        </div>
"""
        
        html += "    </div>"
        
        if context.high_impact_events:
            html += """
    <div class="events-section">
        <h4>⚠️ Upcoming High-Impact Events</h4>
        <ul>
"""
            for event in context.high_impact_events[:5]:
                html += f'            <li>{event["currency"]}: {event["title"]}</li>\n'
            html += "        </ul>\n    </div>"
        
        html += f"""
    <div class="update-time">Last updated: {context.updated_at.strftime('%Y-%m-%d %H:%M UTC')}</div>
</div>
"""
        return html


# Singleton instance for easy access
_advisor_instance: Optional[ForexSentimentAdvisor] = None


def get_advisor() -> ForexSentimentAdvisor:
    """Get the global advisor instance."""
    global _advisor_instance
    if _advisor_instance is None:
        _advisor_instance = ForexSentimentAdvisor()
        _advisor_instance.initialize()
    return _advisor_instance
