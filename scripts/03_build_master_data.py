import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_config():
    with open(ROOT / 'config' / 'data_config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def normalize_description(value):
    if pd.isna(value):
        return ''
    text = str(value).lower()
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def get_matching_expenditure_data(exp, rec):
    exp = exp.copy()
    rec = rec.copy()
    exp['normalized_work_description'] = exp['work_description'].fillna('').map(normalize_description)
    rec['normalized_work_description'] = rec['work_description'].fillna('').map(normalize_description)
    exp['project_key'] = (
        exp['normalized_work_description'].fillna('') + '|' +
        exp['mp_name'].fillna('').astype(str) + '|' +
        exp['constituency'].fillna('').astype(str) + '|' +
        exp['state'].fillna('').astype(str)
    )
    rec['project_key'] = (
        rec['normalized_work_description'].fillna('') + '|' +
        rec['mp_name'].fillna('').astype(str) + '|' +
        rec['constituency'].fillna('').astype(str) + '|' +
        rec['state'].fillna('').astype(str)
    )
    exp_agg = exp.groupby(['mp_name', 'constituency', 'state', 'normalized_work_description'], dropna=False).agg(
        total_expenditure=('expenditure_amount', 'sum'),
        payment_count=('expenditure_amount', 'size'),
        successful_payment_count=('payment_status', lambda s: s.str.lower().isin({'successful', 'paid', 'payment_completed', 'completed'}).sum()),
        pending_payment_count=('payment_status', lambda s: s.str.lower().isin({'pending', 'in_progress', 'payment_in_progress'}).sum()),
        latest_payment_status=('payment_status', lambda s: s.iloc[-1] if len(s) else np.nan),
        primary_vendor=('vendor', lambda s: s.iloc[0] if len(s) else np.nan),
        average_payment=('expenditure_amount', 'mean'),
        maximum_payment=('expenditure_amount', 'max'),
        minimum_payment=('expenditure_amount', 'min')
    ).reset_index()
    return exp_agg


def build_master_works(config):
    recommended = pd.read_csv(ROOT / config['outputs']['recommended_clean'])
    completed = pd.read_csv(ROOT / config['outputs']['completed_clean'])
    expenditures = pd.read_csv(ROOT / config['outputs']['expenditures_clean'])

    recommended['normalized_work_description'] = recommended['work_description'].fillna('').map(normalize_description)
    recommended['project_id'] = (
        recommended['work_id'].astype(str).str.strip() + '|' +
        recommended['mp_name'].fillna('').astype(str).str.strip() + '|' +
        recommended['constituency'].fillna('').astype(str).str.strip() + '|' +
        recommended['state'].fillna('').astype(str).str.strip()
    )
    completed = completed[['work_id', 'final_amount', 'completed_date', 'average_rating']].copy()
    completed = completed.drop_duplicates(subset=['work_id'], keep='last')
    master = recommended.merge(completed, on='work_id', how='left')

    exp_agg = get_matching_expenditure_data(expenditures, recommended)
    exp_agg['project_id'] = exp_agg['normalized_work_description'].astype(str) + '|' + exp_agg['mp_name'].astype(str) + '|' + exp_agg['constituency'].astype(str) + '|' + exp_agg['state'].astype(str)
    phrased_match = master[['project_id', 'mp_name', 'constituency', 'state', 'normalized_work_description']].merge(
        exp_agg[['mp_name', 'constituency', 'state', 'normalized_work_description', 'total_expenditure', 'payment_count', 'successful_payment_count', 'pending_payment_count', 'latest_payment_status', 'primary_vendor', 'average_payment', 'maximum_payment', 'minimum_payment']],
        on=['mp_name', 'constituency', 'state', 'normalized_work_description'],
        how='left'
    )
    master = master.merge(phrased_match[['project_id', 'total_expenditure', 'payment_count', 'successful_payment_count', 'pending_payment_count', 'latest_payment_status', 'primary_vendor', 'average_payment', 'maximum_payment', 'minimum_payment']], on='project_id', how='left')
    master['total_expenditure'] = master['total_expenditure'].fillna(0.0)
    master['payment_count'] = master['payment_count'].fillna(0).astype(int)
    master['successful_payment_count'] = master['successful_payment_count'].fillna(0).astype(int)
    master['pending_payment_count'] = master['pending_payment_count'].fillna(0).astype(int)
    master['primary_vendor'] = master['primary_vendor'].replace({np.nan: 'Unassigned / Pending'})
    master['latest_payment_status'] = master['latest_payment_status'].fillna('No Transactions')
    master['status'] = np.where(master['completed_date'].notna(), 'completed', np.where(master['recommendation_date'].notna(), 'in_progress', 'recommended'))
    master['financial_progress_pct'] = np.where(
        master['recommended_amount'].notna() & (master['recommended_amount'] > 0),
        (master['total_expenditure'] / master['recommended_amount']) * 100,
        np.nan
    )
    master['expenditure_ratio'] = np.where(
        master['recommended_amount'].notna() & (master['recommended_amount'] > 0),
        master['total_expenditure'] / master['recommended_amount'],
        np.nan
    )
    master['average_rating'] = pd.to_numeric(master['average_rating'], errors='coerce')
    master['final_amount'] = pd.to_numeric(master['final_amount'], errors='coerce')
    master['recommended_amount'] = pd.to_numeric(master['recommended_amount'], errors='coerce')
    master['status'] = master['status'].astype(str)

    output_cols = [
        'project_id', 'work_id', 'work_description', 'category', 'mp_name', 'constituency', 'state', 'house',
        'recommended_amount', 'recommendation_date', 'has_images', 'ida', 'final_amount', 'completed_date',
        'average_rating', 'total_expenditure', 'primary_vendor', 'latest_payment_status', 'payment_count',
        'successful_payment_count', 'pending_payment_count', 'status', 'financial_progress_pct', 'expenditure_ratio'
    ]
    master = master[output_cols]
    out = ROOT / config['outputs']['master_works']
    out.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(out, index=False)
    return master


def build_master_mp_summary(config):
    mp = pd.read_csv(ROOT / config['outputs']['mp_summary_clean'])
    out = ROOT / config['outputs']['master_mp_summary']
    out.parent.mkdir(parents=True, exist_ok=True)
    mp = mp[[
        'mp_name', 'constituency', 'state', 'house', 'allocated_amount', 'total_expenditure', 'utilization_pct',
        'completed_works', 'recommended_works', 'completion_rate_pct', 'unspent_amount', 'transaction_count',
        'successful_payments', 'pending_payments', 'average_rating'
    ]]
    mp.to_csv(out, index=False)
    return mp


def build_vendor_features(config):
    expenditures = pd.read_csv(ROOT / config['outputs']['expenditures_clean'])
    if 'work_description' in expenditures.columns and 'mp_name' in expenditures.columns and 'constituency' in expenditures.columns and 'state' in expenditures.columns:
        expenditures['project_key'] = (
            expenditures['work_description'].fillna('').str.lower().str.replace(r'[^a-z0-9]+', ' ', regex=True).str.strip() + '|' +
            expenditures['mp_name'].fillna('').astype(str) + '|' +
            expenditures['constituency'].fillna('').astype(str) + '|' +
            expenditures['state'].fillna('').astype(str)
        )
    vendor = expenditures.groupby('vendor', dropna=False).agg(
        project_count=('project_key', 'nunique'),
        total_expenditure=('expenditure_amount', 'sum'),
        average_project_cost=('expenditure_amount', 'mean'),
        median_project_cost=('expenditure_amount', 'median'),
        completed_project_count=('payment_status', lambda s: s.str.lower().isin({'successful', 'paid', 'payment_completed', 'completed'}).sum()),
        pending_payment_count=('payment_status', lambda s: s.str.lower().isin({'pending', 'in_progress', 'payment_in_progress'}).sum()),
        successful_payment_count=('payment_status', lambda s: s.str.lower().isin({'successful', 'paid', 'payment_completed', 'completed'}).sum())
    ).reset_index()
    vendor = vendor.replace({np.nan: None})
    out = ROOT / config['outputs']['vendor_features']
    out.parent.mkdir(parents=True, exist_ok=True)
    vendor.to_csv(out, index=False)
    return vendor


def main():
    config = load_config()
    print('[3/4] Building master data')
    master_works = build_master_works(config)
    master_mp = build_master_mp_summary(config)
    vendor_features = build_vendor_features(config)
    print('Projects:', len(master_works))
    print('MP entries:', len(master_mp))
    print('Vendors:', len(vendor_features))


if __name__ == '__main__':
    main()
