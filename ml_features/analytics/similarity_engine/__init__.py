"""
MPLAD-Sentinel: Similarity & Duplicate Detection Engine
=======================================================
Detects verbatim copy-pasting, budget discrepancies on duplicates,
location-aware risk, and image reuse across MPLADS work proposals.

Sub-modules:
  - text_similarity_tfidf   : TF-IDF cosine similarity + generic template filter
  - location_proximity      : Geographic risk classification (constituency/state)
  - cost_similarity         : Budget ratio & peer deviation on similar pairs
  - image_hashing           : Perceptual hashing (pHash/dHash) for photo reuse
"""
