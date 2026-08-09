"""
HKEX 北向资金（沪深港通）持股数据爬虫 v2.1
作者: 量化交易 Python 专家系统
Python 版本要求: 3.9+
依赖: aiohttp, pandas, beautifulsoup4, lxml

核心功能：
1. ✅ 沪股通 + 深股通双市场并发抓取
2. ✅ 按股票分文件存储，日期追加模式
3. ✅ 智能命名：北向资金_{A股/H股}_{股票名称}+{股票代码}.csv
4. ✅ 智能去重（避免重复写入同一日期）
5. ✅ 支持日期范围批量查询
6. ✅ 断点续传（基于文件内容检查 + 新旧文件兼容）
7. ✅ 异步多线程架构（极致性能）

更新日志 v2.1：
- 🆕 文件名包含股票名称：{前缀}_{股票名称}+{股票代码}.csv
- 🆕 兼容旧版文件命名规则（自动识别并使用已存在文件）
- 🆕 文件名非法字符清理和长度限制
"""

import asyncio
import aiohttp
import pandas as pd
import logging
import re
import time
import random
import os
import ssl
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Literal
from dataclasses import dataclass
from enum import Enum
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================================
# 🔧 配置与常量
# ============================================================================

class Market(str, Enum):
    """市场枚举"""
    SH = "sh"  # 沪股通（上交所 A 股）
    SZ = "sz"  # 深股通（深交所 A 股）


@dataclass
class MarketConfig:
    """市场配置"""
    code: Market
    name: str
    url: str
    file_prefix: str
    percent_column: str


# 市场配置字典
MARKET_CONFIGS = {
    Market.SH: MarketConfig(
        code=Market.SH,
        name="沪股通",
        url="https://sc.hkexnews.hk/TuniS/www3.hkexnews.hk/sdw/search/mutualmarket_c.aspx?t=sh",
        file_prefix="北向资金_A股",
        percent_column="占于上交所上市及交易的证券总数的百分比"
    ),
    Market.SZ: MarketConfig(
        code=Market.SZ,
        name="深股通",
        url="https://sc.hkexnews.hk/TuniS/www3.hkexnews.hk/sdw/search/mutualmarket_c.aspx?t=sz",
        file_prefix="北向资金_H股",
        percent_column="占于深交所上市及交易的证券总数的百分比"
    ),
}


# ============================================================================
# 🛡️ 工具函数
# ============================================================================

def safe_mkdir(path: Path, mode: int = 0o755) -> Tuple[bool, Optional[str]]:
    """安全创建目录（带权限检查）"""
    try:
        parent = path.parent
        if parent.exists() and not os.access(parent, os.W_OK):
            return False, f"父目录不可写: {parent}"
        
        path.mkdir(parents=True, exist_ok=True, mode=mode)
        
        if not os.access(path, os.W_OK):
            return False, f"目录创建成功但不可写: {path}"
        
        return True, None
        
    except PermissionError as e:
        return False, f"权限错误: {e}"
    except Exception as e:
        return False, f"创建失败: {e}"


def setup_logging() -> logging.Logger:
    """配置日志系统"""
    logger = logging.getLogger("Beixiang_Quant")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    script_dir = Path(__file__).parent.resolve()
    log_dir = script_dir / "log"
    current_month = datetime.now().strftime("%Y%m")
    log_month_dir = log_dir / current_month
    
    success, error_msg = safe_mkdir(log_month_dir)
    
    if success:
        log_filename = log_month_dir / f"beixiang_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        try:
            file_handler = logging.FileHandler(log_filename, encoding='utf-8')
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
            print(f"📝 日志文件: {log_filename.relative_to(script_dir)}")
        except Exception as e:
            print(f"⚠️  无法创建日志文件: {e}")
    else:
        print(f"⚠️  无法创建月份目录: {error_msg}")
        success_root, _ = safe_mkdir(log_dir)
        if success_root:
            log_filename = log_dir / f"beixiang_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            try:
                file_handler = logging.FileHandler(log_filename, encoding='utf-8')
                file_handler.setFormatter(formatter)
                file_handler.setLevel(logging.DEBUG)
                logger.addHandler(file_handler)
                print(f"📝 日志文件（降级）: {log_filename.relative_to(script_dir)}")
            except Exception as e:
                print(f"⚠️  无法创建日志文件: {e}")
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    return logger


logger = setup_logging()


# ============================================================================
# 📅 交易日历
# ============================================================================

class HKEXTradingCalendar:
    """港股交易日历（A 股也适用，因为沪深港通同步）"""
    
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
    
    @classmethod
    def is_trading_day(cls, date_str: str) -> bool:
        """判断是否为交易日"""
        try:
            if len(date_str) == 8 and date_str.isdigit():
                dt = datetime.strptime(date_str, "%Y%m%d")
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            
            date_formatted = dt.strftime("%Y-%m-%d")
            
            if date_formatted in cls.PUBLIC_HOLIDAYS:
                return False
            
            if dt.weekday() in [5, 6]:
                return False
            
            return True
            
        except ValueError:
            return False


class DateRangeUtils:
    """日期范围工具类"""
    
    @staticmethod
    def parse_date_range(start_str: str, end_str: str) -> Tuple[Optional[List[str]], str]:
        """解析日期范围"""
        try:
            start_dt = datetime.strptime(start_str, "%Y%m%d")
            end_dt = datetime.strptime(end_str, "%Y%m%d")
            
            if start_dt > end_dt:
                return None, "起始日期不能晚于结束日期"
            
            if end_dt > datetime.now():
                return None, "不能查询未来日期"
            
            date_list = []
            current = start_dt
            
            while current <= end_dt:
                date_list.append(current.strftime("%Y%m%d"))
                current += timedelta(days=1)
            
            return date_list, ""
            
        except ValueError as e:
            return None, f"日期格式错误: {e}"
    
    @staticmethod
    def filter_trading_days_from_range(date_list: List[str]) -> List[Tuple[str, str]]:
        """从日期范围中过滤交易日"""
        trading_dates = []
        
        for date_str in date_list:
            try:
                dt = datetime.strptime(date_str, "%Y%m%d")
                file_date = dt.strftime("%Y-%m-%d")
                
                if HKEXTradingCalendar.is_trading_day(file_date):
                    hkex_date = dt.strftime("%Y/%m/%d")
                    trading_dates.append((hkex_date, file_date))
                
            except ValueError:
                continue
        
        return trading_dates


# ============================================================================
# 🌐 异步抓取器（多市场版）
# ============================================================================

class AsyncBeixiangFetcher:
    """北向资金异步抓取器（支持沪深港通）"""
    
    TIMEOUT = aiohttp.ClientTimeout(total=30, connect=15)
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]
    
    def __init__(self, market: Market):
        self.market = market
        self.config = MARKET_CONFIGS[market]
        self.session = None
        self.request_count = 0
        self.last_request_time = time.time()
        self.min_interval = 1.0
    
    async def __aenter__(self):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(
            limit=10,
            ssl=ssl_context,
            ttl_dns_cache=300
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.TIMEOUT,
            headers={
                "User-Agent": random.choice(self.USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Connection": "keep-alive",
            }
        )
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            await asyncio.sleep(0.25)
    
    async def _rate_limit(self):
        """速率限制"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.min_interval:
            wait_time = self.min_interval - elapsed
            await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    async def fetch_market_data(self, query_date: str) -> Optional[pd.DataFrame]:
        """
        获取指定日期的市场数据
        
        Args:
            query_date: 查询日期 (格式: YYYY/MM/DD)
        
        Returns:
            DataFrame 或 None
        """
        try:
            await self._rate_limit()
            self.request_count += 1
            
            # 步骤1: 获取 ViewState
            viewstate_data = await self._get_viewstate()
            if not viewstate_data:
                logger.error(f"❌ [{self.config.name}] 无法获取 ViewState")
                return None
            
            logger.info(f"🔍 [{self.config.name}][{self.request_count}] 查询: {query_date}")
            
            # 步骤2: POST 查询
            html = await self._post_query(query_date, viewstate_data)
            
            if not html:
                return None
            
            # 步骤3: 解析 HTML
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, self._parse_html, html)
            
            return df
            
        except asyncio.TimeoutError:
            logger.error(f"❌ [{self.config.name}] 请求超时")
            return None
        except Exception as e:
            logger.error(f"❌ [{self.config.name}] 抓取失败: {e}", exc_info=True)
            return None
    
    async def _get_viewstate(self) -> Optional[dict]:
        """获取页面 ViewState"""
        try:
            async with self.session.get(self.config.url) as response:
                response.raise_for_status()
                html = await response.text()
                
                loop = asyncio.get_event_loop()
                soup = await loop.run_in_executor(None, BeautifulSoup, html, 'lxml')
                
                fields = ['__VIEWSTATE', '__VIEWSTATEGENERATOR', 'today']
                data = {}
                
                for field in fields:
                    element = soup.find(id=field)
                    if not element or 'value' not in element.attrs:
                        logger.error(f"❌ [{self.config.name}] 缺少必需字段: {field}")
                        return None
                    data[field] = element['value']
                
                return data
                
        except Exception as e:
            logger.error(f"❌ [{self.config.name}] 获取 ViewState 失败: {e}")
            return None
    
    async def _post_query(self, query_date: str, viewstate: dict) -> Optional[str]:
        """POST 查询请求"""
        try:
            payload = {
                '__EVENTTARGET': 'btnSearch',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE': viewstate['__VIEWSTATE'],
                '__VIEWSTATEGENERATOR': viewstate['__VIEWSTATEGENERATOR'],
                'today': viewstate['today'],
                'sortBy': 'stockcode',
                'sortDirection': 'asc',
                'txtShareholdingDate': query_date,
            }
            
            headers = {
                'Origin': 'https://sc.hkexnews.hk',
                'Referer': self.config.url,
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            async with self.session.post(
                self.config.url, 
                data=payload, 
                headers=headers
            ) as response:
                response.raise_for_status()
                return await response.text()
                
        except Exception as e:
            logger.error(f"❌ [{self.config.name}] POST 请求失败: {e}")
            return None
    
    def _parse_html(self, html: str) -> Optional[pd.DataFrame]:
        """解析 HTML 返回 DataFrame"""
        soup = BeautifulSoup(html, 'lxml')
        
        # 检查警告信息
        alert = soup.select_one('.alert-warning, .alert-danger')
        if alert:
            msg = alert.get_text(strip=True)
            logger.warning(f"⚠️  [{self.config.name}] 交易所返回: {msg}")
            return None
        
        # 定位表格
        table = soup.select_one('table#mutualmarket-result')
        if not table:
            logger.warning(f"⚠️  [{self.config.name}] 未找到数据表")
            return None
        
        rows = table.select('tbody tr')
        if not rows:
            logger.warning(f"⚠️  [{self.config.name}] 表格无数据行")
            return None
        
        data = []
        for tr in rows:
            cols = [td.get_text(strip=True) for td in tr.find_all('td')]
            
            if len(cols) < 4:
                continue
            
            try:
                stock_code = self._clean_text(cols[0])
                stock_name = self._clean_text(cols[1])
                shareholding_raw = cols[2]
                percent_raw = cols[3]
                
                shareholding = self._clean_number(shareholding_raw)
                percent = self._clean_text(percent_raw)
                
                if not stock_code or shareholding is None:
                    continue
                
                data.append({
                    "股份代号": stock_code.zfill(5),
                    "名称": stock_name,
                    "于中央结算系统的持股量": shareholding,
                    self.config.percent_column: percent
                })
                
            except (ValueError, IndexError):
                continue
        
        if not data:
            return None
        
        df = pd.DataFrame(data)
        logger.info(f"✅ [{self.config.name}] 解析成功: {len(df)} 只股票")
        return df
    
    @staticmethod
    def _clean_text(text: str) -> str:
        """清理文本"""
        if not text:
            return ""
        text = text.strip()
        if ':' in text or '：' in text:
            text = text.replace('：', ':').split(':')[-1].strip()
        return text
    
    @staticmethod
    def _clean_number(text: str) -> Optional[int]:
        """清理数字"""
        if not text or text in ['--', 'N/A', '-']:
            return None
        
        text = AsyncBeixiangFetcher._clean_text(text)
        clean = re.sub(r'[^\d-]', '', text)
        
        try:
            return int(clean) if clean else None
        except ValueError:
            return None


# ============================================================================
# 💾 数据管理器（v2.1 新增智能命名）
# ============================================================================

class BeixiangDataManager:
    """
    北向资金数据管理器 v2.1
    
    目录结构：data-AH/{股票名称}/{文件名}.csv
    
    文件名（新规则）：
      - 沪股通：北向资金_A股_{股票名称}+{股票代码}.csv
      - 深股通：北向资金_H股_{股票名称}+{股票代码}.csv
      示例：北向资金_A股_贵州茅台+600519.csv
    
    兼容旧规则：
      - 自动识别已存在的旧文件（格式：前缀_代码.csv）
      - 优先使用已存在文件，避免重复创建
    """
    
    # 最大文件名长度（Windows 限制为 260，预留路径空间）
    MAX_FILENAME_LENGTH = 100
    
    def __init__(self, base_dir: str = "data-AH"):
        script_dir = Path(__file__).parent.resolve()
        self.base_dir = script_dir / base_dir
        self._ensure_directory()
    
    def _ensure_directory(self) -> None:
        """确保根目录存在"""
        success, error_msg = safe_mkdir(self.base_dir)
        
        if success:
            abs_path = self.base_dir.resolve()
            logger.info(f"📁 数据根目录: {abs_path}")
        else:
            logger.error(f"❌ 创建数据目录失败: {error_msg}")
    
    def _create_stock_directory(self, stock_name: str) -> Path:
        """创建股票目录"""
        clean_name = self._sanitize_filename_component(stock_name)
        if not clean_name:
            clean_name = "未命名股票"
        
        target_dir = self.base_dir / clean_name
        
        success, error_msg = safe_mkdir(target_dir)
        
        if success:
            return target_dir
        else:
            logger.error(f"❌ 创建股票目录失败: {error_msg}")
            return self.base_dir
    
    @staticmethod
    def _sanitize_filename_component(text: str, max_length: int = 30) -> str:
        """
        清理文件名组件（股票名称）
        
        Args:
            text: 原始文本
            max_length: 最大长度
        
        Returns:
            清理后的安全文件名组件
        
        规则：
        1. 移除非法字符: < > : " / \\ | ? *
        2. 空格转下划线
        3. 连续下划线合并
        4. 截取最大长度
        """
        # 移除所有非法字符，替换为下划线
        clean = re.sub(r'[<>:"/\\|?*]', '_', text).strip()
        
        # 移除多余的空格和下划线
        clean = re.sub(r'\s+', '_', clean)  # 空格转下划线
        clean = re.sub(r'_+', '_', clean)    # 连续下划线合并
        clean = clean.strip('_')             # 去除首尾下划线
        
        # 截取长度（防止路径过长）
        if len(clean) > max_length:
            clean = clean[:max_length].rstrip('_')
        
        return clean if clean else "未命名"
    
    def generate_filename(self, market: Market, stock_code: str, stock_name: str) -> str:
        """
        生成文件名（新规则）
        
        Args:
            market: 市场类型
            stock_code: 股票代码（5位数字）
            stock_name: 股票名称
        
        Returns:
            文件名，格式：{前缀}_{股票名称}+{股票代码}.csv
            示例：
            - 沪股通：北向资金_A股_贵州茅台+600519.csv
            - 深股通：北向资金_H股_平安银行+000001.csv
        """
        config = MARKET_CONFIGS[market]
        
        # 清理股票名称
        clean_name = self._sanitize_filename_component(stock_name, max_length=20)
        if not clean_name:
            clean_name = f"股票{stock_code}"
        
        # 组装文件名
        filename = f"{config.file_prefix}_{clean_name}+{stock_code}.csv"
        
        # 再次验证总长度（双重保险）
        if len(filename) > self.MAX_FILENAME_LENGTH:
            # 缩短股票名称部分
            max_name_len = self.MAX_FILENAME_LENGTH - len(config.file_prefix) - len(stock_code) - 10
            clean_name = clean_name[:max_name_len].rstrip('_')
            filename = f"{config.file_prefix}_{clean_name}+{stock_code}.csv"
        
        return filename
    
    def _find_existing_file(self, stock_dir: Path, market: Market, stock_code: str) -> Optional[Path]:
        """
        查找已存在的文件（兼容新旧命名规则）
        
        Args:
            stock_dir: 股票目录
            market: 市场类型
            stock_code: 股票代码
        
        Returns:
            文件路径或 None
        
        查找策略：
        1. 优先匹配新规则：{前缀}_{股票名称}+{股票代码}.csv
        2. 降级匹配旧规则：{前缀}_{股票代码}.csv
        3. 都不存在则返回 None
        """
        config = MARKET_CONFIGS[market]
        
        # 方案1: 精确匹配（新规则，通过 glob 模糊匹配）
        pattern_new = f"{config.file_prefix}_*+{stock_code}.csv"
        matches = list(stock_dir.glob(pattern_new))
        if matches:
            return matches[0]  # 返回第一个匹配
        
        # 方案2: 旧规则兼容（格式：前缀_代码.csv）
        old_filename = f"{config.file_prefix}_{stock_code}.csv"
        old_path = stock_dir / old_filename
        if old_path.exists():
            return old_path
        
        return None
    
    def check_date_exists(self, filepath: Path, query_date: str) -> bool:
        """
        检查指定日期是否已存在于文件中
        
        Args:
            filepath: 文件路径
            query_date: 查询日期 (YYYY-MM-DD)
        
        Returns:
            是否存在
        """
        if not filepath.exists():
            return False
        
        try:
            df_existing = pd.read_csv(filepath, encoding='utf-8-sig')
            
            if '日期' not in df_existing.columns:
                return False
            
            existing_dates = df_existing['日期'].astype(str).str.strip()
            
            # 支持多种日期格式
            query_date_variants = [
                query_date,
                query_date.replace('-', ''),
                query_date.replace('-', '/')
            ]
            
            return any(existing_dates.str.contains(variant, regex=False).any() 
                      for variant in query_date_variants)
            
        except Exception:
            return False
    
    def save_stock_data(
        self,
        market: Market,
        stock_code: str,
        stock_name: str,
        query_date: str,
        shareholding: int,
        percent: str
    ) -> Tuple[bool, Optional[str]]:
        """
        保存单只股票的数据（追加模式，兼容新旧文件）
        
        Args:
            market: 市场类型
            stock_code: 股票代码
            stock_name: 股票名称
            query_date: 日期
            shareholding: 持股量
            percent: 百分比
        
        Returns:
            (是否成功, 文件路径)
        """
        try:
            config = MARKET_CONFIGS[market]
            stock_dir = self._create_stock_directory(stock_name)
            
            # 🔍 查找已存在的文件（新旧规则兼容）
            existing_file = self._find_existing_file(stock_dir, market, stock_code)
            
            if existing_file:
                # 使用已存在的文件
                filepath = existing_file
                logger.debug(f"🔄 [{config.name}][{stock_code}] 使用已存在文件: {filepath.name}")
            else:
                # 创建新文件（使用新规则）
                filename = self.generate_filename(market, stock_code, stock_name)
                filepath = stock_dir / filename
            
            # 检查日期是否已存在
            if self.check_date_exists(filepath, query_date):
                logger.debug(f"⏭️  [{config.name}][{stock_code}] 日期 {query_date} 已存在")
                return True, str(filepath)
            
            # 准备新数据
            new_data = pd.DataFrame([{
                '日期': query_date,
                '股份代号': stock_code,
                '名称': stock_name,
                '于中央结算系统的持股量': shareholding,
                config.percent_column: percent
            }])
            
            # 写入文件
            if filepath.exists():
                new_data.to_csv(
                    filepath, 
                    mode='a', 
                    header=False, 
                    index=False, 
                    encoding='utf-8-sig'
                )
                logger.debug(f"📝 [{config.name}][{stock_code}] 追加: {query_date}")
            else:
                new_data.to_csv(
                    filepath, 
                    mode='w', 
                    header=True, 
                    index=False, 
                    encoding='utf-8-sig'
                )
                logger.info(f"📄 [{config.name}][{stock_code}] 创建新文件: {filepath.name}")
            
            return True, str(filepath)
            
        except Exception as e:
            logger.error(f"❌ [{config.name}][{stock_code}] 保存失败: {e}")
            return False, None
    
    def batch_save_market_data(
        self,
        market: Market,
        df_market: pd.DataFrame,
        query_date: str
    ) -> Tuple[int, int]:
        """
        批量保存市场数据
        
        Args:
            market: 市场类型
            df_market: 市场数据 DataFrame
            query_date: 查询日期
        
        Returns:
            (成功数, 失败数)
        """
        if df_market is None or df_market.empty:
            return 0, 0
        
        config = MARKET_CONFIGS[market]
        success_count = 0
        fail_count = 0
        
        for idx, row in df_market.iterrows():
            try:
                stock_code = str(row['股份代号']).zfill(5)
                stock_name = str(row['名称'])
                shareholding = row['于中央结算系统的持股量']
                percent = str(row[config.percent_column])
                
                success, _ = self.save_stock_data(
                    market, stock_code, stock_name, query_date, shareholding, percent
                )
                
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                
            except Exception as e:
                logger.error(f"❌ [{config.name}] 保存行 {idx} 失败: {e}")
                fail_count += 1
        
        logger.info(f"💾 [{config.name}] 保存完成: 成功 {success_count}, 失败 {fail_count}")
        
        return success_count, fail_count


# ============================================================================
# 🚀 查询引擎（多市场并发版）
# ============================================================================

class BeixiangQueryEngine:
    """北向资金查询引擎（支持沪深港通并发）"""
    
    def __init__(self, data_mgr: BeixiangDataManager):
        self.data_mgr = data_mgr
    
    async def query_date_range(
        self,
        start_date: str,
        end_date: str,
        markets: List[Market] = None,
        skip_existing: bool = True
    ) -> Dict[str, Dict[Market, bool]]:
        """
        日期范围查询（多市场并发）
        
        Args:
            start_date: 起始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            markets: 要查询的市场列表，默认全部
            skip_existing: 是否跳过已存在日期
        
        Returns:
            {日期: {市场: 是否成功}}
        """
        if markets is None:
            markets = [Market.SH, Market.SZ]
        
        # 解析日期范围
        date_list, error_msg = DateRangeUtils.parse_date_range(start_date, end_date)
        if date_list is None:
            logger.error(f"❌ {error_msg}")
            return {}
        
        # 过滤交易日
        trading_dates = DateRangeUtils.filter_trading_days_from_range(date_list)
        
        if not trading_dates:
            logger.warning("⚠️  范围内无交易日")
            return {}
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 北向资金查询（沪深港通）")
        logger.info(f"  - 时间范围: {start_date} 至 {end_date}")
        logger.info(f"  - 交易日数: {len(trading_dates)} 天")
        logger.info(f"  - 市场数量: {len(markets)} 个（{', '.join([MARKET_CONFIGS[m].name for m in markets])}）")
        logger.info(f"  - 断点续传: {'✅' if skip_existing else '❌'}")
        logger.info(f"{'='*80}\n")
        
        # 🔥 并发查询
        results = {}
        
        for hkex_date, file_date in trading_dates:
            logger.info(f"📅 [{file_date}] 开始双市场查询...")
            
            # 并发获取两个市场的数据
            tasks = [
                self._fetch_and_save_market(market, hkex_date, file_date)
                for market in markets
            ]
            
            market_results = await asyncio.gather(*tasks)
            
            results[file_date] = {
                markets[i]: market_results[i]
                for i in range(len(markets))
            }
            
            # 统计
            success_markets = [m for m, success in results[file_date].items() if success]
            logger.info(f"✅ [{file_date}] 完成: {len(success_markets)}/{len(markets)} 市场成功\n")
            
            # 延迟
            await asyncio.sleep(random.uniform(1.5, 3.0))
        
        # 总结
        total_success = sum(
            sum(1 for success in day_results.values() if success)
            for day_results in results.values()
        )
        total_tasks = len(results) * len(markets)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ 查询完成")
        logger.info(f"  - 总任务数: {total_tasks}")
        logger.info(f"  - 成功: {total_success}")
        logger.info(f"  - 失败: {total_tasks - total_success}")
        logger.info(f"{'='*80}\n")
        
        return results
    
    async def _fetch_and_save_market(
        self,
        market: Market,
        hkex_date: str,
        file_date: str
    ) -> bool:
        """获取并保存单个市场的数据"""
        try:
            async with AsyncBeixiangFetcher(market) as fetcher:
                df_market = await fetcher.fetch_market_data(hkex_date)
                
                if df_market is not None and not df_market.empty:
                    success_count, fail_count = self.data_mgr.batch_save_market_data(
                        market, df_market, file_date
                    )
                    
                    return fail_count == 0
                else:
                    logger.warning(f"⚠️  [{MARKET_CONFIGS[market].name}][{file_date}] 无数据")
                    return False
                
        except Exception as e:
            logger.error(f"❌ [{MARKET_CONFIGS[market].name}][{file_date}] 查询失败: {e}")
            return False


# ============================================================================
# 🎮 用户交互
# ============================================================================

def display_menu() -> str:
    """显示主菜单"""
    print("\n" + "=" * 80)
    print("   HKEX 北向资金（沪深港通）持股查询工具 v2.1   ")
    print("=" * 80)
    print("\n📌 新特性:")
    print("  - 智能文件命名：北向资金_{A股/H股}_{股票名称}+{股票代码}.csv")
    print("  - 自动兼容旧版文件，无需迁移")
    print("\n请选择查询模式:")
    print("  [1] 日期范围查询（沪股通 + 深股通双市场并发）")
    print("  [0] 退出程序")
    print("=" * 80)
    
    while True:
        choice = input("\n👉 请输入选项 (0-1): ").strip()
        if choice in ['0', '1']:
            return choice
        print("❌ 无效选项")


def input_date_range() -> Tuple[str, str]:
    """输入日期范围"""
    print("\n" + "=" * 80)
    print("   日期范围设置")
    print("=" * 80)
    
    while True:
        start_raw = input("👉 起始日期 (YYYYMMDD): ").strip()
        
        if len(start_raw) != 8 or not start_raw.isdigit():
            print("❌ 起始日期格式错误")
            continue
        
        end_raw = input("👉 结束日期 (YYYYMMDD，留空表示单日): ").strip()
        
        if not end_raw:
            end_raw = start_raw
        
        if len(end_raw) != 8 or not end_raw.isdigit():
            print("❌ 结束日期格式错误")
            continue
        
        date_list, error_msg = DateRangeUtils.parse_date_range(start_raw, end_raw)
        
        if date_list is None:
            print(f"❌ {error_msg}")
            continue
        
        trading_dates = DateRangeUtils.filter_trading_days_from_range(date_list)
        
        print(f"\n📊 范围信息:")
        print(f"  - 时间跨度: {start_raw} 至 {end_raw}")
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


def input_skip_existing() -> bool:
    """询问是否启用断点续传"""
    raw = input("👉 是否启用智能断点续传? (Y/n): ").strip().lower()
    return raw in ['', 'y', 'yes']


# ============================================================================
# 🚀 主程序
# ============================================================================

def main():
    """主程序"""
    try:
        script_dir = Path(__file__).parent.resolve()
        data_dir = script_dir / "data-AH"
        
        print(f"\n📂 数据将保存到: {data_dir}")
        print(f"   (脚本目录: {script_dir})")
        print(f"\n💡 文件命名示例:")
        print(f"   - 沪股通: 北向资金_A股_贵州茅台+600519.csv")
        print(f"   - 深股通: 北向资金_H股_平安银行+000001.csv\n")
        
        data_mgr = BeixiangDataManager()
        engine = BeixiangQueryEngine(data_mgr)
        
        while True:
            choice = display_menu()
            
            if choice == '0':
                print("\n👋 再见!")
                break
            
            elif choice == '1':
                print("\n" + "=" * 80)
                print("   模式 1: 日期范围查询（沪深港通双市场）")
                print("=" * 80)
                
                start_date, end_date = input_date_range()
                skip_existing = input_skip_existing()
                
                print(f"\n🚀 开始查询...")
                start_time = time.time()
                
                results = asyncio.run(
                    engine.query_date_range(
                        start_date,
                        end_date,
                        markets=[Market.SH, Market.SZ],
                        skip_existing=skip_existing
                    )
                )
                
                elapsed = time.time() - start_time
                
                if results:
                    total_tasks = sum(len(day_results) for day_results in results.values())
                    total_success = sum(
                        sum(1 for success in day_results.values() if success)
                        for day_results in results.values()
                    )
                    
                    print(f"\n⏱️  总耗时: {elapsed:.2f} 秒")
                    print(f"✅ 成功: {total_success}/{total_tasks} 任务")
            
            print("\n" + "=" * 80)
            cont = input("按 Enter 继续，输入 'q' 退出: ").strip().lower()
            if cont == 'q':
                print("\n👋 再见!")
                break
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断程序")
    except Exception as e:
        logger.error(f"❌ 程序异常: {e}", exc_info=True)


if __name__ == "__main__":
    main()

