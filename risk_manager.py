"""
Risk management: daily loss limits, drawdown circuit breaker, position sizing.
State persists in Supabase risk_state table.
"""
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST)


@dataclass
class RiskState:
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    peak_equity: float = 0.0
    current_equity: float = 0.0
    trades_today: int = 0
    halted: bool = False
    halt_reason: str = ""


class RiskManager:
    """
    Enforces risk limits:
      - Daily loss limit: -2% of starting capital
      - Weekly drawdown: -5% triggers halved size
      - Max trades per day: 10
    """
    DAILY_LOSS_LIMIT_PCT = 2.0
    WEEKLY_DRAWDOWN_PCT = 5.0
    MAX_TRADES_PER_DAY = 10

    def __init__(self, starting_capital: float = 100000.0):
        self.starting_capital = starting_capital
        self.state = RiskState(peak_equity=starting_capital,
                                current_equity=starting_capital)

    def reset_daily(self):
        self.state.daily_pnl = 0.0
        self.state.trades_today = 0
        self.state.halted = False
        self.state.halt_reason = ""

    def check_can_trade(self) -> tuple:
        """Returns (can_trade: bool, reason: str)"""
        if self.state.halted:
            return False, self.state.halt_reason

        daily_loss_pct = (self.state.daily_pnl / self.starting_capital) * 100
        if daily_loss_pct <= -self.DAILY_LOSS_LIMIT_PCT:
            self.state.halted = True
            self.state.halt_reason = f"Daily loss limit hit ({daily_loss_pct:.1f}%)"
            return False, self.state.halt_reason

        if self.state.trades_today >= self.MAX_TRADES_PER_DAY:
            self.state.halted = True
            self.state.halt_reason = f"Max trades reached ({self.MAX_TRADES_PER_DAY})"
            return False, self.state.halt_reason

        return True, "OK"

    def adjust_size_mult(self, base_mult: float) -> float:
        """Halve size if weekly drawdown exceeds threshold."""
        weekly_dd_pct = (self.state.weekly_pnl / self.starting_capital) * 100
        if weekly_dd_pct <= -self.WEEKLY_DRAWDOWN_PCT:
            return base_mult * 0.5
        return base_mult

    def register_trade(self, pnl: float):
        """Call after each trade closes."""
        self.state.daily_pnl += pnl
        self.state.weekly_pnl += pnl
        self.state.trades_today += 1
        self.state.current_equity += pnl
        if self.state.current_equity > self.state.peak_equity:
            self.state.peak_equity = self.state.current_equity

    def status(self) -> dict:
        return {
            "daily_pnl": round(self.state.daily_pnl, 2),
            "weekly_pnl": round(self.state.weekly_pnl, 2),
            "trades_today": self.state.trades_today,
            "halted": self.state.halted,
            "halt_reason": self.state.halt_reason,
            "equity": round(self.state.current_equity, 2),
        }
