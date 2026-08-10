import re
from typing import Optional

class StockCodeUtil:
    """股票代码标准化工具类。

    QuantMind 规范格式: suffix 型 600036.SH
    - suffix 格式 (600036.SH) 为唯一规范格式，所有新代码应使用此格式
    - prefix 格式 (SH600036) 保留向后兼容，新代码不应使用
    - qlib 格式 (sh600036) 仅用于 Qlib 迁移桥接
    """

    @staticmethod
    def to_suffix(code: str) -> str:
        """转换为规范 suffix 格式 600036.SH

        这是 QuantMind 的唯一规范格式，所有新代码应优先使用。

        Examples:
            - 'SH600000' -> '600000.SH'
            - 'sh600000' -> '600000.SH'
            - '600000' -> '600000.SH' (自动识别交易所)
            - 'BJ830001' -> '830001.BJ'
        """
        if not code:
            return ""

        code = str(code).upper().strip()

        # 1. 已经是正确的 Suffix 格式
        if re.match(r'^\d{6}\.(SH|SZ|BJ)$', code):
            return code

        # 2. 处理 Prefix 格式
        prefix_match = re.match(r'^(SH|SZ|BJ)(\d{6})$', code)
        if prefix_match:
            market, symbol = prefix_match.groups()
            return f"{symbol}.{market}"

        # 3. 纯 6 位数字，自动识别交易所
        digit_match = re.match(r'^(\d{6})$', code)
        if digit_match:
            symbol = digit_match.group(1)
            if symbol.startswith(('60', '68', '90')):
                return f"{symbol}.SH"
            elif symbol.startswith(('00', '30', '20')):
                return f"{symbol}.SZ"
            elif symbol.startswith(('83', '43', '87', '88')):
                return f"{symbol}.BJ"
            return code

        return code

    @staticmethod
    def to_prefix(code: str) -> str:
        """转换为 prefix 格式 SH600000 (向后兼容，新代码请用 to_suffix)

        Examples:
            - '600000.SH' -> 'SH600000'
            - 'sh600000' -> 'SH600000'
            - '600000' -> 'SH600000' (自动识别交易所)
        """
        if not code:
            return ""

        code = str(code).upper().strip()

        # 1. 已经是正确的 Prefix 格式
        if re.match(r'^(SH|SZ|BJ)\d{6}$', code):
            return code

        # 2. 处理 Suffix 格式
        suffix_match = re.match(r'^(\d{6})\.(SH|SZ|BJ)$', code)
        if suffix_match:
            symbol, market = suffix_match.groups()
            return f"{market}{symbol}"

        # 3. 处理带点但位置反了的情况
        rev_suffix_match = re.match(r'^(SH|SZ|BJ)\.(\d{6})$', code)
        if rev_suffix_match:
            market, symbol = rev_suffix_match.groups()
            return f"{market}{symbol}"

        # 4. 纯 6 位数字，自动识别交易所
        digit_match = re.match(r'^(\d{6})$', code)
        if digit_match:
            symbol = digit_match.group(1)
            if symbol.startswith(('60', '68', '90')):
                return f"SH{symbol}"
            elif symbol.startswith(('00', '30', '20')):
                return f"SZ{symbol}"
            elif symbol.startswith(('83', '43', '87', '88')):
                return f"BJ{symbol}"
            return symbol

        return code

    @staticmethod
    def to_hk_suffix(code: str) -> str:
        """港股代码 → 后缀格式（4位+.HK；创业板8开头保留5位+.HK）。

        港股代码本为 5 位（HKEX 原始格式），但主板前导 0 是补位，实际有效
        位数为 4；创业板代码以 8 开头为真 5 位。为与日线/南向数据
        （0700.HK）一致，主板去前导 0 转 4 位+.HK，创业板保留 5 位+.HK。

        Examples:
            - '00700' -> '0700.HK'
            - '00001' -> '0001.HK'
            - '80001' -> '80001.HK' (创业板保留5位)
            - '0700.HK' -> '0700.HK' (已是后缀，原样返回)
        """
        if not code:
            return ""
        code = str(code).strip()
        if code.endswith(".HK"):
            return code
        code = code.zfill(5)
        if code.startswith("8"):
            return f"{code}.HK"
        stripped = code.lstrip("0")
        if not stripped:
            return "0000.HK"
        return f"{stripped.zfill(4)}.HK"

    @staticmethod
    def to_qlib(code: str) -> str:
        """转换为 Qlib 格式 sh600000 (仅用于 Qlib 迁移桥接)

        Examples:
            - '600036.SH' -> 'sh600036'
            - 'SH600036' -> 'sh600036'
            - '000001.SZ' -> 'sz000001'
        """
        suffix = StockCodeUtil.to_suffix(code)
        if "." in suffix:
            symbol, market = suffix.split(".")
            return f"{market.lower()}{symbol}"
        return code.lower()

    @staticmethod
    def normalize_list(codes: list[str]) -> list[str]:
        """批量标准化为 suffix 格式（规范格式）"""
        return [StockCodeUtil.to_suffix(c) for c in codes if c]
