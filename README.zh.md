<div align="center">

<h1><img src="https://github.com/user-attachments/assets/6fe2b479-0f71-46ec-b5bc-9142184db72b" height="48" align="center" alt=""> anime-voice-collector</h1>

[English](README.md) · **简体中文**

**把整集动画变成一个角色的干净语音数据集，可以直接训练 GPT-SoVITS 或 RVC。<br>你标出这个角色的 10 句台词，剩下的它帮你分。**

[![CI](https://github.com/raindrops0/anime-voice-collector/actions/workflows/ci.yml/badge.svg)](https://github.com/raindrops0/anime-voice-collector/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![平台：Windows · Linux/macOS 未测试](https://img.shields.io/badge/%E5%B9%B3%E5%8F%B0-Windows%20%C2%B7%20Linux%2FmacOS%20%E6%9C%AA%E6%B5%8B%E8%AF%95-0078D6.svg)](#支持的平台)

### [▶ 在浏览器里直接试用，不用安装](https://raindrops0.github.io/avoc-online-demo/)

[它做什么](#它做什么) · [安装](#安装) · [加第一集](#加第一集) · [怎么标注](#怎么标注) · [得到什么](#得到什么) · [常见问题](#常见问题) · [文档（英文）](docs/index.md)

<img src="https://github.com/user-attachments/assets/bdda1308-5ce1-43ae-9d5f-36fc5e579a5b" width="800" alt="演示：给一组台词起名当作一个角色，机器开始猜其余的台词，改掉一处猜错，检查这个角色的名单，再导出">

</div>

## 在线试用

[在线试用](https://raindrops0.github.io/avoc-online-demo/)就是真正的界面，里面有两段已经处理好的虚构日语短剧（用 VOICEVOX 配音）。不用安装，也不用上传任何东西。

1. 在**分组**里勾出同一个人的台词，按 `N` 给他起名。
2. 在**场景**里再标几句，看机器开始猜剩下的台词是谁说的。
3. 改掉一处猜错：它马上重新学，别的猜测也跟着变。

第一次打开时，一段简短的引导会带你认识界面，并带你标上一句。你的标注只在这次访问里有效，添加剧集和导出是关闭的。免费服务器没人用时会休眠，所以页面可能要一分钟左右叫醒它。

## 它做什么

想训练某个角色的声音模型，需要这个角色单独说话的几分钟音频，每段还要配上台词。手工做就得把每一集从头拖到尾。多数工具只做到说话人分离（按声音像谁把台词分成几组），给每组起名字、逐条检查还是要你自己来。

在这里，你一边看画面一边标几句。一个小模型学会你的角色，把剩下的分好类，而且**每次你纠正它，几秒内就重新训练**。你只需要检查它的结果，不用全部自己做。

<img src="https://github.com/user-attachments/assets/c19aeaa2-5064-4783-9bc1-7193e865da50" width="800" alt="一集里的台词排在时间轴上，按是谁说的分进 Mio、Rin 和「其他」三个文件夹">

| | 手工 | 按声音分组（说话人分离，比如 pyannote） | anime-voice-collector |
| --- | --- | --- | --- |
| 这句是哪个角色？ | 每句都由你判断 | 只给出「说话人 3」，每集都要你自己对应到角色 | 你标几句，剩下的它来认 |
| 它弄错的时候 | 要你再过一遍才发现 | 你手动改，它学不到什么 | 你一改，它就重新训练，其他猜测跟着变好 |
| 音乐和音效 | 要另外去掉 | 要另外去掉 | 已经去掉 |
| 每句的原话 | 你自己打字或对齐 | 没有 | 从字幕里取，用原声语言 |
| 能直接训练 GPT-SoVITS 或 RVC | 还要再整理 | 还要再整理 | 能，导出一次即可 |

- 🎬 **每句字幕切成一段**，不会因为语音检测漏掉台词。
- 🎤 **只留人声**：每段里的音乐和音效都去掉了。
- 📺 **边看边标。** 每句台词都配着视频播放，按一个键就能看前后更多内容。
- 🔇 **找出有杂音的台词。** 背景声太大或两人同时说话的台词，从标第一句起就会被提示「可能质量低」（[说明](docs/features/labeling.md#the-maybe-low-quality-hint)）。
- ⌨️ **以键盘操作为主**，每一步都能撤销，较早的某一步也能在操作历史里单独撤销。
- 🈶 **导出角色说出口的原话。** 文字用原声语言，哪怕你标注时看的是译文。

## 安装

需要 Windows；添加剧集时需要 NVIDIA 显卡。没有显卡？[在 Google Colab 的免费 GPU 上添加剧集](docs/guide/install.zh.md#没有-nvidia-显卡)，再在自己电脑上标注；只用 CPU 的话，一集可能要几个小时。

**最简单的办法：** 在 [Releases 页面](https://github.com/raindrops0/anime-voice-collector/releases/latest)下载 `anime-voice-collector-…-windows.zip`，解压到短一点的路径，比如 `D:\avoc`，双击 `start.bat`。第一次启动要下载约 5 GB，都放在这个文件夹里。下文要运行 `uv run …` 的地方，在 `terminal.bat` 打开的窗口里运行。

**用 git：** 先装 [uv](https://docs.astral.sh/uv/)（它会自动装好合适的 Python），然后：

```bash
git clone https://github.com/raindrops0/anime-voice-collector.git
cd anime-voice-collector
uv sync --locked
```

还需要 [FFmpeg](https://ffmpeg.org/)，界面的第一页可以一键装好。包括怎么装 uv 在内的详细步骤见 [安装](docs/guide/install.zh.md)。

## 加第一集

每一集需要：

- **视频**（`.mkv`、`.mp4` 等）；
- **主字幕**：和对白对得上的字幕（`.ass` 或 `.srt`），最好是原声语言的，每句切成一段；
- 想要的话，再加一份你看得懂的**辅助字幕**，比如译文，标注时用小字显示在每句下面。

在你选的一个文件夹上启动界面（`start.bat` 会替你做这一步）：

```bash
uv run avoc app workspace
```

浏览器里会打开添加一集的表单。选好文件，按「开始」：它会去掉音乐、切出每句台词，并显示进度。字幕偏移（字幕时间和声音差了几秒）会自动测，需要先在 [Hugging Face](https://huggingface.co) 做一次设置，表单里会写出步骤。之后从集数菜单里加下一集。

## 怎么标注

你只需要给想要的角色起名（目标角色）。其他人一律是「不是目标」。

| 视图 | 按键 | 在这里做什么 |
| --- | :---: | --- |
| **分组** | `G` | 从这里开始。听起来像同一个人的台词分在一组：勾出同一个人的台词，再选是谁。 |
| **场景** | `S` | 按顺序列出每句台词，同时播放视频。`Enter` 接受机器的猜测，数字键选角色，`Q` 是「不是目标」，`Shift` + 数字键标为质量低，`X` 放到一边。 |
| **角色** | `O` | 机器分给一个角色的全部台词，最没把握的排在前面。改掉错的，用 `Shift+Enter` 确认其余的，再看看它可能漏掉的台词。 |
| **导出** | `E` | 写出数据集。 |

一个角色确认满 10 句、别人也标了几句「不是目标」以后，机器就开始猜，之后每标一句它都马上重新学。`Z` 撤销，`?` 列出所有按键，「指南」按钮可以再走一遍引导。完整步骤见 [第一份数据集](docs/guide/first-dataset.zh.md)。

## 得到什么

```text
exports/2026-10-24/
├── Teio/
│   ├── ep01_00083.120000_00085.430000.wav
│   └── ...
├── train.list      （只有 GPT-SoVITS：路径|角色|语言|文字）
└── rejected.tsv    （没导出的句子和原因）
```

每段是一个角色的一句台词：只有人声、单声道、采样率和视频一样、音量统一。标了质量低的句子不会导出。导出时每个角色一个文件夹（给 RVC），或者再加上带每句文字的 `train.list`（给 GPT-SoVITS）。

## 常见问题

**能用翻译字幕吗？** 能，但用翻译字幕切的集只能导出声音（RVC 等），导不出 GPT-SoVITS 要的文字。只想看懂的译文请放在辅助字幕里。

**做到一半停了，比如显存不够。** 再加一次同一集，会从停下的地方继续。

**出了问题。** 运行 `uv run avoc doctor`：它会检查显卡、FFmpeg、模型和剩余磁盘空间，缺什么会告诉你怎么补。反馈问题时请附上它的输出。

**能用命令行吗？** 能：`uv run avoc add workspace "Episode 01.mkv" --subs "Episode 01.ja.srt"`。见 `uv run avoc --help` 或 [命令（英文）](docs/reference/commands.md)。

## 支持的平台

已在 Windows 11 + NVIDIA 显卡（RTX 4060 Laptop）上测试。Linux 和 macOS 能安装，但还没测试（[路线图（英文）](docs/ROADMAP.md#platforms)），欢迎在 issue 里反馈。

## 文档

一步一步的指南见[安装](docs/guide/install.zh.md)和[第一份数据集](docs/guide/first-dataset.zh.md)；每个视图的功能、所有命令和用到的说法见 [docs/index.md](docs/index.md)（英文）。想参与的话，见 [CONTRIBUTING.md](docs/CONTRIBUTING.md)（英文）。

## 使用规则

代码以 [MIT 许可证](LICENSE)发布。用它提取出的音频和文字属于原作品的权利人，不在 MIT 许可证的范围内。请在下面的规则内使用本工具：

- ✅ 提取的素材用于个人研究或学习。
- ❌ 不把提取的音频、文字或用它们训练的模型用于任何商业用途。
- ❌ 不用提取的声音冒充角色或声优。

本节如与英文版有出入，以英文版为准。

## 致谢

本项目基于 [audio-separator](https://github.com/nomadkaraoke/python-audio-separator)、[anime-speaker-embedding](https://github.com/litagin02/anime_speaker_embedding)、[ReDimNet](https://github.com/PalabraAI/redimnet2)、[pyannote.audio](https://github.com/pyannote/pyannote-audio) 和 [pysubs2](https://github.com/tkarabela/pysubs2)。试用里的声音由 [VOICEVOX](https://voicevox.hiroshiba.jp/) 生成。
