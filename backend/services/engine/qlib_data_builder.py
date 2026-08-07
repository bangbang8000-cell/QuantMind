"""
Qlib 数据构建器 — 从 QuantDB parquet 生成 Qlib 格式缓存。

Qlib binary 格式要求：
- calendars/day.txt: 每行一个日期 YYYY-MM-DD
- instruments/all.txt: tab 分隔 symbol\\tstart_date\\tend_date
- features/{symbol}/{field}.day.bin: 4-byte float32 start_idx + N*4-byte float32 values

QuantDB parquet 是 single source of truth，Qlib 缓存是派生产物，可随时重建。
"""

from __future__ import annotations

import logging
import struct
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub

logger = logging.getLogger(__name__)

# Qlib 期望的字段列表
QLIB_FIELDS = ["open", "high", "low", "close", "volume", "amount", "factor"]

# QuantDB parquet 列名 -> Qlib 字段名映射
_KLINE_COL_MAP = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amount": "amount",
}


class QlibDataBuilder:
    """从 QuantDB parquet 构建 Qlib binary 缓存。

    用法：
        builder = QlibDataBuilder(
            quantdb_dir="data/quantdb",
            qlib_dir="data/quantdb/.qlib_cache/cn_data",
        )
        builder.build_all()
    """

    def __init__(
        self,
        quantdb_dir: str | Path,
        qlib_dir: str | Path,
    ) -> None:
        self._hub = QuantDBDataHub(quantdb_dir)
        self._qlib_dir = Path(qlib_dir)

    @property
    def qlib_dir(self) -> Path:
        return self._qlib_dir

    @property
    def hub(self) -> QuantDBDataHub:
        return self._hub

    def build_all(
        self,
        *,
        incremental: bool = True,
        symbols: list[str] | None = None,
    ) -> dict:
        """构建全部 Qlib 数据。

        Returns:
            {"calendar": int, "instruments": int, "features": int, "skipped": int}
        """
        if not self._hub.available:
            raise RuntimeError(f"QuantDB 数据目录不可用: {self._hub.data_dir}")

        result: dict = {}

        # 1. 构建交易日历
        result["calendar"] = self.build_calendar()

        # 2. 构建标的列表
        result["instruments"] = self.build_instruments()

        # 3. 构建特征 binary
        feat_result = self.build_features(symbols=symbols, incremental=incremental)
        result["features"] = feat_result["updated"]
        result["skipped"] = feat_result["skipped"]

        logger.info(
            "QlibDataBuilder 完成: calendar=%d, instruments=%d, features=%d, skipped=%d",
            result["calendar"], result["instruments"],
            result["features"], result["skipped"],
        )
        return result

    def build_calendar(self) -> int:
        """从 QuantDB 交易日历生成 calendars/day.txt。"""
        cal_dir = self._qlib_dir / "calendars"
        cal_dir.mkdir(parents=True, exist_ok=True)
        cal_file = cal_dir / "day.txt"

        df = self._hub.fetch_calendar()
        if df.empty:
            logger.warning("QuantDB 交易日历为空")
            return 0

        # 确定日期列
        date_col = None
        for col in ("trade_date", "date", "time", "cal_date", "TradingDate"):
            if col in df.columns:
                date_col = col
                break

        if date_col is None:
            logger.warning("QuantDB 交易日历中未找到日期列")
            return 0

        dates = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d").unique()
        dates = sorted(dates)

        with open(cal_file, "w") as f:
            f.write("\n".join(dates) + "\n")

        logger.info("Qlib calendar: %d trading days -> %s", len(dates), cal_file)
        return len(dates)

    def build_instruments(self) -> int:
        """从 QuantDB 股票列表生成 instruments/all.txt。"""
        inst_dir = self._qlib_dir / "instruments"
        inst_dir.mkdir(parents=True, exist_ok=True)
        inst_file = inst_dir / "all.txt"

        df = self._hub.fetch_stock_list()
        if df.empty:
            logger.warning("QuantDB 股票列表为空")
            return 0

        # 获取 symbol 列（可能是 Symbol 或 symbol）
        symbol_col = None
        for col in ("Symbol", "symbol"):
            if col in df.columns:
                symbol_col = col
                break

        if symbol_col is None:
            logger.warning("QuantDB 股票列表中未找到 symbol 列")
            return 0

        # 获取日历范围
        cal_dates = self._load_calendar()
        if not cal_dates:
            logger.warning("请先构建日历 (build_calendar)")
            return 0

        start_date = cal_dates[0]
        end_date = cal_dates[-1]

        # 转换为 Qlib 格式: sh600036
        qlib_symbols = []
        for sym in df[symbol_col].dropna().unique():
            qlib_sym = self._to_qlib_symbol(str(sym))
            if qlib_sym:
                qlib_symbols.append(qlib_sym)

        qlib_symbols = sorted(set(qlib_symbols))

        with open(inst_file, "w") as f:
            for sym in qlib_symbols:
                f.write(f"{sym}\t{start_date}\t{end_date}\n")

        logger.info("Qlib instruments: %d symbols -> %s", len(qlib_symbols), inst_file)

        # 另外为各股票池生成成分文件，供 D.instruments(market="csi300") 使用。
        # 缺失时 Qlib 会直接抛 ValueError，导致因子回测无法运行。
        self._build_universe_instruments(inst_dir, start_date, end_date, set(qlib_symbols))
        return len(qlib_symbols)

    def _build_universe_instruments(
        self, inst_dir: Path, start_date: str, end_date: str, known: set[str]
    ) -> None:
        """为 csi300/csi500/... 生成 Qlib instruments 文件。"""
        universes = getattr(self._hub, "UNIVERSE_MAP", {}) or {}
        for universe in universes:
            try:
                df = self._hub.fetch_universe_stocks(universe)
                if df is None or df.empty or "symbol" not in df.columns:
                    logger.warning("股票池 %s 无成分数据，跳过", universe)
                    continue
                syms = set()
                for sym in df["symbol"].dropna().unique():
                    qs = self._to_qlib_symbol(str(sym))
                    # 只保留有行情数据的标的，否则 Qlib 读 features 时会报缺文件
                    if qs and qs in known:
                        syms.add(qs)
                if not syms:
                    logger.warning("股票池 %s 成分与行情数据无交集，跳过", universe)
                    continue
                out = inst_dir / f"{universe}.txt"
                with open(out, "w") as f:
                    for s in sorted(syms):
                        f.write(f"{s}\t{start_date}\t{end_date}\n")
                logger.info("Qlib universe %s: %d symbols -> %s", universe, len(syms), out)
            except Exception as e:
                logger.warning("生成股票池 %s 成分文件失败: %s", universe, e)

    def build_features(
        self,
        symbols: list[str] | None = None,
        *,
        incremental: bool = True,
        batch_size: int = 100,
    ) -> dict:
        """从 QuantDB 前复权 K 线生成 features/*.day.bin。

        Args:
            symbols: 要构建的 symbol 列表（None = 全部）
            incremental: 增量模式，只追加新数据
            batch_size: 每批处理的 symbol 数量

        Returns:
            {"updated": int, "skipped": int}
        """
        if symbols is None:
            symbols = self._get_all_symbols()

        if not symbols:
            return {"updated": 0, "skipped": 0}

        # 加载日历索引
        cal_dates = self._load_calendar()
        if not cal_dates:
            logger.warning("请先构建日历 (build_calendar)")
            return {"updated": 0, "skipped": 0}

        cal_index = {d: i for i, d in enumerate(cal_dates)}

        updated = 0
        skipped = 0

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            for sym in batch:
                try:
                    qdb_sym = self._to_qdb_symbol(sym)
                    if not qdb_sym:
                        skipped += 1
                        continue

                    result = self._build_symbol_features(
                        sym, qdb_sym, cal_dates, cal_index, incremental=incremental
                    )
                    if result:
                        updated += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    logger.warning("构建 %s features 失败: %s", sym, exc)
                    skipped += 1

            if i + batch_size < len(symbols):
                logger.info(
                    "Features 进度: %d/%d (updated=%d, skipped=%d)",
                    min(i + batch_size, len(symbols)), len(symbols), updated, skipped,
                )

        return {"updated": updated, "skipped": skipped}

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _load_calendar(self) -> list[str]:
        """加载已构建的 Qlib 日历。"""
        cal_file = self._qlib_dir / "calendars" / "day.txt"
        if not cal_file.exists():
            return []
        with open(cal_file) as f:
            return [line.strip() for line in f if line.strip()]

    def _get_all_symbols(self) -> list[str]:
        """获取所有 Qlib 格式的 symbol。"""
        inst_file = self._qlib_dir / "instruments" / "all.txt"
        if not inst_file.exists():
            return []
        symbols = []
        with open(inst_file) as f:
            for line in f:
                parts = line.strip().split("\t")
                if parts:
                    symbols.append(parts[0])
        return symbols

    def _build_symbol_features(
        self,
        qlib_sym: str,
        qdb_sym: str,
        cal_dates: list[str],
        cal_index: dict[str, int],
        *,
        incremental: bool = True,
    ) -> bool:
        """构建单个 symbol 的 Qlib features。"""
        feat_dir = self._qlib_dir / "features" / qlib_sym
        feat_dir.mkdir(parents=True, exist_ok=True)

        if self._is_index_symbol(qlib_sym):
            return self._build_index_features(qlib_sym, qdb_sym, feat_dir, cal_dates, cal_index)

        if incremental:
            return self._incremental_build(qlib_sym, qdb_sym, feat_dir, cal_dates, cal_index)
        else:
            return self._full_build(qlib_sym, qdb_sym, feat_dir, cal_dates, cal_index)

    def _build_index_features(
        self,
        qlib_sym: str,
        qdb_sym: str,
        feat_dir: Path,
        cal_dates: list[str],
        cal_index: dict[str, int],
    ) -> bool:
        """从 QuantDB index_daily 构建指数 features。"""
        df = self._hub.fetch_index_kline(qdb_sym, date(2016, 1, 4), date(2026, 12, 31))
        if df.empty:
            return False

        # 按日期对齐到日历
        first_date = str(df.iloc[0].get("trade_date", ""))[:10]
        start_idx = cal_index.get(first_date, 0)

        # 指数无复权因子，factor=1.0
        field_data = {
            "open": df["open"].values if "open" in df.columns else None,
            "high": df["high"].values if "high" in df.columns else None,
            "low": df["low"].values if "low" in df.columns else None,
            "close": df["close"].values if "close" in df.columns else None,
            "volume": df["volume"].values if "volume" in df.columns else None,
            "amount": df["amount"].values if "amount" in df.columns else None,
            "factor": np.ones(len(df)),
        }

        for field_name, values in field_data.items():
            if values is None:
                continue
            bin_path = feat_dir / f"{field_name}.day.bin"
            self._write_bin_file(bin_path, start_idx, values.astype(np.float32))

        return True

    def _full_build(
        self,
        qlib_sym: str,
        qdb_sym: str,
        feat_dir: Path,
        cal_dates: list[str],
        cal_index: dict[str, int],
    ) -> bool:
        """从 QuantDB parquet 全量构建 symbol 的 features。"""
        # 读取前复权日K + 不复权日K（计算 factor）
        df_qfq = self._hub.fetch_daily_kline(qdb_sym, date(2016, 1, 4), date(2026, 12, 31), adjust="qfq")
        if df_qfq.empty:
            return False

        df_unadj = self._hub.fetch_daily_kline(qdb_sym, date(2016, 1, 4), date(2026, 12, 31), adjust="none")

        # 计算复权因子
        if not df_unadj.empty and len(df_unadj) == len(df_qfq):
            factor = np.where(
                df_unadj["close"].values > 0,
                df_qfq["close"].values / df_unadj["close"].values,
                1.0,
            )
        else:
            factor = np.ones(len(df_qfq))

        # 构建 Qlib 数据：每个字段一个 bin 文件
        field_data = {
            "open": df_qfq["open"].values if "open" in df_qfq.columns else None,
            "high": df_qfq["high"].values if "high" in df_qfq.columns else None,
            "low": df_qfq["low"].values if "low" in df_qfq.columns else None,
            "close": df_qfq["close"].values if "close" in df_qfq.columns else None,
            "volume": df_qfq["volume"].values if "volume" in df_qfq.columns else None,
            "amount": df_qfq["amount"].values if "amount" in df_qfq.columns else None,
            "factor": factor,
        }

        # 个股交易日可能少于全市场日历（停牌、上游缺该日数据），必须按日历索引
        # 逐条落位并对缺失日填 NaN。连续写入会让缺口后的所有数据整体前移。
        row_positions = []
        for raw_date in df_qfq["trade_date"].values:
            idx = cal_index.get(str(raw_date)[:10])
            row_positions.append(-1 if idx is None else idx)
        row_positions = np.asarray(row_positions, dtype=np.int64)

        valid = row_positions >= 0
        if not valid.any():
            return False

        start_idx = int(row_positions[valid].min())
        span = int(row_positions[valid].max()) - start_idx + 1
        offsets = row_positions[valid] - start_idx

        for field_name, values in field_data.items():
            if values is None:
                continue
            aligned = np.full(span, np.nan, dtype=np.float32)
            aligned[offsets] = np.asarray(values, dtype=np.float32)[valid]
            bin_path = feat_dir / f"{field_name}.day.bin"
            self._write_bin_file(bin_path, start_idx, aligned)

        return True

    def _incremental_build(
        self,
        qlib_sym: str,
        qdb_sym: str,
        feat_dir: Path,
        cal_dates: list[str],
        cal_index: dict[str, int],
    ) -> bool:
        """增量构建：追加新数据到现有 bin 文件。"""
        # 检查现有 bin 文件，确定已覆盖到哪个日期
        close_bin = feat_dir / "close.day.bin"
        if not close_bin.exists():
            # 没有现有数据，走全量构建
            return self._full_build(qlib_sym, qdb_sym, feat_dir, cal_dates, cal_index)

        # 读取现有 close bin，确定已覆盖的日期范围
        try:
            existing_start_idx, existing_close = self._read_bin_file(close_bin)
        except Exception:
            return self._full_build(qlib_sym, qdb_sym, feat_dir, cal_dates, cal_index)

        if len(existing_close) == 0:
            return self._full_build(qlib_sym, qdb_sym, feat_dir, cal_dates, cal_index)

        # 已覆盖的最后一个日历索引
        existing_end_idx = existing_start_idx + len(existing_close) - 1
        if existing_end_idx >= len(cal_dates) - 1:
            # 已经是最新，跳过
            return False

        # 需要追加的日期范围
        next_cal_date = cal_dates[existing_end_idx + 1]
        end_cal_date = cal_dates[-1]

        # 从 QuantDB 读取增量数据
        try:
            start_dt = date.fromisoformat(next_cal_date)
            end_dt = date.fromisoformat(end_cal_date)
        except ValueError:
            return False

        df_qfq = self._hub.fetch_daily_kline(qdb_sym, start_dt, end_dt, adjust="qfq")
        if df_qfq.empty:
            return False

        df_unadj = self._hub.fetch_daily_kline(qdb_sym, start_dt, end_dt, adjust="none")

        # 计算复权因子
        if not df_unadj.empty and len(df_unadj) == len(df_qfq):
            new_factor = np.where(
                df_unadj["close"].values > 0,
                df_qfq["close"].values / df_unadj["close"].values,
                1.0,
            )
        else:
            new_factor = np.ones(len(df_qfq))

        # 追加数据到 bin 文件
        new_field_data = {
            "open": df_qfq["open"].values if "open" in df_qfq.columns else None,
            "high": df_qfq["high"].values if "high" in df_qfq.columns else None,
            "low": df_qfq["low"].values if "low" in df_qfq.columns else None,
            "close": df_qfq["close"].values if "close" in df_qfq.columns else None,
            "volume": df_qfq["volume"].values if "volume" in df_qfq.columns else None,
            "amount": df_qfq["amount"].values if "amount" in df_qfq.columns else None,
            "factor": new_factor,
        }

        for field_name, new_values in new_field_data.items():
            if new_values is None:
                continue
            bin_path = feat_dir / f"{field_name}.day.bin"
            if bin_path.exists():
                _, existing = self._read_bin_file(bin_path)
                combined = np.concatenate([existing, new_values.astype(np.float32)])
                self._write_bin_file(bin_path, existing_start_idx, combined)
            else:
                self._write_bin_file(bin_path, existing_start_idx, new_values.astype(np.float32))

        return True

    def build_features_bulk(self) -> dict:
        """一次扫描全市场 parquet，按标的分组写 bin。

        逐标的构建需要对每个 symbol 各做两次全库扫描（前复权 + 不复权），
        5500 个标的会重复扫 2500+ 个分区，容器内直接 OOM。这里改为整体读入
        再 groupby，代价是一次约 10GB 的 DataFrame。
        """
        import duckdb

        cal_dates = self._load_calendar()
        if not cal_dates:
            logger.warning("请先构建日历 (build_calendar)")
            return {"updated": 0, "skipped": 0}
        cal_index = {d: i for i, d in enumerate(cal_dates)}

        fwd = str(self._hub.data_dir / "1_kline_data/daily_forward/dt=*/data.parquet")
        unadj = str(self._hub.data_dir / "1_kline_data/daily_unadjusted/dt=*/data.parquet")

        con = duckdb.connect(config={"memory_limit": "8GB", "threads": "4"})
        try:
            df = con.execute(
                f"""
                SELECT f.symbol, CAST(f.time AS DATE) d,
                       f.open, f.high, f.low, f.close, f.volume, f.amount,
                       u.close AS close_unadj
                FROM read_parquet('{fwd}') f
                LEFT JOIN read_parquet('{unadj}') u
                  ON u.symbol = f.symbol AND CAST(u.time AS DATE) = CAST(f.time AS DATE)
                ORDER BY f.symbol, d
                """
            ).fetchdf()
        finally:
            con.close()

        if df.empty:
            return {"updated": 0, "skipped": 0}

        df["ci"] = df["d"].astype(str).map(cal_index)
        df = df[df["ci"].notna()]
        df["ci"] = df["ci"].astype(np.int64)

        updated = skipped = 0
        for qdb_sym, group in df.groupby("symbol", sort=False):
            qlib_sym = self._to_qlib_symbol(qdb_sym)
            positions = group["ci"].values
            start_idx = int(positions.min())
            span = int(positions.max()) - start_idx + 1
            offsets = positions - start_idx

            feat_dir = self._qlib_dir / "features" / qlib_sym
            feat_dir.mkdir(parents=True, exist_ok=True)

            close_unadj = group["close_unadj"].values.astype(np.float64)
            close_qfq = group["close"].values.astype(np.float64)
            with np.errstate(divide="ignore", invalid="ignore"):
                factor = np.where(close_unadj > 0, close_qfq / close_unadj, 1.0)
            factor = np.nan_to_num(factor, nan=1.0, posinf=1.0, neginf=1.0)

            try:
                for field in ("open", "high", "low", "close", "volume", "amount"):
                    aligned = np.full(span, np.nan, dtype=np.float32)
                    aligned[offsets] = group[field].values.astype(np.float32)
                    self._write_bin_file(feat_dir / f"{field}.day.bin", start_idx, aligned)
                aligned = np.full(span, np.nan, dtype=np.float32)
                aligned[offsets] = factor.astype(np.float32)
                self._write_bin_file(feat_dir / "factor.day.bin", start_idx, aligned)
                updated += 1
            except Exception as exc:
                logger.warning("构建 %s features 失败: %s", qlib_sym, exc)
                skipped += 1

        logger.info("Qlib features (bulk): updated=%d, skipped=%d", updated, skipped)
        return {"updated": updated, "skipped": skipped}

    @staticmethod
    def _write_bin_file(path: Path, start_idx: int, values: np.ndarray) -> None:
        """写入 Qlib binary 文件。

        格式: 4-byte float32 start_idx + N * 4-byte float32 values
        """
        with open(path, "wb") as f:
            f.write(struct.pack("f", float(start_idx)))
            f.write(values.astype(np.float32).tobytes())

    @staticmethod
    def _read_bin_file(path: Path) -> tuple[int, np.ndarray]:
        """读取 Qlib binary 文件。返回 (start_idx, values)。"""
        with open(path, "rb") as f:
            raw = f.read()
        if len(raw) < 4:
            return 0, np.array([], dtype=np.float32)
        start_idx = int(struct.unpack("f", raw[:4])[0])
        values = np.frombuffer(raw[4:], dtype=np.float32)
        return start_idx, values

    @staticmethod
    def _to_qlib_symbol(symbol: str) -> str:
        """suffix 格式 600036.SH -> Qlib 格式 sh600036。"""
        s = symbol.strip()
        if "." in s:
            code, exchange = s.split(".", 1)
            return f"{exchange.lower()}{code}"
        return s.lower()

    @staticmethod
    def _to_qdb_symbol(qlib_symbol: str) -> str:
        """Qlib 格式 sh600036 -> suffix 格式 600036.SH。"""
        s = qlib_symbol.strip()
        # Qlib 格式: sh600036, sz000001, bj830001
        if s.startswith("sh"):
            return f"{s[2:]}.SH"
        if s.startswith("sz"):
            return f"{s[2:]}.SZ"
        if s.startswith("bj"):
            return f"{s[2:]}.BJ"
        # 可能已经是 suffix 格式
        if "." in s:
            return s
        return s

    @staticmethod
    def _is_index_symbol(qlib_symbol: str) -> bool:
        """判断 Qlib 格式 symbol 是否为指数。

        指数代码规则：
        - SH: 000xxx (上证指数系列)
        - SZ: 399xxx (深证指数系列)
        """
        s = qlib_symbol.strip()
        if s.startswith("sh") and s[2:].startswith("000"):
            return True
        if s.startswith("sz") and s[2:].startswith("399"):
            return True
        return False

    def is_built(self) -> bool:
        """检查 Qlib 缓存是否已构建。"""
        cal_file = self._qlib_dir / "calendars" / "day.txt"
        inst_file = self._qlib_dir / "instruments" / "all.txt"
        feat_dir = self._qlib_dir / "features"
        return (
            cal_file.exists()
            and inst_file.exists()
            and feat_dir.exists()
            and any(feat_dir.iterdir())
        )

    def get_status(self) -> dict:
        """返回 Qlib 缓存状态。"""
        cal_file = self._qlib_dir / "calendars" / "day.txt"
        inst_file = self._qlib_dir / "instruments" / "all.txt"
        feat_dir = self._qlib_dir / "features"

        status: dict = {
            "qlib_dir": str(self._qlib_dir),
            "calendar_built": cal_file.exists(),
            "instruments_built": inst_file.exists(),
            "features_built": feat_dir.exists(),
        }

        if cal_file.exists():
            with open(cal_file) as f:
                dates = [l.strip() for l in f if l.strip()]
            status["calendar_count"] = len(dates)
            if dates:
                status["calendar_range"] = f"{dates[0]} ~ {dates[-1]}"

        if inst_file.exists():
            with open(inst_file) as f:
                status["instrument_count"] = sum(1 for _ in f)

        if feat_dir.exists():
            status["feature_symbol_count"] = sum(
                1 for d in feat_dir.iterdir() if d.is_dir()
            )

        return status


def ensure_qlib_cache(quantdb_dir: str | Path, qlib_dir: str | Path | None = None) -> str:
    """确保 Qlib 缓存可用，返回 provider_uri。

    如果缓存不存在或过期，从 QuantDB parquet 构建。
    """
    quantdb_dir = Path(quantdb_dir)
    if qlib_dir is None:
        qlib_dir = quantdb_dir / ".qlib_cache" / "cn_data"
    else:
        qlib_dir = Path(qlib_dir)

    builder = QlibDataBuilder(quantdb_dir, qlib_dir)

    if not builder.is_built():
        logger.info("Qlib 缓存不存在，开始构建...")
        builder.build_all(incremental=False)
    else:
        # 增量更新：先重建日历（trading_calendar 可能已更新），
        # 再增量更新 instruments 和 features
        builder.build_calendar()
        builder.build_instruments()
        builder.build_features(incremental=True)

    return str(qlib_dir)
