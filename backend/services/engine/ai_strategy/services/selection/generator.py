import json
import logging
import os
import re

from openai import AsyncOpenAI

from .prompts import SQL_GENERATOR_SYSTEM_PROMPT_DYNAMIC
from .schema_retriever import TABLE_DESCRIPTIONS, get_schema_retriever

logger = logging.getLogger(__name__)


class SQLGenerator:
    def __init__(self):
        api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("DASHSCOPE_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"

        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = os.getenv("QWEN_MODEL", "qwen-max")

    async def generate_sql(self, parsed_intent: dict) -> str:
        try:
            target_table = parsed_intent.get("target_table") or "stock_selection"
            retriever = await get_schema_retriever()
            schema_info = await retriever.retrieve(parsed_intent.get("query", ""), top_k=30)
            allowed_fields = parsed_intent.get("allowed_fields") or schema_info.get("allowed_fields") or []

            fields_used = parsed_intent.get("fields_used", [])
            required_select = self._build_required_select(target_table, fields_used)
            prompt = SQL_GENERATOR_SYSTEM_PROMPT_DYNAMIC.format(
                target_table=target_table,
                table_description=TABLE_DESCRIPTIONS.get(target_table, ""),
                allowed_fields=", ".join(allowed_fields),
                required_select=required_select,
                intent_json=json.dumps(parsed_intent, ensure_ascii=False),
            )

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "请生成SQL"},
                ],
                temperature=0.0,
            )
            sql = response.choices[0].message.content.strip()
            if sql.startswith("```sql"):
                sql = sql.replace("```sql", "").replace("```", "").strip()
            elif sql.startswith("```"):
                sql = sql.replace("```", "").strip()

            # 修复 LLM 可能生成的错误表名
            sql = sql.replace("stock_daily_latest_latest", "stock_daily_latest")
            sql = sql.replace("stock_selection_selection", "stock_selection")

            if not self._validate_sql(sql, target_table, allowed_fields):
                raise ValueError("SQL 校验失败：包含非法语句或字段")
            return sql
        except Exception as e:
            logger.error(f"Selection SQL generation failed: {e}")
            return ""

    @staticmethod
    def _build_required_select(table: str, fields_used: list[str] | None = None) -> str:
        # 基础固定字段：symbol（股票代码）、name（股票名称）
        base_fields = ["symbol", "stock_name AS name"]
        # 用户条件涉及的字段（去重，排除已在 base 中的）
        extra = []
        if fields_used:
            seen = {"symbol", "name", "stock_name"}
            for f in fields_used:
                if f not in seen:
                    extra.append(f)
                    seen.add(f)
        all_fields = base_fields + extra
        select_clause = "SELECT " + ", ".join(all_fields)
        return f"{select_clause}\nFROM {table}\nWHERE ..."

    @staticmethod
    def _validate_sql(sql: str, target_table: str, allowed_fields: list[str]) -> bool:
        sql_lower = sql.lower()
        if not sql_lower.startswith("select"):
            return False
        if ";" in sql_lower:
            return False
        forbidden = [
            "insert",
            "update",
            "delete",
            "drop",
            "alter",
            "create",
            "truncate",
        ]
        if any(k in sql_lower for k in forbidden):
            return False
        if f"from {target_table}" not in sql_lower:
            return False

        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", sql_lower)
        keywords = {
            "select",
            "from",
            "where",
            "and",
            "or",
            "not",
            "in",
            "is",
            "null",
            "like",
            "between",
            "exists",
            "order",
            "by",
            "limit",
            "offset",
            "asc",
            "desc",
            "join",
            "left",
            "right",
            "inner",
            "outer",
            "on",
            "group",
            "having",
            "as",
            "case",
            "when",
            "then",
            "else",
            "end",
            "distinct",
            "cast",
            "coalesce",
            "max",
            "min",
            "sum",
            "avg",
            "count",
        }
        allowed = {f.lower() for f in allowed_fields} | {target_table}
        for t in tokens:
            if t in keywords:
                continue
            if t.startswith("t") and t[1:].isdigit():
                continue
            if t in allowed:
                continue
            # 容许别名 symbol/name
            if t in {"symbol", "name"}:
                continue
            return False
        return True


_generator = None


def get_sql_generator():
    global _generator
    if _generator is None:
        _generator = SQLGenerator()
    return _generator


# ---------------------------------------------------------------------------
# QuantDB Query Executor — 从 QuantDB parquet 执行选股查询
# ---------------------------------------------------------------------------

import pandas as pd
from datetime import date

# Map QuantDB table prefix to QuantDBDataHub method name
_QUANTDB_SOURCE_MAP: dict[str, str] = {
    "quantdb_valuation": "fetch_valuation",
    "quantdb_sentiment": "fetch_market_sentiment",
    "quantdb_factors": "fetch_l1_factors",
    "quantdb_margin": "fetch_margin_trading",
    "quantdb_technical": "fetch_technical_indicators",
    # quantdb_financial is per-symbol files; requires special handling (see below)
}


class QuantDBQueryExecutor:
    """从 QuantDB parquet 执行选股查询，返回满足条件的 symbol 集合。

    用法:
        executor = QuantDBQueryExecutor()
        symbols = executor.execute(conditions, target_date=date.today())
    """

    # Map QuantDB table name to DuckDB view name
    _VIEW_MAP: dict[str, str] = {
        "quantdb_valuation": "qdb_valuation",
        "quantdb_sentiment": "qdb_market_sentiment",
        "quantdb_factors": "qdb_l1_factors",
        "quantdb_margin": "qdb_margin_trading",
        "quantdb_technical": "qdb_technical_indicators",
        "quantdb_daily": "qdb_daily_unadjusted",
        # quantdb_financial is per-symbol files; requires special handling
        # quantdb_stock_list is handled via hub.fetch_stock_list() (not a DuckDB view)
        # quantdb_turnover is a virtual table handled via SQL JOIN computation
    }

    # Fields that require special SQL computation (not simple column filters)
    _COMPUTED_FIELDS: dict[str, str] = {
        # turnover_rate = volume(手) * 100 / circulating_capital * 100 (percentage)
        "turnover_rate": """
            d.volume * 100.0 / NULLIF(v.circulating_capital, 0) * 100
        """,
    }

    def execute(self, conditions: list[dict], target_date: date | None = None, exchange: str | None = None) -> set[str]:
        """执行 QuantDB 条件查询，返回满足所有条件的 symbol 交集。

        Uses DuckDB SQL for server-side filtering (much faster than loading all data into Pandas).

        Args:
            conditions: List of condition dicts with table/field/operator/value
            target_date: Target date for filtering (defaults to today)
            exchange: Optional exchange filter - SH, SZ, BJ (only for A-share)
        """
        from backend.services.engine.data_platform.quantdb_hub import QuantDBDataHub

        hub = QuantDBDataHub.get_instance()
        if not hub.available:
            logger.info("QuantDB data not available, skipping QuantDB query")
            return set()

        if target_date is None:
            target_date = date.today()

        # Group conditions by source table
        grouped: dict[str, list[dict]] = {}
        for cond in conditions:
            table = cond.get("table", "")
            if table.startswith("quantdb_"):
                grouped.setdefault(table, []).append(cond)

        if not grouped:
            return set()

        result_sets: list[set[str]] = []
        for table_name, table_conditions in grouped.items():
            # quantdb_financial requires per-symbol file access; skip for now
            if table_name == "quantdb_financial":
                logger.info(
                    "quantdb_financial queries skipped (per-symbol file access not yet supported in batch mode)"
                )
                continue

            # quantdb_stock_list: filter via hub.fetch_stock_list() (IsSTGP, industry, index membership)
            if table_name == "quantdb_stock_list":
                result_sets.append(self._execute_stock_list_filter(hub, table_conditions))
                continue

            # quantdb_turnover: computed via SQL JOIN (volume/circulating_capital)
            if table_name == "quantdb_turnover":
                result_sets.append(self._execute_turnover_filter(hub, table_conditions))
                continue

            view_name = self._VIEW_MAP.get(table_name)
            if not view_name:
                # Fallback to pandas-based approach
                method_name = _QUANTDB_SOURCE_MAP.get(table_name)
                if method_name:
                    result_sets.append(self._execute_pandas(hub, method_name, table_name, table_conditions, target_date))
                continue

            try:
                conn = hub._get_duck_conn()
                # Check if view exists
                if not hub._view_exists(view_name):
                    logger.info("QuantDB view %s not available, trying pandas fallback", view_name)
                    method_name = _QUANTDB_SOURCE_MAP.get(table_name)
                    if method_name:
                        result_sets.append(self._execute_pandas(hub, method_name, table_name, table_conditions, target_date))
                    continue

                # Build SQL WHERE clause for conditions
                where_parts = []
                for cond in table_conditions:
                    field = cond.get("field", cond.get("name", ""))
                    op = cond.get("operator", ">")
                    val = cond.get("value", 0)
                    # Map operator to SQL
                    sql_op = {">=": ">=", "<=": "<=", "==": "=", "!=": "!="}.get(op, op)
                    if isinstance(val, str):
                        where_parts.append(f'{field} {sql_op} \'{val}\'')
                    else:
                        where_parts.append(f'{field} {sql_op} {val}')

                where_clause = " AND ".join(where_parts) if where_parts else "1=1"

                # dt 为 BIGINT YYYYMMDD，不是日期字符串
                dt_int = int(target_date.strftime("%Y%m%d"))

                sql = f"""
                    SELECT DISTINCT symbol FROM {view_name}
                    WHERE dt = {dt_int} AND ({where_clause})
                """
                df = conn.execute(sql).fetchdf()

                # 目标日无数据（非交易日/视图滞后）时回退到该视图最新日期
                if df is None or df.empty:
                    sql = f"""
                        SELECT DISTINCT symbol FROM {view_name}
                        WHERE dt = (SELECT MAX(dt) FROM {view_name}) AND ({where_clause})
                    """
                    df = conn.execute(sql).fetchdf()

                if df is not None and not df.empty:
                    sym_col = "symbol" if "symbol" in df.columns else df.columns[0]
                    symbols = set(df[sym_col].dropna().unique())
                    logger.info(
                        "QuantDB %s (SQL): %d stocks passed conditions",
                        table_name,
                        len(symbols),
                    )
                    result_sets.append(symbols)
                else:
                    logger.info("QuantDB %s (SQL): no stocks passed conditions", table_name)

            except Exception as exc:
                logger.warning("QuantDB SQL query failed for %s: %s, trying pandas fallback", table_name, exc)
                method_name = _QUANTDB_SOURCE_MAP.get(table_name)
                if method_name:
                    result_sets.append(self._execute_pandas(hub, method_name, table_name, table_conditions, target_date))

        if not result_sets:
            return set()

        # Intersection of all result sets (stocks must pass ALL table conditions)
        result = set.intersection(*result_sets)

        # Exchange filter: only keep symbols matching .SH / .SZ / .BJ suffix
        if exchange and result:
            suffix = f".{exchange.upper()}"
            result = {s for s in result if s.endswith(suffix)}
            logger.info("QuantDB exchange filter (%s): %d stocks remain", suffix, len(result))

        return result

    def _execute_stock_list_filter(self, hub, conditions: list[dict]) -> set[str]:
        """Filter symbols using hub.fetch_stock_list() for IsSTGP, industry, index membership."""
        try:
            df = hub.fetch_stock_list()
            if df is None or df.empty:
                return set()

            sym_col = "Symbol" if "Symbol" in df.columns else "symbol"
            mask = pd.Series(True, index=df.index)

            for cond in conditions:
                field = cond.get("field", cond.get("name", ""))
                op = cond.get("operator", ">")
                val = cond.get("value", 0)

                if field == "IsSTGP":
                    # is_st: val=0 means exclude ST, val=1 means only ST
                    col = pd.to_numeric(df.get("IsSTGP", 0), errors="coerce").fillna(0)
                    if op in ("==", "=") and val == 0:
                        mask &= col == 0
                    elif op in ("==", "=") and val == 1:
                        mask &= col >= 1
                elif field == "industry":
                    # Industry filter: match against rs_hyname or tdx_dyname
                    for ind_col in ("rs_hyname", "tdx_dyname"):
                        if ind_col in df.columns:
                            ind_mask = df[ind_col].astype(str).str.contains(str(val), case=False, na=False)
                            mask |= ind_mask
                elif field in ("idx_hs300", "idx_zz1000", "idx_zz500", "idx_chinext"):
                    # Index membership: map to BelongHS300 etc. in stock_list
                    idx_col_map = {
                        "idx_hs300": "BelongHS300",
                        "idx_zz1000": "BelongHasKQZ",  # closest available
                    }
                    db_col = idx_col_map.get(field)
                    if db_col and db_col in df.columns:
                        col = pd.to_numeric(df[db_col], errors="coerce").fillna(0)
                        if op in ("==", "=") and val == 1:
                            mask &= col >= 1
                        elif op in ("==", "=") and val == 0:
                            mask &= col == 0

            filtered = df[mask]
            if sym_col in filtered.columns:
                symbols = set(filtered[sym_col].dropna().unique())
                logger.info("QuantDB stock_list filter: %d/%d stocks passed", len(symbols), len(df))
                return symbols
        except Exception as exc:
            logger.warning("QuantDB stock_list filter failed: %s", exc)

        return set()

    def _execute_turnover_filter(self, hub, conditions: list[dict]) -> set[str]:
        """Filter symbols by computed turnover_rate via SQL JOIN.

        turnover_rate = volume(手) * 100 / circulating_capital * 100 (percentage)
        """
        try:
            conn = hub._get_duck_conn()
            if not hub._view_exists("qdb_daily_unadjusted") or not hub._view_exists("qdb_valuation"):
                return set()

            where_parts = []
            for cond in conditions:
                field = cond.get("field", "")
                op = cond.get("operator", ">")
                val = cond.get("value", 0)
                sql_op = {">=": ">=", "<=": "<=", "==": "=", "!=": "!="}.get(op, op)

                if field == "turnover_rate":
                    # val is already in percentage (e.g., 3 = 3%)
                    where_parts.append(
                        f"d.volume * 100.0 / NULLIF(v.circulating_capital, 0) * 100 {sql_op} {val}"
                    )

            if not where_parts:
                return set()

            where_clause = " AND ".join(where_parts)
            sql = f"""
                SELECT DISTINCT d.symbol
                FROM qdb_daily_unadjusted d
                JOIN qdb_valuation v ON d.symbol = v.symbol
                WHERE d.dt = (SELECT MAX(dt) FROM qdb_daily_unadjusted)
                  AND v.dt = (SELECT MAX(dt) FROM qdb_valuation)
                  AND v.circulating_capital > 0
                  AND ({where_clause})
            """
            df = conn.execute(sql).fetchdf()
            if df is not None and not df.empty:
                symbols = set(df["symbol"].dropna().unique())
                logger.info("QuantDB turnover filter: %d stocks passed", len(symbols))
                return symbols
        except Exception as exc:
            logger.warning("QuantDB turnover filter failed: %s", exc)

        return set()

    def _execute_pandas(
        self, hub, method_name: str, table_name: str,
        table_conditions: list[dict], target_date: date,
    ) -> set[str]:
        """Fallback: use pandas-based filtering when DuckDB view is not available."""
        fetch_fn = getattr(hub, method_name, None)
        if fetch_fn is None:
            return set()

        try:
            df = fetch_fn(start=target_date, end=target_date)
            if df is None or df.empty:
                df = fetch_fn()

            if df is None or df.empty:
                return set()

            sym_col = "symbol" if "symbol" in df.columns else "Symbol"
            if sym_col != "symbol" and sym_col in df.columns:
                df = df.rename(columns={sym_col: "symbol"})

            mask = pd.Series(True, index=df.index)
            for cond in table_conditions:
                field = cond.get("field", cond.get("name", ""))
                op = cond.get("operator", ">")
                val = cond.get("value", 0)

                if field not in df.columns:
                    continue

                col = pd.to_numeric(df[field], errors="coerce")
                if op in (">", "gt"):
                    mask &= col > val
                elif op in (">=", "gte", "ge"):
                    mask &= col >= val
                elif op in ("<", "lt"):
                    mask &= col < val
                elif op in ("<=", "lte", "le"):
                    mask &= col <= val
                elif op in ("==", "=", "eq"):
                    mask &= col == val
                elif op in ("!=", "ne"):
                    mask &= col != val

            filtered = df[mask]
            if "symbol" in filtered.columns:
                symbols = set(filtered["symbol"].dropna().unique())
                logger.info("QuantDB %s (pandas): %d/%d stocks passed", table_name, len(symbols), len(df))
                return symbols
        except Exception as exc:
            logger.warning("QuantDB pandas query failed for %s: %s", table_name, exc)

        return set()
