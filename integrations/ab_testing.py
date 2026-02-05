"""
A/B Testing Framework
Run strategy variations in parallel to find optimal parameters.
Paper trades alternative configurations for comparison.
"""

import json
import logging
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from copy import deepcopy

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / 'data'
AB_TEST_FILE = DATA_DIR / 'ab_test_results.json'


@dataclass
class StrategyVariant:
    """A strategy configuration variant for testing."""
    name: str
    description: str
    
    # Configuration parameters to test
    min_confirmations: int = 3
    require_choch: bool = True
    require_15m_confirmation: bool = True
    use_correlation_filter: bool = True
    min_confidence: float = 0.85
    target_rr: float = 2.0  # Fixed at 2.0 to preserve win rate
    
    # Performance tracking
    signals_generated: int = 0
    signals_matched: int = 0  # Would have generated signal
    wins: int = 0
    losses: int = 0
    pips: float = 0.0


class ABTestingFramework:
    """
    Run multiple strategy configurations in parallel for comparison.
    
    Note: This is PAPER TRADING only - tracks what WOULD have happened
    with different configurations while main strategy runs normally.
    """
    
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.variants: Dict[str, StrategyVariant] = {}
        self.test_results: List[Dict] = []
        self.start_date: Optional[date] = None
        self._load_state()
        
        # Initialize default variants for testing
        self._init_default_variants()
    
    def _load_state(self):
        """Load test state from file."""
        try:
            if AB_TEST_FILE.exists():
                with open(AB_TEST_FILE, 'r') as f:
                    data = json.load(f)
                    self.test_results = data.get('results', [])
                    self.start_date = datetime.fromisoformat(data.get('start_date', '')).date() if data.get('start_date') else None
                    
                    # Load variants
                    for name, var_data in data.get('variants', {}).items():
                        self.variants[name] = StrategyVariant(**var_data)
        except Exception as e:
            logger.error(f"Error loading A/B test state: {e}")
    
    def _save_state(self):
        """Save test state to file."""
        try:
            data = {
                'start_date': self.start_date.isoformat() if self.start_date else None,
                'variants': {name: asdict(v) for name, v in self.variants.items()},
                'results': self.test_results[-1000:]  # Keep last 1000 results
            }
            with open(AB_TEST_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving A/B test state: {e}")
    
    def _init_default_variants(self):
        """Initialize default variants if none exist."""
        if self.variants:
            return  # Already have variants
        
        # Baseline: Current production settings
        self.variants['baseline'] = StrategyVariant(
            name='baseline',
            description='Current production settings',
            min_confirmations=3,
            require_choch=True,
            require_15m_confirmation=True,
            use_correlation_filter=True,
            min_confidence=0.85
        )
        
        # Variant A: No 15M confirmation (faster signals)
        self.variants['no_15m'] = StrategyVariant(
            name='no_15m',
            description='Without 15M confirmation filter',
            min_confirmations=3,
            require_choch=True,
            require_15m_confirmation=False,
            use_correlation_filter=True,
            min_confidence=0.85
        )
        
        # Variant B: Lower confidence threshold
        self.variants['low_conf'] = StrategyVariant(
            name='low_conf',
            description='80% confidence threshold (vs 85%)',
            min_confirmations=3,
            require_choch=True,
            require_15m_confirmation=True,
            use_correlation_filter=True,
            min_confidence=0.80
        )
        
        # Variant C: ChoCH optional (original behavior)
        self.variants['choch_optional'] = StrategyVariant(
            name='choch_optional',
            description='ChoCH not required (original)',
            min_confirmations=3,
            require_choch=False,
            require_15m_confirmation=True,
            use_correlation_filter=True,
            min_confidence=0.85
        )
        
        # Variant D: Strict (higher confidence)
        self.variants['strict'] = StrategyVariant(
            name='strict',
            description='90% confidence threshold (stricter)',
            min_confirmations=3,
            require_choch=True,
            require_15m_confirmation=True,
            use_correlation_filter=True,
            min_confidence=0.90
        )
        
        self.start_date = date.today()
        self._save_state()
        logger.info(f"A/B Testing initialized with {len(self.variants)} variants")
    
    def evaluate_setup(self, choch_found: bool, confirmation_15m: bool, 
                       confidence: float) -> Dict[str, bool]:
        """
        Evaluate which variants would have taken this signal.
        
        Returns dict of variant_name -> would_take_signal
        """
        results = {}
        
        for name, variant in self.variants.items():
            would_take = True
            
            # Check ChoCH requirement
            if variant.require_choch and not choch_found:
                would_take = False
            
            # Check 15M confirmation
            if variant.require_15m_confirmation and not confirmation_15m:
                would_take = False
            
            # Check confidence threshold
            if confidence < variant.min_confidence:
                would_take = False
            
            results[name] = would_take
            
            # Track signals matched
            if would_take:
                variant.signals_matched += 1
        
        self._save_state()
        return results
    
    def record_signal_result(self, variant_results: Dict[str, bool], 
                            outcome: str, pips: float):
        """
        Record the outcome of a signal for each variant.
        
        Args:
            variant_results: Which variants would have taken the signal
            outcome: 'win' or 'loss'
            pips: Pips result (positive for win, negative for loss)
        """
        for name, would_take in variant_results.items():
            if would_take and name in self.variants:
                variant = self.variants[name]
                variant.signals_generated += 1
                
                if outcome == 'win':
                    variant.wins += 1
                else:
                    variant.losses += 1
                
                variant.pips += pips
        
        # Record result
        self.test_results.append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'variant_results': variant_results,
            'outcome': outcome,
            'pips': pips
        })
        
        self._save_state()
    
    def get_comparison_report(self) -> Dict[str, Any]:
        """Get comparison report of all variants."""
        report = {
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'days_running': (date.today() - self.start_date).days if self.start_date else 0,
            'variants': {}
        }
        
        for name, variant in self.variants.items():
            total_trades = variant.wins + variant.losses
            win_rate = (variant.wins / total_trades * 100) if total_trades > 0 else 0
            
            # Determine status based on win rate
            if win_rate > 60:
                status = 'outperforming'
            elif win_rate < 55:
                status = 'underperforming'
            else:
                status = 'neutral'
            
            report['variants'][name] = {
                'description': variant.description,
                'signals_matched': variant.signals_matched,
                'trades': total_trades,
                'wins': variant.wins,
                'losses': variant.losses,
                'win_rate': win_rate,
                'total_pips': variant.pips,
                'avg_pips': variant.pips / total_trades if total_trades > 0 else 0,
                'status': status
            }
        
        # Rank variants by win rate
        ranked = sorted(
            report['variants'].items(),
            key=lambda x: (x[1]['win_rate'], x[1]['total_pips']),
            reverse=True
        )
        report['ranking'] = [name for name, _ in ranked]
        report['best_variant'] = ranked[0][0] if ranked else None
        
        return report
    
    def format_telegram_report(self) -> str:
        """Format A/B test results for Telegram."""
        report = self.get_comparison_report()
        
        lines = [
            "🔬 *A/B TEST COMPARISON REPORT*",
            f"Running for {report['days_running']} days",
            "",
            "━━━━━━━━━━━━━━━━━━━━━"
        ]
        
        for name in report.get('ranking', []):
            data = report['variants'][name]
            emoji = "🥇" if name == report.get('best_variant') else "📊"
            if data['status'] == 'outperforming':
                status_emoji = "🟢"
            elif data['status'] == 'underperforming':
                status_emoji = "🔴"
            else:
                status_emoji = "🟡"
            
            lines.extend([
                "",
                f"{emoji} *{name}*",
                f"  {data['description']}",
                f"  {status_emoji} Win Rate: {data['win_rate']:.1f}%",
                f"  Trades: {data['trades']} | Pips: {data['total_pips']:+.1f}"
            ])
        
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"🏆 Best: *{report.get('best_variant', 'TBD')}*"
        ])
        
        return "\n".join(lines)
    
    def reset_tests(self):
        """Reset all A/B test data."""
        for variant in self.variants.values():
            variant.signals_generated = 0
            variant.signals_matched = 0
            variant.wins = 0
            variant.losses = 0
            variant.pips = 0.0
        
        self.test_results = []
        self.start_date = date.today()
        self._save_state()
        logger.info("A/B tests reset")


# Singleton
_ab_framework: Optional[ABTestingFramework] = None


def get_ab_framework() -> ABTestingFramework:
    """Get A/B testing framework instance."""
    global _ab_framework
    if _ab_framework is None:
        _ab_framework = ABTestingFramework()
    return _ab_framework


if __name__ == "__main__":
    # Test the framework
    framework = ABTestingFramework()
    print("A/B Testing Framework initialized")
    print(f"Variants: {list(framework.variants.keys())}")
    print("\nComparison Report:")
    print(framework.format_telegram_report())
