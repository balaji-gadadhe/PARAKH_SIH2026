from __future__ import annotations

from pathlib import Path
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROJECT_FEATURES = ROOT / 'data' / 'ml_input' / 'project_features.csv'
LOCATION_DIR = ROOT / 'data' / 'location'
DEMO_DIR = LOCATION_DIR / 'demo'


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def main() -> None:
    project_df = pd.read_csv(PROJECT_FEATURES)
    real_df = pd.read_csv(LOCATION_DIR / 'project_locations.csv')
    demo_df = pd.read_csv(DEMO_DIR / 'demo_project_locations.csv') if (DEMO_DIR / 'demo_project_locations.csv').exists() else pd.DataFrame()
    feature_df = pd.read_csv(LOCATION_DIR / 'project_location_features.csv') if (LOCATION_DIR / 'project_location_features.csv').exists() else pd.DataFrame()
    similarity_df = pd.read_csv(LOCATION_DIR / 'project_similarity_location.csv') if (LOCATION_DIR / 'project_similarity_location.csv').exists() else pd.DataFrame()

    if not feature_df.empty and 'location_data_available' not in feature_df.columns:
        feature_df = pd.DataFrame(columns=[
            'project_id', 'latitude', 'longitude', 'nearest_project_id',
            'nearest_project_distance_km', 'nearby_projects_500m',
            'nearby_projects_1km', 'nearby_projects_5km',
            'same_constituency_project_count', 'local_project_density',
            'nearest_same_constituency_distance_km', 'location_data_available',
            'location_is_synthetic'
        ])

    total_projects = len(project_df)
    real_coordinates = int(real_df.dropna(subset=['latitude', 'longitude']).shape[0])
    synthetic_coordinates = int(demo_df.dropna(subset=['latitude', 'longitude']).shape[0])
    not_available_coordinates = int(real_df['location_source'].eq('not_available').sum())
    projects_with_coordinates = real_coordinates + synthetic_coordinates
    coordinate_coverage_pct = (projects_with_coordinates / total_projects) * 100 if total_projects else 0.0
    duplicate_project_ids = int(real_df['project_id'].duplicated().sum())
    invalid_latitude = int(((real_df['latitude'].dropna() < -90) | (real_df['latitude'].dropna() > 90)).sum()) + int(((demo_df['latitude'].dropna() < -90) | (demo_df['latitude'].dropna() > 90)).sum())
    invalid_longitude = int(((real_df['longitude'].dropna() < -180) | (real_df['longitude'].dropna() > 180)).sum()) + int(((demo_df['longitude'].dropna() < -180) | (demo_df['longitude'].dropna() > 180)).sum())
    coordinate_pairs = pd.concat([real_df[['latitude', 'longitude']], demo_df[['latitude', 'longitude']]], ignore_index=True).dropna()
    duplicate_coordinates = int(coordinate_pairs.duplicated().sum())

    similarity_df = similarity_df.copy()
    similarity_df['project_id'] = similarity_df['project_id'].astype(str)
    similarity_df['similar_project_id'] = similarity_df['similar_project_id'].astype(str)
    self_similarity_pairs = int((similarity_df['project_id'] == similarity_df['similar_project_id']).sum())
    if 'distance_km' in similarity_df.columns:
        similarity_df['distance_km'] = pd.to_numeric(similarity_df['distance_km'], errors='coerce')
        proximity_relationships = int(similarity_df['distance_km'].notna().sum())
        projects_within_500m = int((similarity_df['distance_km'] <= 0.5).sum())
        projects_within_1km = int((similarity_df['distance_km'] <= 1.0).sum())
        projects_within_5km = int((similarity_df['distance_km'] <= 5.0).sum())
    else:
        proximity_relationships = 0
        projects_within_500m = 0
        projects_within_1km = 0
        projects_within_5km = 0

    if 'similarity_method' in similarity_df.columns:
        description_only_pairs = int(similarity_df['similarity_method'].eq('description_only').sum())
        description_plus_location_pairs = int(similarity_df['similarity_method'].eq('description_plus_location').sum())
    else:
        description_only_pairs = 0
        description_plus_location_pairs = 0

    missing_location_similarity_pairs = int(similarity_df['distance_km'].isna().sum())
    synthetic_similarity_pairs = int(similarity_df['project_id'].isin(demo_df['project_id'].astype(str).tolist()).sum())

    if not feature_df.empty and 'location_data_available' in feature_df.columns:
        projects_with_location_features = int(feature_df['location_data_available'].fillna(False).astype(bool).sum())
        projects_without_location_features = int((~feature_df['location_data_available'].fillna(False).astype(bool)).sum())
    else:
        projects_with_location_features = synthetic_coordinates
        projects_without_location_features = total_projects - synthetic_coordinates

    report = pd.DataFrame([
        ['total_projects', total_projects],
        ['projects_with_coordinates', projects_with_coordinates],
        ['projects_without_coordinates', total_projects - projects_with_coordinates],
        ['coordinate_coverage_pct', round(coordinate_coverage_pct, 4)],
        ['real_coordinates', real_coordinates],
        ['synthetic_coordinates', synthetic_coordinates],
        ['not_available_coordinates', not_available_coordinates],
        ['duplicate_project_ids', duplicate_project_ids],
        ['invalid_latitude', invalid_latitude],
        ['invalid_longitude', invalid_longitude],
        ['duplicate_coordinates', duplicate_coordinates],
        ['self_similarity_pairs', self_similarity_pairs],
        ['proximity_relationships', proximity_relationships],
        ['projects_within_500m', projects_within_500m],
        ['projects_within_1km', projects_within_1km],
        ['projects_within_5km', projects_within_5km],
        ['projects_with_location_features', projects_with_location_features],
        ['projects_without_location_features', projects_without_location_features],
        ['missing_location_similarity_pairs', missing_location_similarity_pairs],
        ['description_plus_location_pairs', description_plus_location_pairs],
        ['description_only_pairs', description_only_pairs],
        ['synthetic_similarity_pairs', synthetic_similarity_pairs],
    ], columns=['metric', 'value'])

    report.to_csv(LOCATION_DIR / 'location_validation_report.csv', index=False)
    print(report.to_string(index=False))


if __name__ == '__main__':
    main()
