#!/usr/bin/env python
import os
import django
import pandas as pd

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_hub.settings')
django.setup()

from django.conf import settings
from inventory.models import Product
from inventory.forecasting import ingest_excel_history, get_combined_data

base_dir = settings.BASE_DIR
out_dir = os.path.join(base_dir, 'presentation_artifacts')
input_dir = os.path.join(out_dir, 'prophet_input')
os.makedirs(input_dir, exist_ok=True)

excel_path = os.path.join(base_dir, 'Online Retail.xlsx')
excel_df = ingest_excel_history(excel_path) if os.path.exists(excel_path) else None

manifest = []
for p in Product.objects.exclude(sku__isnull=True).exclude(sku=''):
    data = get_combined_data(p.id, excel_df)
    if data is None or len(data) < 40:
        continue

    data = data.sort_values('ds').reset_index(drop=True)
    train = data.iloc[:-30].copy()
    test = data.iloc[-30:].copy()
    if len(train) < 10:
        continue

    sku = str(p.sku).strip().upper().replace('/', '_').replace('\\\\', '_')
    train_path = os.path.join(input_dir, f'{sku}_train.csv')
    test_path = os.path.join(input_dir, f'{sku}_test.csv')
    train.to_csv(train_path, index=False)
    test.to_csv(test_path, index=False)

    manifest.append({
        'product_id': p.id,
        'sku': str(p.sku).strip().upper(),
        'name': p.name,
        'train_rows': len(train),
        'test_rows': len(test),
        'train_file': os.path.basename(train_path),
        'test_file': os.path.basename(test_path),
    })

manifest_df = pd.DataFrame(manifest)
manifest_df.to_csv(os.path.join(out_dir, 'manifest.csv'), index=False)
print(f'Export complete. Products ready for Prophet: {len(manifest_df)}')
print(f'Output folder: {out_dir}')
