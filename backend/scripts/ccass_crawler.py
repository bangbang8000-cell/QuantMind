"""
HKEX 中央结算系统持股数据爬虫 v6.2 (自动更新版)
作者: 量化交易 Python 专家系统
Python 版本要求: 3.9+
依赖: requests, pandas, beautifulsoup4, lxml, aiohttp, akshare, yfinance

核心更新 v6.2：
1. ✅ 自动从 AkShare 获取最新港股列表（包含新股 IPO）
2. ✅ 自动从 yfinance 获取交易日历（无需手动维护节假日）
3. ✅ 启动时自动刷新，断点续传避免重复下载
"""

import asyncio
import aiohttp
import requests
import pandas as pd
import logging
import re
import time
import random
import os
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path
import ssl
from typing import Optional, Tuple, List, Dict, Set
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from urllib3.poolmanager import PoolManager
import calendar
import stat

# --- 外部数据源 ---
import akshare as ak
import yfinance as yf

# --- 全局配置 ---
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 🔥 安全的目录创建函数 ---
def safe_mkdir(path: Path, mode: int = 0o755) -> Tuple[bool, Optional[str]]:
    """
    安全创建目录（带权限检查）
    
    Args:
        path: 目录路径
        mode: 权限模式（默认 755）
    
    Returns:
        (是否成功, 错误信息)
    """
    try:
        # 检查父目录是否可写
        parent = path.parent
        if parent.exists() and not os.access(parent, os.W_OK):
            return False, f"父目录不可写: {parent}"
        
        # 创建目录
        path.mkdir(parents=True, exist_ok=True, mode=mode)
        
        # 验证是否可写
        if not os.access(path, os.W_OK):
            return False, f"目录创建成功但不可写: {path}"
        
        return True, None
        
    except PermissionError as e:
        return False, f"权限错误: {e}"
    except Exception as e:
        return False, f"创建失败: {e}"


# --- 日志配置 v6.1 ---
def setup_logging() -> logging.Logger:
    """
    配置日志系统 v6.1
    """
    logger = logging.getLogger("HKEX_Quant")
    logger.setLevel(logging.DEBUG)  # 🔧 提升为 DEBUG 级别用于诊断
    
    # 清除已有的处理器
    logger.handlers.clear()
    
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 强制使用脚本所在目录
    script_dir = Path(__file__).parent.resolve()
    log_dir = script_dir / "log"
    current_month = datetime.now().strftime("%Y%m")
    log_month_dir = log_dir / current_month
    
    success, error_msg = safe_mkdir(log_month_dir)
    
    if success:
        log_filename = log_month_dir / f"hkex_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        try:
            file_handler = logging.FileHandler(log_filename, encoding='utf-8')
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
            logger.addHandler(file_handler)
            print(f"📝 日志文件: {log_filename.relative_to(script_dir)}")
        except Exception as e:
            print(f"⚠️  无法创建日志文件: {e}")
    else:
        print(f"⚠️  无法创建月份目录: {error_msg}")
        
        success_root, error_msg_root = safe_mkdir(log_dir)
        if success_root:
            log_filename = log_dir / f"hkex_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            try:
                file_handler = logging.FileHandler(log_filename, encoding='utf-8')
                file_handler.setFormatter(formatter)
                file_handler.setLevel(logging.DEBUG)
                logger.addHandler(file_handler)
                print(f"📝 日志文件（降级）: {log_filename.relative_to(script_dir)}")
            except Exception as e:
                print(f"⚠️  无法创建日志文件: {e}")
        else:
            print(f"⚠️  无法创建 log 目录: {error_msg_root}")
            print("⚠️  日志将仅输出到控制台")
    
    # 控制台处理器（INFO 级别）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)  # 控制台仅显示 INFO 及以上
    logger.addHandler(console_handler)
    
    return logger


# 初始化日志
logger = setup_logging()


# --- 查询记录管理器 v6.1 ---
class QueryRecordManager:
    """查询记录管理器 v6.1"""
    
    def __init__(self, record_dir: str = "log"):
        script_dir = Path(__file__).parent.resolve()
        self.record_dir = script_dir / record_dir
        self.record_file = None
        self.records = {}
        
        self._init_record_storage()
    
    def _init_record_storage(self) -> None:
        """初始化记录存储（带降级处理）"""
        current_month = datetime.now().strftime("%Y%m")
        
        month_dir = self.record_dir / current_month
        success, error_msg = safe_mkdir(month_dir)
        
        if success:
            self.record_file = month_dir / "query_records.json"
            logger.info(f"📋 查询记录文件: {self.record_file.relative_to(Path(__file__).parent)}")
        else:
            logger.warning(f"⚠️  无法创建月份目录: {error_msg}")
            
            success_root, error_msg_root = safe_mkdir(self.record_dir)
            if success_root:
                self.record_file = self.record_dir / "query_records.json"
                logger.info(f"📋 查询记录文件（降级）: {self.record_file.relative_to(Path(__file__).parent)}")
            else:
                logger.warning(f"⚠️  无法创建 log 目录: {error_msg_root}")
                self.record_file = Path("query_records.json")
                logger.info(f"📋 查询记录文件（当前目录）: {self.record_file}")
        
        self.records = self._load_records()
    
    def _load_records(self) -> Dict:
        """加载历史记录"""
        if self.record_file and self.record_file.exists():
            try:
                with open(self.record_file, 'r', encoding='utf-8') as f:
                    records = json.load(f)
                logger.info(f"✅ 已加载 {len(records)} 条历史记录")
                return records
            except Exception as e:
                logger.warning(f"⚠️  加载记录失败: {e}，创建新记录")
                return {}
        return {}
    
    def _save_records(self) -> None:
        """保存记录到文件"""
        if not self.record_file:
            logger.warning("⚠️  未设置记录文件，跳过保存")
            return
        
        try:
            self.record_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.record_file, 'w', encoding='utf-8') as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ 保存记录失败: {e}")
    
    def _generate_key(self, stock_code: str, query_date: str) -> str:
        """生成唯一键"""
        return f"{stock_code}_{query_date}"
    
    def is_query_completed(
        self, 
        stock_code: str, 
        query_date: str
    ) -> Tuple[bool, Optional[str]]:
        """检查查询是否已完成"""
        key = self._generate_key(stock_code, query_date)
        
        if key not in self.records:
            return False, None
        
        record = self.records[key]
        
        if not record.get('success', False):
            return False, None
        
        file_path = record.get('file_path')
        if file_path and Path(file_path).exists():
            return True, file_path
        
        logger.warning(f"⚠️  记录存在但文件丢失: {file_path}")
        return False, None
    
    def add_record(
        self,
        stock_code: str,
        stock_name: str,
        query_date: str,
        success: bool,
        file_path: Optional[str] = None,
        error_msg: Optional[str] = None
    ) -> None:
        """添加查询记录"""
        key = self._generate_key(stock_code, query_date)
        
        self.records[key] = {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'query_date': query_date,
            'success': success,
            'file_path': file_path,
            'error_msg': error_msg,
            'timestamp': datetime.now().isoformat()
        }
        
        # 定期保存（每 10 条）
        if len(self.records) % 10 == 0:
            self._save_records()
    
    def get_failed_queries(self) -> List[Dict]:
        """获取所有失败的查询"""
        return [
            record for record in self.records.values()
            if not record.get('success', False)
        ]
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        total = len(self.records)
        success = sum(1 for r in self.records.values() if r.get('success', False))
        
        return {
            'total': total,
            'success': success,
            'failed': total - success,
            'success_rate': f"{success/total*100:.1f}%" if total > 0 else "N/A"
        }
    
    def finalize(self) -> None:
        """结束时保存记录"""
        self._save_records()
        stats = self.get_statistics()
        logger.info(f"📊 查询统计: {stats}")


# --- 港股列表管理器 ---
class StockListManager:
    """
    港股列表管理器
    优先从 AkShare 获取最新港股列表（包含新股），失败时回退到本地 hk.csv。
    自动更新本地 CSV 文件，确保每次运行都有最新的股票列表。
    """

    @staticmethod
    def fetch_from_akshare() -> Optional[pd.DataFrame]:
        """
        从东方财富获取全部港股列表

        Returns:
            DataFrame with columns ['id', 'name'] or None
        """
        try:
            logger.info("🌐 正在从 AkShare 获取港股列表...")
            df = ak.stock_hk_spot()

            # 提取股票代码（去除前导零，统一5位）
            code_series = df['代码'].astype(str).str.extract(r'(\d+)')[0]
            code_series = code_series.str.zfill(5)

            result = pd.DataFrame({
                'id': code_series,
                'name': df['中文名称'].astype(str).str.strip(),
            })

            result = result.dropna(subset=['id', 'name'])
            result = result[result['name'].isin(['', 'None', 'nan']) == False]
            result = result.drop_duplicates(subset=['id'])
            result = result.sort_values('id').reset_index(drop=True)

            logger.info(f"✅ AkShare 获取到 {len(result)} 只港股")
            return result

        except Exception as e:
            logger.warning(f"⚠️  AkShare 获取港股列表失败: {e}")
            return None

    @staticmethod
    def load_from_csv(csv_path: str) -> pd.DataFrame:
        """从本地 CSV 加载股票列表"""
        try:
            if not os.path.exists(csv_path):
                return pd.DataFrame(columns=['id', 'name'])

            encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']
            for enc in encodings:
                try:
                    df = pd.read_csv(csv_path, encoding=enc, dtype={'id': str})
                    if 'id' not in df.columns or 'name' not in df.columns:
                        if len(df.columns) >= 2:
                            df.columns = ['id', 'name'] + list(df.columns[2:])
                    df['id'] = df['id'].str.strip().str.zfill(5)
                    df['name'] = df['name'].str.strip()
                    return df[['id', 'name']].dropna().drop_duplicates(subset=['id'])
                except UnicodeDecodeError:
                    continue
            return pd.DataFrame(columns=['id', 'name'])
        except Exception as e:
            logger.warning(f"⚠️  从 CSV 加载股票列表失败: {e}")
            return pd.DataFrame(columns=['id', 'name'])

    @staticmethod
    def save_to_csv(df: pd.DataFrame, csv_path: str) -> bool:
        """保存股票列表到 CSV"""
        try:
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            return True
        except Exception as e:
            logger.error(f"❌ 保存股票列表失败: {e}")
            return False

    @classmethod
    def refresh_stock_list(cls, csv_path: str) -> Tuple[pd.DataFrame, str]:
        """
        刷新股票列表

        逻辑：
        1. 尝试从 AkShare 获取最新列表
        2. 如果成功：与本地 CSV 合并（保留新股），保存并返回
        3. 如果失败：直接使用本地 CSV

        Returns:
            (DataFrame, 来源标识: 'akshare'/'csv')
        """
        # 先加载本地已有数据
        local_df = cls.load_from_csv(csv_path)

        # 尝试从 AkShare 获取
        fresh_df = cls.fetch_from_akshare()

        if fresh_df is not None and not fresh_df.empty:
            # 合并：本地 + 新数据，去重保留最新
            merged = pd.concat([local_df, fresh_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=['id'], keep='last')
            merged = merged.sort_values('id').reset_index(drop=True)

            if cls.save_to_csv(merged, csv_path):
                new_count = len(merged) - len(local_df)
                if new_count > 0:
                    logger.info(f"🆕 新增 {new_count} 只股票（当前共 {len(merged)} 只）")
                return merged, 'akshare'

        # 回退到本地 CSV
        if not local_df.empty:
            logger.info(f"📂 使用本地股票列表 ({len(local_df)} 只)")
            return local_df, 'csv'

        logger.warning("⚠️  无可用股票列表数据")
        return pd.DataFrame(columns=['id', 'name']), 'none'


# --- 港股休市日历 v6.2 ---
class HKEXTradingCalendar:
    """港股交易日历 v6.2（自动从 yfinance 获取交易日 + 硬编码节假日兜底）"""

    # 硬编码节假日作为兜底（当 yfinance 不可用时使用）
    PUBLIC_HOLIDAYS = {
        # 2024 年
        "2024-01-01", "2024-02-10", "2024-02-12", "2024-02-13",
        "2024-03-29", "2024-03-30", "2024-04-01", "2024-04-04",
        "2024-05-01", "2024-05-15", "2024-06-10", "2024-07-01",
        "2024-09-18", "2024-10-01", "2024-10-11", "2024-12-25",
        "2024-12-26",

        # 2025 年
        "2025-01-01", "2025-01-29", "2025-01-30", "2025-01-31",
        "2025-04-04", "2025-04-18", "2025-04-19", "2025-04-21",
        "2025-05-01", "2025-05-05", "2025-05-31", "2025-07-01",
        "2025-10-01", "2025-10-07", "2025-10-29", "2025-12-25",
        "2025-12-26",
    }

    # 动态交易日历缓存（从 yfinance 获取）
    _trading_days_cache: Set[str] = set()
    _cache_start: Optional[datetime] = None
    _cache_end: Optional[datetime] = None
    _cache_built = False
    _cache_failed = False

    @classmethod
    def _build_trading_calendar(cls, start_date: Optional[str] = None) -> bool:
        """
        从 yfinance 恒生指数历史数据构建交易日历

        Args:
            start_date: 起始日期 YYYY-MM-DD（None 表示最近一年）

        Returns:
            是否成功
        """
        if cls._cache_built or cls._cache_failed:
            return cls._cache_built

        try:
            period = '2y' if start_date else '1y'
            logger.info(f"📅 正在从 yfinance 获取港股交易日历（{period}）...")

            hsi = yf.Ticker('^HSI')
            hist = hsi.history(period=period)

            if hist.empty:
                raise ValueError("恒生指数历史数据为空")

            cls._trading_days_cache = set(
                d.strftime('%Y-%m-%d') for d in hist.index
            )
            cls._cache_start = hist.index[0]
            cls._cache_end = hist.index[-1]
            cls._cache_built = True

            # 将 yfinance 已知的节假日也纳入 PUBLIC_HOLIDAYS
            all_business_days = set(
                d.strftime('%Y-%m-%d')
                for d in pd.date_range(start=hist.index[0], end=hist.index[-1], freq='B')
            )
            holidays_from_yf = all_business_days - cls._trading_days_cache
            cls.PUBLIC_HOLIDAYS.update(holidays_from_yf)

            logger.info(
                f"✅ 交易日历加载完成: {len(cls._trading_days_cache)} 个交易日, "
                f"识别 {len(holidays_from_yf)} 个节假日"
            )
            return True

        except Exception as e:
            logger.warning(f"⚠️  yfinance 获取交易日历失败: {e}，使用硬编码节假日")
            cls._cache_failed = True
            return False

    @classmethod
    def is_trading_day(cls, date_str: str) -> bool:
        """
        判断是否为交易日

        优先使用 yfinance 动态交易日历，失败时回退到硬编码节假日。

        Args:
            date_str: YYYYMMDD 或 YYYY-MM-DD 格式

        Returns:
            是否为交易日
        """
        try:
            if len(date_str) == 8 and date_str.isdigit():
                dt = datetime.strptime(date_str, "%Y%m%d")
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d")

            date_formatted = dt.strftime("%Y-%m-%d")

            # 周末一定不是交易日
            if dt.weekday() in [5, 6]:
                logger.debug(f"🚫 周末: {date_formatted} (周{dt.weekday()+1})")
                return False

            # 优先使用 yfinance 交易日历（仅限缓存范围内）
            if cls._cache_built and cls._cache_start and cls._cache_end:
                # 比较时去掉时区信息（pandas Timestamp 带时区，dt 是无时区的）
                cache_start_naive = cls._cache_start.replace(tzinfo=None)
                cache_end_naive = cls._cache_end.replace(tzinfo=None)
                if cache_start_naive <= dt <= cache_end_naive:
                    is_trading = date_formatted in cls._trading_days_cache
                    if not is_trading:
                        logger.debug(f"🚫 非交易日（yfinance）: {date_formatted}")
                    else:
                        logger.debug(f"✅ 交易日（yfinance）: {date_formatted}")
                    return is_trading
                # 缓存范围外的日期，回退到硬编码节假日

            # 回退到硬编码节假日
            if date_formatted in cls.PUBLIC_HOLIDAYS:
                logger.debug(f"🚫 公众假期: {date_formatted}")
                return False

            logger.debug(f"✅ 交易日（默认）: {date_formatted}")
            return True

        except ValueError as e:
            logger.error(f"❌ 无效日期格式: {date_str}, 错误: {e}")
            return False
    
    @classmethod
    def get_previous_trading_day(cls, date_str: str, max_days: int = 10) -> Optional[str]:
        """获取前一个交易日"""
        try:
            if len(date_str) == 8 and date_str.isdigit():
                current_dt = datetime.strptime(date_str, "%Y%m%d")
            else:
                current_dt = datetime.strptime(date_str, "%Y-%m-%d")
            
            for i in range(1, max_days + 1):
                prev_dt = current_dt - timedelta(days=i)
                prev_str = prev_dt.strftime("%Y-%m-%d")
                
                if cls.is_trading_day(prev_str):
                    return prev_str
            
            return None
            
        except ValueError:
            return None


# --- 🆕 日期范围工具类 v6.1 ---
class DateRangeUtils:
    """日期范围工具类 v6.1（修复跨年问题）"""
    
    @staticmethod
    def parse_date_range(start_str: str, end_str: str) -> Tuple[Optional[List[str]], str]:
        """
        解析日期范围
        
        Args:
            start_str: 起始日期 (YYYYMMDD)
            end_str: 结束日期 (YYYYMMDD)
        
        Returns:
            (日期列表, 错误信息)
        """
        try:
            start_dt = datetime.strptime(start_str, "%Y%m%d")
            end_dt = datetime.strptime(end_str, "%Y%m%d")
            
            # 验证时间顺序
            if start_dt > end_dt:
                return None, "起始日期不能晚于结束日期"
            
            # 验证未来日期
            if end_dt > datetime.now():
                return None, "不能查询未来日期"
            
            # 🔧 修复：生成日期列表（确保包含边界）
            date_list = []
            current = start_dt
            
            while current <= end_dt:
                date_list.append(current.strftime("%Y%m%d"))
                current += timedelta(days=1)
            
            logger.debug(f"📅 生成日期列表: {len(date_list)} 天 ({date_list[0]} 至 {date_list[-1]})")
            
            return date_list, ""
            
        except ValueError as e:
            return None, f"日期格式错误: {e}"
    
    @staticmethod
    def filter_trading_days_from_range(date_list: List[str]) -> List[Tuple[str, str]]:
        """
        从日期范围中过滤交易日 v6.1（修复格式问题）
        
        Args:
            date_list: YYYYMMDD 格式日期列表
        
        Returns:
            [(HKEX格式日期, 文件格式日期), ...]
        """
        trading_dates = []
        
        logger.debug(f"🔍 开始过滤交易日，总日期数: {len(date_list)}")
        
        for idx, date_str in enumerate(date_list):
            try:
                # 🔧 修复：确保正确解析 YYYYMMDD 格式
                dt = datetime.strptime(date_str, "%Y%m%d")
                file_date = dt.strftime("%Y-%m-%d")
                
                # 使用 YYYY-MM-DD 格式检查
                if HKEXTradingCalendar.is_trading_day(file_date):
                    hkex_date = dt.strftime("%Y/%m/%d")
                    trading_dates.append((hkex_date, file_date))
                    
                    if idx < 5:  # 记录前 5 个交易日
                        logger.debug(f"  ✅ [{idx+1}] {file_date} -> {hkex_date}")
                
            except ValueError as e:
                logger.error(f"❌ 日期解析失败: {date_str}, 错误: {e}")
                continue
        
        logger.info(f"📊 交易日过滤完成: {len(trading_dates)}/{len(date_list)} 天为交易日")
        
        if len(trading_dates) > 0:
            logger.info(f"  首个交易日: {trading_dates[0][1]}")
            logger.info(f"  最后交易日: {trading_dates[-1][1]}")
        
        return trading_dates
    
    @staticmethod
    def describe_date_range(start_str: str, end_str: str) -> str:
        """生成日期范围描述"""
        start_dt = datetime.strptime(start_str, "%Y%m%d")
        end_dt = datetime.strptime(end_str, "%Y%m%d")
        
        days = (end_dt - start_dt).days + 1
        
        if days == 1:
            return f"{start_dt.strftime('%Y年%m月%d日')} (单日)"
        elif days <= 31:
            return f"{start_dt.strftime('%Y年%m月%d日')} - {end_dt.strftime('%m月%d日')} (共{days}天)"
        else:
            return f"{start_dt.strftime('%Y年%m月%d日')} - {end_dt.strftime('%Y年%m月%d日')} (共{days}天)"


# --- 🆕 智能断点续传管理器 v6.1 ---
class SmartResumeManager:
    """
    智能断点续传管理器 v6.1
    
    双重验证机制：
    1. 查询记录系统（JSON）
    2. 文件系统扫描（实际文件）
    """
    
    def __init__(self, record_mgr: QueryRecordManager, data_mgr: 'DataManager'):
        self.record_mgr = record_mgr
        self.data_mgr = data_mgr
        self.file_cache: Dict[str, Set[Tuple[str, str]]] = {}  # {股票代码: {(代码, 日期)}}
        self.cache_built = False
    
    def build_file_cache(self, stock_codes: Optional[List[str]] = None) -> None:
        """
        构建文件系统缓存
        
        Args:
            stock_codes: 指定股票代码列表（None 表示全量扫描）
        """
        logger.info("🔍 开始扫描数据目录...")
        start_time = time.time()
        
        # 正则匹配：股票名_股票代码_YYYY-MM-DD_top50.csv
        pattern = re.compile(r'^(.+?)_(\d{5})_([\d-]+)_top50\.csv$')
        
        total_files = 0
        matched_files = 0
        
        for csv_file in self.data_mgr.base_dir.rglob("*.csv"):
            total_files += 1
            match = pattern.match(csv_file.name)
            
            if match:
                stock_name, code, date_str = match.groups()
                
                # 过滤指定股票
                if stock_codes is not None and code not in stock_codes:
                    continue
                
                if code not in self.file_cache:
                    self.file_cache[code] = set()
                
                self.file_cache[code].add((code, date_str))
                matched_files += 1
                
                if matched_files <= 5:  # 记录前 5 个
                    logger.debug(f"  📁 发现: {csv_file.name}")
        
        elapsed = time.time() - start_time
        
        total_records = sum(len(dates) for dates in self.file_cache.values())
        
        logger.info(f"✅ 文件扫描完成 (耗时 {elapsed:.2f}s)")
        logger.info(f"  总文件数: {total_files}")
        logger.info(f"  匹配文件: {matched_files}")
        logger.info(f"  覆盖股票: {len(self.file_cache)}")
        logger.info(f"  总记录数: {total_records}")
        
        self.cache_built = True
    
    def is_completed(
        self, 
        stock_code: str, 
        file_date: str
    ) -> Tuple[bool, str]:
        """
        双重验证查询是否已完成
        
        Args:
            stock_code: 股票代码 (5位)
            file_date: 文件日期 (YYYY-MM-DD)
        
        Returns:
            (是否完成, 来源: 'both'/'record'/'file'/'none')
        """
        # 验证 1：记录系统
        record_ok, file_path = self.record_mgr.is_query_completed(stock_code, file_date)
        
        # 验证 2：文件系统
        file_ok = False
        if stock_code in self.file_cache:
            file_ok = (stock_code, file_date) in self.file_cache[stock_code]
        
        # 组合判断
        if record_ok and file_ok:
            return True, 'both'
        elif record_ok and not file_ok:
            logger.warning(f"⚠️  [{stock_code}@{file_date}] 记录存在但文件丢失，重新查询")
            return False, 'none'
        elif not record_ok and file_ok:
            logger.debug(f"📁 [{stock_code}@{file_date}] 文件存在但记录缺失，信任文件")
            return True, 'file'
        else:
            return False, 'none'
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            'cache_built': self.cache_built,
            'cached_stocks': len(self.file_cache),
            'cached_records': sum(len(dates) for dates in self.file_cache.values())
        }


# --- 日期工具类（兼容旧版）---
class DateUtils:
    """日期工具类 v6.1"""
    
    @staticmethod
    def is_valid_date_format(date_str: str, format_str: str) -> bool:
        try:
            datetime.strptime(date_str, format_str)
            return True
        except ValueError:
            return False


# --- 核心组件 ---
class CipherAdapter(HTTPAdapter):
    """TLS 指纹绕过适配器"""
    def init_poolmanager(self, connections, maxsize, block=False):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_ciphers('DEFAULT:!DH:!aNULL:!eNULL:!LOW:!EXPORT:!SSLv2')
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=ctx
        )


class StockDatabase:
    """港股数据库管理器"""
    
    def __init__(self, csv_path: str = "hk.csv"):
        self.csv_path = csv_path
        self.df = None
        self._load_database()
    
    def _load_database(self) -> None:
        """加载股票数据库"""
        try:
            if not os.path.exists(self.csv_path):
                logger.error(f"❌ 未找到股票数据库: {self.csv_path}")
                self.df = pd.DataFrame(columns=['id', 'name'])
                return
            
            encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
            for enc in encodings:
                try:
                    self.df = pd.read_csv(self.csv_path, encoding=enc, dtype=str)
                    break
                except UnicodeDecodeError:
                    continue
            
            if self.df is None:
                raise ValueError("无法解码 CSV 文件")
            
            self.df.columns = self.df.columns.str.strip().str.lower()
            
            if 'id' not in self.df.columns or 'name' not in self.df.columns:
                logger.warning(f"⚠️  CSV 缺少 'id' 或 'name' 列，尝试推断...")
                if len(self.df.columns) >= 2:
                    self.df.columns = ['id', 'name'] + list(self.df.columns[2:])
            
            self.df['id'] = self.df['id'].str.strip().str.zfill(5)
            self.df['name'] = self.df['name'].str.strip()
            self.df = self.df.dropna(subset=['id', 'name'])
            
            logger.info(f"✅ 已加载 {len(self.df)} 只港股数据")
            
        except Exception as e:
            logger.error(f"❌ 加载股票数据库失败: {e}", exc_info=True)
            self.df = pd.DataFrame(columns=['id', 'name'])
    
    def get_name_by_code(self, stock_code: str) -> Optional[str]:
        """根据代码获取名称"""
        if self.df is None or self.df.empty:
            return None
        
        code = stock_code.zfill(5)
        result = self.df[self.df['id'] == code]
        
        if not result.empty:
            return result.iloc[0]['name']
        return None
    
    def get_all_codes(self) -> List[str]:
        """获取所有股票代码"""
        if self.df is None or self.df.empty:
            return []
        return self.df['id'].tolist()


class AsyncHKEXFetcher:
    """HKEX 异步抓取器 v6.1"""
    
    URL = "https://www3.hkexnews.hk/sdw/search/searchsdw_c.aspx"
    TIMEOUT = aiohttp.ClientTimeout(total=20, connect=10)
    # ViewState 连续失败达到该次数判定 HKEX 封禁，调用方应立即中止而非空转
    BAN_THRESHOLD = 5
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    ]
    
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.semaphore = None
        self.session = None
        self.request_count = 0
        self.last_request_time = time.time()
        self.min_interval = 0.3
        # ViewState 复用：一次 GET 获取后供所有 POST 复用，避免每只股票
        # 额外一次 GET（2800 只 = 省 2800 个请求，显著降低 HKEX 封禁概率）
        self._viewstate: dict | None = None
        # 连续封禁标记：ViewState 连续失败 N 次视为被封，调用方应中止
        self._consecutive_viewstate_fails = 0
        self.banned = False
    
    async def __aenter__(self):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent * 2,
            limit_per_host=self.max_concurrent,
            ssl=ssl_context,
            ttl_dns_cache=300
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.TIMEOUT,
            headers={
                "User-Agent": random.choice(self.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
            }
        )
        
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            await asyncio.sleep(0.25)
    
    async def _rate_limit(self):
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.min_interval:
            wait_time = self.min_interval - elapsed
            await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    async def fetch_data(
        self,
        stock_code: str,
        query_date: str
    ) -> Optional[pd.DataFrame]:
        async with self.semaphore:
            try:
                await self._rate_limit()
                self.request_count += 1

                viewstate_data = self._viewstate
                if viewstate_data is None:
                    viewstate_data = await self._get_viewstate()
                if not viewstate_data:
                    self._consecutive_viewstate_fails += 1
                    if self._consecutive_viewstate_fails >= self.BAN_THRESHOLD:
                        self.banned = True
                        logger.error("⛔ ViewState 连续失败 %d 次，HKEX 疑似封禁，中止抓取", self._consecutive_viewstate_fails)
                    else:
                        logger.error(f"❌ [{stock_code}] 无法获取 ViewState")
                    return None
                self._consecutive_viewstate_fails = 0

                logger.info(f"🔍 [{self.request_count}] 查询: {stock_code} @ {query_date}")
                html = await self._post_query(stock_code, query_date, viewstate_data)

                if not html:
                    return None

                loop = asyncio.get_event_loop()
                df = await loop.run_in_executor(None, self._parse_html, html)

                return df

            except asyncio.TimeoutError:
                logger.error(f"❌ [{stock_code}] 请求超时")
                return None
            except Exception as e:
                logger.error(f"❌ [{stock_code}] 抓取失败: {e}")
                return None

    async def _get_viewstate(self) -> Optional[dict]:
        try:
            async with self.session.get(self.URL) as response:
                response.raise_for_status()
                html = await response.text()

                loop = asyncio.get_event_loop()
                soup = await loop.run_in_executor(None, BeautifulSoup, html, 'lxml')

                fields = ['__VIEWSTATE', '__VIEWSTATEGENERATOR', 'today']
                data = {}

                for field in fields:
                    element = soup.find(id=field)
                    if not element or 'value' not in element.attrs:
                        logger.error(f"❌ 缺少必需字段: {field}")
                        return None
                    data[field] = element['value']

                # 缓存供后续所有查询复用（ASP.NET ViewState 为会话级令牌）
                self._viewstate = data
                return data

        except Exception as e:
            logger.error(f"❌ 获取 ViewState 失败: {e}")
            return None
    
    async def _post_query(
        self, 
        stock_code: str, 
        query_date: str, 
        viewstate: dict
    ) -> Optional[str]:
        try:
            payload = {
                '__EVENTTARGET': 'btnSearch',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': viewstate['__VIEWSTATE'],
                '__VIEWSTATEGENERATOR': viewstate['__VIEWSTATEGENERATOR'],
                'today': viewstate['today'],
                'sortBy': 'shareholding',
                'sortDirection': 'desc',
                'txtShareholdingDate': query_date,
                'txtStockCode': stock_code,
            }
            
            headers = {
                'Origin': 'https://www3.hkexnews.hk',
                'Referer': self.URL,
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            async with self.session.post(
                self.URL, 
                data=payload, 
                headers=headers
            ) as response:
                response.raise_for_status()
                return await response.text()
                
        except Exception as e:
            logger.error(f"❌ POST 请求失败: {e}")
            return None
    
    @staticmethod
    def _parse_html(html: str) -> Optional[pd.DataFrame]:
        soup = BeautifulSoup(html, 'lxml')
        
        alert = soup.select_one('.alert-warning, .alert-danger')
        if alert:
            msg = alert.get_text(strip=True)
            logger.warning(f"⚠️  交易所返回: {msg}")
            return None
        
        table = soup.select_one('table.table')
        if not table:
            logger.warning("⚠️  未找到数据表")
            return None
        
        rows = table.select('tbody tr')
        if not rows:
            rows = table.find_all('tr')[1:]
        
        if not rows:
            logger.warning("⚠️  表格无数据行")
            return None
        
        data = []
        for idx, tr in enumerate(rows, 1):
            cols = [td.get_text(strip=True) for td in tr.find_all('td')]
            
            if len(cols) < 4:
                continue
            
            try:
                participant_id = AsyncHKEXFetcher._clean_text(cols[0])
                participant_name = AsyncHKEXFetcher._clean_text(cols[1])
                shareholding_raw = cols[3] if len(cols) > 3 else cols[2]
                percent_raw = cols[4] if len(cols) > 4 else cols[3]
                
                shareholding = AsyncHKEXFetcher._clean_number(shareholding_raw)
                percent = AsyncHKEXFetcher._clean_text(percent_raw)
                
                if not participant_id or shareholding is None:
                    continue
                
                data.append({
                    "参与者编号": participant_id,
                    "参与者名称": participant_name,
                    "持股数量": shareholding,
                    "占已发行股份百分比": percent
                })
                
            except (ValueError, IndexError):
                continue
        
        if not data:
            return None
        
        return pd.DataFrame(data)
    
    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ""
        
        if ':' in text or '：' in text:
            text = text.replace('：', ':').split(':')[-1].strip()
        
        return text.strip()
    
    @staticmethod
    def _clean_number(text: str) -> Optional[int]:
        if not text or text in ['--', 'N/A', '-']:
            return None
        
        text = AsyncHKEXFetcher._clean_text(text)
        clean = re.sub(r'[^\d-]', '', text)
        
        try:
            return int(clean) if clean else None
        except ValueError:
            return None


class DataManager:
    """数据管理器 v6.1"""
    
    def __init__(self, base_dir: str = "data"):
        base_path = Path(base_dir)
        if not base_path.is_absolute():
            script_dir = Path(__file__).parent.resolve()
            self.base_dir = script_dir / base_dir
        else:
            self.base_dir = base_path
        
        self._ensure_directory()
    
    def _ensure_directory(self) -> None:
        """确保数据目录存在（带权限检查）"""
        success, error_msg = safe_mkdir(self.base_dir)
        
        if success:
            abs_path = self.base_dir.resolve()
            logger.info(f"📁 数据根目录: {abs_path.relative_to(Path(__file__).parent)}")
            
            test_file = self.base_dir / ".write_test"
            try:
                test_file.touch()
                test_file.unlink()
            except Exception as e:
                logger.error(f"❌ 目录不可写: {abs_path}, 错误: {e}")
        else:
            logger.error(f"❌ 创建数据目录失败: {error_msg}")
            logger.warning("⚠️  尝试使用当前目录作为数据目录")
            self.base_dir = Path(".")
    
    def _create_layered_directory(self, stock_name: str, year: str) -> Path:
        """创建分层目录结构"""
        clean_name = re.sub(r'[<>:"/\\|?*]', '', stock_name).strip()
        if not clean_name:
            clean_name = "未命名股票"
        
        target_dir = self.base_dir / clean_name / year
        
        success, error_msg = safe_mkdir(target_dir)
        
        if success:
            return target_dir
        else:
            logger.error(f"❌ 创建目录失败: {error_msg}")
            return self.base_dir
    
    def generate_filename(
        self, 
        stock_code: str, 
        stock_name: str, 
        file_date: str
    ) -> str:
        clean_name = re.sub(r'[<>:"/\\|?*]', '', stock_name).strip()
        if not clean_name:
            clean_name = f"股票{stock_code}"
        
        filename = f"{clean_name}_{stock_code}_{file_date}_top50.csv"
        return filename
    
    def save_data(
        self, 
        df: pd.DataFrame, 
        stock_code: str,
        stock_name: str,
        file_date: str,
        query_date: str
    ) -> Tuple[bool, Optional[str]]:
        """保存数据到 CSV"""
        if df is None or df.empty:
            logger.warning("⚠️  数据为空，跳过保存")
            return False, None
        
        try:
            df_save = df.copy()
            df_save.insert(0, '查询日期', query_date)
            df_save.insert(1, '股票名称', stock_name)
            df_save.insert(2, '股票代码', stock_code)
            
            year = file_date.split('-')[0]
            target_dir = self._create_layered_directory(stock_name, year)
            
            filename = self.generate_filename(stock_code, stock_name, file_date)
            filepath = target_dir / filename
            abs_filepath = filepath.resolve()
            
            logger.info(f"💾 保存数据: {target_dir.name}/{year}/{filename} ({len(df_save)} 行)")
            
            df_save.to_csv(abs_filepath, index=False, encoding='utf-8-sig')
            
            if abs_filepath.exists():
                file_size = abs_filepath.stat().st_size
                logger.info(f"✅ 保存成功! 文件大小: {file_size:,} 字节")
                return True, str(abs_filepath)
            else:
                logger.error(f"❌ 文件未创建: {abs_filepath}")
                return False, None
            
        except Exception as e:
            logger.error(f"❌ 保存失败: {e}", exc_info=True)
            return False, None


# --- 查询引擎 v6.1 ---
class QueryEngine:
    """查询引擎 v6.1（集成智能断点续传）"""
    
    def __init__(
        self, 
        stock_db: StockDatabase, 
        data_mgr: DataManager,
        record_mgr: QueryRecordManager
    ):
        self.stock_db = stock_db
        self.data_mgr = data_mgr
        self.record_mgr = record_mgr
        self.resume_mgr = SmartResumeManager(record_mgr, data_mgr)  # 🆕 智能断点续传
    
    async def range_query_single_stock(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        max_concurrent: int = 5,
        skip_existing: bool = True
    ) -> Dict[str, bool]:
        """
        单股日期范围查询 v6.1
        """
        stock_code = stock_code.zfill(5)
        stock_name = self.stock_db.get_name_by_code(stock_code) or f"股票{stock_code}"
        
        # 解析日期范围
        date_list, error_msg = DateRangeUtils.parse_date_range(start_date, end_date)
        if date_list is None:
            logger.error(f"❌ {error_msg}")
            return {}
        
        # 🔧 修复：过滤交易日
        trading_dates = DateRangeUtils.filter_trading_days_from_range(date_list)
        
        if not trading_dates:
            logger.warning("⚠️  范围内无交易日")
            return {}
        
        description = DateRangeUtils.describe_date_range(start_date, end_date)
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 单股范围查询: {stock_name}({stock_code})")
        logger.info(f"时间范围: {description}")
        logger.info(f"交易日数: {len(trading_dates)} 天")
        logger.info(f"⚡ 并发数: {max_concurrent}")
        logger.info(f"{'='*80}\n")
        
        # 🆕 智能断点续传
        if skip_existing:
            # 构建文件缓存（仅针对当前股票）
            self.resume_mgr.build_file_cache([stock_code])
            
            dates_to_query = []
            skipped_count = 0
            skip_reasons = {'both': 0, 'record': 0, 'file': 0}
            
            for hkex_date, file_date in trading_dates:
                is_completed, source = self.resume_mgr.is_completed(stock_code, file_date)
                
                if is_completed:
                    logger.debug(f"⏭️  跳过已完成: {file_date} (来源: {source})")
                    skipped_count += 1
                    skip_reasons[source] = skip_reasons.get(source, 0) + 1
                else:
                    dates_to_query.append((hkex_date, file_date))
            
            logger.info(f"📋 断点续传分析:")
            logger.info(f"  - 总交易日: {len(trading_dates)}")
            logger.info(f"  - 已完成: {skipped_count} 天")
            logger.info(f"    · 记录+文件: {skip_reasons.get('both', 0)}")
            logger.info(f"    · 仅文件: {skip_reasons.get('file', 0)}")
            logger.info(f"  - 待查询: {len(dates_to_query)} 天\n")
            
            if not dates_to_query:
                logger.info("✅ 所有日期已完成，无需查询")
                return {}
        else:
            dates_to_query = trading_dates
        
        # 🔧 修复：异步查询（增加日志）
        logger.info(f"🚀 开始异步查询 {len(dates_to_query)} 个任务...\n")
        
        async with AsyncHKEXFetcher(max_concurrent=max_concurrent) as fetcher:
            tasks = [
                self._fetch_and_save(fetcher, stock_code, stock_name, hkex_date, file_date)
                for hkex_date, file_date in dates_to_query
            ]
            
            # 🔧 增加进度提示
            if len(tasks) > 0:
                logger.info(f"⏳ 任务队列: {len(tasks)} 个查询任务")
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        success_count = sum(1 for r in results if r is True)
        error_count = sum(1 for r in results if isinstance(r, Exception))
        
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ 查询完成")
        logger.info(f"  - 成功: {success_count}/{len(dates_to_query)}")
        logger.info(f"  - 失败: {len(dates_to_query) - success_count}")
        if error_count > 0:
            logger.warning(f"  - 异常: {error_count}")
        logger.info(f"{'='*80}\n")
        
        return {file_date: (result is True) for (_, file_date), result in zip(dates_to_query, results)}
    
    async def range_query_batch_stocks(
        self,
        start_date: str,
        end_date: str,
        stock_codes: Optional[List[str]] = None,
        max_concurrent: int = 5,
        skip_existing: bool = True
    ) -> Dict[str, Dict[str, bool]]:
        """
        批量股票日期范围查询 v6.1
        """
        if stock_codes is None:
            stock_codes = self.stock_db.get_all_codes()
        
        # 解析日期范围
        date_list, error_msg = DateRangeUtils.parse_date_range(start_date, end_date)
        if date_list is None:
            logger.error(f"❌ {error_msg}")
            return {}
        
        # 🔧 修复：过滤交易日
        trading_dates = DateRangeUtils.filter_trading_days_from_range(date_list)
        
        if not trading_dates:
            logger.warning("⚠️  范围内无交易日")
            return {}
        
        description = DateRangeUtils.describe_date_range(start_date, end_date)
        total_stocks = len(stock_codes)
        total_queries = total_stocks * len(trading_dates)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 批量范围查询")
        logger.info(f"  - 股票数量: {total_stocks}")
        logger.info(f"  - 时间范围: {description}")
        logger.info(f"  - 交易日数: {len(trading_dates)} 天")
        logger.info(f"  - 预计查询: {total_queries} 次")
        logger.info(f"  - 并发数: {max_concurrent}")
        logger.info(f"{'='*80}\n")
        
        # 🆕 智能断点续传
        task_mapping = []
        skipped_count = 0
        
        if skip_existing:
            # 全量扫描文件系统
            logger.info("🔍 正在扫描数据目录（全量）...")
            self.resume_mgr.build_file_cache()
            
            for code in stock_codes:
                stock_code = code.zfill(5)
                
                for hkex_date, file_date in trading_dates:
                    is_completed, _ = self.resume_mgr.is_completed(stock_code, file_date)
                    
                    if is_completed:
                        skipped_count += 1
                    else:
                        task_mapping.append((stock_code, hkex_date, file_date))
            
            logger.info(f"📋 断点续传分析:")
            logger.info(f"  - 总任务数: {total_queries}")
            logger.info(f"  - 已完成: {skipped_count}")
            logger.info(f"  - 待执行: {len(task_mapping)}\n")
        else:
            for code in stock_codes:
                stock_code = code.zfill(5)
                for hkex_date, file_date in trading_dates:
                    task_mapping.append((stock_code, hkex_date, file_date))
        
        if not task_mapping:
            logger.info("✅ 所有查询已完成")
            return {}
        
        # 🔧 修复：异步批量查询
        logger.info(f"🚀 开始批量异步查询...\n")
        
        async with AsyncHKEXFetcher(max_concurrent=max_concurrent) as fetcher:
            tasks = []
            
            for stock_code, hkex_date, file_date in task_mapping:
                stock_name = self.stock_db.get_name_by_code(stock_code) or f"股票{stock_code}"
                task = self._fetch_and_save(fetcher, stock_code, stock_name, hkex_date, file_date)
                tasks.append(task)
            
            logger.info(f"⏳ 任务队列: {len(tasks)} 个查询任务\n")
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 整理结果
        result_dict = {}
        success_total = 0
        error_total = 0
        
        for (stock_code, _, file_date), result in zip(task_mapping, results):
            if stock_code not in result_dict:
                result_dict[stock_code] = {}
            
            if isinstance(result, Exception):
                logger.error(f"❌ [{stock_code}@{file_date}] 异常: {result}")
                result_dict[stock_code][file_date] = False
                error_total += 1
            else:
                is_success = result is True
                result_dict[stock_code][file_date] = is_success
                
                if is_success:
                    success_total += 1
        
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ 批量查询完成")
        logger.info(f"  - 成功: {success_total}/{len(tasks)}")
        logger.info(f"  - 失败: {len(tasks) - success_total}")
        if len(tasks) > 0:
            logger.info(f"  - 成功率: {success_total/len(tasks)*100:.1f}%")
        if error_total > 0:
            logger.warning(f"  - 异常: {error_total}")
        logger.info(f"{'='*80}\n")
        
        return result_dict
    
    async def _fetch_and_save(
        self,
        fetcher: AsyncHKEXFetcher,
        stock_code: str,
        stock_name: str,
        hkex_date: str,
        file_date: str
    ) -> bool:
        """辅助方法：抓取并保存"""
        try:
            df_raw = await fetcher.fetch_data(stock_code, hkex_date)
            
            if df_raw is not None and not df_raw.empty:
                df_top50 = df_raw.head(50).copy()
                success, file_path = self.data_mgr.save_data(
                    df_top50, stock_code, stock_name, file_date, file_date
                )
                
                self.record_mgr.add_record(
                    stock_code, stock_name, file_date,
                    success=success, file_path=file_path
                )
                
                return success
            else:
                self.record_mgr.add_record(
                    stock_code, stock_name, file_date,
                    success=False, error_msg="无数据"
                )
                return False
                
        except Exception as e:
            logger.error(f"❌ [{stock_code}@{file_date}] 处理失败: {e}")
            self.record_mgr.add_record(
                stock_code, stock_name, file_date,
                success=False, error_msg=str(e)
            )
            return False


# --- 用户交互模块 v6.1 ---
def display_menu() -> str:
    """显示主菜单 v6.2"""
    print("\n" + "=" * 80)
    print("   HKEX 中央结算系统持股量查询工具 v6.2 (自动更新版)   ")
    print("=" * 80)
    print("\n请选择查询模式:")
    print("  [1] 单股查询 (指定1只股票 + 日期范围)")
    print("  [2] 批量查询 (全市场所有股票 + 日期范围)")
    print("  [3] 刷新股票列表 (从 AkShare 获取最新港股)")
    print("  [0] 退出程序")
    print("=" * 80)

    while True:
        choice = input("\n👉 请输入选项 (0-3): ").strip()
        if choice in ['0', '1', '2', '3']:
            return choice
        print("❌ 无效选项")


def input_stock_code(stock_db: StockDatabase) -> str:
    """输入股票代码"""
    while True:
        raw = input("👉 请输入股票代码 (如 1810): ").strip()
        if raw.isdigit():
            stock_code = raw.zfill(5)
            stock_name = stock_db.get_name_by_code(stock_code)
            
            if stock_name:
                print(f"✅ 匹配到股票: {stock_name} ({stock_code})")
                confirm = input("   确认吗? (Y/n): ").strip().lower()
                if confirm in ['', 'y', 'yes']:
                    return stock_code
            else:
                print(f"⚠️  数据库中未找到 {stock_code}，是否继续?")
                confirm = input("   (Y/n): ").strip().lower()
                if confirm in ['', 'y', 'yes']:
                    return stock_code
        else:
            print("❌ 格式错误")


def input_date_range() -> Tuple[str, str]:
    """
    输入日期范围 v6.1
    """
    print("\n" + "=" * 80)
    print("   日期范围设置")
    print("=" * 80)
    print("提示:")
    print("  - 单日查询: 起始和结束日期相同 (如 20250701 到 20250701)")
    print("  - 月度查询: 输入整月范围 (如 20250701 到 20250731)")
    print("  - 年度查询: 输入整年范围 (如 20250101 到 20251231)")
    print("=" * 80)
    
    while True:
        start_raw = input("👉 起始日期 (YYYYMMDD): ").strip()
        
        if not DateUtils.is_valid_date_format(start_raw, "%Y%m%d"):
            print("❌ 起始日期格式错误")
            continue
        
        end_raw = input("👉 结束日期 (YYYYMMDD，留空表示单日): ").strip()
        
        if not end_raw:
            end_raw = start_raw
            print(f"💡 未输入结束日期，默认为单日查询: {start_raw}")
        
        if not DateUtils.is_valid_date_format(end_raw, "%Y%m%d"):
            print("❌ 结束日期格式错误")
            continue
        
        # 验证日期范围
        date_list, error_msg = DateRangeUtils.parse_date_range(start_raw, end_raw)
        
        if date_list is None:
            print(f"❌ {error_msg}")
            continue
        
        # 显示范围描述
        description = DateRangeUtils.describe_date_range(start_raw, end_raw)
        trading_dates = DateRangeUtils.filter_trading_days_from_range(date_list)
        
        print(f"\n📊 范围信息:")
        print(f"  - 时间跨度: {description}")
        print(f"  - 自然日: {len(date_list)} 天")
        print(f"  - 交易日: {len(trading_dates)} 天")
        
        if len(trading_dates) == 0:
            print("⚠️  该范围内无交易日!")
            retry = input("   重新输入? (Y/n): ").strip().lower()
            if retry in ['', 'y', 'yes']:
                continue
            else:
                return start_raw, end_raw
        
        confirm = input("\n✅ 确认此范围? (Y/n): ").strip().lower()
        if confirm in ['', 'y', 'yes']:
            return start_raw, end_raw


def input_concurrent() -> int:
    """输入并发数"""
    while True:
        raw = input("👉 请输入并发数 (建议 3-10，默认 5): ").strip()
        
        if not raw:
            return 5
        
        if raw.isdigit():
            concurrent = int(raw)
            if 1 <= concurrent <= 20:
                return concurrent
            else:
                print("❌ 并发数必须在 1-20 之间")
        else:
            print("❌ 请输入数字")


def input_skip_existing() -> bool:
    """询问是否启用断点续传"""
    raw = input("👉 是否启用智能断点续传? (Y/n): ").strip().lower()
    return raw in ['', 'y', 'yes']


# --- 主程序 v6.2 ---
def main():
    """主程序 v6.2（自动刷新股票列表 + 交易日历）"""
    try:
        # 强制使用脚本目录
        script_dir = Path(__file__).parent.resolve()

        # 🆕 自动刷新股票列表（从 AkShare 获取最新港股，包含新股）
        csv_path = str(script_dir / "hk.csv")
        stock_df, source = StockListManager.refresh_stock_list(csv_path)

        # 初始化组件（使用刷新后的数据）
        stock_db = StockDatabase(csv_path)
        # 如果 AkShare 获取的数据比本地更新过，直接覆盖内存中的数据库
        if source == 'akshare' and not stock_df.empty:
            stock_db.df = stock_df[['id', 'name']].copy()
            logger.info(f"✅ 股票列表已加载: {len(stock_db.df)} 只（来源: {source}）")

        # 🆕 构建交易日历（从 yfinance 恒生指数推导）
        HKEXTradingCalendar._build_trading_calendar()

        data_mgr = DataManager(str(script_dir / "data"))
        record_mgr = QueryRecordManager(str(script_dir / "log"))

        engine = QueryEngine(stock_db, data_mgr, record_mgr)
        
        while True:
            choice = display_menu()
            
            if choice == '0':
                record_mgr.finalize()
                print("\n👋 再见!")
                break
            
            elif choice == '1':
                # 单股范围查询
                print("\n" + "=" * 80)
                print("   模式 1: 单股查询")
                print("=" * 80)
                
                stock_code = input_stock_code(stock_db)
                start_date, end_date = input_date_range()
                concurrent = input_concurrent()
                skip_existing = input_skip_existing()
                
                print(f"\n🚀 开始查询...")
                start_time = time.time()
                
                results = asyncio.run(
                    engine.range_query_single_stock(
                        stock_code,
                        start_date,
                        end_date,
                        max_concurrent=concurrent,
                        skip_existing=skip_existing
                    )
                )
                
                elapsed = time.time() - start_time
                
                if results:
                    success_list = [k for k, v in results.items() if v]
                    fail_list = [k for k, v in results.items() if not v]
                    
                    print(f"\n⏱️  总耗时: {elapsed:.2f} 秒")
                    print(f"✅ 成功: {len(success_list)} 天")
                    print(f"❌ 失败: {len(fail_list)} 天")
                    
                    if fail_list:
                        print(f"\n失败日期: {', '.join(fail_list[:10])}")
                        if len(fail_list) > 10:
                            print(f"... 还有 {len(fail_list)-10} 个")
            
            elif choice == '2':
                # 批量范围查询
                print("\n" + "=" * 80)
                print("   模式 2: 批量查询")
                print("=" * 80)
                
                start_date, end_date = input_date_range()
                concurrent = input_concurrent()
                skip_existing = input_skip_existing()
                
                # 显示任务预览
                date_list, _ = DateRangeUtils.parse_date_range(start_date, end_date)
                trading_dates = DateRangeUtils.filter_trading_days_from_range(date_list)
                total_stocks = len(stock_db.get_all_codes())
                
                print(f"\n📊 任务预览:")
                print(f"  - 股票数量: {total_stocks}")
                print(f"  - 交易日数: {len(trading_dates)}")
                print(f"  - 预计查询: {total_stocks * len(trading_dates)} 次")
                print(f"  - 并发数: {concurrent}")
                print(f"  - 智能断点续传: {'✅' if skip_existing else '❌'}")
                
                confirm = input("\n⚠️  确定执行吗? (yes/no): ").strip().lower()
                
                if confirm == 'yes':
                    print(f"\n🚀 开始批量查询...")
                    start_time = time.time()
                    
                    results = asyncio.run(
                        engine.range_query_batch_stocks(
                            start_date,
                            end_date,
                            max_concurrent=concurrent,
                            skip_existing=skip_existing
                        )
                    )
                    
                    elapsed = time.time() - start_time
                    
                    if results:
                        total_success = sum(
                            sum(1 for v in dates.values() if v)
                            for dates in results.values()
                        )
                        total_queries = sum(len(dates) for dates in results.values())
                        
                        print(f"\n⏱️  总耗时: {elapsed:.2f} 秒")
                        print(f"✅ 成功: {total_success}/{total_queries}")
                        if total_queries > 0:
                            print(f"成功率: {total_success/total_queries*100:.1f}%")
                else:
                    print("❌ 已取消")

            elif choice == '3':
                # 手动刷新股票列表
                print("\n" + "=" * 80)
                print("   刷新股票列表")
                print("=" * 80)

                csv_path = str(script_dir / "hk.csv")
                stock_df, source = StockListManager.refresh_stock_list(csv_path)

                if not stock_df.empty:
                    stock_db.df = stock_df[['id', 'name']].copy()
                    print(f"✅ 当前股票列表: {len(stock_db.df)} 只（来源: {source}）")

                    # 显示最近新增的股票
                    if source == 'akshare':
                        local_df = StockListManager.load_from_csv(csv_path)
                        logger.info(f"📋 股票列表已更新: {len(stock_df)} 只")
                else:
                    print("⚠️  未获取到股票数据")

            print("\n" + "=" * 80)
            cont = input("按 Enter 继续，输入 'q' 退出: ").strip().lower()
            if cont == 'q':
                record_mgr.finalize()
                print("\n👋 再见!")
                break
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断程序")
        if 'record_mgr' in locals():
            record_mgr.finalize()
    except Exception as e:
        logger.error(f"❌ 程序异常: {e}", exc_info=True)
        if 'record_mgr' in locals():
            record_mgr.finalize()


if __name__ == "__main__":
    main()
