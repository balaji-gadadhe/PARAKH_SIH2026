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


def normalize_text(value):
    if pd.isna(value):
        return ""
    return re.sub(r'\s+', ' ', str(value).strip())


def build_missing_report(config):
    dataset_map = {
        'recommended_works': ROOT / config['outputs']['recommended_clean'],
        'completed_works': ROOT / config['outputs']['completed_clean'],
        'expenditures': ROOT / config['outputs']['expenditures_clean'],
        'mp_summary': ROOT / config['outputs']['mp_summary_clean'],
    }
    rows = []
    for name, path in dataset_map.items():
        df = pd.read_csv(path)
        for col in df.columns:
            missing_count = int(df[col].isna().sum())
            if missing_count > 0:
                rows.append({
                    'dataset': name,
                    'column_name': col,
                    'missing_count': missing_count,
                    'missing_percentage': round((missing_count / len(df)) * 100, 2) if len(df) else 0.0,
                })
    out_path = ROOT / config['outputs']['missing_value_report']
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_path, index=False)
    return rows


def add_issue(report_rows, dataset, issue_type, category, field, row_id, message):
    report_rows.append({
        'dataset': dataset,
        'issue_type': issue_type,
        'issue_category': category,
        'field': field,
        'row_id': row_id,
        'message': message,
    })


def validate_recommended(config, report_rows):
    df = pd.read_csv(ROOT / config['outputs']['recommended_clean'])
    if 'work_id' in df.columns:
        missing = df['work_id'].isna() | df['work_id'].astype(str).str.strip().eq('')
        for idx in df.index[missing]:
            add_issue(report_rows, 'recommended_works', 'missing_work_id', 'DATA_QUALITY_ERROR', 'work_id', idx, 'Missing Work ID')
        dup = df['work_id'].dropna().astype(str).str.strip().ne('')
        for work_id in df.loc[dup, 'work_id'].astype(str).str.strip():
            ids = df['work_id'].astype(str).str.strip() == work_id
            if ids.sum() > 1:
                for idx in df.index[ids]:
                    add_issue(report_rows, 'recommended_works', 'duplicate_work_id', 'DATA_QUALITY_ERROR', 'work_id', idx, 'Duplicate Work ID detected')
    for col in ['recommended_amount']:
        if col in df.columns:
            neg = df[col] < 0
            zero = df[col].fillna(0) == 0
            for idx in df.index[neg]:
                add_issue(report_rows, 'recommended_works', 'negative_amount', 'POTENTIAL_ANOMALY', col, idx, f'{col} is negative')
            for idx in df.index[zero]:
                add_issue(report_rows, 'recommended_works', 'zero_amount', 'POTENTIAL_ANOMALY', col, idx, f'{col} is zero')


def validate_completed(config, report_rows):
    df = pd.read_csv(ROOT / config['outputs']['completed_clean'])
    if 'work_id' in df.columns:
        missing = df['work_id'].isna() | df['work_id'].astype(str).str.strip().eq('')
        for idx in df.index[missing]:
            add_issue(report_rows, 'completed_works', 'missing_work_id', 'DATA_QUALITY_ERROR', 'work_id', idx, 'Missing Work ID')
        dup = df['work_id'].dropna().astype(str).str.strip().ne('')
        for work_id in df.loc[dup, 'work_id'].astype(str).str.strip():
            ids = df['work_id'].astype(str).str.strip() == work_id
            if ids.sum() > 1:
                for idx in df.index[ids]:
                    add_issue(report_rows, 'completed_works', 'duplicate_work_id', 'DATA_QUALITY_ERROR', 'work_id', idx, 'Duplicate Work ID in completed works')
    for col in ['final_amount']:
        if col in df.columns:
            neg = df[col] < 0
            zero = df[col].fillna(0) == 0
            for idx in df.index[neg]:
                add_issue(report_rows, 'completed_works', 'negative_amount', 'POTENTIAL_ANOMALY', col, idx, f'{col} is negative')
            for idx in df.index[zero]:
                add_issue(report_rows, 'completed_works', 'zero_amount', 'POTENTIAL_ANOMALY', col, idx, f'{col} is zero')


def validate_expenditures(config, report_rows):
    df = pd.read_csv(ROOT / config['outputs']['expenditures_clean'])
    for col in ['expenditure_amount']:
        if col in df.columns:
            neg = df[col] < 0
            zero = df[col].fillna(0) == 0
            for idx in df.index[neg]:
                add_issue(report_rows, 'expenditures', 'negative_amount', 'POTENTIAL_ANOMALY', col, idx, f'{col} is negative')
            for idx in df.index[zero]:
                add_issue(report_rows, 'expenditures', 'zero_amount', 'POTENTIAL_ANOMALY', col, idx, f'{col} is zero')
    if 'payment_status' in df.columns:
        valid = df['payment_status'].astype(str).str.lower().isin({
            'successful', 'pending', 'paid', 'payment_in_progress', 'in_progress',
            'payment_completed', 'cancelled', 'rejected', 'not_started'
        })
        for idx in df.index[~valid]:
            add_issue(report_rows, 'expenditures', 'invalid_payment_status', 'DATA_QUALITY_ERROR', 'payment_status', idx, 'Payment status is not in the accepted set')
    for col in ['mp_name', 'constituency', 'state']:
        if col in df.columns:
            missing = df[col].isna() | df[col].astype(str).str.strip().eq('')
            for idx in df.index[missing]:
                add_issue(report_rows, 'expenditures', f'missing_{col}', 'DATA_QUALITY_ERROR', col, idx, f'{col} is missing')


def validate_mp_summary(config, report_rows):
    df = pd.read_csv(ROOT / config['outputs']['mp_summary_clean'])
    for col in ['allocated_amount', 'total_expenditure', 'unspent_amount']:
        if col in df.columns:
            neg = df[col] < 0
            for idx in df.index[neg]:
                add_issue(report_rows, 'mp_summary', 'negative_amount', 'POTENTIAL_ANOMALY', col, idx, f'{col} is negative')
    for col in ['utilization_pct', 'completion_rate_pct']:
        if col in df.columns:
            invalid = (df[col] < 0) | (df[col] > 100)
            for idx in df.index[invalid]:
                add_issue(report_rows, 'mp_summary', 'invalid_percentage', 'DATA_QUALITY_ERROR', col, idx, f'{col} is out of range')


def generate_quality_report(config, report_rows):
    df = pd.DataFrame(report_rows, columns=['dataset', 'issue_type', 'issue_category', 'field', 'row_id', 'message'])
    out_path = ROOT / config['outputs']['data_quality_report']
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return df


def generate_expenditure_matching_report(config):
    expenditures = pd.read_csv(ROOT / config['outputs']['expenditures_clean'])
    recommended = pd.read_csv(ROOT / config['outputs']['recommended_clean'])
    recommended['normalized_work_description'] = recommended['work_description'].fillna('').str.lower().str.replace(r'[^a-z0-9]+', ' ', regex=True).str.strip()
    expenditures['normalized_work_description'] = expenditures['work_description'].fillna('').str.lower().str.replace(r'[^a-z0-9]+', ' ', regex=True).str.strip()

    key_counts = (
        recommended[['mp_name', 'constituency', 'state', 'normalized_work_description']]
        .fillna('')
        .astype(str)
        .assign(
            mp_name=lambda df: df['mp_name'].str.strip(),
            constituency=lambda df: df['constituency'].str.strip(),
            state=lambda df: df['state'].str.strip(),
            normalized_work_description=lambda df: df['normalized_work_description'].str.strip(),
        )
        .groupby(['mp_name', 'constituency', 'state', 'normalized_work_description'])
        .size()
        .to_dict()
    )

    records = []
    for _, row in expenditures.iterrows():
        key = (
            str(row.get('mp_name', '') or '').strip(),
            str(row.get('constituency', '') or '').strip(),
            str(row.get('state', '') or '').strip(),
            str(row.get('normalized_work_description', '') or '').strip(),
        )
        candidate_count = key_counts.get(key, 0)
        if candidate_count == 1:
            match_status = 'matched'
        elif candidate_count > 1:
            match_status = 'ambiguous'
        else:
            match_status = 'unmatched'
        records.append({
            'mp_name': row.get('mp_name'),
            'constituency': row.get('constituency'),
            'state': row.get('state'),
            'work_description': row.get('work_description'),
            'match_status': match_status,
            'candidate_count': candidate_count,
        })
    matching_df = pd.DataFrame(records)
    out_path = ROOT / config['outputs']['expenditure_matching_report']
    out_path.parent.mkdir(parents=True, exist_ok=True)
    matching_df.to_csv(out_path, index=False)
    return matching_df


def generate_allocation_reconciliation(config):
    mp_summary = pd.read_csv(ROOT / config['outputs']['mp_summary_clean'])
    allocation_df = pd.DataFrame({
        'mp_name': mp_summary['mp_name'],
        'constituency': mp_summary['constituency'],
        'state': mp_summary['state'],
        'allocation_from_excel': [np.nan] * len(mp_summary),
        'allocation_from_mp_summary': mp_summary['allocated_amount'],
        'difference': [np.nan] * len(mp_summary),
        'reconciliation_status': ['missing_in_excel'] * len(mp_summary),
    })
    excel_path = ROOT / config['source_files']['allocation_excel']
    if excel_path.exists():
        try:
            xls = pd.ExcelFile(excel_path)
            sheet = xls.sheet_names[0]
            excel_df = xls.parse(sheet)
            excel_df.columns = [normalize_text(c) for c in excel_df.columns]
            if 'mp name' in excel_df.columns:
                excel_df = excel_df.rename(columns={'mp name': 'mp_name'})
            if 'allocation amount' in excel_df.columns:
                excel_df = excel_df.rename(columns={'allocation amount': 'allocation_from_excel'})
            if 'mp_name' in excel_df.columns and 'allocation_from_excel' in excel_df.columns:
                excel_df['mp_name'] = excel_df['mp_name'].map(normalize_text)
                excel_df['allocation_from_excel'] = pd.to_numeric(excel_df['allocation_from_excel'], errors='coerce')
                merged = mp_summary[['mp_name', 'constituency', 'state', 'allocated_amount']].copy().rename(columns={'allocated_amount': 'allocation_from_mp_summary'})
                merged = merged.merge(excel_df[['mp_name', 'allocation_from_excel']], on='mp_name', how='left')
                merged['difference'] = merged['allocation_from_excel'] - merged['allocation_from_mp_summary']
                merged['reconciliation_status'] = np.where(
                    merged['allocation_from_excel'].notna() & merged['allocation_from_mp_summary'].notna(),
                    np.where(np.isclose(merged['difference'], 0, atol=1e-6), 'match', 'difference'),
                    np.where(merged['allocation_from_excel'].notna(), 'missing_in_summary', 'missing_in_excel')
                )
                allocation_df = merged[['mp_name', 'constituency', 'state', 'allocation_from_excel', 'allocation_from_mp_summary', 'difference', 'reconciliation_status']]
        except Exception:
            pass
    out_path = ROOT / config['outputs']['allocation_reconciliation']
    out_path.parent.mkdir(parents=True, exist_ok=True)
    allocation_df.to_csv(out_path, index=False)
    return allocation_df


def write_quality_md(config, report_df):
    counts = report_df['issue_category'].value_counts().to_dict() if isinstance(report_df, pd.DataFrame) and not report_df.empty else {}
    contents = [
        '# Data Quality Report',
        '',
        '## Summary',
        '',
        f"- DATA_QUALITY_ERROR: {counts.get('DATA_QUALITY_ERROR', 0)}",
        f"- POTENTIAL_ANOMALY: {counts.get('POTENTIAL_ANOMALY', 0)}",
        '',
        '## Notes',
        '',
        '- Suspicious or anomalous values are flagged but not deleted.',
        '- Placeholder physical progress values are not used in downstream ML features.',
        '- Expenditure matching is kept conservative: only definite matches are marked as matched.',
    ]
    out_path = ROOT / config['validation_dir'] / 'DATA_QUALITY_REPORT.md'
    out_path.write_text('\n'.join(contents), encoding='utf-8')


def main():
    config = load_config()
    print('[2/4] Validating data')
    report_rows = []
    validate_recommended(config, report_rows)
    validate_completed(config, report_rows)
    validate_expenditures(config, report_rows)
    validate_mp_summary(config, report_rows)
    quality = generate_quality_report(config, report_rows)
    build_missing_report(config)
    matching_rows = generate_expenditure_matching_report(config)
    allocation = generate_allocation_reconciliation(config)
    write_quality_md(config, quality)
    missing_rows = build_missing_report(config)
    print('Missing value rows:', len(missing_rows))
    print('Data quality issues:', len(quality))
    print('Expenditure matching counts:', matching_rows['match_status'].value_counts().to_dict())
    print('Allocation reconciliation statuses:', allocation['reconciliation_status'].value_counts().to_dict())


if __name__ == '__main__':
    main()
