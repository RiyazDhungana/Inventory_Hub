#!/usr/bin/env python
import os
import django
import numpy as np
import pandas as pd

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_hub.settings')
django.setup()

from django.conf import settings

base_dir = settings.BASE_DIR
out_dir = os.path.join(base_dir, 'presentation_artifacts')
manifest_path = os.path.join(out_dir, 'manifest.csv')
input_dir = os.path.join(out_dir, 'prophet_input')
forecast_dir = os.path.join(out_dir, 'prophet_output')

manifest = pd.read_csv(manifest_path)
rows = []
for _, m in manifest.iterrows():
    sku = str(m['sku']).strip().upper()
    test_path = os.path.join(input_dir, f'{sku}_test.csv')
    pred_path = os.path.join(forecast_dir, f'{sku}_forecast.csv')
    if not (os.path.exists(test_path) and os.path.exists(pred_path)):
        continue

    test_df = pd.read_csv(test_path)
    pred_df = pd.read_csv(pred_path)
    if 'ds' not in test_df.columns or 'y' not in test_df.columns or 'ds' not in pred_df.columns or 'yhat' not in pred_df.columns:
        continue

    test_df['ds'] = pd.to_datetime(test_df['ds'], errors='coerce')
    pred_df['ds'] = pd.to_datetime(pred_df['ds'], errors='coerce')
    merged = test_df[['ds', 'y']].merge(pred_df[['ds', 'yhat']], on='ds', how='inner').dropna()
    if merged.empty:
        continue

    y_true = merged['y'].values.astype(float)
    y_pred = merged['yhat'].values.astype(float)

    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    non_zero = y_true != 0
    mape = float(np.mean(np.abs((y_true[non_zero] - y_pred[non_zero]) / y_true[non_zero])) * 100) if np.any(non_zero) else np.nan

    rows.append({
        'sku': sku,
        'product_name': m['name'],
        'points_compared': len(merged),
        'mae': round(mae, 4),
        'rmse': round(rmse, 4),
        'mape_percent': round(mape, 4) if not np.isnan(mape) else np.nan,
    })

result = pd.DataFrame(rows)
out_path = os.path.join(out_dir, 'accuracy_report.csv')
result.to_csv(out_path, index=False)
print(f'Accuracy report generated: {out_path}')
if not result.empty:
    print(result.head(10).to_string(index=False))
else:
    print('No comparable forecast files found yet.')
