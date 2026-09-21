# OCR 可选组件安装

Picture Capture v2.13.2 起，Windows 提供 `install_ocr_windows.bat`，用于统一管理 PaddleOCR、PaddlePaddle CPU/GPU runtime 与 Google Lens。项目继续使用 uv 管理 `.venv`，不会把依赖安装到系统 Python。

## Windows 推荐方式

在程序根目录双击或从命令行运行：

```bat
install_ocr_windows.bat
```

安装器提供以下配置：

| 选项 | uv profile | 内容 |
| --- | --- | --- |
| CPU | `ocr-cpu` | PaddleOCR + PaddlePaddle CPU 3.3.0 + Google Lens |
| GPU CUDA 11.8 | `ocr-gpu-cu118` | PaddleOCR + PaddlePaddle GPU 3.3.0 + Google Lens |
| GPU CUDA 12.6 | `ocr-gpu-cu126` | PaddleOCR + PaddlePaddle GPU 3.3.0 + Google Lens |
| GPU CUDA 12.9 | `ocr-gpu-cu129` | PaddleOCR + PaddlePaddle GPU 3.3.0 + Google Lens |
| Lens only | `lens` | Google Lens / chrome-lens-py |
| Core only | 无 | 删除可选 OCR profile，仅保留核心环境 |

GPU 模式下，安装器先通过对应的 uv profile 同步 PaddleOCR 与 Google Lens，然后自动从 PaddlePaddle 对应 CUDA 专用索引安装 `paddlepaddle-gpu==3.3.0`。CPU/GPU runtime 会先清理再安装，避免 `paddlepaddle` 与 `paddlepaddle-gpu` 同时提供 `paddle` 模块。

## profile 持久化

安装成功后，根目录会生成：

```text
.picture_capture_ocr_extra
```

文件只保存当前 profile 名，例如：

```text
ocr-gpu-cu126
```

`run_windows.bat` 启动时会读取它，并自动运行等价于：

```bat
uv run --locked --extra ocr-gpu-cu126 python run.py
```

因此用户不需要每次重新输入 `--extra`。该 profile 文件属于本机环境设置，已加入 `.gitignore`。

## 为什么 GPU runtime 由安装器处理

PaddlePaddle GPU 的 wheel 使用 CUDA 专用索引。`ocr-gpu-cu118`、`ocr-gpu-cu126`、`ocr-gpu-cu129` 是正式 uv profile extra，用于锁定共同的 Python 侧 OCR 依赖（PaddleOCR + Google Lens）；安装器再根据所选 profile 从对应官方索引安装 GPU runtime。

这样既保持 `uv.lock` 对通用 Python 依赖的可复现性，也避免把不同 CUDA runtime 同时解析进同一个环境。

## 验证

安装器会自动运行：

```bat
uv run --locked --extra <profile> python scripts\verify_ocr_environment.py --expect gpu --profile <profile>
```

GPU 模式会检查：

- PaddleOCR 是否可导入；
- Google Lens / chrome-lens-py 是否可导入；
- 是否只存在一个 Paddle runtime；
- Paddle 是否为 CUDA build；
- 当前 Paddle 设备信息。

也可在软件内点击【OCR / 简化环境状态】再次确认。

## 切换 CUDA 配置

直接重新运行 `install_ocr_windows.bat` 并选择新的 CUDA profile 即可。安装器会先同步新的 profile，再清理旧 Paddle runtime，最后安装新的 GPU runtime 并覆盖 `.picture_capture_ocr_extra`。

不建议同时手工选择多个 GPU profile，也不要在 GPU 环境中叠加旧的 `paddleocr` CPU extra。

## Tesseract

Tesseract 仍是系统级程序，不由 uv 管理。Windows 可使用：

```bat
winget install tesseract-ocr.tesseract
```
