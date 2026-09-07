"""
Curator — local image quality analysis, enhancement, print-size export,
and procedural interior-mockup generation for Forge image assets.

Everything here is pure local image processing on top of Pillow (+
numpy for the analysis heuristics). No network calls, no third-party
API, no connector approval needed — this only ever reads/writes files
already on this machine.

Three jobs, matching the request this was built for:

1. Quality enhancement for different formats
   - enhance_image() / enhance_image_asset(): auto-contrast, mild
     denoise, unsharp-mask sharpening, and a clean resize/re-encode.
   - export_print_format() / export_print_format_asset(): crop or pad
     to the exact pixel dimensions a specific Etsy print size needs at
     a target DPI (default 300), and flags when the source image is
     too small to hit that DPI honestly instead of silently upscaling
     and calling it "best quality" (see UPSCALE_NEEDED_HINT below).

2. Analysis and removal of unnecessary details
   - analyze_image() / analyze_image_asset(): sharpness/noise/contrast
     stats, DPI fit against common print sizes, and a border-band
     scanner that looks for a sharp brightness "step" near any edge —
     the same kind of boundary a scanned institutional citation
     banner, watermark strip, or scan-bed margin produces — and
     suggests a crop box to remove it. It never crops anything by
     itself; a human (or --crop auto in enhance_image_asset.py) has to
     apply the suggestion.

3. Interior placement mockups
   - generate_interior_mockup_image() / generate_interior_mockup():
     composites the art into a procedurally-drawn framed-poster-on-a-
     wall scene (gradient wall, soft drop shadow, mat + frame) so a
     buyer gets an "in a room" preview without needing a photographed
     room template. This is clearly a rendered/stylized scene, not a
     photograph — good enough for a listing's secondary photos, not a
     substitute for a real room photo if you have one.

Every image this module PRODUCES from an existing image_asset (enhanced
masters, print-size exports) is recorded as its OWN new image_asset via
forge_image_kernel.record_image_asset(), linked back to the source via
derived_from_image_asset_id. It does not inherit the source asset's
Sentinel Visual QA approval — a fresh Visual QA is required before a
derived asset can be marked approved_for_product, same as any other
image source in this repo. Interior mockups are recorded separately in
mockup_assets.json since they are marketing collateral, not a
print-ready master file, and are not gated by Ledger/Sentinel.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from forge_image_kernel import (
    IMAGE_ASSETS_FILE,
    load_json,
    next_id,
    record_image_asset,
    save_json,
)
from image_generation_budget import find_by_id


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"
GENERATED_ASSETS_DIR = STATE / "generated_assets"

IMAGE_ANALYSIS_REPORTS_FILE = STATE / "image_analysis_reports.json"
MOCKUP_ASSETS_FILE = STATE / "mockup_assets.json"

UPSCALE_NEEDED_HINT = (
    "Source resolution is below the target print DPI for this format. Pillow's "
    "resize can't invent real detail — either use a higher-resolution source, or "
    "run run_qwen_edit_style_transfer.py with --lora-adapter Upscaler on this "
    "asset first (community HF Space; still needs fresh Visual QA afterward)."
)

# (width_inches, height_inches) at whatever orientation is listed; exporters
# match this to the source image's own orientation automatically.
PRINT_FORMATS: Dict[str, Tuple[float, float]] = {
    "4x6": (4, 6),
    "5x7": (5, 7),
    "8x10": (8, 10),
    "11x14": (11, 14),
    "16x20": (16, 20),
    "18x24": (18, 24),
    "24x36": (24, 36),
    "12x12": (12, 12),
    "16x16": (16, 16),
    "a4": (8.27, 11.69),
    "a3": (11.69, 16.54),
}

RECOMMENDED_DPI = 300
MINIMUM_DPI = 150

ROOM_STYLES: Dict[str, Dict[str, Any]] = {
    "warm_neutral": {"wall_top": (240, 233, 223), "wall_bottom": (214, 202, 184), "floor": (163, 130, 97), "floor_highlight": (185, 152, 118)},
    "cool_gallery": {"wall_top": (236, 237, 239), "wall_bottom": (205, 208, 213), "floor": (120, 111, 103), "floor_highlight": (145, 136, 128)},
    "sage_green": {"wall_top": (214, 223, 206), "wall_bottom": (177, 191, 163), "floor": (140, 111, 79), "floor_highlight": (163, 132, 97)},
    "charcoal_modern": {"wall_top": (62, 62, 66), "wall_bottom": (36, 36, 40), "floor": (24, 24, 26), "floor_highlight": (44, 44, 48)},
    "blush_studio": {"wall_top": (243, 227, 224), "wall_bottom": (222, 197, 194), "floor": (196, 176, 165), "floor_highlight": (214, 196, 186)},
}

FRAME_STYLES: Dict[str, Optional[Dict[str, Any]]] = {
    "black": {"frame": (22, 22, 22), "mat": (250, 248, 244)},
    "white": {"frame": (247, 247, 245), "mat": (255, 255, 255)},
    "natural_wood": {"frame": (172, 132, 90), "mat": (250, 248, 244)},
    "walnut": {"frame": (81, 54, 36), "mat": (238, 231, 221)},
    "none": None,  # unframed print, no mat — just the art with a thin edge shadow
}


class CuratorError(RuntimeError):
    pass


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat
    except ImportError as exc:
        raise CuratorError(
            "Pillow is not installed. Run: pip install Pillow (see requirements.txt)."
        ) from exc
    return Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat


def _numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise CuratorError(
            "numpy is not installed. Run: pip install numpy (see requirements.txt)."
        ) from exc
    return np


def _get_image_asset(image_asset_id: str) -> Optional[Dict[str, Any]]:
    assets = load_json(IMAGE_ASSETS_FILE, [])
    return find_by_id(assets, image_asset_id)


def _safe_stem(image_asset_id: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(image_asset_id))
    return "_".join(part for part in cleaned.split("_") if part) or "curator_image"


# ---------------------------------------------------------------------------
# 1. Analysis (sharpness/noise/DPI-fit) + border-band ("unnecessary detail")
#    crop suggestion
# ---------------------------------------------------------------------------

def _find_border_cut(profile, search_frac: float = 0.25, min_prominence_ratio: float = 0.12, from_end: bool = False) -> Optional[Dict[str, Any]]:
    """
    Scan the outer `search_frac` of a 1-D brightness profile (row means
    or column means) for the single biggest brightness "step" — the
    boundary a solid-color caption/watermark band or scan-bed margin
    makes against real artwork. Returns None if nothing prominent
    enough is found (meaning: don't suggest a crop on this side).
    """
    np = _numpy()
    n = len(profile)
    search_len = max(2, int(n * search_frac))
    window = profile[-search_len:] if from_end else profile[:search_len]

    if len(window) < 2:
        return None

    overall_range = float(profile.max() - profile.min()) or 1.0
    diffs = np.abs(np.diff(window))
    idx = int(np.argmax(diffs))
    prominence = float(diffs[idx]) / overall_range

    if prominence < min_prominence_ratio:
        return None

    if from_end:
        cut_from_end = len(window) - (idx + 1)
        return {"cut_px_from_edge": cut_from_end, "prominence": round(prominence, 3)}

    return {"cut_px_from_edge": idx + 1, "prominence": round(prominence, 3)}


def suggest_crop_box(file_path: str, search_frac: float = 0.25, min_prominence_ratio: float = 0.12) -> Dict[str, Any]:
    """
    Suggest a crop box (left, top, right, bottom) that trims any edge
    where a prominent brightness step was found near the border. Every
    side defaults to "no cut" (full extent) unless a confident step was
    detected — this is a suggestion for a human to confirm, not an
    automatic decision.
    """
    Image, *_ = _pil()
    np = _numpy()

    img = Image.open(file_path)
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    height, width = gray.shape

    row_means = gray.mean(axis=1)
    col_means = gray.mean(axis=0)

    top = _find_border_cut(row_means, search_frac, min_prominence_ratio, from_end=False)
    bottom = _find_border_cut(row_means, search_frac, min_prominence_ratio, from_end=True)
    left = _find_border_cut(col_means, search_frac, min_prominence_ratio, from_end=False)
    right = _find_border_cut(col_means, search_frac, min_prominence_ratio, from_end=True)

    box_top = top["cut_px_from_edge"] if top else 0
    box_bottom = height - (bottom["cut_px_from_edge"] if bottom else 0)
    box_left = left["cut_px_from_edge"] if left else 0
    box_right = width - (right["cut_px_from_edge"] if right else 0)

    return {
        "width": width,
        "height": height,
        "crop_box": [box_left, box_top, box_right, box_bottom],
        "sides_flagged": {
            "top": top,
            "bottom": bottom,
            "left": left,
            "right": right,
        },
        "any_side_flagged": any([top, bottom, left, right]),
    }


def _dpi_fit_report(width: int, height: int, formats: List[str]) -> Dict[str, Any]:
    report = {}
    for name in formats:
        if name not in PRINT_FORMATS:
            continue
        w_in, h_in = PRINT_FORMATS[name]

        # Match target orientation to the source image's own orientation.
        if width >= height and w_in < h_in:
            w_in, h_in = h_in, w_in
        elif height > width and h_in < w_in:
            w_in, h_in = h_in, w_in

        effective_dpi = round(min(width / w_in, height / h_in), 1)
        report[name] = {
            "target_inches": f"{w_in:g}x{h_in:g}",
            "effective_dpi": effective_dpi,
            "meets_recommended_dpi": effective_dpi >= RECOMMENDED_DPI,
            "meets_minimum_dpi": effective_dpi >= MINIMUM_DPI,
        }
    return report


def analyze_image(file_path: str, print_formats: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Pure read-only analysis: quality stats + print-size DPI fit + a
    border-band crop suggestion. Never writes anything to disk.
    """
    Image, _, _, ImageFilter, _, ImageStat = _pil()
    np = _numpy()

    img = Image.open(file_path)
    img.load()
    width, height = img.size
    file_size_bytes = Path(file_path).stat().st_size

    gray = img.convert("L")
    gray_arr = np.asarray(gray, dtype=np.float32)

    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_arr = np.asarray(edges, dtype=np.float32)
    sharpness_score = round(float(edge_arr.std()), 2)

    blurred = gray.filter(ImageFilter.GaussianBlur(radius=2))
    blurred_arr = np.asarray(blurred, dtype=np.float32)
    noise_score = round(float((gray_arr - blurred_arr).std()), 2)

    stat = ImageStat.Stat(gray)
    mean_brightness = round(stat.mean[0], 1)
    contrast_stddev = round(stat.stddev[0], 1)

    crop_suggestion = suggest_crop_box(file_path)

    quality_warnings = []
    if sharpness_score < 8:
        quality_warnings.append("low_sharpness_image_may_look_soft_at_print_size")
    if noise_score > 12:
        quality_warnings.append("elevated_noise_consider_denoise")
    if contrast_stddev < 25:
        quality_warnings.append("low_contrast_consider_auto_contrast")

    return {
        "file_path": str(file_path),
        "format": img.format,
        "mode": img.mode,
        "width": width,
        "height": height,
        "megapixels": round(width * height / 1_000_000, 2),
        "aspect_ratio": round(width / height, 3) if height else None,
        "file_size_bytes": file_size_bytes,
        "sharpness_score": sharpness_score,
        "noise_score": noise_score,
        "mean_brightness": mean_brightness,
        "contrast_stddev": contrast_stddev,
        "quality_warnings": quality_warnings,
        "dpi_fit": _dpi_fit_report(width, height, print_formats or list(PRINT_FORMATS.keys())),
        "crop_suggestion": crop_suggestion,
    }


def analyze_image_asset(image_asset_id: str, print_formats: Optional[List[str]] = None) -> Dict[str, Any]:
    reports = load_json(IMAGE_ANALYSIS_REPORTS_FILE, [])
    asset = _get_image_asset(image_asset_id)

    if not asset:
        report = {
            "id": next_id("IMGANALYSIS", reports),
            "type": "image_analysis_report",
            "status": "blocked_missing_image_asset",
            "image_asset_id": image_asset_id,
            "issues": ["missing_image_asset"],
            "created_at": now_stamp(),
        }
        reports.append(report)
        save_json(IMAGE_ANALYSIS_REPORTS_FILE, reports)
        return report

    file_path = Path(asset.get("file_path", ""))

    if not file_path.exists():
        report = {
            "id": next_id("IMGANALYSIS", reports),
            "type": "image_analysis_report",
            "status": "blocked_file_missing",
            "image_asset_id": image_asset_id,
            "file_path": str(file_path),
            "issues": ["file_missing"],
            "created_at": now_stamp(),
        }
        reports.append(report)
        save_json(IMAGE_ANALYSIS_REPORTS_FILE, reports)
        return report

    analysis = analyze_image(str(file_path), print_formats=print_formats)

    report = {
        "id": next_id("IMGANALYSIS", reports),
        "type": "image_analysis_report",
        "status": "pass" if not analysis["quality_warnings"] else "pass_with_warnings",
        "image_asset_id": image_asset_id,
        "design_package_id": asset.get("design_package_id"),
        "issues": [],
        **analysis,
        "created_at": now_stamp(),
    }

    reports.append(report)
    save_json(IMAGE_ANALYSIS_REPORTS_FILE, reports)

    assets = load_json(IMAGE_ASSETS_FILE, [])
    for item in assets:
        if item.get("id") == image_asset_id:
            item["image_analysis_report"] = report["id"]
            item["image_analysis_status"] = report["status"]
            break
    save_json(IMAGE_ASSETS_FILE, assets)

    return report


# ---------------------------------------------------------------------------
# 2. Enhancement (quality improvement)
# ---------------------------------------------------------------------------

def enhance_image(
    file_path: str,
    output_path: str,
    crop_box: Optional[Tuple[int, int, int, int]] = None,
    auto_contrast: bool = True,
    sharpen: bool = True,
    denoise: bool = False,
    target_long_edge_px: Optional[int] = None,
    output_format: Optional[str] = None,
    quality: int = 95,
) -> Dict[str, Any]:
    Image, _, _, ImageFilter, ImageOps, _ = _pil()

    img = Image.open(file_path)
    img = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img

    if crop_box:
        img = img.crop(tuple(crop_box))

    if denoise:
        img = img.filter(ImageFilter.MedianFilter(size=3))

    if auto_contrast:
        rgb_for_contrast = img.convert("RGB")
        adjusted = ImageOps.autocontrast(rgb_for_contrast, cutoff=1)
        if img.mode == "RGBA":
            adjusted.putalpha(img.getchannel("A"))
            img = adjusted
        else:
            img = adjusted

    if sharpen:
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))

    if target_long_edge_px and max(img.size) != target_long_edge_px:
        scale = target_long_edge_px / max(img.size)
        new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fmt_key = (output_format or out_path.suffix.lstrip(".") or "jpg").lower()
    pil_format = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}.get(fmt_key, "JPEG")

    if pil_format == "JPEG":
        img = img.convert("RGB")
        img.save(out_path, pil_format, quality=quality, optimize=True, progressive=True)
    elif pil_format == "WEBP":
        img.save(out_path, pil_format, quality=quality, method=6)
    else:
        img.save(out_path, pil_format, optimize=True)

    return {"file_path": str(out_path), "width": img.width, "height": img.height, "format": pil_format}


def enhance_image_asset(
    image_asset_id: str,
    crop_mode: str = "none",
    crop_box: Optional[Tuple[int, int, int, int]] = None,
    auto_contrast: bool = True,
    sharpen: bool = True,
    denoise: bool = False,
    target_long_edge_px: Optional[int] = None,
    output_format: Optional[str] = None,
    quality: int = 95,
    notes: str = "",
) -> Dict[str, Any]:
    """
    crop_mode: "none" (no crop), "auto" (use suggest_crop_box's result),
    or "explicit" (use the caller-supplied crop_box).
    """
    asset = _get_image_asset(image_asset_id)

    if not asset:
        return {
            "id": None,
            "status": "blocked_missing_image_asset",
            "image_asset_id": image_asset_id,
            "issues": ["missing_image_asset"],
        }

    file_path = Path(asset.get("file_path", ""))
    if not file_path.exists():
        return {
            "id": None,
            "status": "blocked_file_missing",
            "image_asset_id": image_asset_id,
            "issues": ["file_missing"],
        }

    resolved_crop_box = None
    crop_notes = ""

    if crop_mode == "auto":
        suggestion = suggest_crop_box(str(file_path))
        if suggestion["any_side_flagged"]:
            resolved_crop_box = tuple(suggestion["crop_box"])
            crop_notes = f" Auto-crop applied from suggest_crop_box(): {suggestion['sides_flagged']}."
        else:
            crop_notes = " Auto-crop requested but no confident border step was found; no crop applied."
    elif crop_mode == "explicit":
        if not crop_box:
            return {
                "id": None,
                "status": "blocked_missing_crop_box",
                "image_asset_id": image_asset_id,
                "issues": ["crop_mode_explicit_requires_crop_box"],
            }
        resolved_crop_box = tuple(crop_box)

    GENERATED_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fmt_ext = (output_format or file_path.suffix.lstrip(".") or "jpg").lower()
    out_path = GENERATED_ASSETS_DIR / f"{_safe_stem(image_asset_id)}_enhanced_{timestamp}.{fmt_ext}"

    result = enhance_image(
        file_path=str(file_path),
        output_path=str(out_path),
        crop_box=resolved_crop_box,
        auto_contrast=auto_contrast,
        sharpen=sharpen,
        denoise=denoise,
        target_long_edge_px=target_long_edge_px,
        output_format=output_format,
        quality=quality,
    )

    ops = []
    if resolved_crop_box:
        ops.append(f"cropped_to={list(resolved_crop_box)}")
    if auto_contrast:
        ops.append("auto_contrast")
    if sharpen:
        ops.append("unsharp_mask")
    if denoise:
        ops.append("median_denoise")
    if target_long_edge_px:
        ops.append(f"resized_long_edge={target_long_edge_px}px")

    new_asset = record_image_asset(
        image_request_id=asset.get("image_request_id"),
        file_path=result["file_path"],
        provider_id="curator_local_enhancement",
        generation_notes=(
            f"Curator-enhanced derivative of {image_asset_id}. Operations: {', '.join(ops) or 'none'}."
            f"{crop_notes} {notes}".strip()
        ),
    )

    assets = load_json(IMAGE_ASSETS_FILE, [])
    for item in assets:
        if item.get("id") == new_asset["id"]:
            item["derived_from_image_asset_id"] = image_asset_id
            item["derivation_type"] = "enhancement"
            item["derivation_operations"] = ops
            break
    save_json(IMAGE_ASSETS_FILE, assets)

    new_asset["derived_from_image_asset_id"] = image_asset_id
    new_asset["derivation_operations"] = ops
    new_asset["output_width"] = result["width"]
    new_asset["output_height"] = result["height"]
    return new_asset


# ---------------------------------------------------------------------------
# Print-size export
# ---------------------------------------------------------------------------

def export_print_format(
    file_path: str,
    output_path: str,
    format_name: str,
    dpi: int = RECOMMENDED_DPI,
    fill_mode: str = "crop",
    mat_color: Tuple[int, int, int] = (255, 255, 255),
) -> Dict[str, Any]:
    if format_name not in PRINT_FORMATS:
        raise CuratorError(f"Unknown print format '{format_name}'. Known formats: {', '.join(PRINT_FORMATS)}.")

    Image, *_ = _pil()

    w_in, h_in = PRINT_FORMATS[format_name]
    img = Image.open(file_path).convert("RGB")
    src_w, src_h = img.size

    if src_w >= src_h and w_in < h_in:
        w_in, h_in = h_in, w_in
    elif src_h > src_w and h_in < w_in:
        w_in, h_in = h_in, w_in

    target_w = max(1, round(w_in * dpi))
    target_h = max(1, round(h_in * dpi))

    needs_upscale = src_w < target_w or src_h < target_h

    if fill_mode == "pad":
        scale = min(target_w / src_w, target_h / src_h)
        new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGB", (target_w, target_h), mat_color)
        canvas.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2))
        final = canvas
    else:
        target_ratio = target_w / target_h
        src_ratio = src_w / src_h

        if src_ratio > target_ratio:
            new_w = round(src_h * target_ratio)
            left = max(0, (src_w - new_w) // 2)
            img = img.crop((left, 0, left + new_w, src_h))
        else:
            new_h = round(src_w / target_ratio)
            top = max(0, (src_h - new_h) // 2)
            img = img.crop((0, top, src_w, top + new_h))

        final = img.resize((target_w, target_h), Image.LANCZOS)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(out_path, "JPEG", quality=95, optimize=True, progressive=True)

    return {
        "file_path": str(out_path),
        "width": target_w,
        "height": target_h,
        "format_name": format_name,
        "dpi": dpi,
        "fill_mode": fill_mode,
        "needs_upscale": needs_upscale,
    }


def export_print_format_assets(
    image_asset_id: str,
    format_names: List[str],
    dpi: int = RECOMMENDED_DPI,
    fill_mode: str = "crop",
    mat_color: Tuple[int, int, int] = (255, 255, 255),
    notes: str = "",
) -> Dict[str, Any]:
    asset = _get_image_asset(image_asset_id)

    if not asset:
        return {"status": "blocked_missing_image_asset", "image_asset_id": image_asset_id, "issues": ["missing_image_asset"], "assets": []}

    file_path = Path(asset.get("file_path", ""))
    if not file_path.exists():
        return {"status": "blocked_file_missing", "image_asset_id": image_asset_id, "issues": ["file_missing"], "assets": []}

    GENERATED_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    created_assets = []
    warnings = []

    for format_name in format_names:
        if format_name not in PRINT_FORMATS:
            warnings.append(f"unknown_print_format_skipped:{format_name}")
            continue

        out_path = GENERATED_ASSETS_DIR / f"{_safe_stem(image_asset_id)}_{format_name}_{timestamp}.jpg"

        result = export_print_format(
            file_path=str(file_path),
            output_path=str(out_path),
            format_name=format_name,
            dpi=dpi,
            fill_mode=fill_mode,
            mat_color=mat_color,
        )

        if result["needs_upscale"]:
            warnings.append(f"source_resolution_below_target_dpi:{format_name}")

        new_asset = record_image_asset(
            image_request_id=asset.get("image_request_id"),
            file_path=result["file_path"],
            provider_id=f"curator_print_export:{format_name}",
            generation_notes=(
                f"Curator print-size export of {image_asset_id} for {format_name} at {dpi} DPI "
                f"({fill_mode} fill). {UPSCALE_NEEDED_HINT if result['needs_upscale'] else ''} {notes}".strip()
            ),
        )

        assets = load_json(IMAGE_ASSETS_FILE, [])
        for item in assets:
            if item.get("id") == new_asset["id"]:
                item["derived_from_image_asset_id"] = image_asset_id
                item["derivation_type"] = "print_format_export"
                item["print_format"] = format_name
                item["target_dpi"] = dpi
                item["needs_upscale"] = result["needs_upscale"]
                break
        save_json(IMAGE_ASSETS_FILE, assets)

        new_asset["print_format"] = format_name
        new_asset["needs_upscale"] = result["needs_upscale"]
        new_asset["output_width"] = result["width"]
        new_asset["output_height"] = result["height"]
        created_assets.append(new_asset)

    return {
        "status": "pass" if not warnings else "pass_with_warnings",
        "image_asset_id": image_asset_id,
        "issues": [],
        "warnings": warnings,
        "assets": created_assets,
    }


# ---------------------------------------------------------------------------
# 3. Interior placement mockup (procedural, no stock photo needed)
# ---------------------------------------------------------------------------

def _vertical_gradient(size: Tuple[int, int], color_top: Tuple[int, int, int], color_bottom: Tuple[int, int, int]):
    Image, *_ = _pil()
    np = _numpy()

    width, height = size
    top = np.array(color_top, dtype=np.float32)
    bottom = np.array(color_bottom, dtype=np.float32)
    t = np.linspace(0, 1, height, dtype=np.float32).reshape(height, 1, 1)
    grad = top.reshape(1, 1, 3) * (1 - t) + bottom.reshape(1, 1, 3) * t
    grad = np.repeat(grad, width, axis=1).astype("uint8")
    return Image.fromarray(grad, mode="RGB")


def generate_interior_mockup_image(
    art_path: str,
    output_path: str,
    room_style: str = "warm_neutral",
    frame_style: str = "black",
    canvas_size: Tuple[int, int] = (1600, 1600),
) -> Dict[str, Any]:
    if room_style not in ROOM_STYLES:
        raise CuratorError(f"Unknown room_style '{room_style}'. Known: {', '.join(ROOM_STYLES)}.")
    if frame_style not in FRAME_STYLES:
        raise CuratorError(f"Unknown frame_style '{frame_style}'. Known: {', '.join(FRAME_STYLES)}.")

    Image, ImageDraw, _, ImageFilter, _, _ = _pil()

    room = ROOM_STYLES[room_style]
    frame = FRAME_STYLES[frame_style]
    canvas_w, canvas_h = canvas_size

    floor_h = round(canvas_h * 0.16)
    wall_h = canvas_h - floor_h

    wall = _vertical_gradient((canvas_w, wall_h), room["wall_top"], room["wall_bottom"])
    canvas = Image.new("RGB", (canvas_w, canvas_h), room["floor"])
    canvas.paste(wall, (0, 0))

    draw = ImageDraw.Draw(canvas)
    draw.line([(0, wall_h), (canvas_w, wall_h)], fill=room["floor_highlight"], width=max(2, canvas_h // 300))

    art = Image.open(art_path).convert("RGB")
    art_ratio = art.width / art.height

    art_zone_h = round(wall_h * 0.62)
    art_zone_w = round(canvas_w * 0.42)

    if art_ratio >= (art_zone_w / art_zone_h):
        frame_art_w = art_zone_w
        frame_art_h = round(frame_art_w / art_ratio)
    else:
        frame_art_h = art_zone_h
        frame_art_w = round(frame_art_h * art_ratio)

    frame_border = max(6, round(min(canvas_w, canvas_h) * 0.012)) if frame else 0
    mat_border = max(10, round(min(canvas_w, canvas_h) * 0.018)) if frame else 0

    outer_w = frame_art_w + 2 * (frame_border + mat_border)
    outer_h = frame_art_h + 2 * (frame_border + mat_border)

    center_x = canvas_w // 2
    center_y = round(wall_h * 0.5)

    outer_left = center_x - outer_w // 2
    outer_top = center_y - outer_h // 2
    outer_right = outer_left + outer_w
    outer_bottom = outer_top + outer_h

    # Soft drop shadow, offset down-right, blurred.
    shadow_offset = max(8, round(outer_w * 0.02))
    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_draw.rectangle(
        [outer_left + shadow_offset, outer_top + shadow_offset, outer_right + shadow_offset, outer_bottom + shadow_offset],
        fill=(0, 0, 0, 110),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=max(8, round(outer_w * 0.025))))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow_layer).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    if frame:
        draw.rectangle([outer_left, outer_top, outer_right, outer_bottom], fill=frame["frame"])
        mat_left = outer_left + frame_border
        mat_top = outer_top + frame_border
        mat_right = outer_right - frame_border
        mat_bottom = outer_bottom - frame_border
        draw.rectangle([mat_left, mat_top, mat_right, mat_bottom], fill=frame["mat"])
        art_left = mat_left + mat_border
        art_top = mat_top + mat_border
    else:
        # Unframed: just a thin dark edge line for definition against the wall.
        art_left = outer_left
        art_top = outer_top
        edge = Image.new("RGBA", (frame_art_w + 4, frame_art_h + 4), (0, 0, 0, 60))
        canvas.paste(Image.new("RGB", edge.size, (0, 0, 0)), (art_left - 2, art_top - 2))

    art_resized = art.resize((frame_art_w, frame_art_h), Image.LANCZOS)
    canvas.paste(art_resized, (art_left, art_top))

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "JPEG", quality=92, optimize=True, progressive=True)

    return {
        "file_path": str(out_path),
        "width": canvas_w,
        "height": canvas_h,
        "room_style": room_style,
        "frame_style": frame_style,
    }


def generate_interior_mockup(
    image_asset_id: str,
    room_style: str = "warm_neutral",
    frame_style: str = "black",
    canvas_size: Tuple[int, int] = (1600, 1600),
    notes: str = "",
) -> Dict[str, Any]:
    asset = _get_image_asset(image_asset_id)

    if not asset:
        return {"id": None, "status": "blocked_missing_image_asset", "image_asset_id": image_asset_id, "issues": ["missing_image_asset"]}

    file_path = Path(asset.get("file_path", ""))
    if not file_path.exists():
        return {"id": None, "status": "blocked_file_missing", "image_asset_id": image_asset_id, "issues": ["file_missing"]}

    GENERATED_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = GENERATED_ASSETS_DIR / f"{_safe_stem(image_asset_id)}_mockup_{room_style}_{frame_style}_{timestamp}.jpg"

    result = generate_interior_mockup_image(
        art_path=str(file_path),
        output_path=str(out_path),
        room_style=room_style,
        frame_style=frame_style,
        canvas_size=canvas_size,
    )

    mockups = load_json(MOCKUP_ASSETS_FILE, [])
    mockup = {
        "id": next_id("MOCKUP", mockups),
        "type": "interior_mockup",
        "status": "mockup_generated",
        "image_asset_id": image_asset_id,
        "design_package_id": asset.get("design_package_id"),
        "file_path": result["file_path"],
        "width": result["width"],
        "height": result["height"],
        "room_style": room_style,
        "frame_style": frame_style,
        "rendering_method": "procedural_pillow_composite_not_a_photograph",
        "notes": notes,
        "created_at": now_stamp(),
    }
    mockups.append(mockup)
    save_json(MOCKUP_ASSETS_FILE, mockups)

    return mockup
