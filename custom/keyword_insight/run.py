# custom/keyword_insight/run.py
import sys
from custom.keyword_insight.generator import Generator


if __name__ == "__main__":
    if len(sys.argv) > 1:
        keyword = sys.argv[1]
        Generator().run_all(keyword)