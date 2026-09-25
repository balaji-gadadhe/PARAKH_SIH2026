import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
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


def compute_similarity_data(master_works, config):
    df = master_works[['project_id', 'work_description', 'category', 'state', 'constituency']].copy()
    df['clean_description'] = df['work_description'].fillna('').map(normalize_description)
    df = df[df['clean_description'] != ''].copy()
    if df.empty:
        out = ROOT / config['outputs']['project_similarity_data']
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=['project_id', 'work_description', 'clean_description', 'category', 'state', 'constituency']).to_csv(out, index=False)
        return df
    vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), max_features=2000)
    vectors = vectorizer.fit_transform(df['clean_description'])
    if len(df) < 2:
        df['description_similarity_score'] = 0.0
    else:
        neighbors = NearestNeighbors(n_neighbors=2, metric='cosine', algorithm='brute')
        neighbors.fit(vectors)
        distances, _ = neighbors.kneighbors(vectors)
        # The closest row is the project itself; the second row is its nearest peer.
        df['description_similarity_score'] = 1.0 - distances[:, 1]
    df = df[['project_id', 'work_description', 'clean_description', 'category', 'state', 'constituency', 'description_similarity_score']]
    out = ROOT / config['outputs']['project_similarity_data']
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df


def create_project_features(config):
    master = pd.read_csv(ROOT / config['outputs']['master_works'])
    expenditures = pd.read_csv(ROOT / config['outputs']['expenditures_clean'])
    vendor_features = pd.read_csv(ROOT / config['outputs']['vendor_features'])
    similarity = pd.read_csv(ROOT / config['outputs']['project_similarity_data']) if (ROOT / config['outputs']['project_similarity_data']).exists() else pd.DataFrame()
    master = master.copy()
    master['project_id'] = master['project_id'].astype(str)
    master['is_completed'] = master['completed_date'].notna().astype(int)
    master['has_images'] = master['has_images'].fillna(False).astype(bool)
    master['recommended_amount'] = pd.to_numeric(master['recommended_amount'], errors='coerce')
    master['final_amount'] = pd.to_numeric(master['final_amount'], errors='coerce')
    master['total_expenditure'] = pd.to_numeric(master['total_expenditure'], errors='coerce')

    master['cost_variation_pct'] = np.where(
        master['recommended_amount'].notna() & master['final_amount'].notna() & (master['recommended_amount'] != 0),
        ((master['final_amount'] - master['recommended_amount']) / master['recommended_amount']) * 100,
        np.nan
    )
    master['expenditure_ratio'] = np.where(
        master['recommended_amount'].notna() & (master['recommended_amount'] != 0),
        master['total_expenditure'] / master['recommended_amount'],
        np.nan
    )
    master['payment_count'] = master['payment_count'].fillna(0)
    master['average_payment'] = np.where(master['payment_count'] > 0, master['total_expenditure'] / master['payment_count'], np.nan)
    master['maximum_payment'] = np.where(master['payment_count'] > 0, master['total_expenditure'].clip(lower=0), np.nan)
    master['minimum_payment'] = np.where(master['payment_count'] > 0, master['total_expenditure'].clip(lower=0), np.nan)
    master['pending_payment_count'] = master['pending_payment_count'].fillna(0)
    master['successful_payment_count'] = master['successful_payment_count'].fillna(0)
    recommendation_date = pd.to_datetime(master['recommendation_date'], utc=True).dt.tz_localize(None)
    completed_date = pd.to_datetime(master['completed_date'], utc=True).dt.tz_localize(None)
    master['recommendation_to_completion_days'] = np.where(
        recommendation_date.notna() & completed_date.notna(),
        (completed_date - recommendation_date).dt.days,
        np.nan
    )
    ref_date = pd.Timestamp('2026-09-01')
    master['days_since_recommendation'] = np.where(
        recommendation_date.notna(),
        (ref_date - recommendation_date).dt.days,
        np.nan
    )
    master['average_rating'] = pd.to_numeric(master['average_rating'], errors='coerce')
    if not similarity.empty:
        similarity_map = similarity.set_index('project_id')['description_similarity_score'].to_dict()
        master['description_similarity_score'] = master['project_id'].map(similarity_map)
    else:
        master['description_similarity_score'] = np.nan

    peer_group = master.groupby(['category', 'state'], dropna=False)['recommended_amount']
    med = peer_group.median().rename('peer_median_cost')
    mean = peer_group.mean().rename('peer_mean_cost')
    std = peer_group.std(ddof=1).rename('peer_std_cost')
    peer = pd.concat([med, mean, std], axis=1).reset_index()
    master = master.merge(peer, on=['category', 'state'], how='left')
    master['cost_deviation_from_peer'] = np.where(
        master['recommended_amount'].notna() & master['peer_median_cost'].notna(),
        ((master['recommended_amount'] - master['peer_median_cost']) / master['peer_median_cost']) * 100,
        np.nan
    )

    if 'vendor' in expenditures.columns:
        vendor_lookup = expenditures.groupby('vendor', dropna=False).agg(
            vendor_project_count=('work_description', 'nunique'),
            vendor_total_expenditure=('expenditure_amount', 'sum'),
            vendor_average_project_cost=('expenditure_amount', 'mean')
        ).reset_index()
        vendor_lookup = vendor_lookup.rename(columns={'vendor': 'primary_vendor'})
        master = master.merge(vendor_lookup[['primary_vendor', 'vendor_project_count', 'vendor_total_expenditure', 'vendor_average_project_cost']], on='primary_vendor', how='left')
    else:
        master['vendor_project_count'] = np.nan
        master['vendor_total_expenditure'] = np.nan
        master['vendor_average_project_cost'] = np.nan

    feature_cols = [
        'project_id', 'mp_name', 'state', 'constituency', 'category',
        'recommended_amount', 'final_amount', 'total_expenditure',
        'cost_variation_pct', 'expenditure_ratio', 'payment_count',
        'average_payment', 'maximum_payment', 'minimum_payment', 'payment_frequency',
        'pending_payment_count', 'successful_payment_count', 'vendor_project_count',
        'vendor_total_expenditure', 'vendor_average_project_cost',
        'recommendation_to_completion_days', 'days_since_recommendation',
        'is_completed', 'has_images', 'average_rating', 'peer_median_cost',
        'peer_mean_cost', 'peer_std_cost', 'cost_deviation_from_peer', 'description_similarity_score'
    ]
    # payment_frequency is not available in master but can be derived from count and days since recommendation.
    master['payment_frequency'] = np.where(
        master['payment_count'].gt(0) & master['days_since_recommendation'].notna() & (master['days_since_recommendation'] > 0),
        master['payment_count'] / master['days_since_recommendation'],
        np.nan
    )
    master = master[feature_cols]
    out = ROOT / config['outputs']['project_features']
    out.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(out, index=False)
    return master


def create_mp_features(config):
    mp = pd.read_csv(ROOT / config['outputs']['master_mp_summary'])
    mp = mp.copy()
    if 'allocated_amount' in mp.columns and 'total_expenditure' in mp.columns:
        mp['utilization_ratio'] = np.where(mp['allocated_amount'].notna() & (mp['allocated_amount'] != 0), mp['total_expenditure'] / mp['allocated_amount'], np.nan)
    if 'recommended_works' in mp.columns and 'completed_works' in mp.columns:
        mp['completion_gap'] = mp['recommended_works'] - mp['completed_works']
    mp = mp[[
        'mp_name', 'constituency', 'state', 'house', 'allocated_amount', 'total_expenditure', 'utilization_pct',
        'completed_works', 'recommended_works', 'completion_rate_pct', 'unspent_amount', 'transaction_count',
        'successful_payments', 'pending_payments', 'average_rating', 'utilization_ratio', 'completion_gap'
    ]]
    out = ROOT / config['outputs']['mp_features']
    out.parent.mkdir(parents=True, exist_ok=True)
    mp.to_csv(out, index=False)
    return mp


def feature_quality_report(project_features):
    report_rows = []
    for col in project_features.columns:
        series = project_features[col]
        dtype = str(series.dtype)
        missing_count = int(series.isna().sum())
        missing_pct = round((missing_count / len(series)) * 100, 2) if len(series) else 0.0
        unique_values = int(series.nunique(dropna=True))
        is_numeric = pd.api.types.is_numeric_dtype(series)
        min_val = series.min() if is_numeric else np.nan
        max_val = series.max() if is_numeric else np.nan
        mean_val = series.mean() if is_numeric else np.nan
        median_val = series.median() if is_numeric else np.nan
        usable_for_ml = is_numeric and missing_count < max(1, int(len(series) * 0.5))
        notes = 'Numeric feature usable for ML.' if usable_for_ml else 'Categorical or highly sparse; use with caution.'
        report_rows.append({
            'feature_name': col,
            'dtype': dtype,
            'missing_count': missing_count,
            'missing_percentage': missing_pct,
            'unique_values': unique_values,
            'min': min_val,
            'max': max_val,
            'mean': mean_val,
            'median': median_val,
            'usable_for_ml': usable_for_ml,
            'notes': notes
        })
    return pd.DataFrame(report_rows)


def create_ml_handoff(config):
    project_features = pd.read_csv(ROOT / config['outputs']['project_features'])
    mp_features = pd.read_csv(ROOT / config['outputs']['mp_features'])
    similarity = pd.read_csv(ROOT / config['outputs']['project_similarity_data'])
    vendor_features = pd.read_csv(ROOT / config['outputs']['vendor_features'])
    project_features.to_csv(ROOT / config['outputs']['ml_project_features'], index=False)
    mp_features.to_csv(ROOT / config['outputs']['ml_mp_features'], index=False)
    similarity.to_csv(ROOT / config['outputs']['ml_project_similarity_data'], index=False)
    vendor_features.to_csv(ROOT / config['outputs']['ml_vendor_features'], index=False)

    feature_report = feature_quality_report(project_features)
    feature_path = ROOT / config['outputs']['feature_quality_report']
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    feature_report.to_csv(feature_path, index=False)

    data_dictionary = pd.DataFrame([
        {'dataset': 'project_features', 'column_name': 'project_id', 'data_type': 'string', 'description': 'Stable project identifier', 'source': 'SOURCE DATA', 'calculation': 'work_id combined with MP, constituency, and state', 'missing_value_policy': 'No missing values expected', 'usable_for_ml': True, 'notes': 'Primary key for project-level learning; work_id alone is not globally unique'},
        {'dataset': 'project_features', 'column_name': 'physical_progress_pct', 'data_type': 'float', 'description': 'Legacy placeholder not used', 'source': 'UNAVAILABLE FEATURE', 'calculation': 'Not calculated', 'missing_value_policy': 'Always missing or omitted', 'usable_for_ml': False, 'notes': 'Do not use old artificial placeholder values; banned from ML dataset.'},
        {'dataset': 'project_features', 'column_name': 'latitude', 'data_type': 'float', 'description': 'Project latitude', 'source': 'UNAVAILABLE FEATURE', 'calculation': 'Not available in source data', 'missing_value_policy': 'Not available', 'usable_for_ml': False, 'notes': 'Location/distance similarity requires actual project latitude/longitude.'},
        {'dataset': 'project_features', 'column_name': 'longitude', 'data_type': 'float', 'description': 'Project longitude', 'source': 'UNAVAILABLE FEATURE', 'calculation': 'Not available in source data', 'missing_value_policy': 'Not available', 'usable_for_ml': False, 'notes': 'Location/distance similarity requires actual project latitude/longitude.'},
        {'dataset': 'project_features', 'column_name': 'description_similarity_score', 'data_type': 'float', 'description': 'TF-IDF cosine similarity to nearest project description', 'source': 'DERIVED FEATURE', 'calculation': 'Cosine similarity over normalized descriptions', 'missing_value_policy': 'NaN when descriptions missing', 'usable_for_ml': True, 'notes': 'This measures text similarity only, not fraud.'},
        {'dataset': 'vendor_features', 'column_name': 'vendor', 'data_type': 'string', 'description': 'Vendor name from expenditure data', 'source': 'SOURCE DATA', 'calculation': 'Raw vendor field', 'missing_value_policy': 'Empty vendor strings are retained only if present', 'usable_for_ml': True, 'notes': 'Vendor profiling is based on expenditure data only.'},
        {'dataset': 'mp_features', 'column_name': 'allocated_amount', 'data_type': 'float', 'description': 'Allocated funding for MP', 'source': 'SOURCE DATA', 'calculation': 'From MP summary', 'missing_value_policy': 'Missing values treated as NaN', 'usable_for_ml': True, 'notes': 'Project-level and MP-level analysis only.'}
    ])
    writer = pd.ExcelWriter(ROOT / config['outputs']['data_dictionary'], engine='openpyxl')
    data_dictionary.to_excel(writer, index=False)
    writer.close()

    readme = '''# MPLAD Sentinel ML Input Documentation

## Datasets

- project_features.csv: primary ML dataset containing project-level financial, time, categorical, and text features.
- mp_features.csv: MP-level summary features for program and constituency monitoring.
- project_similarity_data.csv: normalized project descriptions and computed similarity values.
- vendor_features.csv: vendor-level expenditure and payment profiling.

## Primary key

- project_id

## Recommended ML dataset

The main training and scoring dataset is project_features.csv.

## Numeric features

- recommended_amount
- final_amount
- total_expenditure
- cost_variation_pct
- expenditure_ratio
- payment_count
- average_payment
- maximum_payment
- minimum_payment
- payment_frequency
- pending_payment_count
- successful_payment_count
- vendor_project_count
- vendor_total_expenditure
- vendor_average_project_cost
- recommendation_to_completion_days
- days_since_recommendation
- average_rating
- peer_median_cost
- peer_mean_cost
- peer_std_cost
- cost_deviation_from_peer
- description_similarity_score

## Categorical features

- mp_name
- state
- constituency
- category
- house
- primary_vendor (in master data)

## Text features

- work_description
- clean_description

## Missing-value handling

Use rows with valid project_id and only model on features where data is available. Do not impute non-existent or forbidden variables.

## Known limitations

- Image similarity requires access to actual project image files.
- Location/distance similarity requires actual project latitude/longitude.
- Expenditure matching is conservative; ambiguous records are not forced into a project match.
- Physical progress is intentionally absent because legacy placeholder logic is unsafe and not valid for ML.

## Unavailable features

- physical_progress_pct (legacy placeholder; explicitly excluded)
- image embeddings (no image files available)
- latitude/longitude (not present in source data)

## Forbidden / unsafe features

DO NOT USE physical_progress_pct if it originates from the old placeholder logic.

Do not use any fabricated GPS, image embeddings, or false progress values.

Text similarity and model anomalies are risk indicators, not proof of fraud, and require investigation.
'''
    (ROOT / config['outputs']['ml_readme']).write_text(readme, encoding='utf-8')

    ml_output_readme = '''# ML Output Contract

The ML teammate must return a file named ml_predictions.csv.

## Required fields

- project_id
- anomaly_score
- anomaly_flag
- model_reason

## Preferred fields

- delay_risk
- cost_anomaly_score

## Contract notes

- anomaly_flag should be boolean or 0/1.
- model_reason should be human-readable and explain the risk indicator.
- Do not output confirmed fraud labels.
- Use potential anomaly, risk indicator, or requires investigation wording.
- The output will later be merged into the risk engine.
'''
    (ROOT / config['outputs']['ml_output_readme']).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / config['outputs']['ml_output_readme']).write_text(ml_output_readme, encoding='utf-8')


def main():
    config = load_config()
    print('[4/4] Creating features')
    similarity = compute_similarity_data(pd.read_csv(ROOT / config['outputs']['master_works']), config)
    project_features = create_project_features(config)
    mp_features = create_mp_features(config)
    create_ml_handoff(config)
    print('Project features rows:', len(project_features))
    print('MP features rows:', len(mp_features))
    print('Similarity rows:', len(similarity))


if __name__ == '__main__':
    main()
