"""AlertManager - threshold & volatility detection with anti-flapping and cooldown."""
import time
from collections import deque


class AlertManager:
    """Pure-logic alert evaluator. No signals — returns decisions, caller emits."""

    def __init__(self, get_config):
        self._get_config = get_config

        # Per-metal, per-direction anti-flapping
        self._upper_triggered: dict[str, bool] = {"AU": False, "XAU": False}
        self._lower_triggered: dict[str, bool] = {"AU": False, "XAU": False}
        self._upper_last_ts: dict[str, float] = {"AU": 0.0, "XAU": 0.0}
        self._lower_last_ts: dict[str, float] = {"AU": 0.0, "XAU": 0.0}

        # Volatility sliding window
        self._price_history: dict[str, deque[tuple[float, float]]] = {
            "AU": deque(), "XAU": deque(),
        }
        self._extreme_last_ts: dict[str, float] = {"AU": 0.0, "XAU": 0.0}

    # ── threshold ──────────────────────────────────────────────

    def check_thresholds(self, metal: str, price: float) -> str | None:
        """Return 'upper' / 'lower' if price crosses threshold (with cooldown)."""
        cfg = self._get_config()
        upper = cfg.get(f"{metal.lower()}_threshold_upper", 0.0)
        lower = cfg.get(f"{metal.lower()}_threshold_lower", 0.0)
        cooldown = cfg.get("alert_cooldown_seconds", 60)
        now = time.time()

        if upper > 0 and price >= upper and not self._upper_triggered[metal]:
            if now - self._upper_last_ts[metal] >= cooldown:
                self._upper_last_ts[metal] = now
                self._upper_triggered[metal] = True
                return "upper"

        if upper > 0 and price < upper:
            self._upper_triggered[metal] = False

        if lower > 0 and price <= lower and not self._lower_triggered[metal]:
            if now - self._lower_last_ts[metal] >= cooldown:
                self._lower_last_ts[metal] = now
                self._lower_triggered[metal] = True
                return "lower"

        if lower > 0 and price > lower:
            self._lower_triggered[metal] = False

        return None

    # ── volatility ─────────────────────────────────────────────

    def check_volatility(self, metal: str, price: float) -> str | None:
        """Return 'up' / 'down' if price changed ≥ threshold% within the window."""
        cfg = self._get_config()
        window_sec = cfg.get("volatility_window_minutes", 5) * 60
        threshold_pct = cfg.get("volatility_threshold_pct", 1.0)
        cooldown = cfg.get("alert_cooldown_seconds", 60)

        if threshold_pct <= 0:
            return None

        now = time.time()
        history = self._price_history[metal]
        history.append((now, price))

        cutoff = now - window_sec
        while history and history[0][0] < cutoff:
            history.popleft()

        if len(history) < 2:
            return None

        start_price = history[0][1]
        if start_price <= 0:
            return None

        # Convert absolute delta to percentage for comparison
        change_pct = abs(price - start_price) / start_price * 100
        if change_pct < threshold_pct:
            return None

        if now - self._extreme_last_ts[metal] < cooldown:
            return None

        self._extreme_last_ts[metal] = now
        return "up" if price > start_price else "down"
