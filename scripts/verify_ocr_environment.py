from __future__ import annotations

import argparse
import importlib.util
from importlib import metadata
import sys


def dist_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Picture Capture optional OCR environment")
    parser.add_argument("--expect", choices=("cpu", "gpu", "lens"), default="cpu")
    parser.add_argument("--profile", default="")
    args = parser.parse_args()

    print(f"Python: {sys.version.split()[0]}")
    if args.profile:
        print(f"OCR profile: {args.profile}")

    errors: list[str] = []

    lens_version = dist_version("chrome-lens-py")
    lens_spec = importlib.util.find_spec("chrome_lens_py")
    if lens_version and lens_spec is not None:
        print(f"Google Lens: OK ({lens_version})")
    else:
        errors.append("Google Lens / chrome-lens-py is not available")

    if args.expect == "lens":
        if errors:
            for item in errors:
                print(f"ERROR: {item}")
            return 1
        print("Verification: OK")
        return 0

    paddleocr_version = dist_version("paddleocr")
    if paddleocr_version and importlib.util.find_spec("paddleocr") is not None:
        print(f"PaddleOCR: OK ({paddleocr_version})")
    else:
        errors.append("PaddleOCR is not available")

    cpu_version = dist_version("paddlepaddle")
    gpu_version = dist_version("paddlepaddle-gpu")
    if cpu_version and gpu_version:
        errors.append(f"both paddlepaddle CPU {cpu_version} and paddlepaddle-gpu {gpu_version} are installed")
    elif gpu_version:
        print(f"PaddlePaddle runtime: GPU {gpu_version}")
    elif cpu_version:
        print(f"PaddlePaddle runtime: CPU {cpu_version}")
    else:
        errors.append("PaddlePaddle runtime is not installed")

    try:
        import paddle  # type: ignore

        compiled_cuda = bool(paddle.device.is_compiled_with_cuda())
        print(f"Paddle CUDA build: {compiled_cuda}")
        try:
            print(f"Paddle device: {paddle.device.get_device()}")
        except Exception as exc:  # pragma: no cover - environment specific
            print(f"Paddle device query: unavailable ({exc})")

        if args.expect == "gpu" and not compiled_cuda:
            errors.append("GPU profile selected but Paddle was not compiled with CUDA")
        if args.expect == "cpu" and compiled_cuda:
            errors.append("CPU profile selected but CUDA Paddle runtime is active")
    except Exception as exc:
        errors.append(f"Paddle import/runtime check failed: {exc}")

    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        return 1

    print("Verification: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
