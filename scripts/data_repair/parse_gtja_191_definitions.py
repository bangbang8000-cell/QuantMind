"""一次性脚本：从 OCR 后的国泰君安研报 markdown 解析出 191 个 Alpha 公式定义。

输出: scripts/data_repair/gtja_191_definitions.csv
列: alpha_id, formula_ocr, has_impl_in_gtja_py, impl_excerpt

数据源:
1. /workspace/dell/下载/国泰君安－基于短周期价量特征的多因子选股体系.md (OCR'd)
2. /home/dell/桌面/sata_drive/A_H/Alpha 101 & GTJA 191(1) (1)/Alpha 101 & GTJA 191/GTJA_Alpha191.py
"""
from __future__ import annotations

import csv
import re
from pathlib import Path


MD_FILE = Path("/workspace/dell/下载/国泰君安－基于短周期价量特征的多因子选股体系.md")
PY_FILE = Path("/home/dell/桌面/sata_drive/A_H/Alpha 101 & GTJA 191(1) (1)/Alpha 101 & GTJA 191/GTJA_Alpha191.py")
OUT_CSV = Path("/workspace/quantmind/scripts/data_repair/gtja_191_definitions.csv")


def parse_md_formulas() -> dict[int, str]:
    """从 markdown 表格里解析 Alpha → formula 映射。"""
    raw = MD_FILE.read_text(encoding="utf-8")

    # 表格里每个因子都是: <td>AlphaN</td><td>formula</td>
    # 用 regex 提取这种 cell pair
    pattern = re.compile(
        r"<td[^>]*>\s*Alpha\s*(\d+)\s*</td>\s*<td[^>]*>(.*?)</td>",
        re.IGNORECASE | re.DOTALL,
    )
    results = {}
    for m in pattern.finditer(raw):
        idx = int(m.group(1))
        formula = m.group(2).strip()
        # HTML 解码
        formula = (formula.replace("&gt;", ">")
                          .replace("&lt;", "<")
                          .replace("&amp;", "&")
                          .replace("&quot;", '"'))
        # 删多余空白
        formula = re.sub(r"\s+", " ", formula).strip()
        results[idx] = formula

    # 注意：181, 190 是裸的"Alpha181 ..."形式（OCR 错位丢了 <td>），再扫一遍
    line_pattern = re.compile(r"^Alpha\s*(\d+)\s+(.+)$", re.MULTILINE)
    for m in line_pattern.finditer(raw):
        idx = int(m.group(1))
        if idx not in results:
            formula = m.group(2).strip()
            results[idx] = formula

    return results


def parse_py_impls() -> dict[int, str]:
    """从 GTJA_Alpha191.py 解析每个 alpha 函数的代码片段。

    返回: {1: "...code...", 2: "...code..."}; return_0 的 placeholder 也算 "实现"，
    后续我们标记它。
    """
    raw = PY_FILE.read_text(encoding="utf-8")
    # 切分: def alpha_NNN(self): ... 下一个 def 之前
    pattern = re.compile(
        r"def\s+alpha_(\d+)\s*\(self.*?\):\s*\n(.*?)(?=\n\s*def\s+|\Z)",
        re.DOTALL,
    )
    out = {}
    for m in pattern.finditer(raw):
        idx = int(m.group(1))
        body = m.group(2).rstrip()
        out[idx] = body
    return out


def is_return_zero(body: str) -> bool:
    """判断 body 是不是 placeholder（只 return 0 / return）"""
    # 去注释行
    stripped = "\n".join(
        ln for ln in body.split("\n")
        if ln.strip() and not ln.strip().startswith("#")
    )
    # 如果代码量很小且包含 return 0 / pass
    if "return 0" in stripped and len(stripped) < 100:
        return True
    return False


def main():
    md_map = parse_md_formulas()
    py_map = parse_py_impls()

    print(f"OCR 解析到 alpha 数: {len(md_map)}")
    print(f"Python 代码里 alpha 数: {len(py_map)}")

    all_ids = sorted(set(md_map) | set(py_map))
    print(f"合计独立 alpha 数: {len(all_ids)} (min={min(all_ids)} max={max(all_ids)})")

    # 缺失分析
    missing_in_md = [i for i in all_ids if i not in md_map]
    missing_in_py = [i for i in all_ids if i not in py_map]
    placeholder_py = [i for i in py_map if is_return_zero(py_map[i])]

    print(f"\nMD 缺失（代码有公式无）: {len(missing_in_md)}: {missing_in_md}")
    print(f"PY 缺失（公式有代码无）: {len(missing_in_py)}: {missing_in_py}")
    print(f"PY 是 return 0 占位的: {len(placeholder_py)}: {placeholder_py}")

    # 写 CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["alpha_id", "formula_ocr", "py_status", "py_first_line"])
        for i in sorted(all_ids):
            formula = md_map.get(i, "")
            py = py_map.get(i, "")
            if not py:
                py_status = "missing"
                py_first = ""
            elif is_return_zero(py):
                py_status = "placeholder"
                py_first = "return 0"
            else:
                py_status = "implemented"
                # 取首个非空非注释行
                first = ""
                for ln in py.split("\n"):
                    s = ln.strip()
                    if s and not s.startswith("#"):
                        first = s[:80]
                        break
                py_first = first
            w.writerow([i, formula, py_status, py_first])

    print(f"\n输出: {OUT_CSV}")

    # 概览统计
    print("\n=== 概览 ===")
    statuses = {}
    for i in all_ids:
        py = py_map.get(i, "")
        if not py:
            s = "py_missing"
        elif is_return_zero(py):
            s = "py_placeholder"
        else:
            s = "py_implemented"
        statuses[s] = statuses.get(s, 0) + 1
    for s, c in sorted(statuses.items()):
        print(f"  {s:18s}: {c}")


if __name__ == "__main__":
    main()
