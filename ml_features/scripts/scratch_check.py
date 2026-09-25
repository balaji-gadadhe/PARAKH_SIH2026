import pandas as pd, re
df = pd.read_csv("ml_input/project_similarity_data.csv")
df["mp_name"] = df["project_id"].str.split("|").str[1]
LOCATION_MARKERS = r"(ward|gp |gram panchayat|sector|nagar|village|phase|plot|block|mohalla|tola|pada|khurd|kalan|chowk|marg|road no)"
df["has_loc"] = df["clean_description"].str.lower().str.contains(LOCATION_MARKERS, regex=True, na=False)
print("Has location markers:", df["has_loc"].value_counts().to_dict())
print("\nSample WITH markers:")
for d in df[df["has_loc"]]["clean_description"].head(5):
    print(" -", d[:120])
print("\nSample WITHOUT markers:")
for d in df[~df["has_loc"]]["clean_description"].head(5):
    print(" -", d[:80])
