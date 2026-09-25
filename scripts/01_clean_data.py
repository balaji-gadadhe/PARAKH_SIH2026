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
    cfg_path = ROOT / 'config' / 'data_config.yaml'
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def normalize_text(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def canonicalize_column_name(value):
    text = normalize_text(value).lower()
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_amount(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        val = float(value)
        return val if np.isfinite(val) else np.nan
    text = str(value).strip()
    if text == '':
        return np.nan
    text = text.replace('₹', '').replace('Rs', '').replace('INR', '').replace(',', '').replace(' ', '')
    text = text.replace('(', '-').replace(')', '')
    try:
        val = float(text)
    except ValueError:
        numbers = re.findall(r'-?\d+(?:\.\d+)?', text)
        if not numbers:
            return np.nan
        val = float(numbers[0])
    return float(val)


def parse_date(value):
    if pd.isna(value):
        return pd.NaT
    text = str(value).strip()
    if text == '' or text.lower() in {'nan', 'na', 'n/a', 'none'}:
        return pd.NaT
    try:
        dt = pd.to_datetime(text, errors='coerce')
    except Exception:
        dt = pd.NaT
    return dt


def parse_bool(value):
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'y'}:
        return True
    if text in {'0', 'false', 'no', 'n'}:
        return False
    return bool(text)


def copy_raw_data(config):
    raw_dir = ROOT / config['raw_dir']
    raw_dir.mkdir(parents=True, exist_ok=True)
    for key in ['recommended', 'completed', 'expenditures', 'mp_summary']:
        src_name = config['source_files'][key]
        source_path = ROOT / src_name
        target_path = raw_dir / src_name
        if source_path.exists() and not target_path.exists():
            target_path.write_bytes(source_path.read_bytes())


def find_source_in_root(filename):
    for path in ROOT.iterdir():
        if path.is_file() and filename.lower() in path.name.lower():
            return path
    return ROOT / filename


def clean_recommended_works(config):
    raw_file = find_source_in_root(config['source_files']['recommended'])
    df = pd.read_csv(raw_file)
    before = len(df)
    df.columns = [canonicalize_column_name(c) for c in df.columns]
    rename_map = {
        'work id': 'work_id',
        'work description': 'work_description',
        'category': 'category',
        'mp name': 'mp_name',
        'constituency': 'constituency',
        'state': 'state',
        'house': 'house',
        'recommended amount': 'recommended_amount',
        'recommendation date': 'recommendation_date',
        'has images': 'has_images',
        'ida': 'ida'
    }
    df = df.rename(columns=rename_map)
    for col in ['work_id', 'work_description', 'category', 'mp_name', 'constituency', 'state', 'house', 'ida']:
        if col in df.columns:
            df[col] = df[col].map(normalize_text)
    df['recommended_amount'] = pd.to_numeric(df['recommended_amount'].map(parse_amount), errors='coerce')
    df['recommendation_date'] = pd.to_datetime(df['recommendation_date'].map(parse_date), errors='coerce')
    df['has_images'] = df['has_images'].map(parse_bool)
    df = df.drop_duplicates().reset_index(drop=True)
    cleaned_path = ROOT / config['outputs']['recommended_clean']
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cleaned_path, index=False)
    print(f"Recommended works cleaned: {before} -> {len(df)} rows; duplicates removed: {before - len(df)}")
    return df


def clean_completed_works(config):
    raw_file = find_source_in_root(config['source_files']['completed'])
    df = pd.read_csv(raw_file)
    before = len(df)
    df.columns = [canonicalize_column_name(c) for c in df.columns]
    rename_map = {
        'work id': 'work_id',
        'work description': 'work_description',
        'category': 'category',
        'mp name': 'mp_name',
        'constituency': 'constituency',
        'state': 'state',
        'house': 'house',
        'final amount': 'final_amount',
        'completed date': 'completed_date',
        'has images': 'has_images',
        'average rating': 'average_rating',
        'ida': 'ida'
    }
    df = df.rename(columns=rename_map)
    for col in ['work_id', 'work_description', 'category', 'mp_name', 'constituency', 'state', 'house', 'ida']:
        if col in df.columns:
            df[col] = df[col].map(normalize_text)
    df['final_amount'] = pd.to_numeric(df['final_amount'].map(parse_amount), errors='coerce')
    df['completed_date'] = pd.to_datetime(df['completed_date'].map(parse_date), errors='coerce')
    df['has_images'] = df['has_images'].map(parse_bool)
    df['average_rating'] = pd.to_numeric(df['average_rating'].map(parse_amount), errors='coerce')
    df = df.drop_duplicates().reset_index(drop=True)
    cleaned_path = ROOT / config['outputs']['completed_clean']
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cleaned_path, index=False)
    print(f"Completed works cleaned: {before} -> {len(df)} rows; duplicates removed: {before - len(df)}")
    return df


def clean_expenditures(config):
    raw_file = find_source_in_root(config['source_files']['expenditures'])
    df = pd.read_csv(raw_file)
    before = len(df)
    df.columns = [canonicalize_column_name(c) for c in df.columns]
    rename_map = {
        'mp name': 'mp_name',
        'constituency': 'constituency',
        'state': 'state',
        'house': 'house',
        'work description': 'work_description',
        'vendor': 'vendor',
        'ida': 'ida',
        'expenditure amount': 'expenditure_amount',
        'expenditure date': 'expenditure_date',
        'payment status': 'payment_status'
    }
    df = df.rename(columns=rename_map)
    for col in ['mp_name', 'constituency', 'state', 'house', 'work_description', 'vendor', 'ida', 'payment_status']:
        if col in df.columns:
            df[col] = df[col].map(normalize_text)
    df['expenditure_amount'] = pd.to_numeric(df['expenditure_amount'].map(parse_amount), errors='coerce')
    df['expenditure_date'] = pd.to_datetime(df['expenditure_date'].map(parse_date), errors='coerce')
    df['payment_status'] = df['payment_status'].str.strip().str.lower().replace({'payment in-progress': 'payment_in_progress', 'in progress': 'in_progress', 'successful': 'successful', 'pending': 'pending', 'paid': 'paid', 'payment completed': 'payment_completed', 'cancelled': 'cancelled'})
    df['match_status'] = 'unmatched'
    df = df.drop_duplicates().reset_index(drop=True)
    cleaned_path = ROOT / config['outputs']['expenditures_clean']
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cleaned_path, index=False)
    print(f"Expenditures cleaned: {before} -> {len(df)} rows; duplicates removed: {before - len(df)}")
    return df


def clean_mp_summary(config):
    raw_file = find_source_in_root(config['source_files']['mp_summary'])
    df = pd.read_csv(raw_file)
    before = len(df)
    df.columns = [canonicalize_column_name(c) for c in df.columns]
    rename_map = {
        'mp name': 'mp_name',
        'constituency': 'constituency',
        'state': 'state',
        'house': 'house',
        'allocated amount': 'allocated_amount',
        'total expenditure': 'total_expenditure',
        'utilization': 'utilization_pct',
        'completed works': 'completed_works',
        'recommended works': 'recommended_works',
        'completion rate': 'completion_rate_pct',
        'unspent amount': 'unspent_amount',
        'transaction count': 'transaction_count',
        'successful payments': 'successful_payments',
        'pending payments': 'pending_payments',
        'average rating': 'average_rating'
    }
    df = df.rename(columns=rename_map)
    for col in ['mp_name', 'constituency', 'state', 'house']:
        if col in df.columns:
            df[col] = df[col].map(normalize_text)
    for col in ['allocated_amount', 'total_expenditure', 'utilization_pct', 'completed_works', 'recommended_works', 'completion_rate_pct', 'unspent_amount', 'transaction_count', 'successful_payments', 'pending_payments', 'average_rating']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].map(parse_amount), errors='coerce')
    df = df.drop_duplicates().reset_index(drop=True)
    cleaned_path = ROOT / config['outputs']['mp_summary_clean']
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cleaned_path, index=False)
    print(f"MP summary cleaned: {before} -> {len(df)} rows; duplicates removed: {before - len(df)}")
    return df


def generate_duplicate_report(config):
    report_rows = []
    dataset_map = {
        'recommended_works': find_source_in_root(config['source_files']['recommended']),
        'completed_works': find_source_in_root(config['source_files']['completed']),
        'expenditures': find_source_in_root(config['source_files']['expenditures']),
        'mp_summary': find_source_in_root(config['source_files']['mp_summary'])
    }
    for dataset_name, path in dataset_map.items():
        df = pd.read_csv(path)
        rows_before = len(df)
        exact_duplicates = int(df.duplicated().sum())
        rows_after = int(df.drop_duplicates().shape[0])
        report_rows.append({
            'dataset': dataset_name,
            'rows_before': rows_before,
            'exact_duplicates': exact_duplicates,
            'rows_after': rows_after
        })
    out_path = ROOT / config['outputs']['duplicate_report']
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(report_rows).to_csv(out_path, index=False)
    return report_rows


def main():
    config = load_config()
    print('[1/4] Cleaning data')
    copy_raw_data(config)
    rec = clean_recommended_works(config)
    comp = clean_completed_works(config)
    exp = clean_expenditures(config)
    summary = clean_mp_summary(config)
    duplicate_report = generate_duplicate_report(config)
    print('Rows before cleaning:')
    print({
        'recommended_works': len(pd.read_csv(find_source_in_root(config['source_files']['recommended']))),
        'completed_works': len(pd.read_csv(find_source_in_root(config['source_files']['completed']))),
        'expenditures': len(pd.read_csv(find_source_in_root(config['source_files']['expenditures']))),
        'mp_summary': len(pd.read_csv(find_source_in_root(config['source_files']['mp_summary'])))
    })
    print('Rows after cleaning:')
    print({
        'recommended_works': len(rec),
        'completed_works': len(comp),
        'expenditures': len(exp),
        'mp_summary': len(summary)
    })
    print('Duplicates removed:')
    print({row['dataset']: row['exact_duplicates'] for row in duplicate_report})
    print('Missing values summary:')
    for name, df in [('recommended_works', rec), ('completed_works', comp), ('expenditures', exp), ('mp_summary', summary)]:
        print(name, int(df.isna().sum().sum()))


if __name__ == '__main__':
    main()
