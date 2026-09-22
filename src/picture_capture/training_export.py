from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import json
import shutil
import zipfile

from PIL import Image, ImageOps

from .formats import pdic_path, read_pdic, read_ppp
from .image_utils import normalize_page_rgb
from .models import AppSettings
from .processing import column_index, derive_geometry
from .project_storage import (
    headword_filter_rules_path, ocr_cache_root, ppp_read_path_for_image,
    profile_path, replace_rules_path, settings_path,
)


TRAINING_EXPORT_FORMAT = "picture-capture-training-v1"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _copy_if_exists(source: Path, target: Path) -> str | None:
    if not source.exists() or not source.is_file():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target.as_posix()


def _candidate_ground_truth_link(candidate: dict[str, Any], ground_truth: list[dict[str, Any]], line_height: int) -> dict[str, Any]:
    """Link one OCR candidate to the nearest final saved line in the same column.

    The saved PDIC is the exported ground truth. Candidate linkage is only
    provenance/diagnostic metadata; it never changes the final labels.
    """
    try:
        column = int(candidate.get("column", -1))
        y = int(candidate.get("source_y", candidate.get("refined_source_y", -999999)))
    except Exception:
        return {"ground_truth_selected": False, "nearest_ground_truth_y": None, "ground_truth_y_delta": None}
    same_col = [row for row in ground_truth if int(row.get("column", -2)) == column]
    if not same_col:
        return {"ground_truth_selected": False, "nearest_ground_truth_y": None, "ground_truth_y_delta": None}
    nearest = min(same_col, key=lambda row: abs(int(row["y"]) - y))
    delta = abs(int(nearest["y"]) - y)
    tolerance = max(4, round(max(1, line_height) * 0.60))
    return {
        "ground_truth_selected": bool(delta <= tolerance),
        "nearest_ground_truth_y": int(nearest["y"]),
        "ground_truth_y_delta": int(delta),
    }


def export_training_page(
    page: Path,
    project_root: Path,
    settings: AppSettings,
    staging_root: Path,
    page_index: int,
) -> dict[str, Any]:
    """Export one annotated page into a training-package staging directory."""
    page = Path(page)
    project_root = Path(project_root)
    staging_root = Path(staging_root)

    images_dir = staging_root / "images"
    annotations_dir = staging_root / "annotations"
    artifacts_dir = staging_root / "artifacts"
    ocr_dir = staging_root / "ocr"
    images_dir.mkdir(parents=True, exist_ok=True)
    annotations_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    ocr_dir.mkdir(parents=True, exist_ok=True)

    image_target = images_dir / page.name
    shutil.copy2(page, image_target)

    with Image.open(page) as opened:
        image = normalize_page_rgb(opened)
        width, height = image.size
        geometry = derive_geometry(image, settings)

    pdic = pdic_path(page)
    entries = read_pdic(pdic)
    ground_truth: list[dict[str, Any]] = []
    for order, entry in enumerate(entries, 1):
        col = column_index(int(entry.x), geometry, int(entry.y)) if geometry.column_starts else 0
        ground_truth.append({
            "order": order,
            "word": entry.word,
            "x": int(entry.x),
            "y": int(entry.y),
            "column": int(col),
            "label_source": "saved_pdic",
        })

    pdic_rel = None
    if pdic.exists():
        target = artifacts_dir / pdic.name
        shutil.copy2(pdic, target)
        pdic_rel = target.relative_to(staging_root).as_posix()

    ppp = ppp_read_path_for_image(page)
    polygons = read_ppp(ppp) if ppp.exists() else []
    ppp_rel = None
    if ppp.exists():
        target = artifacts_dir / ppp.name
        shutil.copy2(ppp, target)
        ppp_rel = target.relative_to(staging_root).as_posix()

    cache_source = ocr_cache_root(project_root) / f"{page.stem}.json"
    cache = _read_json(cache_source) if cache_source.exists() else {}
    ocr_files: list[str] = []
    ocr_names = [
        f"{page.stem}.json",
        f"{page.stem}_manual_selection.json",
        f"{page.stem}_ocr_diagnostics.txt",
        f"{page.stem}_ocr_comparison.txt",
        f"{page.stem}_issues.tsv",
        f"{page.stem}_ocr_engines.tsv",
        f"{page.stem}_fusion.tsv",
    ]
    ocr_source_dir = ocr_cache_root(project_root)
    for name in ocr_names:
        source = ocr_source_dir / name
        if source.exists():
            target = ocr_dir / name
            shutil.copy2(source, target)
            ocr_files.append(target.relative_to(staging_root).as_posix())

    manual_selection = _read_json(ocr_source_dir / f"{page.stem}_manual_selection.json")
    candidates: list[dict[str, Any]] = []
    for raw in list(cache.get("review_candidates") or []):
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        row.update(_candidate_ground_truth_link(row, ground_truth, settings.character_height))
        candidates.append(row)

    annotation = {
        "format": TRAINING_EXPORT_FORMAT,
        "page_index": int(page_index),
        "page": page.name,
        "image": {
            "file": image_target.relative_to(staging_root).as_posix(),
            "width": int(width),
            "height": int(height),
            "mode": "RGB",
        },
        "annotation_status": "human_verified_saved_pdic",
        "ground_truth_lines": ground_truth,
        "illustration_polygons": [
            {"label": region.label, "points": [[int(x), int(y)] for x, y in region.points]}
            for region in polygons
        ],
        "layout": {
            "columns": int(settings.columns),
            "header_y": int(settings.start_y),
            "column_width": int(settings.column_width),
            "gutter": int(settings.gutter),
            "line_height": int(settings.character_height),
            "row_padding": int(settings.row_padding),
            "derived_column_starts": [int(v) for v in geometry.column_starts],
            "derived_column_widths": [int(v) for v in geometry.column_widths],
            "derived_top": int(geometry.top),
            "derived_bottom": int(geometry.bottom),
        },
        "artifacts": {
            "pdic": pdic_rel,
            "ppp": ppp_rel,
        },
        "ocr_trace": {
            "cache_available": bool(cache),
            "ocr_files": ocr_files,
            "manual_override_count": int(cache.get("manual_override_count") or 0),
            "page_quality": cache.get("page_quality") or {},
            "manual_selection": manual_selection,
            "candidates": candidates,
        },
    }

    annotation_path = annotations_dir / f"{page.stem}.json"
    annotation_path.write_text(json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "page": page.name,
        "annotation": annotation_path.relative_to(staging_root).as_posix(),
        "image": image_target.relative_to(staging_root).as_posix(),
        "ground_truth_count": len(ground_truth),
        "polygon_count": len(polygons),
        "ocr_candidate_count": len(candidates),
        "ocr_cache_available": bool(cache),
    }


def copy_project_context(project_root: Path, staging_root: Path) -> list[str]:
    """Copy compact project-level context useful for reproducible training."""
    project_root = Path(project_root)
    staging_root = Path(staging_root)
    target_root = staging_root / "project_context"
    copied: list[str] = []
    sources = [
        (settings_path(project_root), "picture_capture_settings.json"),
        (project_root / "wordslist.txt", "wordslist.txt"),
        (profile_path(project_root), "dictionary_profile.json"),
        (replace_rules_path(project_root), "_Replace.txt"),
        (headword_filter_rules_path(project_root), "headword_filter_rules.txt"),
    ]
    for source, name in sources:
        if source.exists() and source.is_file():
            target = target_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target.relative_to(staging_root).as_posix())
    return copied


def write_training_manifest(
    staging_root: Path,
    *,
    project_name: str,
    settings: AppSettings,
    pages: list[dict[str, Any]],
    context_files: list[str],
    software_version: str,
) -> Path:
    manifest = {
        "format": TRAINING_EXPORT_FORMAT,
        "software_version": software_version,
        "project_name": project_name,
        "annotation_contract": {
            "ground_truth": "saved .pdic lines confirmed by the user at export time",
            "negative_candidates": "OCR review candidates not matched to a saved ground-truth line",
            "coordinates": "original-image pixels",
            "page_split_rule": "future train/validation/test splits should be performed by dictionary, not adjacent pages",
        },
        "settings": asdict(settings),
        "page_count": len(pages),
        "ground_truth_line_count": sum(int(p.get("ground_truth_count", 0)) for p in pages),
        "page_records": pages,
        "project_context_files": context_files,
    }
    path = Path(staging_root) / "dataset_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def make_training_zip(staging_root: Path, zip_path: Path) -> Path:
    """Create a deterministic-ish zip from the staging directory."""
    staging_root = Path(staging_root)
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(staging_root.rglob("*"), key=lambda p: p.as_posix().casefold()):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(staging_root).as_posix())
    return zip_path
