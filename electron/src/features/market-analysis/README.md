# 市场分析模块 (Market Analysis)

## 模块说明
市场分析功能板块，提供全市场大盘全景、多周期资金流向、板块/个股资金链、申万一级行业热力矩形图谱等可视化与交互分析。

## 核心组件与页面
- `pages/MarketAnalysisPage.tsx`: 市场分析主页面组件，包含顶部 Banner 顶栏、核心指数快照、功能 Tab 导航以及资金流向下钻面板。
- `components/ShenwanHeatmapChart.tsx`: 申万一级分类矩形树图 (Treemap) 热力图组件。
- `components/CapitalFlowHorizontalBarChart.tsx`: 多周期（1日/3日/5日/10日/20日）横向柱状图图表组件。
- `components/CapitalFlowSankeyChart.tsx`: 主力与散户资金流动全景桑基图组件。
- `components/MarketBreadthCard.tsx`: 市场情绪温度计与赚钱效应卡片。
- `components/StockMoneyFlowTable.tsx`: 个股资金流向排行榜表格。
- `components/TagLookupPanel.tsx`: 概念与行业标签双向查询面板。

## 最近优化
- 规范展示文案，将“申万一级 31 个行业”统一简化命名为“申万一级分类”。
- 采用容器原生 CSS `mask-image` 线性渐隐方案，滚动时在顶底边缘产生自然平滑渐隐，保持精致视觉过渡与流畅交互。
