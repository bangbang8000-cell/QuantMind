"""
负分精细决策矩阵：分数范围 × 市值 × 板块 → 精确概率

用户需求：把"微盘做空、大盘错杀"等定性规律落实成具体分数范围 + 概率最大

方法：
- 分数按 0.01 分档（负分全区间）
- 交叉 市值分桶 × 板块
- 计算每个格子：做空收益、下跌概率、上涨概率、样本量
- 找出：做空概率最大的分数范围、负分反弹概率最大的分数范围
"""

import pandas as pd
import numpy as np

OUT = 'negative_score_analysis/cross_year'
full = pd.read_parquet(f'{OUT}/score_long.parquet')
print(f"长表: {len(full)} 行")

# ── 补充市值/板块/行业 ──
p = '/home/zbox/projects/quantmind/data/quantdb/2_base_sector/instrument_detail/instrument_detail.parquet'
det = pd.read_parquet(p, columns=['Symbol', 'Zsz', 'Ltsz', 'rs_hyname'])
det['sym_num'] = det['Symbol'].str.split('.').str[0]
meta = det[['sym_num', 'Zsz', 'rs_hyname']].rename(columns={'sym_num': 'symbol', 'Zsz': 'mv', 'rs_hyname': 'industry'})

def market_board(sym):
    s = sym.split('.')[0]
    if s.startswith(('688', '689')): return '科创板'
    if s.startswith('920') or s.startswith(('4', '8')): return '北交所'
    if s.startswith('3'): return '创业板'
    if s.startswith(('6', '9')): return '沪主板'
    if s.startswith(('0', '2')): return '深主板'
    return '其他'
meta['board'] = meta['symbol'].map(market_board)

full = full.merge(meta, on='symbol', how='left')
print(f"merge后: {full['mv'].notna().sum()} 有市值, 负分+ret5+市值: "
      f"{(full['score']<0) & full['ret5'].notna() & full['mv'].notna()}")

# ── 只取负分且有收益的样本 ──
neg = full[(full['score'] < 0) & full['ret5'].notna() & full['mv'].notna()].copy()
neg['mv'] = pd.to_numeric(neg['mv'], errors='coerce')
neg = neg.dropna(subset=['mv'])
print(f"负分有效样本: {len(neg)}")

# 市值分桶（亿元）
def size_bucket(yi):
    if yi < 30: return '微盘<30亿'
    if yi < 100: return '小盘30-100亿'
    if yi < 300: return '中盘100-300亿'
    if yi < 1000: return '大盘300-1000亿'
    return '超大盘>1000亿'
neg['size'] = neg['mv'].map(size_bucket)

# 分数按 0.01 分档
neg['score_bin'] = np.floor(neg['score'] * 100).astype(int) / 100  # -0.31, -0.30, ...

# ══════════════════════════════════════════════════════════════
# A. 分数 × 市值 全网格：下跌/上涨概率
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 78)
print("A. 负分分数档 × 市值 → 下跌概率/上涨概率 (T+5)")
print("=" * 78)
# 只看 -0.20 以上的较极端负分（分档更多样本）
grid_rows = []
for (sb, sz), grp in neg.groupby(['score_bin', 'size']):
    if len(grp) < 200:
        continue
    arr = grp['ret5']
    grid_rows.append({
        '分数档': sb, '市值': sz, '样本': len(grp),
        'T+5均收%': round(arr.mean() * 100, 2),
        '下跌概率%': round((arr < 0).mean() * 100, 1),
        '上涨概率%': round((arr > 0).mean() * 100, 1),
    })
grid = pd.DataFrame(grid_rows)
grid.to_csv(f'{OUT}/decision_matrix_size.csv', index=False, encoding='utf-8-sig')

# 打印精简版：每个市值桶，最值得做空的分数段（下跌概率最高的前3档）+ 最值得关注的分数段
print("\n[各市值桶 · 做空概率最高的分数段]")
for sz in ['微盘<30亿', '小盘30-100亿', '中盘100-300亿', '大盘300-1000亿', '超大盘>1000亿']:
    sub = grid[grid['市值'] == sz]
    if sub.empty:
        continue
    top = sub.sort_values('下跌概率%', ascending=False).head(3)
    print(f"\n  {sz}:")
    for _, r in top.iterrows():
        print(f"    分数{r['分数档']:+.2f}: 下跌概率{r['下跌概率%']:.1f}%  均收{r['T+5均收%']:+.2f}%  n={int(r['样本'])}")

print("\n[各市值桶 · 负分反弹概率最高的分数段]")
for sz in ['微盘<30亿', '小盘30-100亿', '中盘100-300亿', '大盘300-1000亿', '超大盘>1000亿']:
    sub = grid[grid['市值'] == sz]
    if sub.empty:
        continue
    top = sub.sort_values('上涨概率%', ascending=False).head(3)
    print(f"\n  {sz}:")
    for _, r in top.iterrows():
        print(f"    分数{r['分数档']:+.2f}: 上涨概率{r['上涨概率%']:.1f}%  均收{r['T+5均收%']:+.2f}%  n={int(r['样本'])}")

# ══════════════════════════════════════════════════════════════
# B. 分数 × 板块：科创板 vs 主板 关键分界线
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 78)
print("B. 分数档 × 板块 → 下跌概率 (T+5)")
print("=" * 78)
grid_b = []
for (sb, bd), grp in neg.groupby(['score_bin', 'board']):
    if len(grp) < 200:
        continue
    arr = grp['ret5']
    grid_b.append({
        '分数档': sb, '板块': bd, '样本': len(grp),
        'T+5均收%': round(arr.mean() * 100, 2),
        '下跌概率%': round((arr < 0).mean() * 100, 1),
        '上涨概率%': round((arr > 0).mean() * 100, 1),
    })
grid_b = pd.DataFrame(grid_b)
grid_b.to_csv(f'{OUT}/decision_matrix_board.csv', index=False, encoding='utf-8-sig')

# 关键对比：科创板 vs 沪主板，逐分数档
print("\n[科创板 vs 沪主板 逐档下跌概率]")
kcb = grid_b[grid_b['板块'] == '科创板'].set_index('分数档')
sh = grid_b[grid_b['板块'] == '沪主板'].set_index('分数档')
common = sorted(set(kcb.index) & set(sh.index))
print(f"{'分数':>6} {'科创下跌%':>9} {'科创均收%':>9} {'沪主板下跌%':>10} {'沪主板均收%':>10}  差幅")
for sb in common:
    k = kcb.loc[sb]; s = sh.loc[sb]
    diff = s['下跌概率%'] - k['下跌概率%']
    print(f"{sb:+6.2f} {k['下跌概率%']:>8.1f}% {k['T+5均收%']:>+8.2f} {s['下跌概率%']:>9.1f}% {s['T+5均收%']:>+9.2f}  {diff:>+.1f}pp")

# ══════════════════════════════════════════════════════════════
# C. 最优做空阈值：分数 ≤ X 的下跌概率曲线
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 78)
print("C. 分数阈值扫描：分数 ≤ X 的下跌概率（做空概率最大化）")
print("=" * 78)
thr_rows = []
for sz in ['微盘<30亿', '小盘30-100亿', '中盘100-300亿', '大盘300-1000亿', '超大盘>1000亿', '全部']:
    sub = neg if sz == '全部' else neg[neg['size'] == sz]
    for x in [-0.05, -0.06, -0.08, -0.10, -0.12, -0.15, -0.20]:
        s2 = sub[sub['score'] <= x]
        if len(s2) < 100:
            continue
        arr = s2['ret5']
        thr_rows.append({
            '市值': sz, '分数≤': x, '样本': len(s2),
            '下跌概率%': round((arr < 0).mean() * 100, 1),
            '做空收益%': round(-arr.mean() * 100, 2),
            '上涨概率%': round((arr > 0).mean() * 100, 1),
        })
thr = pd.DataFrame(thr_rows)
thr.to_csv(f'{OUT}/threshold_scan.csv', index=False, encoding='utf-8-sig')
print(f"{'市值':<14}{'分数≤':>7}{'样本':>7}{'下跌概率%':>10}{'做空收益%':>10}")
for _, r in thr.iterrows():
    if r['分数≤'] in (-0.08, -0.10, -0.15):
        print(f"{r['市值']:<14}{r['分数≤']:>+7.2f}{int(r['样本']):>7}{r['下跌概率%']:>9.1f}%{r['做空收益%']:>+9.2f}%")

# ══════════════════════════════════════════════════════════════
# D. 最优"负分反弹"区间：负分中上涨概率最高的连续区间
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 78)
print("D. 负分中上涨概率最高的分数段（错杀机会）")
print("=" * 78)
# 大市值 + 负分，按分数档看上涨概率
big = neg[neg['size'].isin(['大盘300-1000亿', '超大盘>1000亿'])]
big_stats = big.groupby('score_bin').agg(
    样本=('ret5', 'count'), 均收=('ret5', 'mean'),
    上涨概率=('ret5', lambda x: (x > 0).mean() * 100),
).reset_index()
big_stats = big_stats[big_stats['样本'] >= 100]
print(f"\n[大盘+超大盘 负分 逐档]")
print(f"{'分数':>6} {'样本':>7} {'均收%':>8} {'上涨概率%':>9}")
for _, r in big_stats.sort_values('score_bin', ascending=False).iterrows():
    flag = ' ◀ 上涨概率>50%' if r['上涨概率'] > 50 else ''
    print(f"{r['score_bin']:+6.2f} {int(r['样本']):>7} {r['均收']*100:>+7.2f} {r['上涨概率']:>8.1f}%{flag}")

print(f"\n所有矩阵已保存到 {OUT}/decision_matrix_*.csv 和 threshold_scan.csv")
