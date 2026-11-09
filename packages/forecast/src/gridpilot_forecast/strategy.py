"""ML forecast-driven strategies (thin wrappers; paper trading only)."""
from __future__ import annotations

from dataclasses import dataclass, field

from gridpilot_forecast.forecaster import WalkForwardQuantileForecast

try:
    from gridpilot_strategies.forecast_lp import ForecastDrivenLP, RiskAwareForecastLP
except Exception:  # pragma: no cover - optional until strategies is on path
    ForecastDrivenLP = None  # type: ignore
    RiskAwareForecastLP = None  # type: ignore


def _ml_forecast(**kwargs) -> WalkForwardQuantileForecast:
    return WalkForwardQuantileForecast(**kwargs)


@dataclass
class MLForecastDrivenLP:
    """ForecastDrivenLP backed by walk-forward LEAR-lite + quantile GBM ensemble."""

    name: str = "ml_forecast_driven_lp"
    dt_h: float = 1.0
    lookback_days: int = 45
    refit_every_days: int = 1
    price_quantile: float = 0.50
    _inner: object | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if ForecastDrivenLP is None:
            raise ImportError("gridpilot-strategies is required for MLForecastDrivenLP")
        fc = _ml_forecast(
            lookback_days=self.lookback_days,
            refit_every_days=self.refit_every_days,
        )
        self._inner = ForecastDrivenLP(
            name=self.name,
            dt_h=self.dt_h,
            forecast=fc,  # duck-typed
            price_quantile=self.price_quantile,
        )

    def decide(self, **kwargs):
        return self._inner.decide(**kwargs)


@dataclass
class MLRiskAwareForecastLP:
    """RiskAwareForecastLP backed by the same ML quantile forecaster."""

    name: str = "ml_risk_aware_forecast_lp"
    dt_h: float = 1.0
    lookback_days: int = 45
    refit_every_days: int = 1
    mode: str = "pessimistic_path"
    _inner: object | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if RiskAwareForecastLP is None:
            raise ImportError("gridpilot-strategies is required for MLRiskAwareForecastLP")
        fc = _ml_forecast(
            lookback_days=self.lookback_days,
            refit_every_days=self.refit_every_days,
        )
        self._inner = RiskAwareForecastLP(
            name=self.name,
            dt_h=self.dt_h,
            forecast=fc,
            mode=self.mode,
        )

    def decide(self, **kwargs):
        return self._inner.decide(**kwargs)
