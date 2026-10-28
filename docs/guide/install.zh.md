# 安装

[English](install.md) · **简体中文**

这一页让程序在你的电脑上跑起来。下一步：[做出第一份数据集](first-dataset.zh.md)。

需要 Windows。强烈建议有 NVIDIA 显卡；没有的话，分离一集的人声要慢很多。Linux 和 macOS 还没有测试过（[平台](../ROADMAP.md#platforms)，英文）。

## Windows 下载包（最简单）

1. 在 [Releases 页面](https://github.com/raindrops0/anime-voice-collector/releases/latest)下载 `anime-voice-collector-…-windows.zip`，大约 16 MB。里面有项目本身、`uv.exe`，以及两个双击就能用的文件。
2. 解压到短一点的路径，比如 `D:\avoc`。Windows 不接受超过 260 个字符的文件路径，而依赖库本身就要占掉大约 170 个。
3. 双击 `start.bat`。第一次启动会下载 Python 和依赖库，大约 5 GB；之后启动只要几秒。用的时候别关它的窗口。

两个文件的用处：

- `start.bat` 用下载包里的 `workspace` 文件夹启动程序。要打开别的工作区，把它的文件夹拖到 `start.bat` 上，或者运行 `start.bat D:\my-workspace`。文件夹后面的选项会交给 `avoc app`，比如 `--port 8800`。
- `terminal.bat` 打开一个命令行窗口，文档里的 `uv run avoc …` 命令都可以照原样在里面运行，比如 `uv run avoc doctor`。

Python、依赖库和下载的模型都放在解压出来的文件夹里（[做法](../../scripts/release/env.bat)），所以删掉这个文件夹就全删干净了；只有 Hugging Face 的令牌留在你的用户文件夹里。更新时，把新版本解压覆盖到旧文件夹上：工作区、依赖库和模型都会保留，下次启动只装有变化的部分。

## 用 git

先装 [uv](https://docs.astral.sh/uv/)，它也会装好合适的 Python。在 PowerShell 里运行：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

新开一个终端窗口（这样才能找到 uv），然后：

```powershell
git clone https://github.com/raindrops0/anime-voice-collector.git
cd anime-voice-collector
uv sync --locked
uv run avoc doctor
```

## FFmpeg

FFmpeg 要在 `PATH` 里。在 Windows 上，程序的第一页有一个「一键帮我安装」按钮：它运行 [install_ffmpeg.ps1](../../src/avoc/install_ffmpeg.ps1)，如果你没有 [Scoop](https://scoop.sh) 就先装上，再用它装 FFmpeg，不需要管理员权限。装好后程序马上能用，不用重启。

想自己装的话：有 Scoop 就运行 `scoop install ffmpeg`；没有的话，从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载 Windows 版，解压，把里面的 `bin` 文件夹加进 `PATH` 环境变量。

## 检查电脑

```powershell
uv run avoc doctor
```

`doctor` 逐项列出：操作系统、显卡、FFmpeg、人声分离模型、Hugging Face 令牌，以及剩余磁盘空间。

- 标着「缺少」的要先解决。
- 标着「可选」的可以不管，照样能用。
- 「未测试」表示不是 Windows：大多能用，但只在 Windows 上测过。

报告问题时，请附上它的输出。

## Hugging Face 令牌（用于自动对时间）

字幕偏移是字幕时间和声音差了多少秒。程序可以用 Hugging Face 上的一个免费模型帮你测出来。要用这个功能，只需做一次：

1. 在[模型页面](https://huggingface.co/pyannote/speaker-diarization-community-1)接受使用条款。Hugging Face 账号是免费的。
2. 在[令牌页面](https://huggingface.co/settings/tokens)创建一个 Read 令牌。
3. 运行 `uv run hf auth login`，把令牌粘贴进去。

缺少令牌时，添加表单会显示这些步骤。没有令牌也可以自己填偏移。运行要求和模型来源见 [TOOLS.md](../TOOLS.md)（英文）。
