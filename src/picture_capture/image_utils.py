from __future__ import annotations

from PIL import Image, ImageOps


def normalize_page_rgb(image: Image.Image) -> Image.Image:
    """Return a detached, EXIF-oriented RGB page image.

    Any image carrying transparency (RGBA/LA/P with transparency, etc.) is
    composited onto an opaque white page *before* RGB conversion.  This keeps
    display, OCR, separator detection and Y refinement on the same pixels and
    avoids transparent PNGs becoming dark when alpha is discarded.

    For ordinary opaque RGB pages, pixel values are preserved exactly.
    """
    oriented = ImageOps.exif_transpose(image)
    try:
        has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
        if has_alpha:
            rgba = oriented.convert("RGBA")
            try:
                white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                try:
                    return Image.alpha_composite(white, rgba).convert("RGB")
                finally:
                    white.close()
            finally:
                if rgba is not oriented:
                    rgba.close()
        if oriented.mode == "RGB":
            return oriented.copy()
        return oriented.convert("RGB")
    finally:
        if oriented is not image:
            oriented.close()
