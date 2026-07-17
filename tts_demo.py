from kokoro import KPipeline
import soundfile as sf


pipeline = KPipeline(lang_code="zh")

text = "啊啊啊啊啊！ 喜欢喜欢！！！"

generator = pipeline(
    text,
    voice="zf_xiaoxiao",
    speed=1.0,
    split_pattern=r"\n+",
)

for i, (graphemes, phonemes, audio) in enumerate(generator):
    sf.write(f"{i}.wav", audio, 24000)
    print(f"已生成 {i}.wav")
