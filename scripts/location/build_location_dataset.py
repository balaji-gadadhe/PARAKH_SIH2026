from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROJECT_FEATURES = ROOT / 'data' / 'ml_input' / 'project_features.csv'
LOCATION_DIR = ROOT / 'data' / 'location'
DEMO_DIR = LOCATION_DIR / 'demo'


def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def build_real_project_locations(project_df: pd.DataFrame) -> pd.DataFrame:
    """Keep the real project dataset separate and explicitly mark the lack of coordinates."""
    real = project_df[['project_id']].copy()
    real['state'] = project_df.get('state', pd.Series([pd.NA] * len(project_df), index=project_df.index)).map(normalize_text).replace({'': pd.NA})
    real['constituency'] = project_df.get('constituency', pd.Series([pd.NA] * len(project_df), index=project_df.index)).map(normalize_text).replace({'': pd.NA})
    real['location_text'] = ''
    real['latitude'] = pd.NA
    real['longitude'] = pd.NA
    real['location_source'] = 'not_available'
    real['location_method'] = 'not_available'
    real['confidence'] = 0.0
    real['is_verified'] = False

    columns = [
        'project_id', 'state', 'constituency', 'location_text',
        'latitude', 'longitude', 'location_source', 'location_method',
        'confidence', 'is_verified'
    ]
    return real[columns]


def build_synthetic_demo(project_df: pd.DataFrame) -> pd.DataFrame:
    """Create a clearly labeled demo dataset for proximity testing only."""
    centers = [
        (28.6139, 77.2090),
        (19.0760, 72.8777),
        (13.0827, 80.2707),
        (12.9716, 77.5946),
        (23.2599, 77.4126),
        (22.5726, 88.3639),
        (26.8467, 80.9462),
        (25.3176, 82.9739),
    ]
    groups = (
        project_df.dropna(subset=['project_id', 'state', 'constituency'])
        .groupby(['state', 'constituency'], dropna=False)
        .groups
    )

    demo_rows = []
    group_index = 0
    for (_, group_df) in groups.items():
        if group_index >= len(centers):
            break
        state = str(project_df.iloc[group_df[0]]['state']).strip()
        constituency = str(project_df.iloc[group_df[0]]['constituency']).strip()
        lat0, lon0 = centers[group_index % len(centers)]
        for j, project_idx in enumerate(list(group_df)[:12]):
            project_id = project_df.iloc[project_idx]['project_id']
            delta_lat = ((j % 6) * 0.0024) + ((j // 6) * 0.0008)
            delta_lon = ((j % 4) * 0.0031) + ((j // 4) * 0.0010)
            if j % 2 == 0:
                delta_lat *= -1
            if j % 3 == 0:
                delta_lon *= -1
            demo_rows.append({
                'project_id': project_id,
                'state': state,
                'constituency': constituency,
                'location_text': f'Demo location {j + 1} for {constituency}',
                'latitude': round(lat0 + delta_lat, 6),
                'longitude': round(lon0 + delta_lon, 6),
                'location_source': 'synthetic_demo',
                'location_method': 'synthetic_demo',
                'confidence': 0.0,
                'is_verified': False,
                'demo_only': True,
            })
        group_index += 1

    if not demo_rows:
        return pd.DataFrame(columns=[
            'project_id', 'state', 'constituency', 'location_text',
            'latitude', 'longitude', 'location_source', 'location_method',
            'confidence', 'is_verified', 'demo_only'
        ])

    demo_df = pd.DataFrame(demo_rows)
    demo_df = demo_df[[
        'project_id', 'state', 'constituency', 'location_text',
        'latitude', 'longitude', 'location_source', 'location_method',
        'confidence', 'is_verified', 'demo_only'
    ]]
    return demo_df


def main() -> None:
    LOCATION_DIR.mkdir(parents=True, exist_ok=True)
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    project_df = pd.read_csv(PROJECT_FEATURES)
    real_df = build_real_project_locations(project_df)
    demo_df = build_synthetic_demo(project_df)

    real_df.to_csv(LOCATION_DIR / 'project_locations.csv', index=False)
    demo_df.to_csv(DEMO_DIR / 'demo_project_locations.csv', index=False)

    print(f'Wrote {len(real_df)} real project location rows to project_locations.csv')
    print(f'Wrote {len(demo_df)} synthetic demo rows to demo_project_locations.csv')


if __name__ == '__main__':
    main()
