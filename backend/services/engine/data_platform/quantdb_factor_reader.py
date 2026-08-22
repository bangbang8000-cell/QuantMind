"""Direct reader for the three QuantDB model-factor datasets.

This module deliberately never writes a derived feature parquet.  It provides
one canonical, in-memory frame per source (L1, L2, or the L1+L2 wide table)
for training, inference, and backtesting.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Literal

import pandas as pd

from .quantdb_hub import _resolve_data_dir
from backend.shared.stock_utils import StockCodeUtil

logger = logging.getLogger(__name__)

FactorSource = Literal["l1_factors", "l2_factors", "l1_l2_factors"]

FACTOR_SOURCE_DIRS: dict[FactorSource, str] = {
    "l1_factors": "6_ml_datasets/l1_factors",
    "l2_factors": "6_ml_datasets/l2_factors",
    "l1_l2_factors": "6_ml_datasets/l1_l2_factors",
}
DEFAULT_FACTOR_SOURCE: FactorSource = "l1_l2_factors"
REQUIRED_COLUMNS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)
KEY_COLUMNS = {"symbol", "date", "dt", "time", "release_id", "published_at"}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class QuantDBFactorError(RuntimeError):
    """The configured QuantDB factor source cannot safely serve a model."""


@dataclass(frozen=True)
class FactorSourceStatus:
    dataset_id: FactorSource
    path: str
    files: int
    columns: list[str]
    column_types: dict[str, str]
    schema_hash: str
    min_date: str | None
    max_date: str | None
    ready: bool
    missing_required: list[str]
    reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _quote(identifier: str) -> str:
    if not _IDENTIFIER.fullmatch(identifier):
        raise QuantDBFactorError(f"Invalid QuantDB column name: {identifier!r}")
    return f'"{identifier}"'


class QuantDBFactorReader:
    """Read one raw QuantDB factor source without materialising a snapshot."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else _resolve_data_dir()

    @staticmethod
    def validate_source(source: str) -> FactorSource:
        if source not in FACTOR_SOURCE_DIRS:
            allowed = ", ".join(FACTOR_SOURCE_DIRS)
            raise QuantDBFactorError(
                f"Unsupported factor source {source!r}; expected one of {allowed}"
            )
        return source  # type: ignore[return-value]

    def source_path(self, source: str) -> Path:
        return self.data_dir / FACTOR_SOURCE_DIRS[self.validate_source(source)]

    def _files(self, source: str) -> list[Path]:
        root = self.source_path(source)
        return sorted(root.rglob("*.parquet")) if root.is_dir() else []

    @staticmethod
    def _duckdb():
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover - deployment dependency
            raise QuantDBFactorError(
                "duckdb is required to read QuantDB factor datasets"
            ) from exc
        return duckdb

    def _relation(self, source: str) -> str:
        root = self.source_path(source)
        if not root.is_dir():
            raise QuantDBFactorError(f"QuantDB factor directory does not exist: {root}")
        # All values come from the local QuantDB root; quote for a DuckDB string literal.
        parquet_glob = str(root / "**" / "*.parquet").replace("'", "''")
        return f"read_parquet('{parquet_glob}', hive_partitioning=true, union_by_name=true)"

    def describe(self, source: str) -> FactorSourceStatus:
        source = self.validate_source(source)
        files = self._files(source)
        root = self.source_path(source)
        if not files:
            return FactorSourceStatus(
                dataset_id=source,
                path=str(root),
                files=0,
                columns=[],
                column_types={},
                schema_hash="",
                min_date=None,
                max_date=None,
                ready=False,
                missing_required=list(REQUIRED_COLUMNS),
                reason="No parquet files found",
            )

        duckdb = self._duckdb()
        con = duckdb.connect(config={"memory_limit": "2GB", "threads": "2"})
        try:
            relation = self._relation(source)
            described = con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
            columns = [str(row[0]) for row in described]
            column_types = {str(row[0]): str(row[1]) for row in described}
            date_expr = self._date_expression(columns)
            date_row = con.execute(
                f"SELECT min({date_expr}), max({date_expr}) FROM {relation}"
            ).fetchone()
        except Exception as exc:
            return FactorSourceStatus(
                dataset_id=source,
                path=str(root),
                files=len(files),
                columns=[],
                column_types={},
                schema_hash="",
                min_date=None,
                max_date=None,
                ready=False,
                missing_required=list(REQUIRED_COLUMNS),
                reason=str(exc),
            )
        finally:
            con.close()

        schema_hash = hashlib.sha256("\n".join(columns).encode()).hexdigest()
        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        return FactorSourceStatus(
            dataset_id=source,
            path=str(root),
            files=len(files),
            columns=columns,
            column_types=column_types,
            schema_hash=schema_hash,
            min_date=str(date_row[0])[:10] if date_row and date_row[0] else None,
            max_date=str(date_row[1])[:10] if date_row and date_row[1] else None,
            ready=not missing,
            missing_required=missing,
            reason=None if not missing else "Missing required common columns",
        )

    def discover(self) -> dict[str, dict]:
        return {
            source: self.describe(source).to_dict() for source in FACTOR_SOURCE_DIRS
        }

    @staticmethod
    def _date_expression(columns: Iterable[str]) -> str:
        cols = set(columns)
        if "date" in cols:
            return 'CAST("date" AS DATE)'
        # Compatibility only.  New factor sources must publish the date column.
        if "dt" in cols:
            return "strptime(CAST(\"dt\" AS VARCHAR), '%Y%m%d')::DATE"
        raise QuantDBFactorError("Factor source has neither date nor dt")

    def assert_ready(
        self,
        source: str,
        *,
        start: str | date | None = None,
        end: str | date | None = None,
    ) -> FactorSourceStatus:
        status = self.describe(source)
        if not status.ready:
            detail = (
                ", ".join(status.missing_required) or status.reason or "unknown reason"
            )
            raise QuantDBFactorError(
                f"{source} is not ready for direct training: {detail}"
            )
        if start and status.min_date and str(start)[:10] < status.min_date:
            raise QuantDBFactorError(
                f"{source} starts at {status.min_date}; requested {start}"
            )
        if end and status.max_date and str(end)[:10] > status.max_date:
            raise QuantDBFactorError(
                f"{source} ends at {status.max_date}; requested {end}"
            )
        return status

    def factor_columns(self, source: str) -> list[str]:
        return [
            column
            for column in self.describe(source).columns
            if column not in KEY_COLUMNS and column not in REQUIRED_COLUMNS
        ]

    def read_range(
        self,
        source: str,
        *,
        features: list[str],
        feature_sources: dict[str, str] | None = None,
        start: str | date,
        end: str | date,
        include_ohlcv: bool = True,
    ) -> pd.DataFrame:
        """Project raw source columns for a date range into an in-memory DataFrame."""
        status = self.assert_ready(source, start=start, end=end)
        available = set(status.columns)
        requested = list(dict.fromkeys(features))
        reserved = set(REQUIRED_COLUMNS) | {"trade_date"}
        if any(feature in reserved for feature in requested):
            raise QuantDBFactorError(
                "Mapped factor names cannot overwrite key or OHLCV columns"
            )
        if any(not _IDENTIFIER.fullmatch(feature) for feature in requested):
            raise QuantDBFactorError("Mapped factor names must be SQL identifiers")
        feature_sources = feature_sources or {}
        source_columns = {
            feature: feature_sources.get(feature, feature) for feature in requested
        }
        missing = [
            column for column in source_columns.values() if column not in available
        ]
        if missing:
            raise QuantDBFactorError(
                f"{source} is missing mapped fields: {', '.join(missing[:10])}"
            )

        selected = [
            '"symbol"',
            f"{self._date_expression(status.columns)} AS trade_date",
        ]
        if include_ohlcv:
            selected.extend(_quote(column) for column in REQUIRED_COLUMNS[2:])
        selected.extend(
            f"{_quote(source_column)} AS {_quote(feature)}"
            if source_column != feature
            else _quote(feature)
            for feature, source_column in source_columns.items()
        )
        start_s, end_s = str(start)[:10], str(end)[:10]

        duckdb = self._duckdb()
        con = duckdb.connect(config={"memory_limit": "8GB", "threads": "4"})
        try:
            relation = self._relation(source)
            date_expr = self._date_expression(status.columns)
            sql = (
                f"SELECT {', '.join(selected)} FROM {relation} "
                f"WHERE {date_expr} BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)"
            )
            frame = con.execute(sql, [start_s, end_s]).fetchdf()
        finally:
            con.close()
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
        # QuantDB may publish either suffix or prefix codes.  QuantMind's
        # canonical internal representation is the prefix form (SH600036),
        # including model inputs, prediction outputs, and persistence keys.
        frame["symbol"] = frame["symbol"].map(
            lambda value: StockCodeUtil.to_prefix(str(value))
        )
        return frame.dropna(subset=["symbol", "trade_date"]).drop_duplicates(
            subset=["symbol", "trade_date"], keep="last"
        )

    def read_day(
        self,
        source: str,
        *,
        features: list[str],
        trade_date: str | date,
        feature_sources: dict[str, str] | None = None,
    ) -> pd.DataFrame:
        return self.read_range(
            source,
            features=features,
            feature_sources=feature_sources,
            start=trade_date,
            end=trade_date,
        )

    def available_dates(
        self, source: str, *, start: str | None = None, end: str | None = None
    ) -> list[str]:
        status = self.assert_ready(source)
        duckdb = self._duckdb()
        con = duckdb.connect(config={"memory_limit": "2GB", "threads": "2"})
        try:
            date_expr = self._date_expression(status.columns)
            relation = self._relation(source)
            conditions, params = [], []
            if start:
                conditions.append(f"{date_expr} >= CAST(? AS DATE)")
                params.append(start)
            if end:
                conditions.append(f"{date_expr} <= CAST(? AS DATE)")
                params.append(end)
            where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = con.execute(
                f"SELECT DISTINCT {date_expr} AS d FROM {relation}{where} ORDER BY d",
                params,
            ).fetchall()
            return [str(row[0])[:10] for row in rows]
        finally:
            con.close()

    @staticmethod
    def forward_labels(
        frame: pd.DataFrame, *, horizon: int, signal_lag_days: int = 1
    ) -> pd.DataFrame:
        """Build labels from the source close column without persisting a derived dataset."""
        if "close" not in frame.columns:
            raise QuantDBFactorError(
                "close is required to construct direct-training labels"
            )
        data = frame[["symbol", "trade_date", "close"]].copy()
        data["close"] = pd.to_numeric(data["close"], errors="coerce")
        data = data[data["close"] > 0].sort_values(["symbol", "trade_date"])
        lag = max(0, int(signal_lag_days))
        horizon = max(1, int(horizon))
        execution_close = data.groupby("symbol")["close"].shift(-lag)
        future_close = data.groupby("symbol")["close"].shift(-(lag + horizon))
        data["label"] = future_close / execution_close - 1.0
        return data[["symbol", "trade_date", "label"]]
