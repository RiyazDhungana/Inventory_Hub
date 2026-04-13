import logging
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

import pandas as pd
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import TruncDate

from .models import DemandForecast, Product, SaleItem

logger = logging.getLogger(__name__)


def _normalize_sku(value):
    return str(value).strip().upper()


def ingest_excel_history(file_path):
    try:
        df = pd.read_excel(file_path)

        if "InvoiceDate" in df.columns:
            df = df.rename(
                columns={
                    "InvoiceDate": "date",
                    "StockCode": "product_id",
                    "Quantity": "quantity",
                }
            )
        elif "Date" in df.columns:
            df = df.rename(
                columns={
                    "Date": "date",
                    "Product_ID": "product_id",
                    "Quantity_Sold": "quantity",
                }
            )

        required = {"date", "product_id", "quantity"}
        if not required.issubset(df.columns):
            logger.error("Excel ingestion failed: missing required columns %s", required)
            return None

        df = df[["date", "product_id", "quantity"]].copy()
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date", "product_id", "quantity"])
        df = df[df["quantity"] > 0]

        df["product_id"] = df["product_id"].astype(str).str.strip().str.upper()
        df["date"] = df["date"].dt.tz_localize(None).dt.date

        return df
    except Exception as e:
        logger.error("Excel ingestion failed: %s", e)
        return None


def get_combined_data(product_id, excel_df=None):
    product = Product.objects.get(pk=product_id)

    live_sales = (
        SaleItem.objects.filter(product=product)
        .annotate(ds=TruncDate("sale__sale_date"))
        .values("ds")
        .annotate(y=Sum("quantity"))
        .order_by("ds")
    )
    live_df = pd.DataFrame(list(live_sales))
    if not live_df.empty:
        live_df["ds"] = pd.to_datetime(live_df["ds"]).dt.tz_localize(None)

    if excel_df is not None and product.sku:
        sku = _normalize_sku(product.sku)
        hist_df = excel_df[excel_df["product_id"] == sku].copy()
        if not hist_df.empty:
            hist_df = hist_df.rename(columns={"date": "ds", "quantity": "y"})
            hist_df["ds"] = pd.to_datetime(hist_df["ds"]).dt.tz_localize(None)
            combined = pd.concat(
                [
                    hist_df[["ds", "y"]],
                    live_df[["ds", "y"]]
                    if not live_df.empty
                    else pd.DataFrame(columns=["ds", "y"]),
                ],
                ignore_index=True,
            )
        else:
            combined = live_df
    else:
        combined = live_df

    if combined is None or combined.empty:
        return None

    combined["y"] = pd.to_numeric(combined["y"], errors="coerce")
    combined = combined.dropna(subset=["ds", "y"])
    combined = combined[combined["y"] > 0]
    if combined.empty:
        return None

    combined = combined.groupby("ds", as_index=False)["y"].sum().sort_values("ds")
    return combined


def _run_prophet_worker(data_df, days=30):
    base_dir = Path(__file__).resolve().parent.parent
    py311 = base_dir / ".venv311" / "Scripts" / "python.exe"
    worker = Path(__file__).resolve().parent / "prophet_worker.py"

    if not py311.exists():
        logger.error("Python 3.11 worker runtime not found at %s", py311)
        return None

    with tempfile.TemporaryDirectory() as td:
        in_csv = Path(td) / "forecast_input.csv"
        out_csv = Path(td) / "forecast_output.csv"
        data_df.to_csv(in_csv, index=False)

        cmd = [
            str(py311),
            str(worker),
            "--input",
            str(in_csv),
            "--output",
            str(out_csv),
            "--days",
            str(days),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            logger.error("Prophet worker failed: %s", proc.stderr.strip())
            return None

        if not out_csv.exists():
            return None

        pred = pd.read_csv(out_csv)
        if pred.empty:
            return None

        pred["ds"] = pd.to_datetime(pred["ds"], errors="coerce")
        pred = pred.dropna(subset=["ds"])
        return pred


def run_forecast_for_product(product_id, excel_df=None, days=30):
    data = get_combined_data(product_id, excel_df)
    if data is None or len(data) < 7:
        return False

    latest_date = data["ds"].max()
    start_cutoff = latest_date - timedelta(days=365)
    data = data[data["ds"] >= start_cutoff].copy()
    if len(data) < 7:
        return False

    pred = _run_prophet_worker(data, days=days)
    if pred is None or pred.empty:
        return False

    # If source history is old (e.g., 2011 demo data), shift predicted dates
    # so forecast windows appear on the current calendar for operational use.
    timeline_shift_days = 0
    latest_history_date = latest_date.date()
    current_date = pd.Timestamp.now().date()
    if (current_date - latest_history_date).days > 30:
        timeline_shift_days = (current_date - latest_history_date).days

    product = Product.objects.get(pk=product_id)
    rows = []
    for _, row in pred.iterrows():
        yhat = max(0.0, float(row.get("yhat", 0.0)))
        ylow = max(0.0, float(row.get("yhat_lower", yhat)))
        yup = max(0.0, float(row.get("yhat_upper", yhat)))
        forecast_date = row["ds"].date() + timedelta(days=timeline_shift_days)
        rows.append(
            DemandForecast(
                product=product,
                date=forecast_date,
                predicted_quantity=yhat,
                lower_bound=ylow,
                upper_bound=yup,
            )
        )

    if not rows:
        return False

    with transaction.atomic():
        DemandForecast.objects.filter(product=product).delete()
        DemandForecast.objects.bulk_create(rows)

    return True
