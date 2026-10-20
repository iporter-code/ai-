"""Print reproducible corpus size statistics under several counting conventions."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("| 文件 | 总字符 | 非空白字符 | 纯汉字 | 汉字+英文/数字串 |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for path in sorted(RAW.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        total = len(text)
        nonspace = len(re.sub(r"\s", "", text))
        han = len(re.findall(r"[\u4e00-\u9fff]", text))
        words = len(re.findall(r"[A-Za-z0-9_]+", text))
        print(f"| `{path.name}` | {total} | {nonspace} | {han} | {han + words} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
