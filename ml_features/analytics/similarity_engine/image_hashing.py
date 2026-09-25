"""
analytics/similarity_engine/image_hashing.py
=============================================
Perceptual image hashing for MPLAD-Sentinel.

Detects duplicate project completion photos submitted across different work orders
using perceptual hashing (pHash, dHash, aHash) via Pillow + imagehash.

Since raw JPEG images are NOT present in the base dataset (ml_input/),
ALL functions include robust fallback behaviour:
  - If imagehash is not installed → returns ImageHashResult with is_available=False.
  - If image file does not exist   → returns None hash with a clear reason string.
  - If image is corrupt            → logs a warning and returns None.

Usage:
    from analytics.similarity_engine.image_hashing import ImageHasher
    hasher = ImageHasher()
    result = hasher.compare_images("path/to/img_a.jpg", "path/to/img_b.jpg")
    # result.is_duplicate → True/False  |  result.hamming_distance → int
"""
from __future__ import annotations
import os
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Hamming distance threshold: <= this value → consider images perceptually duplicate.
DUPLICATE_HAMMING_THRESHOLD: int = 5

# Try importing imagehash (optional dependency)
try:
    import imagehash
    from PIL import Image
    _IMAGEHASH_AVAILABLE = True
except ImportError:
    _IMAGEHASH_AVAILABLE = False
    logger.warning(
        "imagehash / Pillow not installed. Image hashing will run in STUB mode. "
        "Install with: pip install imagehash Pillow"
    )


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ImageHashResult:
    """Holds the result of comparing two images."""
    image_path_a:       Optional[str] = None
    image_path_b:       Optional[str] = None
    phash_a:            Optional[str] = None
    phash_b:            Optional[str] = None
    dhash_a:            Optional[str] = None
    dhash_b:            Optional[str] = None
    ahash_a:            Optional[str] = None
    ahash_b:            Optional[str] = None
    hamming_phash:      Optional[int] = None
    hamming_dhash:      Optional[int] = None
    hamming_ahash:      Optional[int] = None
    is_duplicate:       bool  = False
    confidence:         float = 0.0     # 0.0 (different) to 1.0 (identical)
    reason:             str   = ""
    is_available:       bool  = _IMAGEHASH_AVAILABLE


@dataclass
class ProjectImageSummary:
    """Summary of image hash status for a single project."""
    project_id:         str
    image_paths:        List[str]       = field(default_factory=list)
    image_hashes:       Dict[str, str]  = field(default_factory=dict)   # path → phash hex
    duplicate_pairs:    List[Tuple[str, str, int]] = field(default_factory=list)  # (a, b, hamming)
    has_images:         bool  = False
    image_hash_score:   float = 0.0     # 0.0 = unique, 1.0 = fully duplicated
    status:             str   = "NO_IMAGES"


# ── ImageHasher ───────────────────────────────────────────────────────────────

class ImageHasher:
    """
    Computes and compares perceptual hashes (pHash, dHash, aHash) for project images.

    Gracefully handles missing dependencies and missing image files.
    """

    def __init__(self, hamming_threshold: int = DUPLICATE_HAMMING_THRESHOLD) -> None:
        self.hamming_threshold = hamming_threshold
        self.is_available = _IMAGEHASH_AVAILABLE

    # ── Single image hashing ──────────────────────────────────────────────────

    def hash_image(self, image_path: str) -> Optional[Dict[str, str]]:
        """
        Compute pHash, dHash, and aHash for a single image file.

        Parameters
        ----------
        image_path : str
            Absolute or relative path to a JPEG/PNG image.

        Returns
        -------
        dict with keys: phash, dhash, ahash (all hex strings)
        or None if the file is missing / unreadable / imagehash unavailable.
        """
        if not self.is_available:
            logger.debug("imagehash not available; returning stub None for %s", image_path)
            return None
        if not os.path.isfile(image_path):
            logger.debug("Image file not found: %s", image_path)
            return None
        try:
            img = Image.open(image_path).convert("RGB")
            return {
                "phash": str(imagehash.phash(img)),
                "dhash": str(imagehash.dhash(img)),
                "ahash": str(imagehash.average_hash(img)),
            }
        except Exception as exc:
            logger.warning("Could not hash image %s: %s", image_path, exc)
            return None

    # ── Pair comparison ───────────────────────────────────────────────────────

    def compare_images(
        self, image_path_a: str, image_path_b: str
    ) -> ImageHashResult:
        """
        Compare two project completion images using perceptual hashing.

        Parameters
        ----------
        image_path_a, image_path_b : str
            Paths to the two images.

        Returns
        -------
        ImageHashResult with is_duplicate=True if Hamming distance <= threshold
        across at least 2 of the 3 hash algorithms.
        """
        result = ImageHashResult(
            image_path_a=image_path_a,
            image_path_b=image_path_b,
            is_available=self.is_available,
        )

        if not self.is_available:
            result.reason = "imagehash_not_installed"
            return result

        hashes_a = self.hash_image(image_path_a)
        hashes_b = self.hash_image(image_path_b)

        if hashes_a is None:
            result.reason = f"image_a_unreadable: {image_path_a}"
            return result
        if hashes_b is None:
            result.reason = f"image_b_unreadable: {image_path_b}"
            return result

        # Store hash strings
        result.phash_a = hashes_a["phash"];  result.phash_b = hashes_b["phash"]
        result.dhash_a = hashes_a["dhash"];  result.dhash_b = hashes_b["dhash"]
        result.ahash_a = hashes_a["ahash"];  result.ahash_b = hashes_b["ahash"]

        # Hamming distances
        result.hamming_phash = int(imagehash.hex_to_hash(hashes_a["phash"]) - imagehash.hex_to_hash(hashes_b["phash"]))
        result.hamming_dhash = int(imagehash.hex_to_hash(hashes_a["dhash"]) - imagehash.hex_to_hash(hashes_b["dhash"]))
        result.hamming_ahash = int(imagehash.hex_to_hash(hashes_a["ahash"]) - imagehash.hex_to_hash(hashes_b["ahash"]))

        # Majority vote: duplicate if >=2 of 3 hashes are within threshold
        votes = sum([
            result.hamming_phash <= self.hamming_threshold,
            result.hamming_dhash <= self.hamming_threshold,
            result.hamming_ahash <= self.hamming_threshold,
        ])
        result.is_duplicate = votes >= 2

        # Confidence: inverse of normalised average hamming distance (0-64 range for 64-bit hash)
        avg_hamming = (result.hamming_phash + result.hamming_dhash + result.hamming_ahash) / 3.0
        result.confidence = round(max(0.0, 1.0 - avg_hamming / 64.0), 4)

        result.reason = (
            f"phash={result.hamming_phash}, dhash={result.hamming_dhash}, "
            f"ahash={result.hamming_ahash}, votes={votes}/3"
        )
        return result

    # ── Project-level image analysis ──────────────────────────────────────────

    def analyse_project_images(
        self, project_id: str, image_paths: List[str]
    ) -> ProjectImageSummary:
        """
        Hash all images for a project and detect intra-project duplicates.

        Parameters
        ----------
        project_id : str
        image_paths : list of str

        Returns
        -------
        ProjectImageSummary
        """
        summary = ProjectImageSummary(project_id=project_id, image_paths=image_paths)

        if not image_paths:
            summary.status = "NO_IMAGES"
            return summary

        if not self.is_available:
            summary.status = "HASHING_UNAVAILABLE"
            return summary

        # Hash each image
        hashes: Dict[str, str] = {}
        for path in image_paths:
            h = self.hash_image(path)
            if h:
                hashes[path] = h["phash"]

        summary.image_hashes = hashes
        summary.has_images = len(hashes) > 0

        # Detect intra-project duplicate images
        paths = list(hashes.keys())
        dup_pairs = []
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                result = self.compare_images(paths[i], paths[j])
                if result.is_duplicate:
                    dup_pairs.append((paths[i], paths[j], result.hamming_phash or 0))

        summary.duplicate_pairs = dup_pairs
        if dup_pairs:
            summary.image_hash_score = min(1.0, len(dup_pairs) / max(1, len(paths)))
            summary.status = "DUPLICATES_FOUND"
        else:
            summary.image_hash_score = 0.0
            summary.status = "UNIQUE"

        return summary

    # ── Batch cross-project comparison ────────────────────────────────────────

    def find_cross_project_image_duplicates(
        self, project_image_map: Dict[str, List[str]]
    ) -> List[Dict]:
        """
        Find projects that submitted identical completion photos across different works.

        Parameters
        ----------
        project_image_map : dict
            {project_id: [list of image file paths]}

        Returns
        -------
        list of dicts with keys:
            project_id_a, project_id_b, image_a, image_b,
            hamming_phash, is_duplicate, confidence
        """
        if not self.is_available:
            logger.warning("imagehash not available. Cross-project image check skipped.")
            return []

        # Build flat (project_id, path, phash) index
        index: List[Tuple[str, str, str]] = []
        for pid, paths in project_image_map.items():
            for path in paths:
                h = self.hash_image(path)
                if h:
                    index.append((pid, path, h["phash"]))

        logger.info("Image index built: %d images across %d projects.", len(index), len(project_image_map))

        results = []
        for i in range(len(index)):
            for j in range(i + 1, len(index)):
                pid_a, path_a, hash_a = index[i]
                pid_b, path_b, hash_b = index[j]
                if pid_a == pid_b:
                    continue  # Skip intra-project
                ham = int(imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b))
                if ham <= self.hamming_threshold:
                    confidence = round(max(0.0, 1.0 - ham / 64.0), 4)
                    results.append({
                        "project_id_a":   pid_a,
                        "project_id_b":   pid_b,
                        "image_a":        path_a,
                        "image_b":        path_b,
                        "hamming_phash":  ham,
                        "is_duplicate":   True,
                        "confidence":     confidence,
                    })

        logger.info("Cross-project image duplicates found: %d pairs.", len(results))
        return results

    # ── Stub / Mock for testing without real images ───────────────────────────

    @staticmethod
    def create_mock_hash_result(
        hamming_distance: int = 3,
        is_duplicate: bool = True,
    ) -> ImageHashResult:
        """
        Create a mock ImageHashResult for unit testing without real images.

        Parameters
        ----------
        hamming_distance : int
            Simulated Hamming distance.
        is_duplicate : bool
            Whether to flag as duplicate.

        Returns
        -------
        ImageHashResult
        """
        return ImageHashResult(
            image_path_a="mock_image_a.jpg",
            image_path_b="mock_image_b.jpg",
            phash_a="aabbccddeeff0011",
            phash_b="aabbccddeeff0014",
            dhash_a="1122334455667788",
            dhash_b="1122334455667789",
            ahash_a="ffeeddccbbaa9988",
            ahash_b="ffeeddccbbaa9985",
            hamming_phash=hamming_distance,
            hamming_dhash=hamming_distance,
            hamming_ahash=hamming_distance,
            is_duplicate=is_duplicate,
            confidence=round(max(0.0, 1.0 - hamming_distance / 64.0), 4),
            reason=f"mock result: hamming={hamming_distance}",
            is_available=True,
        )
