from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageOps

from .models import AppSettings
from .image_utils import normalize_page_rgb
from .processing import parameter_scale


@dataclass(slots=True)
class LayoutEstimate:
    columns: int
    start_y: int
    column_width: int
    gutter: int
    manual_x: int
    bottom_y: int
    character_height: int
    row_padding: int
    source_boxes: int
    method: str = "paddle"


@dataclass(slots=True)
class LayoutConsistencyEstimate:
    header_rule_y: int | None
    body_left_x: int | None
    is_blank: bool = False


_TEXT_DETECTION_CACHE: dict[str, Any] = {}


def _result_payload(result: Any) -> dict[str, Any]:
    payload = getattr(result, "json", result)
    if callable(payload):
        payload = payload()
    if not isinstance(payload, dict):
        raise RuntimeError("PaddleOCR TextDetection 返回了无法解析的结果格式")
    nested = payload.get("res")
    return nested if isinstance(nested, dict) else payload


def _get_text_detector(settings: AppSettings) -> Any:
    """Create a detection-only PaddleOCR model with CPU oneDNN/PIR disabled.

    PaddlePaddle 3.3.x + recent PaddleOCR builds can enter a PIR/oneDNN CPU
    execution path that raises ConvertPirAttribute2RuntimeAttribute for text
    detection models.  Layout detection values compatibility over peak speed,
    so explicitly disable that acceleration path here.
    """
    key = f"{settings.paddle_device or 'cpu'}|nomkldnn"
    if key in _TEXT_DETECTION_CACHE:
        return _TEXT_DETECTION_CACHE[key]

    # Must be set before importing/constructing PaddleOCR/PaddleX components.
    # This is intentionally an assignment (not setdefault): some PaddleX builds
    # may have set it to 1 earlier in the process.
    os.environ["FLAGS_enable_pir_api"] = "0"
    try:
        from paddleocr import TextDetection
    except ImportError as exc:
        raise RuntimeError(
            "尚未安装 PaddleOCR。Windows 请运行 install_ocr_windows.bat；CPU 用户也可执行：uv sync --extra ocr-cpu"
        ) from exc

    kwargs: dict[str, Any] = {"enable_mkldnn": False}
    if settings.paddle_device:
        kwargs["device"] = settings.paddle_device

    # Newer PaddleOCR 3.x exposes enable_mkldnn directly.  Keep compatibility
    # with older 3.x signatures by progressively dropping unsupported kwargs.
    attempts = [
        kwargs,
        {k: v for k, v in kwargs.items() if k != "device"},
        {"device": settings.paddle_device} if settings.paddle_device else {},
        {},
    ]
    seen: set[tuple[tuple[str, str], ...]] = set()
    last_exc: Exception | None = None
    for attempt in attempts:
        marker = tuple(sorted((str(k), repr(v)) for k, v in attempt.items()))
        if marker in seen:
            continue
        seen.add(marker)
        try:
            detector = TextDetection(**attempt)
            # Layout detection only needs the active device configuration.
            # Keeping stale detector instances for every past device can pin
            # substantial Paddle/PaddleX memory for the whole GUI session.
            _TEXT_DETECTION_CACHE.clear()
            _TEXT_DETECTION_CACHE[key] = detector
            return detector
        except TypeError as exc:
            last_exc = exc
            continue
        except Exception as exc:
            last_exc = exc
            break
    raise RuntimeError(f"PaddleOCR 文本检测模型初始化失败：{last_exc}") from last_exc


def _boxes_from_detection(result: Any, width: int, height: int) -> list[tuple[int, int, int, int]]:
    payload = _result_payload(result)
    raw_polys = payload.get("dt_polys")
    if raw_polys is None:
        raw_polys = payload.get("polys")
    if raw_polys is None:
        return []
    boxes: list[tuple[int, int, int, int]] = []
    for raw in list(raw_polys):
        arr = np.asarray(raw, dtype=float)
        if arr.ndim != 2 or arr.shape[0] < 3 or arr.shape[1] < 2:
            continue
        x0 = max(0, min(width - 1, int(round(float(arr[:, 0].min())))))
        x1 = max(1, min(width, int(round(float(arr[:, 0].max())))))
        y0 = max(0, min(height - 1, int(round(float(arr[:, 1].min())))))
        y1 = max(1, min(height, int(round(float(arr[:, 1].max())))))
        if x1 - x0 >= 3 and y1 - y0 >= 3:
            boxes.append((x0, y0, x1, y1))
    return boxes


def _split_left_edge_groups(
    boxes: list[tuple[int, int, int, int]], width: int
) -> list[list[tuple[int, int, int, int]]]:
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda box: box[0])
    split_gap = max(36, int(round(width * 0.14)))
    groups: list[list[tuple[int, int, int, int]]] = [[ordered[0]]]
    for box in ordered[1:]:
        if box[0] - groups[-1][-1][0] >= split_gap:
            groups.append([box])
        else:
            groups[-1].append(box)

    minimum = max(4, int(round(len(boxes) * 0.055)))
    useful = [group for group in groups if len(group) >= minimum]
    if not useful:
        useful = [max(groups, key=len)]
    useful.sort(key=lambda group: float(np.percentile([b[0] for b in group], 10)))
    return useful[:6]


def _longest_low_density_run(
    density: np.ndarray, start: int, end: int
) -> tuple[int, int] | None:
    if end <= start + 3:
        return None
    region = density[start:end]
    positive = region[region > 0]
    if positive.size:
        threshold = max(float(np.percentile(positive, 12)) * 0.35, float(region.max()) * 0.018)
    else:
        threshold = 0.0
    mask = region <= threshold
    best: tuple[int, int] | None = None
    run_start: int | None = None
    for i, flag in enumerate(mask):
        if flag and run_start is None:
            run_start = i
        if (not flag or i == len(mask) - 1) and run_start is not None:
            run_end = i if not flag else i + 1
            if best is None or run_end - run_start > best[1] - best[0]:
                best = (start + run_start, start + run_end)
            run_start = None
    return best


def _estimate_start_y(boxes: list[tuple[int, int, int, int]], height: int) -> int:
    if not boxes:
        return 0
    heights = [box[3] - box[1] for box in boxes]
    median_h = max(4.0, float(np.median(heights)))
    intervals = sorted((box[1], box[3]) for box in boxes)
    merged: list[list[int]] = []
    merge_gap = max(2, int(round(median_h * 0.25)))
    for y0, y1 in intervals:
        if not merged or y0 > merged[-1][1] + merge_gap:
            merged.append([y0, y1])
        else:
            merged[-1][1] = max(merged[-1][1], y1)

    top_limit = int(round(height * 0.36))
    candidates: list[tuple[int, int]] = []
    for prev, nxt in zip(merged, merged[1:]):
        gap = nxt[0] - prev[1]
        if nxt[0] <= top_limit and gap >= median_h * 1.45:
            candidates.append((gap, nxt[0]))
    if candidates:
        _gap, y = max(candidates)
        return int(y)
    return int(np.percentile([box[1] for box in boxes], 2))


def infer_layout_from_boxes(
    boxes: Iterable[tuple[int, int, int, int]],
    image_size: tuple[int, int],
    display_scale: float = 1.0,
) -> LayoutEstimate:
    width, height = image_size
    raw = [
        tuple(map(int, box)) for box in boxes
        if box[2] > box[0] and box[3] > box[1]
    ]
    if len(raw) < 4:
        raise RuntimeError("整页文本检测框过少，无法可靠估计版面参数。")

    median_h = float(np.median([box[3] - box[1] for box in raw]))
    filtered = [
        box for box in raw
        if box[3] - box[1] >= max(3.0, median_h * 0.40)
        and box[2] - box[0] <= width * 0.92
    ] or raw

    groups = _split_left_edge_groups(filtered, width)
    starts = [int(round(float(np.percentile([box[0] for box in group], 6)))) for group in groups]
    starts = sorted(set(starts))
    if not starts:
        starts = [int(np.percentile([box[0] for box in filtered], 4))]

    density = np.zeros(max(1, width), dtype=float)
    for x0, y0, x1, y1 in filtered:
        density[max(0, x0):min(width, x1)] += max(1, y1 - y0)

    gap_widths: list[int] = []
    col_widths: list[int] = []
    for left, right in zip(starts, starts[1:]):
        pitch = right - left
        search_left = left + max(6, int(round(pitch * 0.42)))
        search_right = right - max(4, int(round(pitch * 0.035)))
        run = _longest_low_density_run(density, search_left, search_right)
        if run and run[1] - run[0] >= max(6, int(round(width * 0.006))):
            gap_start, gap_end = run
            gap_widths.append(gap_end - gap_start)
            col_widths.append(max(10, gap_start - left))
        else:
            fallback_gutter = max(8, int(round(pitch * 0.055)))
            gap_widths.append(fallback_gutter)
            col_widths.append(max(10, pitch - fallback_gutter))

    if len(starts) == 1:
        right_edges = [box[2] for box in filtered if box[0] >= starts[0] - width * 0.04]
        right = int(np.percentile(right_edges, 97)) if right_edges else width - starts[0]
        col_widths = [max(10, right - starts[0])]
        gutter_source = 0
    else:
        col_widths.append(int(round(float(np.median(col_widths)))))
        gutter_source = int(round(float(np.median(gap_widths)))) if gap_widths else 0

    start_y_source = _estimate_start_y(filtered, height)
    bottom_y_source = int(np.percentile([box[3] for box in filtered], 99))
    character_height_source = max(1, round(float(np.median([box[3] - box[1] for box in filtered]))))
    ordered_tops = sorted({box[1] for box in filtered})
    top_steps = [b - a for a, b in zip(ordered_tops, ordered_tops[1:]) if b - a > character_height_source * 0.5]
    row_padding_source = max(1, round((float(np.median(top_steps)) - character_height_source) / 2)) if top_steps else 1
    scale = max(0.01, float(display_scale))
    return LayoutEstimate(
        columns=len(starts),
        start_y=max(0, round(start_y_source * scale)),
        column_width=max(10, round(float(np.median(col_widths)) * scale)),
        gutter=max(0, round(gutter_source * scale)),
        manual_x=max(0, round(starts[0] * scale)),
        bottom_y=max(1, round(bottom_y_source * scale)),
        character_height=max(1, round(character_height_source * scale)),
        row_padding=max(1, round(row_padding_source * scale)),
        source_boxes=len(filtered),
        method="paddle",
    )


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start: int | None = None
    for i, flag in enumerate(mask.tolist()):
        if flag and start is None:
            start = i
        if start is not None and (not flag or i == len(mask) - 1):
            end = i if not flag else i + 1
            result.append((start, end))
            start = None
    return result


def _smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    if window <= 1:
        return values.astype(float, copy=False)
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(values.astype(float), kernel, mode="same")


def _otsu_threshold(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256).astype(float)
    total = hist.sum()
    if total <= 0:
        return 200
    cumulative = np.cumsum(hist)
    means = np.cumsum(hist * np.arange(256))
    global_mean = means[-1]
    denom = cumulative * (total - cumulative)
    valid = denom > 0
    score = np.zeros(256, dtype=float)
    score[valid] = (global_mean * cumulative[valid] - means[valid] * total) ** 2 / denom[valid]
    # Do not let very bright paper noise become foreground on faint scans.
    return int(min(235, max(80, int(np.argmax(score)))))


def _projection_layout_estimate(source: Image.Image, settings: AppSettings) -> LayoutEstimate:
    """OCR-free fallback based on dark-pixel projections.

    This is only used when PaddleOCR's detector cannot run in the installed
    Paddle/PaddleX stack.  It has no user-facing projection parameters and does
    not revive the removed projection-based headword drawing mode.
    """
    original_w, original_h = source.size
    max_dim = max(original_w, original_h)
    resize_scale = min(1.0, 1800.0 / max(1, max_dim))
    if resize_scale < 1.0:
        work = source.resize(
            (max(1, round(original_w * resize_scale)), max(1, round(original_h * resize_scale))),
            Image.Resampling.BILINEAR,
        )
    else:
        work = source
    gray = np.asarray(ImageOps.grayscale(work), dtype=np.uint8)
    h, w = gray.shape
    threshold = _otsu_threshold(gray)
    ink = gray < threshold

    # Ignore a narrow outer rim where scanner shadows/page borders live.
    mx = max(1, round(w * 0.015)); my = max(1, round(h * 0.01))
    ink[:my, :] = False; ink[-my:, :] = False
    ink[:, :mx] = False; ink[:, -mx:] = False

    row_density = _smooth_1d(ink.mean(axis=1), max(3, round(h * 0.0025)))
    active_floor = max(0.002, float(np.percentile(row_density[row_density > 0], 25)) * 0.35) if np.any(row_density > 0) else 0.002
    blank_rows = row_density <= active_floor
    early_limit = max(1, round(h * 0.38))
    header_gaps = [
        (a, b) for a, b in _runs(blank_rows[:early_limit])
        if b - a >= max(6, round(h * 0.006)) and a > round(h * 0.015)
    ]
    if header_gaps:
        # Prefer the largest early whitespace band.  Its lower edge usually
        # marks the start of dictionary body text after a running header/title.
        start_y_small = max(header_gaps, key=lambda run: run[1] - run[0])[1]
    else:
        active_idx = np.flatnonzero(~blank_rows)
        start_y_small = int(active_idx[0]) if active_idx.size else 0

    body_top = min(max(0, start_y_small), max(0, h - 1))
    body_bottom = max(body_top + 1, round(h * 0.97))
    body = ink[body_top:body_bottom, :]
    x_density = _smooth_1d(body.mean(axis=0), max(5, round(w * 0.006)))
    positive = x_density[x_density > 0]
    if positive.size == 0:
        raise RuntimeError("图像回退检测未发现可用正文像素。")
    blank_threshold = max(0.001, float(np.percentile(positive, 18)) * 0.38)
    blank_cols = x_density <= blank_threshold

    min_gap = max(6, round(w * 0.008))
    gap_candidates = [
        (a, b) for a, b in _runs(blank_cols)
        if b - a >= min_gap
        and a >= round(w * 0.05)
        and b <= round(w * 0.95)
    ]

    # Keep only gaps that leave plausible dictionary columns on both sides.
    # Greedy by width makes real inter-column gutters win over accidental
    # whitespace created by short definitions.
    chosen: list[tuple[int, int]] = []
    for gap in sorted(gap_candidates, key=lambda g: (g[1] - g[0]), reverse=True):
        center = (gap[0] + gap[1]) / 2
        if any(abs(center - (g[0] + g[1]) / 2) < w * 0.12 for g in chosen):
            continue
        test = sorted(chosen + [gap])
        edges = [round(w * 0.03)] + [int((a + b) / 2) for a, b in test] + [round(w * 0.97)]
        widths = [b - a for a, b in zip(edges, edges[1:])]
        if widths and min(widths) >= w * 0.13:
            chosen.append(gap)
        if len(chosen) >= 5:
            break
    chosen.sort()

    text_mask = x_density > blank_threshold
    text_positions = np.flatnonzero(text_mask)
    if not text_positions.size:
        raise RuntimeError("图像回退检测无法确定正文水平范围。")
    page_left = int(text_positions[0]); page_right = int(text_positions[-1] + 1)

    starts: list[int] = []
    widths: list[int] = []
    gutters: list[int] = []
    region_left = page_left
    for gap_start, gap_end in chosen:
        region = np.flatnonzero(text_mask[region_left:gap_start])
        if region.size:
            start = region_left + int(region[0])
            starts.append(start)
            widths.append(max(10, gap_start - start))
            gutters.append(gap_end - gap_start)
        region_left = gap_end
    region = np.flatnonzero(text_mask[region_left:page_right])
    if region.size:
        start = region_left + int(region[0])
        starts.append(start)
        widths.append(max(10, page_right - start))

    if not starts:
        starts = [page_left]
        widths = [max(10, page_right - page_left)]
        gutters = []
    if len(starts) > 1:
        # Last column may have shorter lines; use preceding widths as the more
        # stable estimate of the designed column width.
        stable = widths[:-1] if widths[:-1] else widths
        widths[-1] = int(round(float(np.median(stable))))

    back = 1.0 / resize_scale
    display = parameter_scale(source, settings)
    factor = back * display
    return LayoutEstimate(
        columns=max(1, min(6, len(starts))),
        start_y=max(0, round(start_y_small * factor)),
        column_width=max(10, round(float(np.median(widths)) * factor)),
        gutter=max(0, round((float(np.median(gutters)) if gutters else 0.0) * factor)),
        manual_x=max(0, round(starts[0] * factor)),
        bottom_y=max(1, round(body_bottom * factor)),
        character_height=max(1, round(max(1, h * 0.008) * factor)),
        row_padding=1,
        source_boxes=max(1, len(starts) + len(chosen)),
        method="projection_fallback",
    )


def detect_layout_parameters(image: Image.Image, settings: AppSettings) -> LayoutEstimate:
    """Detect dictionary page geometry without OCR text recognition.

    Primary path: PaddleOCR TextDetection with CPU oneDNN/PIR disabled.
    Compatibility path: OCR-free image-density layout estimation when the
    installed Paddle/PaddleX stack still cannot execute detection.
    """
    source = normalize_page_rgb(image)
    paddle_error: Exception | None = None
    try:
        detector = _get_text_detector(settings)
        # Reassert immediately before predict because PaddleX can modify flags
        # while constructing other pipelines in the same application process.
        os.environ["FLAGS_enable_pir_api"] = "0"
        try:
            results = list(detector.predict(np.asarray(source), batch_size=1, limit_side_len=2400))
        except TypeError:
            results = list(detector.predict(np.asarray(source)))
        if results:
            boxes = _boxes_from_detection(results[0], source.width, source.height)
            if boxes:
                return infer_layout_from_boxes(
                    boxes,
                    source.size,
                    display_scale=parameter_scale(source, settings),
                )
            paddle_error = RuntimeError("PaddleOCR 整页版面检测没有返回文本框。")
        else:
            paddle_error = RuntimeError("PaddleOCR 整页版面检测没有返回结果。")
    except Exception as exc:
        paddle_error = exc

    try:
        return _projection_layout_estimate(source, settings)
    except Exception as fallback_exc:
        raise RuntimeError(
            f"PaddleOCR 整页版面检测失败：{paddle_error}\n"
            f"兼容回退检测也失败：{fallback_exc}"
        ) from fallback_exc


def detect_layout_consistency(image: Image.Image, settings: AppSettings) -> LayoutConsistencyEstimate:
    """Quickly measure header-rule Y and first body-text X using projections.

    This deliberately avoids OCR/VLM inference: downscaled grayscale projections
    are deterministic and substantially cheaper for projects containing thousands
    of pages.
    """
    source = normalize_page_rgb(image)
    scale = min(1.0, 1600.0 / max(source.size))
    work = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.BILINEAR,
    ) if scale < 1.0 else source
    gray = np.asarray(ImageOps.grayscale(work), dtype=np.uint8)
    ink = gray < _otsu_threshold(gray)
    active_rows = int(np.count_nonzero(ink.mean(axis=1) > 0.002))
    active_columns = int(np.count_nonzero(ink.mean(axis=0) > 0.002))
    is_blank = float(ink.mean()) < 0.0008 or active_rows < 6 or active_columns < 12
    if is_blank:
        return LayoutConsistencyEstimate(None, None, is_blank=True)
    parameter_to_source = 1.0 / max(0.01, parameter_scale(source, settings))
    header_limit = min(ink.shape[0], max(1, round(settings.start_y * parameter_to_source * scale)))
    header_density = ink[:header_limit].mean(axis=1)
    header_rule_y: int | None = None
    if header_density.size and float(header_density.max()) >= 0.12:
        header_rule_y = round(int(np.argmax(header_density)) / scale * parameter_scale(source, settings))

    body = ink[header_limit:, :]
    body_left_x: int | None = None
    if body.size:
        column_density = body.mean(axis=0)
        threshold = max(0.002, float(np.percentile(column_density[column_density > 0], 20)) * 0.35) if np.any(column_density > 0) else 0.002
        active = np.flatnonzero(column_density > threshold)
        if active.size:
            body_left_x = round(int(active[0]) / scale * parameter_scale(source, settings))
    return LayoutConsistencyEstimate(header_rule_y=header_rule_y, body_left_x=body_left_x, is_blank=False)
