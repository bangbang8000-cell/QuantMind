"""
市值维度：负分反弹与市值大小的关系（向量化，merge 替代 lambda map）

发现科创板负分抗跌后，进一步验证市值维度——负分反弹是否与市值有关。
"""
import pandas as pd
import numpy as np

full = pd.read_parquet('negative_score_analysis/cross_year/score_long.parquet')
print(f"长表: {len(full)} 行")

# 加载市值（Zsz 总市值, 单位亿元）
p = '/home/zbox/projects/quantmind/data/quantdb/2_base_sector/instrument_detail/instrument_detail.parquet'
det = pd.read_parquet(p, columns=['Symbol', 'Zsz', 'Ltsz', 'Name'])
det['sym_num'] = det['Symbol'].str.split('.').str[0]
mv = det[['sym_num', 'Zsz', 'Ltsz']].rename(columns={'sym_num': 'symbol'})
mv['Zsz'] = pd.to_numeric(mv['Zsz'], errors='coerce')
mv['Ltsz'] = pd.to_numeric(mv['Ltsz'], errors='coerce')
print(f"市值表: {len(mv)} 只, Zsz非空 {mv['Zsz'].notna().sum()}")

# merge 而非 map
full = full.merge(mv, on='symbol', how='left')
print(f"merge后 Zsz非空: {full['Zsz'].notna().sum()}")

# 补板块/行业
import sys
sys.path.insert(0, '.')
from cross_year_loader import load_industry
ind = load_industry()
full = full.merge(ind[['sym_num', 'board', 'industry']].rename(columns={'sym_num': 'symbol'}), on='symbol', how='left')

neg = full[(full['score'] < 0) & full['ret5'].notna() & full['Zsz'].notna()].copy()
print(f"\n负分且有市值: {len(neg)}")

def size_bucket(yi):
    if yi < 30: return '微盘(<30亿)'
    if yi < 100: return '小盘(30-100亿)'
    if yi < 300: return '中盘(100-300亿)'
    if yi < 1000: return '大盘(300-1000亿)'
    return '超大盘(>1000亿)'

neg['size'] = neg['Zsz'].map(size_bucket)

print("\n=== 负分股票 T+5 按市值分桶 ===")
for sz, grp in neg.groupby('size'):
    print(f"  {sz:<16}: n={len(grp):>8}  T+5均收{grp['ret5'].mean()*100:+.3f}%  "
          f"上涨比例{(grp['ret5']>0).mean()*100:.1f}% 中位{grp['ret5'].median()*100:+.3f}%")

print("\n=== 极端负分[-0.15,-0.31) 按市值分桶 ===")
ext = neg[(neg['score'] >= -0.31) & (neg['score'] < -0.15)]
for sz, grp in ext.groupby('size'):
    if len(grp) < 100: continue
    print(f"  {sz:<16}: n={len(grp):>7}  T+5均收{grp['ret5'].mean()*100:+.3f}%  "
          f"上涨比例{(grp['ret5']>0).mean()*100:.1f}%")

# 板块 x 市值
print("\n=== 科创板负分按市值 ===")
kcb = neg[neg['board'] == '科创板']
for sz, grp in kcb.groupby('size'):
    if len(grp) < 100: continue
    print(f"  {sz:<16}: n={len(grp):>7}  T+5均收{grp['ret5'].mean()*100:+.3f}%  "
          f"上涨比例{(grp['ret5']>0).mean()*100:.1f}%")

# 极端负分内，市值是否有区分
print("\n=== 极端负分内：市值对做空的影响 ===")
ext_small = ext[ext['size'].isin(['微盘(<30亿)', '小盘(30-100亿)'])]
ext_big = ext[ext['size'].isin(['大盘(300-1000亿)', '超大盘(>1000亿)'])]
print(f"  小市值极端负分: n={len(ext_small)}  T+5均收{ext_small['ret5'].mean()*100:+.3f}%  上涨比例{(ext_small['ret5']>0).mean()*100:.1f}%")
print(f"  大市值极端负分: n={len(ext_big)}  T+5均收{ext_big['ret5'].mean()*100:+.3f}%  上涨比例{(ext_big['ret5']>0).mean()*100:.1f}%")
