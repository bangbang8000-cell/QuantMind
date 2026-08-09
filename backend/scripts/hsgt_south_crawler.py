"""
HKEX 南向资金（港股通）持股数据爬虫 v1.0
作者: 量化交易 Python 专家系统
Python 版本要求: 3.9+
依赖: requests, pandas, beautifulsoup4, lxml, aiohttp

核心功能：
1. ✅ 单日期查询全市场港股通持股数据
2. ✅ 按股票分文件存储，日期追加模式
3. ✅ 智能去重（避免重复写入同一日期）
4. ✅ 支持日期范围批量查询
5. ✅ 断点续传（基于文件内容检查）
"""

import asyncio
import aiohttp
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
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 🔥 安全的目录创建函数 ---
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


# --- 日志配置 ---
def setup_logging() -> logging.Logger:
    """配置日志系统"""
    logger = logging.getLogger("Nanxiang_Quant")
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
        log_filename = log_month_dir / f"nanxiang_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
        
        success_root, error_msg_root = safe_mkdir(log_dir)
        if success_root:
            log_filename = log_dir / f"nanxiang_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()


# --- 港股休市日历 ---
class HKEXTradingCalendar:
    """港股交易日历"""
    
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
                logger.debug(f"🚫 公众假期: {date_formatted}")
                return False
            
            if dt.weekday() in [5, 6]:
                logger.debug(f"🚫 周末: {date_formatted}")
                return False
            
            logger.debug(f"✅ 交易日: {date_formatted}")
            return True
            
        except ValueError as e:
            logger.error(f"❌ 无效日期格式: {date_str}, 错误: {e}")
            return False


# --- 日期范围工具类 ---
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
            
            logger.debug(f"📅 生成日期列表: {len(date_list)} 天 ({date_list[0]} 至 {date_list[-1]})")
            
            return date_list, ""
            
        except ValueError as e:
            return None, f"日期格式错误: {e}"
    
    @staticmethod
    def filter_trading_days_from_range(date_list: List[str]) -> List[Tuple[str, str]]:
        """从日期范围中过滤交易日"""
        trading_dates = []
        
        logger.debug(f"🔍 开始过滤交易日，总日期数: {len(date_list)}")
        
        for idx, date_str in enumerate(date_list):
            try:
                dt = datetime.strptime(date_str, "%Y%m%d")
                file_date = dt.strftime("%Y-%m-%d")
                
                if HKEXTradingCalendar.is_trading_day(file_date):
                    hkex_date = dt.strftime("%Y/%m/%d")
                    trading_dates.append((hkex_date, file_date))
                    
                    if idx < 5:
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


# --- 🆕 南向资金异步抓取器 ---
class AsyncNanxiangFetcher:
    """南向资金（港股通）异步抓取器"""
    
    URL = "https://sc.hkexnews.hk/TuniS/www3.hkexnews.hk/sdw/search/mutualmarket_c.aspx?t=hk"
    TIMEOUT = aiohttp.ClientTimeout(total=30, connect=15)
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]
    
    def __init__(self):
        self.session = None
        self.request_count = 0
        self.last_request_time = time.time()
        self.min_interval = 1.0  # 南向资金数据量大，延长间隔
    
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
        获取指定日期的全市场南向资金数据
        
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
                logger.error(f"❌ 无法获取 ViewState")
                return None
            
            logger.info(f"🔍 [{self.request_count}] 查询南向资金: {query_date}")
            
            # 步骤2: POST 查询
            html = await self._post_query(query_date, viewstate_data)
            
            if not html:
                return None
            
            # 步骤3: 解析 HTML
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, self._parse_html, html)
            
            return df
            
        except asyncio.TimeoutError:
            logger.error(f"❌ 请求超时")
            return None
        except Exception as e:
            logger.error(f"❌ 抓取失败: {e}", exc_info=True)
            return None
    
    async def _get_viewstate(self) -> Optional[dict]:
        """获取页面 ViewState"""
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
                
                return data
                
        except Exception as e:
            logger.error(f"❌ 获取 ViewState 失败: {e}")
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
        """解析 HTML 返回 DataFrame"""
        soup = BeautifulSoup(html, 'lxml')
        
        # 检查警告信息
        alert = soup.select_one('.alert-warning, .alert-danger')
        if alert:
            msg = alert.get_text(strip=True)
            logger.warning(f"⚠️  交易所返回: {msg}")
            return None
        
        # 定位表格
        table = soup.select_one('table#mutualmarket-result')
        if not table:
            logger.warning("⚠️  未找到数据表")
            return None
        
        rows = table.select('tbody tr')
        if not rows:
            logger.warning("⚠️  表格无数据行")
            return None
        
        data = []
        for tr in rows:
            cols = [td.get_text(strip=True) for td in tr.find_all('td')]
            
            if len(cols) < 4:
                continue
            
            try:
                stock_code = AsyncNanxiangFetcher._clean_text(cols[0])
                stock_name = AsyncNanxiangFetcher._clean_text(cols[1])
                shareholding_raw = cols[2]
                percent_raw = cols[3]
                
                shareholding = AsyncNanxiangFetcher._clean_number(shareholding_raw)
                percent = AsyncNanxiangFetcher._clean_text(percent_raw)
                
                if not stock_code or shareholding is None:
                    continue
                
                data.append({
                    "股份代号": stock_code.zfill(5),
                    "名称": stock_name,
                    "于中央结算系统的持股量": shareholding,
                    "占已发行股份/单位百分比": percent
                })
                
            except (ValueError, IndexError) as e:
                logger.debug(f"⚠️  解析行失败: {e}")
                continue
        
        if not data:
            return None
        
        df = pd.DataFrame(data)
        logger.info(f"✅ 解析成功: {len(df)} 只股票")
        return df
    
    @staticmethod
    def _clean_text(text: str) -> str:
        """清理文本"""
        if not text:
            return ""
        text = text.strip()
        # 移除标签内容
        if ':' in text or '：' in text:
            text = text.replace('：', ':').split(':')[-1].strip()
        return text
    
    @staticmethod
    def _clean_number(text: str) -> Optional[int]:
        """清理数字"""
        if not text or text in ['--', 'N/A', '-']:
            return None
        
        text = AsyncNanxiangFetcher._clean_text(text)
        clean = re.sub(r'[^\d-]', '', text)
        
        try:
            return int(clean) if clean else None
        except ValueError:
            return None


# --- 🆕 南向资金数据管理器 ---
class NanxiangDataManager:
    """
    南向资金数据管理器
    
    目录结构：data-hs/{股票名称}/南向资金_{股票名称}_{股票代码}.csv
    """
    
    def __init__(self, base_dir: str = "data-hs"):
        # 🔧 修复：强制使用脚本所在目录
        script_dir = Path(__file__).parent.resolve()
        self.base_dir = script_dir / base_dir
        self._ensure_directory()
    
    def _ensure_directory(self) -> None:
        """确保根目录存在"""
        success, error_msg = safe_mkdir(self.base_dir)
        
        if success:
            abs_path = self.base_dir.resolve()
            logger.info(f"📁 数据根目录: {abs_path}")
            
            # 验证目录是否可写
            test_file = self.base_dir / ".write_test"
            try:
                test_file.touch()
                test_file.unlink()
                logger.debug(f"✅ 目录可写验证通过")
            except Exception as e:
                logger.error(f"❌ 目录不可写: {abs_path}, 错误: {e}")
        else:
            logger.error(f"❌ 创建数据目录失败: {error_msg}")
            logger.warning("⚠️  尝试使用脚本目录作为数据目录")
            self.base_dir = Path(__file__).parent / base_dir
            safe_mkdir(self.base_dir)
    
    def _create_stock_directory(self, stock_name: str) -> Path:
        """创建股票目录"""
        clean_name = re.sub(r'[<>:"/\\|?*]', '', stock_name).strip()
        if not clean_name:
            clean_name = "未命名股票"
        
        target_dir = self.base_dir / clean_name
        
        success, error_msg = safe_mkdir(target_dir)
        
        if success:
            return target_dir
        else:
            logger.error(f"❌ 创建股票目录失败: {error_msg}")
            return self.base_dir
    
    def generate_filename(self, stock_code: str, stock_name: str) -> str:
        """生成文件名"""
        clean_name = re.sub(r'[<>:"/\\|?*]', '', stock_name).strip()
        if not clean_name:
            clean_name = f"股票{stock_code}"
        
        return f"南向资金_{clean_name}_{stock_code}.csv"
    
    def check_date_exists(self, filepath: Path, query_date: str) -> bool:
        """检查指定日期是否已存在于文件中"""
        if not filepath.exists():
            return False
        
        try:
            df_existing = pd.read_csv(filepath, encoding='utf-8-sig')
            
            if '查询日期' not in df_existing.columns:
                return False
            
            # 归一化日期格式
            existing_dates = df_existing['查询日期'].astype(str).str.strip()
            
            # 支持多种格式匹配
            query_date_variants = [
                query_date,  # YYYY-MM-DD
                query_date.replace('-', ''),  # YYYYMMDD
                query_date.replace('-', '/')  # YYYY/MM/DD
            ]
            
            return any(existing_dates.str.contains(variant, regex=False).any() 
                      for variant in query_date_variants)
            
        except Exception as e:
            logger.warning(f"⚠️  检查文件失败: {e}")
            return False
    
    def save_stock_data(
        self,
        stock_code: str,
        stock_name: str,
        query_date: str,
        shareholding: int,
        percent: str
    ) -> Tuple[bool, Optional[str]]:
        """
        保存单只股票的数据（追加模式）
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            query_date: 查询日期 (YYYY-MM-DD)
            shareholding: 持股量
            percent: 占比
        
        Returns:
            (是否成功, 文件路径)
        """
        try:
            # 创建股票目录
            stock_dir = self._create_stock_directory(stock_name)
            
            # 生成文件路径
            filename = self.generate_filename(stock_code, stock_name)
            filepath = stock_dir / filename
            
            # 检查日期是否已存在
            if self.check_date_exists(filepath, query_date):
                logger.debug(f"⏭️  [{stock_code}] 日期 {query_date} 已存在，跳过")
                return True, str(filepath)  # 返回成功（幂等性）
            
            # 准备新数据
            new_data = pd.DataFrame([{
                '查询日期': query_date,
                '股份代号': stock_code,
                '名称': stock_name,
                '于中央结算系统的持股量': shareholding,
                '占已发行股份/单位百分比': percent
            }])
            
            # 追加写入
            if filepath.exists():
                # 文件存在，追加模式
                new_data.to_csv(
                    filepath, 
                    mode='a', 
                    header=False, 
                    index=False, 
                    encoding='utf-8-sig'
                )
                logger.debug(f"📝 [{stock_code}] 追加数据: {query_date}")
            else:
                # 文件不存在，新建
                new_data.to_csv(
                    filepath, 
                    mode='w', 
                    header=True, 
                    index=False, 
                    encoding='utf-8-sig'
                )
                logger.info(f"📄 [{stock_code}] 创建新文件: {filename}")
            
            return True, str(filepath)
            
        except Exception as e:
            logger.error(f"❌ [{stock_code}] 保存失败: {e}", exc_info=True)
            return False, None
    
    def batch_save_market_data(
        self,
        df_market: pd.DataFrame,
        query_date: str
    ) -> Tuple[int, int]:
        """
        批量保存全市场数据
        
        Args:
            df_market: 市场数据 DataFrame
            query_date: 查询日期 (YYYY-MM-DD)
        
        Returns:
            (成功数, 失败数)
        """
        if df_market is None or df_market.empty:
            logger.warning("⚠️  市场数据为空")
            return 0, 0
        
        success_count = 0
        fail_count = 0
        
        for idx, row in df_market.iterrows():
            try:
                stock_code = str(row['股份代号']).zfill(5)
                stock_name = str(row['名称'])
                shareholding = row['于中央结算系统的持股量']
                percent = str(row['占已发行股份/单位百分比'])
                
                success, _ = self.save_stock_data(
                    stock_code, stock_name, query_date, shareholding, percent
                )
                
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                
            except Exception as e:
                logger.error(f"❌ 保存行 {idx} 失败: {e}")
                fail_count += 1
        
        logger.info(f"💾 保存完成: 成功 {success_count}, 失败 {fail_count}")
        
        return success_count, fail_count


# --- 🆕 查询引擎 ---
class NanxiangQueryEngine:
    """南向资金查询引擎"""
    
    def __init__(self, data_mgr: NanxiangDataManager):
        self.data_mgr = data_mgr
    
    async def query_date_range(
        self,
        start_date: str,
        end_date: str,
        skip_existing: bool = True
    ) -> Dict[str, bool]:
        """
        日期范围查询
        
        Args:
            start_date: 起始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            skip_existing: 是否跳过已存在日期
        
        Returns:
            {日期: 是否成功}
        """
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
        
        description = DateRangeUtils.describe_date_range(start_date, end_date)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 南向资金查询")
        logger.info(f"  - 时间范围: {description}")
        logger.info(f"  - 交易日数: {len(trading_dates)} 天")
        logger.info(f"  - 断点续传: {'✅' if skip_existing else '❌'}")
        logger.info(f"{'='*80}\n")
        
        # 🆕 断点续传：检查哪些日期已完成
        dates_to_query = []
        skipped_count = 0
        
        if skip_existing:
            for hkex_date, file_date in trading_dates:
                # 简单检查：扫描 data-hs 下是否有该日期的文件
                if self._check_date_completed(file_date):
                    logger.debug(f"⏭️  跳过已完成: {file_date}")
                    skipped_count += 1
                else:
                    dates_to_query.append((hkex_date, file_date))
            
            logger.info(f"📋 断点续传分析:")
            logger.info(f"  - 总交易日: {len(trading_dates)}")
            logger.info(f"  - 已完成: {skipped_count} 天")
            logger.info(f"  - 待查询: {len(dates_to_query)} 天\n")
        else:
            dates_to_query = trading_dates
        
        if not dates_to_query:
            logger.info("✅ 所有日期已完成")
            return {}
        
        # 🚀 异步查询
        logger.info(f"🚀 开始查询 {len(dates_to_query)} 个交易日...\n")
        
        async with AsyncNanxiangFetcher() as fetcher:
            results = {}
            
            for hkex_date, file_date in dates_to_query:
                try:
                    # 获取全市场数据
                    df_market = await fetcher.fetch_market_data(hkex_date)
                    
                    if df_market is not None and not df_market.empty:
                        # 批量保存
                        success_count, fail_count = self.data_mgr.batch_save_market_data(
                            df_market, file_date
                        )
                        
                        results[file_date] = (fail_count == 0)
                        
                        logger.info(f"✅ [{file_date}] 保存完成: {len(df_market)} 只股票")
                    else:
                        results[file_date] = False
                        logger.warning(f"⚠️  [{file_date}] 无数据")
                    
                    # 延迟（避免封IP）
                    await asyncio.sleep(random.uniform(1.5, 3.0))
                    
                except Exception as e:
                    logger.error(f"❌ [{file_date}] 查询失败: {e}")
                    results[file_date] = False
        
        # 统计结果
        success_count = sum(1 for v in results.values() if v)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"✅ 查询完成")
        logger.info(f"  - 成功: {success_count}/{len(results)}")
        logger.info(f"  - 失败: {len(results) - success_count}")
        logger.info(f"{'='*80}\n")
        
        return results
    
    def _check_date_completed(self, query_date: str) -> bool:
        """
        检查指定日期是否已完成（快速检查）
        
        策略：随机抽样 10 个文件，如果都包含该日期则认为完成
        """
        try:
            csv_files = list(self.data_mgr.base_dir.rglob("南向资金_*.csv"))
            
            if len(csv_files) == 0:
                return False
            
            # 随机抽样
            sample_size = min(10, len(csv_files))
            sampled_files = random.sample(csv_files, sample_size)
            
            for filepath in sampled_files:
                if not self.data_mgr.check_date_exists(filepath, query_date):
                    return False
            
            return True
            
        except Exception as e:
            logger.debug(f"⚠️  检查日期失败: {e}")
            return False


# --- 🆕 用户交互模块 ---
def display_menu() -> str:
    """显示主菜单"""
    print("\n" + "=" * 80)
    print("   HKEX 南向资金（港股通）持股查询工具 v1.0   ")
    print("=" * 80)
    print("\n请选择查询模式:")
    print("  [1] 日期范围查询 (获取指定时间段的南向资金数据)")
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
    print("提示:")
    print("  - 单日查询: 起始和结束日期相同 (如 20250701 到 20250701)")
    print("  - 月度查询: 输入整月范围 (如 20250701 到 20250731)")
    print("  - 年度查询: 输入整年范围 (如 20250101 到 20251231)")
    print("=" * 80)
    
    while True:
        start_raw = input("👉 起始日期 (YYYYMMDD): ").strip()
        
        if len(start_raw) != 8 or not start_raw.isdigit():
            print("❌ 起始日期格式错误")
            continue
        
        end_raw = input("👉 结束日期 (YYYYMMDD，留空表示单日): ").strip()
        
        if not end_raw:
            end_raw = start_raw
            print(f"💡 未输入结束日期，默认为单日查询: {start_raw}")
        
        if len(end_raw) != 8 or not end_raw.isdigit():
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


def input_skip_existing() -> bool:
    """询问是否启用断点续传"""
    raw = input("👉 是否启用智能断点续传? (Y/n): ").strip().lower()
    return raw in ['', 'y', 'yes']


# --- 主程序 ---
def main():
    """主程序"""
    try:
        # 🔧 修复：显示数据目录的绝对路径
        script_dir = Path(__file__).parent.resolve()
        data_dir = script_dir / "data-hs"
        
        print(f"\n📂 数据将保存到: {data_dir}")
        print(f"   (脚本目录: {script_dir})\n")
        
        # 初始化组件
        data_mgr = NanxiangDataManager()
        engine = NanxiangQueryEngine(data_mgr)
        
        while True:
            choice = display_menu()
            
            if choice == '0':
                print("\n👋 再见!")
                break
            
            elif choice == '1':
                print("\n" + "=" * 80)
                print("   模式 1: 日期范围查询")
                print("=" * 80)
                
                start_date, end_date = input_date_range()
                skip_existing = input_skip_existing()
                
                print(f"\n🚀 开始查询...")
                start_time = time.time()
                
                results = asyncio.run(
                    engine.query_date_range(
                        start_date,
                        end_date,
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
