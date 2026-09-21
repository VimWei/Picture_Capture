# CC-CEDICT 安装说明

Picture Capture 支持本地 CC-CEDICT 词典核验与繁体→简体词形对照。CC-CEDICT 不属于 Python/PIP 软件包，不需要执行 `pip install`。

## 安装步骤

1. 在浏览器打开 CC-CEDICT 官方下载页：
   https://www.mdbg.net/chinese/dictionary?page=cc-cedict
2. 下载 UTF-8 版本，推荐 ZIP：`cedict_1_0_ts_utf-8_mdbg.zip`。
3. 打开 Picture Capture 的【词条校对】窗口。
4. 点击 `CC-CEDICT(未装)`。
5. 选择【是】，然后直接选择刚下载的 ZIP 文件；无需手动解压。
6. 安装成功后按钮会变为 `CC-CEDICT(?)`；选择词条或点【立即】后显示 `CC-CEDICT(√)` / `CC-CEDICT(×)`。

## 繁简词形比较

安装后，校对界面除 `CC-CEDICT(√/×)` 收录状态外，还会显示 `CC简`：

- `CC简(√)`：OpenCC 自动简化结果与 CC-CEDICT 的 Simplified 字段一致。
- `CC简:词形` / `CC简(N候选)`：CC-CEDICT 提供不同或多个简体候选，供人工复核。
- `CC简(×)`：未找到繁体词条对应的简体映射；这只表示缺少词典证据，不自动判定 OpenCC 错误。

点击 `CC简` 可查看原词条、OpenCC 结果、当前已保存简体和 CC-CEDICT 候选的完整对照。

## 本地位置

Windows 默认保存到：

`%LOCALAPPDATA%\PictureCapture\dictionaries\cc-cedict\`

词典为当前 Windows 用户的所有 Picture Capture 项目共享，不会复制到各项目的 `_PictureCapture` 目录。

## 数据与许可

CC-CEDICT 由 MDBG 提供下载，采用 CC BY-SA 4.0。Picture Capture 只读取用户下载的本地数据库，不自动抓取 MDBG 查询网页，也不会修改 CC-CEDICT 内容。
