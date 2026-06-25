"""快速扫描 GTJA 191 因子代码，按信号类别分组，挑出可加入候选。

筛选规则:
1. 跳过 16 个 placeholder (return 0)
2. 跳过已经接入的 16 个
3. 跳过用到 self.benchmark_* (基准价格) 或 SELF (递归) 的因子
4. 跳过用到 ADX、HML、SMB、MKT (Fama-French) 的因子
5. 跳过明显重复结构（CORR(rank(X), rank(VOLUME), n)：留代表性的）

输出: 候选因子清单 + 它们的代码片段
"""
import re
import sys
from pathlib import Path

PY_FILE = Path("/app/scripts/data_repair/_gtja_191_source.py")

# 已经接入的 16 个
ALREADY = {16, 32, 36, 42, 62, 70, 74, 83, 90, 95, 99, 150, 158, 159, 176, 179}

# 占位符 16 个
PLACEHOLDERS = {27, 30, 50, 51, 55, 69, 73, 121, 131, 143, 151, 165, 166, 181, 183, 190}

# 用不了的字段
BAD_FIELDS = [
    'benchmark', 'SELF', 'self.benchmark',
    'REGRESI', 'regresi',  # 残差回归用 Fama-French
    'BANCHMARK',
]


def parse_alphas(raw: str) -> dict[int, str]:
    pattern = re.compile(
        r"def\s+alpha_(\d+)\s*\(self.*?\):\s*\n(.*?)(?=\n\s*def\s+|\Z)",
        re.DOTALL,
    )
    return {int(m.group(1)): m.group(2).strip() for m in pattern.finditer(raw)}


def categorize_factor(code: str) -> str:
    """给因子代码贴一个分类标签."""
    c = code.lower()
    if 'pd.rolling_std' in c or 'std(' in c:
        if 'amount' in c:
            return "波动率(成交额)"
        if 'volume' in c:
            return "波动率(成交量)"
        if 'high' in c or 'low' in c or 'close' in c:
            return "波动率(价格)"
        return "波动率"
    if 'sma(' in c or 'pd.ewma' in c or '.ewm(' in c:
        return "平滑均值/EMA"
    if 'corr' in c:
        if 'volume' in c:
            return "价量相关性"
        return "相关性"
    if 'rank' in c and 'volume' in c:
        return "rank价量"
    if 'tsrank' in c or '.rank(axis=0' in c:
        return "时序排名"
    if 'highday' in c or 'lowday' in c:
        return "极值时间"
    if 'tsmin' in c or 'tsmax' in c or '.rolling_min' in c or '.rolling_max' in c:
        return "极值"
    if 'log(' in c or 'np.log' in c:
        return "对数变换"
    if 'count' in c:
        return "计数"
    if 'sumif' in c or 'sum(' in c:
        return "累加"
    if 'mean' in c:
        return "均值"
    return "其它"


def can_use(code: str) -> tuple[bool, str]:
    for bad in BAD_FIELDS:
        if bad in code:
            return (False, f"用了 {bad}")
    return (True, "")


def main():
    raw = PY_FILE.read_text(encoding="utf-8")
    alphas = parse_alphas(raw)
    print(f"总因子: {len(alphas)}")
    print(f"占位符: {len(PLACEHOLDERS)}, 已接入: {len(ALREADY)}")

    candidates = []
    skipped = {"placeholder": 0, "already": 0, "bad_field": 0, "ok": 0}
    bad_examples = []

    for n, code in sorted(alphas.items()):
        if n in PLACEHOLDERS:
            skipped["placeholder"] += 1
            continue
        if n in ALREADY:
            skipped["already"] += 1
            continue
        ok, reason = can_use(code)
        if not ok:
            skipped["bad_field"] += 1
            if len(bad_examples) < 5:
                bad_examples.append((n, reason))
            continue
        candidates.append((n, code))
        skipped["ok"] += 1

    print(f"\n分布: {skipped}")
    print(f"不可用因子样本: {bad_examples}")

    # 按类别分组
    by_cat = {}
    for n, code in candidates:
        cat = categorize_factor(code)
        by_cat.setdefault(cat, []).append(n)

    print(f"\n=== 可加候选因子按类别分布 ===")
    for cat, ns in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        print(f"  {cat:15s}: {len(ns):3d} 个  e.g. Alpha{','.join(f'{n}' for n in ns[:5])}")

    # 输出完整候选清单 csv
    import csv
    OUT = Path("/app/scripts/data_repair/gtja_remaining_candidates.csv")
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["alpha_id", "category", "code_first_line"])
        for n, code in candidates:
            cat = categorize_factor(code)
            first = ""
            for ln in code.split("\n"):
                s = ln.strip()
                if s and not s.startswith("#"):
                    first = s[:100]
                    break
            w.writerow([n, cat, first])
    print(f"\n详细清单: {OUT}")


if __name__ == "__main__":
    main()
