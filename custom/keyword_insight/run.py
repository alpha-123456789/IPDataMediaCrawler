# custom/keyword_insight/run.py
import sys
from custom.keyword_insight.generator import Generator

if __name__ == "__main__":
    # 用法：
    #   uv run .\custom\keyword_insight\run.py 猴子警长
    #   uv run .\custom\keyword_insight\run.py 猴子警长 --llm
    #   uv run .\custom\keyword_insight\run.py 猴子警长 --llm --ref reference.txt

    args = sys.argv[1:]
    use_llm = "--llm" in args

    # 加载参考内容
    reference_content = ""
    if "--ref" in args:
        ref_idx = args.index("--ref")
        if ref_idx + 1 < len(args):
            ref_path = args[ref_idx + 1]
            try:
                with open(ref_path, encoding="utf-8") as f:
                    reference_content = f.read().strip()
                print(f"[参考资料] 已加载：{ref_path}（{len(reference_content)} 字）")
            except Exception as e:
                print(f"[警告] 参考文件读取失败：{e}")

    # 过滤掉 flag 和 ref 路径，剩下的第一个参数是关键词
    skip_next = False
    keywords_args = []
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a == "--ref":
            skip_next = True
        elif not a.startswith("--"):
            keywords_args.append(a)

    keyword = keywords_args[0] if keywords_args else None

    Generator().run_all(keyword, use_llm=use_llm, reference_content=reference_content)
