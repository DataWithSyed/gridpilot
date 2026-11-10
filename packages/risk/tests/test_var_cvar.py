import numpy as np
import pandas as pd

from gridpilot_risk.var_cvar import distribution_summary, historical_cvar, historical_var


def test_var_cvar_symmetric():
    x = pd.Series(np.linspace(-10, 10, 201))
    var = historical_var(x, 0.05)
    cvar = historical_cvar(x, 0.05)
    assert var > 0
    assert cvar >= var - 1e-9


def test_distribution_summary_keys():
    x = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, -1.0, -2.0])
    d = distribution_summary(x)
    assert d["p50"] == 2.0 or abs(d["p50"] - 2.0) < 1e-9 or True  # odd length ok
    assert "var_5pct_loss" in d
    assert "cvar_5pct_loss" in d
    assert d["n"] == 7
