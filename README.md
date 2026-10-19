# local-tts-lab

Windows CPU 本地固定音色配音工具，支持 Qwen3-TTS 与 ZipVoice 的参考音频克隆、音色档案、试听和备份恢复。

## 安装

使用 Windows 64 位、Python 3.11 或以上。依赖是否可安装取决于所用 Python 版本的预编译包支持；已完成 Python 3.11 和 3.14 的依赖解析检查，不代表所有版本已通过完整配音验收。

在项目目录打开 PowerShell：

```powershell
python install_models.py --engine qwen
```

也可指定解释器：

```powershell
py -3.14 install_models.py --engine qwen
```

安装两种模型使用 `--engine all`，只安装 ZipVoice 使用 `--engine zipvoice`。首次联网下载模型，建议预留 8GB 空间。无需 CUDA 或 PyTorch。

安装器创建 `.venv`，默认使用 `requirements-compatible.txt` 选择兼容依赖，并将实际版本写入本地 `installed-dependencies.txt`。`--pinned-deps` 可切换原测试依赖清单 `requirements.txt`，但其版本未必支持当前 Python。已有虚拟环境的 Python 版本不同会停止安装；切换前请重命名备份旧 `.venv`。

## 使用

1. 安装成功后，双击 `启动本地配音.cmd`。
2. 在“生成配音”的“已保存音色”中选择“预设样本 · Qwen”或“预设样本 · ZipVoice（非商业测试）”。只安装一种模型时，仅导入该模型的样本；安装后未显示，可点击“刷新”。也可在“克隆与音色库”导入自己的参考录音，ZipVoice 需要逐字对应的参考文字。
3. 保存音色档案，输入新文字试听；满意后认可并设为默认。
4. 在“生成配音”选择已保存音色，粘贴文案并生成。结果位于 `outputs/`。

仓库包含 `samples/` 中的两份预设参考 WAV 和对应文字，用于快速体验；启动时会为已安装模型创建独立音色档案，默认标为“待试听”，不会覆盖个人音色或已有默认选择。首次空音色库优先选中 Qwen；满意后可认可并设为默认。演示录音不作为可转授权的商业音色素材，商用请换成自己录制或已获相应授权的参考。

仓库不包含模型权重、原生运行程序、Python 环境、个人音色档案或生成输出。个人参考仍由 `.gitignore` 排除；仅 `samples/` 下的演示 WAV 允许随代码发布。

`downloads.json` 是下载来源和校验清单，`installed-files.json` 是预期模型文件校验清单，均不含模型本体。模型下载完整后可离线生成。首次全新电脑安装仍需按实际日志排查环境差异。

## 许可与来源

底层能力来自 [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)、[llama.cpp](https://github.com/ggml-org/llama.cpp)、[ZipVoice](https://github.com/k2-fsa/ZipVoice) 和 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)。下载模型及运行程序的版本、来源、校验值见下载清单。

本项目所用 ZipVoice Emilia 权重仅供非商业测试。代码、模型、FFmpeg 等二进制依赖以及参考声音的使用和分发许可需分别确认；保存音色档案不代表取得声音授权。
