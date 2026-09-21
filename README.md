# Picture Capture

面向**多栏词典扫描页**的桌面制作工具：自动/半自动为词头画线，调用多引擎 OCR 识别与校对词条，切词条与插图，导出 PDIC/PicDic/训练集。界面基于 Tkinter。

## 版本渊源

本程序是根据 2016 年的 VB.NET 项目 `picture_capture_V2016`（`Form1.vb`、`Form2.vb`、Designer 与 RESX 文件）重建的 **Python 复原版**。它保留原程序的主要工作流与数据格式（`.pdic`、`.ppp`、`wordslist.txt`、`_Mysettings.ini` 等），并修复了旧代码中的若干越界与批处理问题。

版本演进见 [CHANGELOG.md](CHANGELOG.md)（完整版本历史，含 hotfix）。

## 主要能力

- 自动/手动词头画线（`left_edge` 左缘规则与 `paddleocr` OCR 识别）。
- PaddleOCR / Tesseract / Google Lens 多引擎识别、融合仲裁与人工复核。
- 校对窗口：参考词表定位、网络词典核验、繁简对照与 CC-CEDICT 本地核验。
- 词条切图、插图多边形（PPP）、PicDic 制作、训练标注导出、PDIC 备份/恢复。

## 环境要求

- **uv >= 0.11**（依赖与 Python 环境管理）：<https://docs.astral.sh/uv/getting-started/installation/>
- Python 版本由 `.python-version` 锁定（当前 **3.13**）；uv 会自动准备，无需手动安装。
- 可选：**Tesseract 5**（系统级 OCR）、**PaddleOCR**、**Google Lens**、**CC-CEDICT**。

> PaddleOCR 目前支持 Python 3.10–3.13，因此 `requires-python` 设为 `>=3.10,<3.14`。

## 安装与运行

核心依赖只有 Pillow、NumPy、pypinyin、OpenCC，无需 OCR 也可启动。

**Windows**

```bat
run_windows.bat
```

该脚本使用已提交的 `uv.lock` 启动，等价于：

```bat
uv run --locked python run.py
```

**macOS / Linux**

```bash
uv run --locked python run.py
```

首次运行会自动创建项目专属 `.venv` 并按 `uv.lock` 安装依赖；不会把依赖装进系统 Python。日常启动请使用 `run_windows.bat` 或 `uv run --locked python run.py`。

### 可选组件

```bash
uv sync --extra paddleocr            # PaddleOCR（含 CPU 版 PaddlePaddle）
uv sync --extra lens                 # Google Lens（chrome-lens-py）
uv sync --extra lens --extra paddleocr   # 多个 extra 需一次列全
```

- `uv sync` 默认会移除未列出的 extra；`uv run` 则保留已安装的 extra。
- `paddleocr` extra 当前是 **CPU 预设**，会安装 `paddlepaddle==3.3.0`。GPU 用户不要再叠加该 CPU extra；应在同一个项目 `.venv` 中按 PaddlePaddle 官方 CUDA 说明安装匹配的 `paddlepaddle-gpu` 与 PaddleOCR，避免 CPU/GPU runtime 同时提供 `paddle` 模块。
- **Tesseract 5** 不是 pip 包，需单独安装：Windows 用 `winget install tesseract-ocr.tesseract`，Ubuntu/Debian 用 `sudo apt install tesseract-ocr`。官方 Windows 安装包默认只含 `eng`/`osd`，如需 `spa`、`chi_sim`、`chi_tra`，可把对应 `*.traineddata` 从 <https://github.com/tesseract-ocr/tessdata_fast> 放入 `%LOCALAPPDATA%\Tesseract-OCR\tessdata`，并设置用户环境变量 `TESSDATA_PREFIX` 指向该目录。
- **CC-CEDICT** 本地词典安装见 [docs/cc-cedict-install.md](docs/cc-cedict-install.md)。

## 快速上手

1. 启动后，在左侧“页面列表”点击“打开项目目录”，选择词典项目文件夹。
2. 点击“检测引擎”确认 OCR 引擎可用状态。
3. 在一页上校准版面参数并试画线，确认无误后再执行批量操作。

## 项目目录

新建项目的数据统一写入项目下的 `_PictureCapture/`；旧项目保持历史目录布局。详见 [docs/usage.md](docs/usage.md)。

## 命令行

```bash
uv run picture-capture-cli "D:\Dictionary" inspect
uv run picture-capture-cli "D:\Dictionary" autodraw --page page001.tif
```

完整命令见 [docs/usage.md](docs/usage.md)。

## 文档索引

| 文件 | 内容 |
| --- | --- |
| [docs/usage.md](docs/usage.md) | 使用与参考：目录、坐标、画线方式、OCR 词头识别、规则、CLI、测试 |
| [CHANGELOG.md](CHANGELOG.md) | 完整版本历史（含 hotfix） |
| [docs/architecture.md](docs/architecture.md) | v2 OCR/词头管线与存储架构 |
| [docs/legacy-function-map.md](docs/legacy-function-map.md) | 旧 VB.NET 功能到 Python 的映射 |
| [docs/cc-cedict-install.md](docs/cc-cedict-install.md) | CC-CEDICT 本地词典安装 |
