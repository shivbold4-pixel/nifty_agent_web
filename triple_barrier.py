import numpy as np
import pandas as pd

def apply_triple_barrier_labels(
    df: pd.DataFrame,
    volatility_series: pd.Series,
    pt_mult: float = 1.5,
    sl_mult: float = 1.0,
    max_holding_bars: int = 12
) -> pd.DataFrame:
    """
    Barrier 1: Take Profit = Entry * (1 + vol * pt_mult)
    Barrier 2: Stop Loss   = Entry * (1 - vol * sl_mult)
    Barrier 3: Vertical Expiry = t + max_holding_bars
    """
    labels = []
    realized_returns = []

    for i in range(len(df) - max_holding_bars):
        entry_price = df['close'].iloc[i]
        vol = volatility_series.iloc[i]
        upper_barrier = entry_price * (1.0 + vol * pt_mult)
        lower_barrier = entry_price * (1.0 - vol * sl_mult)

        horizon = df.iloc[i + 1 : i + 1 + max_holding_bars]
        label = 0
        realized_ret = (horizon['close'].iloc[-1] - entry_price) / entry_price

        for _, bar in horizon.iterrows():
            if bar['high'] >= upper_barrier:
                label = 1   # Profit target touched first
                realized_ret = (upper_barrier - entry_price) / entry_price
                break
            elif bar['low'] <= lower_barrier:
                label = -1  # Stop loss touched first
                realized_ret = (lower_barrier - entry_price) / entry_price
                break

        labels.append(label)
        realized_returns.append(realized_ret)

    result_df = df.iloc[: len(labels)].copy()
    result_df['label'] = labels
    result_df['realized_return'] = realized_returns
    return result_df
