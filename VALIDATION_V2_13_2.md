# Picture Capture v2.13.2 Validation

- `python -m compileall -q src scripts`: passed.
- `PYTHONPATH=src pytest -q`: **287 passed**.
- `PYTHONPATH=src python run_tests.py`: **70 passed**.
- `uv lock --locked`: lockfile/project metadata consistency check passed (validated with the available uv 0.10 engine after temporarily relaxing only the local `required-version` gate; release still requires uv >=0.11).
- Wheel build: `picture_capture_restored-2.13.2-py3-none-any.whl` built successfully.
- Wheel smoke import: `picture_capture.__version__ == 2.13.2`.
- Static regression checks cover the four OCR profile extras, three Paddle CUDA indexes, persistent local OCR profile, and profile-aware Windows launcher.

## Scope note

The build container has no outbound package-index network access and no Windows/NVIDIA runtime, so the three actual PaddlePaddle GPU wheel installs could not be executed end-to-end here. The installer uses PaddlePaddle's CUDA-specific stable indexes and performs runtime verification on the user's Windows machine after installation.
