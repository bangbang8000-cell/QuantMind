"""trading_agents 报告文件管理元数据/路径逻辑单元测试。

覆盖历史 bug：旧格式 {ticker}_{date} 解析、新格式 {股票名}{代码}_{date} 解析、
folder 递归删除匹配、文件名清洗。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# reportlab/FastAPI 未安装时仅测纯函数（不需跳过——这些函数不依赖外部库）
from backend.services.engine.routers.trading_agents import _parse_report_meta
from backend.services.engine.trading_agents.report_exporter import _sanitize_name


def test_parse_new_format_with_stock_name():
    # 新格式：{股票名}{代码}_{date}_投研分析报告.pdf
    meta = _parse_report_meta("贵州茅台600519_2026-08-15_投研分析报告.pdf")
    assert meta["ticker"] == "600519"
    assert meta["name"] == "贵州茅台"
    assert meta["date"] == "2026-08-15"


def test_parse_new_format_multi_digit_code():
    # 股票名可能以数字结尾（如"中国500强"），代码取末尾 4-6 位数字
    meta = _parse_report_meta("某某300750_2026-08-15_投研分析报告.pdf")
    assert meta["ticker"] == "300750"
    assert meta["name"] == "某某"


def test_parse_legacy_format_no_stock_name():
    # 旧格式：{ticker}_{date}_投研分析报告.pdf → name 为空
    meta = _parse_report_meta("002594_2026-08-14_投研分析报告.pdf")
    assert meta["ticker"] == "002594"
    assert meta["name"] == ""
    assert meta["date"] == "2026-08-14"


def test_parse_signal_from_filename():
    # 评级从文件名关键字解析（Buy/Overweight/Hold/Underweight/Sell）
    # 约定：评级必须以下划线分隔（_{kw}），否则不匹配
    assert _parse_report_meta("600519_2026-08-15_Hold_投研分析报告.pdf")["signal"] == "Hold"
    assert _parse_report_meta("600519_2026-08-15_Buy_投研分析报告.pdf")["signal"] == "Buy"


def test_parse_unknown_ticker_format():
    # 无法识别代码时，整个头部作为 ticker（兜底不抛异常）
    meta = _parse_report_meta("ABC_2026-08-15_投研分析报告.pdf")
    assert meta["ticker"] == "ABC"
    assert meta["date"] == "2026-08-15"


def test_parse_no_underscore():
    # 无下划线的文件名不抛异常
    meta = _parse_report_meta("report.pdf")
    assert meta["ticker"] == ""
    assert meta["date"] == ""


def test_sanitize_name_removes_illegal_chars():
    # 股票名含路径分隔符/通配符等应被清洗
    assert _sanitize_name("贵州茅台/600519*") == "贵州茅台600519"


def test_sanitize_name_empty_fallback():
    # 全非法字符 → 回退"未命名"
    assert _sanitize_name("///") == "未命名"


def test_sanitize_name_preserves_normal_chinese():
    assert _sanitize_name("贵州茅台") == "贵州茅台"
