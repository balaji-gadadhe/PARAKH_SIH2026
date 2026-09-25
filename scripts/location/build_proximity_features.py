from __future__ import annotations

from pathlib import Path
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
LOCATION_DIR = ROOT / 'data' / 'location'
DEMO_DIR = LOCATION_DIR / 'demo'
SIMILARITY_FILE = ROOT / 'data' / 'ml_input' / 'project_similarity_data.csv'


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def build_project_location_features() -> pd.DataFrame:
    project_locations = pd.read_csv(LOCATION_DIR / 'project_locations.csv')
    demo_locations = pd.read_csv(DEMO_DIR / 'demo_project_locations.csv')
    project_ids = project_locations['project_id'].tolist()

    valid_demo = demo_locations.dropna(subset=['project_id', 'latitude', 'longitude']).copy().reset_index(drop=True)
    valid_demo['project_id'] = valid_demo['project_id'].astype(str)
    demo_lookup = {}
    for row in valid_demo.itertuples(index=False):
        demo_lookup[str(row.project_id)] = (float(row.latitude), float(row.longitude), row.state, row.constituency)

    feature_rows = []
    for project_id in project_ids:
        pid = str(project_id)
        row = project_locations[project_locations['project_id'].astype(str) == pid].iloc[0]
        if pid in demo_lookup:
            lat, lon, state, constituency = demo_lookup[pid]
            others = valid_demo[valid_demo['project_id'].astype(str) != pid].copy()
            if not others.empty:
                others = others.reset_index(drop=True)
                dists = others.apply(lambda r: haversine_km(lat, lon, float(r['latitude']), float(r['longitude'])), axis=1)
                nearest_row = others.loc[dists.idxmin()]
                nearest_pid = str(nearest_row['project_id'])
                nearest_dist = float(dists.min())
                nearby_500 = int((dists <= 0.5).sum())
                nearby_1k = int((dists <= 1.0).sum())
                nearby_5k = int((dists <= 5.0).sum())
                same_mask = (others['state'] == state) & (others['constituency'] == constituency)
                same_count = int(same_mask.sum())
                same_dists = dists[same_mask]
                nearest_same = float(same_dists.min()) if not same_dists.empty else pd.NA
                area = math.pi * (5.0 ** 2)
                density = float(nearby_5k / area) if area else pd.NA
            else:
                nearest_pid = pd.NA
                nearest_dist = pd.NA
                nearby_500 = pd.NA
                nearby_1k = pd.NA
                nearby_5k = pd.NA
                same_count = 0
                nearest_same = pd.NA
                density = pd.NA
        else:
            lat, lon = pd.NA, pd.NA
            nearest_pid = pd.NA
            nearest_dist = pd.NA
            nearby_500 = pd.NA
            nearby_1k = pd.NA
            nearby_5k = pd.NA
            same_count = pd.NA
            nearest_same = pd.NA
            density = pd.NA

        feature_rows.append({
            'project_id': pid,
            'latitude': lat,
            'longitude': lon,
            'nearest_project_id': nearest_pid,
            'nearest_project_distance_km': nearest_dist,
            'nearby_projects_500m': nearby_500,
            'nearby_projects_1km': nearby_1k,
            'nearby_projects_5km': nearby_5k,
            'same_constituency_project_count': same_count,
            'local_project_density': density,
            'nearest_same_constituency_distance_km': nearest_same,
            'location_data_available': not pd.isna(lat) and not pd.isna(lon),
            'location_is_synthetic': pid in demo_lookup,
        })

    feature_df = pd.DataFrame(feature_rows)
    feature_df = feature_df[[
        'project_id', 'latitude', 'longitude', 'nearest_project_id',
        'nearest_project_distance_km', 'nearby_projects_500m',
        'nearby_projects_1km', 'nearby_projects_5km',
        'same_constituency_project_count', 'local_project_density',
        'nearest_same_constituency_distance_km', 'location_data_available',
        'location_is_synthetic'
    ]]
    return feature_df


def build_similarity_with_location() -> pd.DataFrame:
    similarity_df = pd.read_csv(SIMILARITY_FILE).copy()
    similarity_df['project_id'] = similarity_df['project_id'].astype(str)
    similarity_df['description_similarity_score'] = pd.to_numeric(similarity_df['description_similarity_score'], errors='coerce').clip(0, 1)

    valid_demo = pd.read_csv(DEMO_DIR / 'demo_project_locations.csv').dropna(subset=['project_id', 'latitude', 'longitude']).copy()
    valid_demo['project_id'] = valid_demo['project_id'].astype(str)

    rows = []
    for record in similarity_df.itertuples(index=False):
        pid = str(record.project_id)
        desc_score = float(record.description_similarity_score)
        similar_pid = None
        distance_km = pd.NA
        location_proximity_score = pd.NA
        combined_score = desc_score
        similarity_method = 'description_only'
        location_available = False

        if pid in valid_demo['project_id'].values:
            current = valid_demo[valid_demo['project_id'].astype(str) == pid].iloc[0]
            others = valid_demo[valid_demo['project_id'].astype(str) != pid].copy()
            if not others.empty:
                others = others.reset_index(drop=True)
                dists = others.apply(lambda r: haversine_km(float(current['latitude']), float(current['longitude']), float(r['latitude']), float(r['longitude'])), axis=1)
                nearest_idx = dists.idxmin()
                similar_pid = str(others.loc[nearest_idx, 'project_id'])
                distance_km = float(dists.min())
                location_proximity_score = math.exp(-distance_km / 5.0)
                combined_score = 0.6 * desc_score + 0.4 * location_proximity_score
                similarity_method = 'description_plus_location'
                location_available = True

        if pid == similar_pid:
            continue

        rows.append({
            'project_id': pid,
            'similar_project_id': similar_pid,
            'description_similarity_score': desc_score,
            'distance_km': distance_km,
            'location_proximity_score': location_proximity_score,
            'combined_similarity_score': combined_score,
            'similarity_method': similarity_method,
            'location_data_available': location_available,
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(columns=[
            'project_id', 'similar_project_id', 'description_similarity_score',
            'distance_km', 'location_proximity_score', 'combined_similarity_score',
            'similarity_method', 'location_data_available'
        ])
    result = result.drop_duplicates(subset=['project_id', 'similar_project_id'], keep='first')
    result['description_similarity_score'] = result['description_similarity_score'].clip(0, 1)
    if 'location_proximity_score' in result.columns:
        result['location_proximity_score'] = pd.to_numeric(result['location_proximity_score'], errors='coerce').clip(0, 1)
    if 'combined_similarity_score' in result.columns:
        result['combined_similarity_score'] = pd.to_numeric(result['combined_similarity_score'], errors='coerce').clip(0, 1)
    return result[[
        'project_id', 'similar_project_id', 'description_similarity_score',
        'distance_km', 'location_proximity_score', 'combined_similarity_score',
        'similarity_method', 'location_data_available'
    ]]


def build_demo_similarity_pairs() -> pd.DataFrame:
    demo_locations = pd.read_csv(DEMO_DIR / 'demo_project_locations.csv').dropna(subset=['project_id', 'latitude', 'longitude']).copy()
    demo_locations = demo_locations.reset_index(drop=True)
    rows = []
    for idx, current in demo_locations.iterrows():
        others = demo_locations.drop(index=idx).copy()
        if others.empty:
            continue
        others = others.reset_index(drop=True)
        dists = others.apply(lambda r: haversine_km(float(current['latitude']), float(current['longitude']), float(r['latitude']), float(r['longitude'])), axis=1)
        nearest_idx = dists.idxmin()
        nearest = others.loc[nearest_idx]
        dist = float(dists.min())
        proximity = math.exp(-dist / 5.0)
        rows.append({
            'project_id': str(current['project_id']),
            'similar_project_id': str(nearest['project_id']),
            'description_similarity_score': round(0.65 + (1.0 - min(dist / 10.0, 1.0)) * 0.3, 6),
            'distance_km': dist,
            'location_proximity_score': proximity,
            'combined_similarity_score': round(0.6 * (0.65 + (1.0 - min(dist / 10.0, 1.0)) * 0.3) + 0.4 * proximity, 6),
            'similarity_method': 'description_plus_location',
            'location_data_available': True,
            'demo_only': True,
        })
    return pd.DataFrame(rows)


def main() -> None:
    project_location_features = build_project_location_features()
    project_location_features.to_csv(LOCATION_DIR / 'project_location_features.csv', index=False)

    similarity_location = build_similarity_with_location()
    similarity_location.to_csv(LOCATION_DIR / 'project_similarity_location.csv', index=False)

    demo_similarity = build_demo_similarity_pairs()
    demo_similarity.to_csv(DEMO_DIR / 'demo_project_similarity_location.csv', index=False)

    print(f'Wrote {len(project_location_features)} rows to project_location_features.csv')
    print(f'Wrote {len(similarity_location)} rows to project_similarity_location.csv')
    print(f'Wrote {len(demo_similarity)} rows to demo_project_similarity_location.csv')


if __name__ == '__main__':
    main()
