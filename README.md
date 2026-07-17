# Kokoro 中文 TTS 小作业

本分支 `feat/lzy-tts` 配置了一个轻量化中文文本转语音示例，当前方法使用 `kokoro` 的 `KPipeline` 直接生成 wav 音频。

## 当前方法

核心代码在 `tts_demo.py`：

```python
from kokoro import KPipeline
import soundfile as sf

pipeline = KPipeline(lang_code="zh")

text = "你好，这是一个轻量化文本转语音的小作业测试。"

generator = pipeline(
    text,
    voice="zf_xiaoxiao",
    speed=1.0,
    split_pattern=r"\n+",
)

for i, (graphemes, phonemes, audio) in enumerate(generator):
    sf.write(f"{i}.wav", audio, 24000)
```

说明：

- `lang_code="zh"` 表示中文。
- `voice="zf_xiaoxiao"` 是中文女声。
- 输出文件默认保存为 `0.wav`、`1.wav` 等。
- 生成的 `.wav` 文件已加入 `.gitignore`，不会提交到仓库。

可选中文声音：

- 女声：`zf_xiaobei`、`zf_xiaoni`、`zf_xiaoxiao`、`zf_xiaoyi`
- 男声：`zm_yunjian`、`zm_yunxi`、`zm_yunxia`、`zm_yunyang`

## 安装位置

按要求，本项目的新环境和模型缓存都放在当前 E 盘项目目录下，不安装到 C 盘：

- Python 虚拟环境：`E:\summer-hw\.venv`
- pip 缓存：`E:\summer-hw\.cache\pip`
- Hugging Face / Kokoro 模型缓存：`E:\summer-hw\.cache\huggingface`
- Torch 缓存：`E:\summer-hw\.cache\torch`
- 临时目录：`E:\summer-hw\.cache\temp`

注意：创建虚拟环境时使用的是机器上已经存在的 Python 解释器；项目新增依赖安装在 `E:\summer-hw\.venv`。

## 启动方式

在 PowerShell 中运行：

```powershell
cd E:\summer-hw
.\run.ps1
```

如果 PowerShell 执行策略阻止脚本运行，可以用：

```powershell
powershell -ExecutionPolicy Bypass -File E:\summer-hw\run.ps1
```

如果需要重新安装或补齐依赖：

```powershell
cd E:\summer-hw
.\setup.ps1
```

建议始终使用 `run.ps1` 启动，因为脚本会先设置缓存路径，避免模型和临时文件写到 C 盘。

## 修改要朗读的文本

编辑 `tts_demo.py` 里的 `text`：

```python
text = "这里换成你想合成的中文内容。"
```

换声音时修改 `voice`：

```python
voice="zf_xiaoxiao"
```

## Fine-tuning 怎么做

Kokoro 当前更适合作为轻量推理模型使用。这个项目安装的 `kokoro` Python 包主要面向直接合成语音，不提供很完整的一键微调流程；如果目标是“用自己的声音”或“训练一个特定音色”，直接 fine-tune Kokoro 并不算方便。

更现实的路线有三种：

1. 先用 Kokoro 完成作业演示
   - 优点：最轻、安装快、代码短。
   - 适合：课程小作业、快速 demo、中文 TTS 基础展示。

2. 用支持 zero-shot / voice clone 的模型
   - 例如 CosyVoice、F5-TTS。
   - 准备一小段参考音频，就能尝试克隆音色，不一定要真正训练。
   - 适合：想快速做“像某个声音”的效果。

3. 真正 fine-tune
   - 推荐优先看 F5-TTS 或 CosyVoice 这类有训练脚本和社区教程的项目。
   - 一般需要准备成对数据：音频、转写文本、说话人信息。
   - 还需要 GPU、较干净的数据集、训练配置和验证集。
   - 如果只是在普通笔记本 CPU 上做，训练会比较慢，不推荐从 fine-tuning 起步。

如果后续要尝试 F5-TTS 或 CosyVoice，建议新建独立环境，不要和当前 Kokoro 环境混装：

```text
E:\summer-hw\.venv-kokoro
E:\summer-hw\.venv-f5tts
E:\summer-hw\.venv-cosyvoice
```

这样能减少 PyTorch、音频库和模型依赖互相冲突的概率。
