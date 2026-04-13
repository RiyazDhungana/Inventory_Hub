#!/usr/bin/env python
import os
import django
import pandas as pd

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_hub.settings')
django.setup()

from django.conf import settings
from inventory.models import Product, DemandForecast
from django.db import transaction

base_dir = settings.BASE_DIR
out_dir = os.path.join(base_dir, 'presentation_artifacts')
manifest_path = os.path.join(out_dir, 'manifest.csv')
forecast_dir = os.path.join(out_dir, 'prophet_output')

if not os.path.exists(manifest_path):
    raise SystemExit('manifest.csv not found. Run prophet_presentation_export.py first.')
if not os.path.exists(forecast_dir):
    raise SystemExit('prophet_output folder not found. Put forecast CSV files there first.')

manifest = pd.read_csv(manifest_path)
imported = 0
for _, row in manifest.iterrows():
    sku = str(row['sku']).strip().upper()
    product = Product.objects.filter(id=int(row['product_id'])).first()
    if not product:
        continue

    fc_path = os.path.join(forecast_dir, f'{sku}_forecast.csv')
    if not os.path.exists(fc_path):
        continue

    pred = pd.read_csv(fc_path)
    required = {'ds', 'yhat'}
    if not required.issubset(pred.columns):
        print(f'Skipped {sku}: forecast file missing required columns')
        continue

    pred['ds'] = pd.to_datetime(pred['ds'], errors='coerce')
    pred = pred.dropna(subset=['ds'])

    rows = []
    for _, r in pred.iterrows():
        yhat = max(0.0, float(r.get('yhat', 0.0)))
        ylow = max(0.0, float(r.get('yhat_lower', yhat)))
        yup = max(0.0, float(r.get('yhat_upper', yhat)))
        rows.append(DemandForecast(
            product=product,
            date=r['ds'].date(),
            predicted_quantity=yhat,
            lower_bound=ylow,
            upper_bound=yup,
        ))

    with transaction.atomic():
        DemandForecast.objects.filter(product=product).delete()
        DemandForecast.objects.bulk_create(rows)
    imported += 1
    print(f'Imported forecast for {product.name} ({sku}) with {len(rows)} rows')

print(f'Import complete. Products imported: {imported}')
