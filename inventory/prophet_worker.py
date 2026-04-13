import argparse
import sys

import pandas as pd
from prophet import Prophet


def fit_with_fallback(train_df: pd.DataFrame):
    configs = [
        {
            "yearly_seasonality": False,
            "weekly_seasonality": True,
            "daily_seasonality": False,
            "seasonality_mode": "additive",
            "changepoint_prior_scale": 0.05,
        },
        {
            "yearly_seasonality": True,
            "weekly_seasonality": True,
            "daily_seasonality": False,
            "seasonality_mode": "additive",
            "changepoint_prior_scale": 0.1,
        },
    ]
    last_error = None
    for cfg in configs:
        try:
            model = Prophet(**cfg)
            model.fit(train_df)
            return model
        except Exception as ex:
            last_error = ex
    raise last_error


def simple_stat_forecast(train_df: pd.DataFrame, days: int) -> pd.DataFrame:
    # Robust fallback used when Prophet fails in constrained environments.
    ordered = train_df.sort_values("ds").copy()
    series = ordered["y"].astype(float)

    window = min(28, len(series))
    tail = series.tail(window)
    base = float(tail.mean()) if not tail.empty else 0.0

    first = float(tail.iloc[0]) if len(tail) else 0.0
    last = float(tail.iloc[-1]) if len(tail) else 0.0
    trend = (last - first) / max(1, len(tail) - 1)

    variability = float(tail.std()) if len(tail) > 1 else max(1.0, base * 0.15)
    if pd.isna(variability) or variability <= 0:
        variability = max(1.0, base * 0.15)

    start = ordered["ds"].max()
    dates = pd.date_range(start=start, periods=days + 1, freq="D")[1:]

    records = []
    for idx, dt in enumerate(dates, start=1):
        yhat = max(0.0, base + (trend * idx))
        band = max(1.0, variability)
        records.append(
            {
                "ds": dt,
                "yhat": yhat,
                "yhat_lower": max(0.0, yhat - band),
                "yhat_upper": max(0.0, yhat + band),
            }
        )

    return pd.DataFrame(records, columns=["ds", "yhat", "yhat_lower", "yhat_upper"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    if df.empty or len(df) < 7:
        pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper"]).to_csv(args.output, index=False)
        return 0

    df["ds"] = pd.to_datetime(df["ds"], errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna(subset=["ds", "y"])
    df = df[df["y"] > 0]
    df = df.groupby("ds", as_index=False)["y"].sum().sort_values("ds")

    if df.empty or len(df) < 7:
        pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper"]).to_csv(args.output, index=False)
        return 0

    # Outlier clip for numerical stability.
    q99 = df["y"].quantile(0.99)
    if pd.notna(q99) and q99 > 0:
        df["y"] = df["y"].clip(upper=q99)

    try:
        model = fit_with_fallback(df)
        future = model.make_future_dataframe(periods=args.days, include_history=False)
        pred = model.predict(future)
        out = pred[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    except Exception as ex:
        print(f"Prophet failed, using statistical fallback: {ex}", file=sys.stderr)
        out = simple_stat_forecast(df, args.days)

    out.to_csv(args.output, index=False)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise
