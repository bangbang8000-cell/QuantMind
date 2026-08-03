"""batch_aggregator 纯函数聚合的单元测试。

守护的核心口径：跨日主排序键必须是截面分位而非原始分数；缺席日是 NaN 而非 0 分。
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = (
    _ROOT / "backend" / "services" / "engine" / "inference" / "batch_aggregator.py"
)


def _load_batch_aggregator():
    """按文件路径加载，绕过 inference/__init__ 的 DB 依赖。"""
    name = "_ba_test_batch_aggregator"
    if name in sys.modules:
        return sys.modules[name]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    spec = importlib.util.spec_from_file_location(name, _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ba = _load_batch_aggregator()

DATES = ["2026-07-16", "2026-07-17", "2026-07-20", "2026-07-21", "2026-07-22"]


def _panel(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """由 (date, symbol, score) 三元组补齐 rk/pct，模拟取数 SQL 的窗口函数。"""
    df = pd.DataFrame(rows)
    out = []
    for _, day in df.groupby("trade_date"):
        day = day.copy()
        n = len(day)
        day["rk"] = day["fusion_score"].rank(ascending=False, method="min").astype(int)
        asc = day["fusion_score"].rank(ascending=True, method="min")
        day["pct"] = 0.5 if n == 1 else (asc - 1.0) / (n - 1)
        out.append(day)
    res = pd.concat(out, ignore_index=True)
    if "signal_side" not in res.columns:
        res["signal_side"] = "HOLD"
    if "stock_name" not in res.columns:
        res["stock_name"] = ""
    return res


def _grid(score_map: dict[str, dict[str, float]]) -> pd.DataFrame:
    """score_map[symbol][date] = score；缺 key 即该股当日缺席。"""
    rows = []
    for symbol, per_day in score_map.items():
        for date, score in per_day.items():
            rows.append(
                {"trade_date": date, "symbol": symbol, "fusion_score": float(score)}
            )
    return _panel(rows)


def _by_symbol(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["symbol"]: r for r in result["per_symbol"]}


def _symbols(items: list[dict[str, Any]]) -> list[str]:
    return [r["symbol"] for r in items]


@pytest.fixture
def ladder_panel() -> pd.DataFrame:
    """9 只股票 × 5 日。RISER 名次严格上升，FADER 严格下降，其余保持不动。

    分数刻意取小数偏移以避开并列 —— 并列时 PERCENT_RANK 的 min 语义不满足
    `pct(-s) == 1 - pct(s)`，会污染空头镜像用例。
    """
    score_map: dict[str, dict[str, float]] = {
        f"FLAT{i}": {d: float(i) for d in DATES} for i in range(7)
    }
    score_map["RISER"] = {d: -0.5 + 1.7 * k for k, d in enumerate(DATES)}
    score_map["FADER"] = {d: 6.2 - 1.5 * k for k, d in enumerate(DATES)}
    return _grid(score_map)


class TestMonotonicRiser:
    def test_riser_identified_by_trend_jump_and_monotonicity(
        self, ladder_panel: pd.DataFrame
    ) -> None:
        res = ba.aggregate_batch(ladder_panel, dates=DATES, horizon_days=10, top_k=3)
        riser = _by_symbol(res)["RISER"]

        assert riser["is_monotonic_up"] is True
        assert riser["is_monotonic_down"] is False
        assert riser["up_streak"] == 5
        assert riser["trend_rho"] == pytest.approx(1.0)
        assert riser["mk_s"] == 10  # C(5,2) 全为上升对
        assert "RISER" in _symbols(res["groups"]["rising"])
        assert _symbols(res["movers"]["pct_jump"]["up"])[0] == "RISER"

    def test_fader_identified_symmetrically(self, ladder_panel: pd.DataFrame) -> None:
        res = ba.aggregate_batch(ladder_panel, dates=DATES, horizon_days=10, top_k=3)
        fader = _by_symbol(res)["FADER"]

        assert fader["is_monotonic_down"] is True
        assert fader["down_streak"] == 5
        assert fader["trend_rho"] == pytest.approx(-1.0)
        assert "FADER" in _symbols(res["groups"]["fading"])
        assert _symbols(res["movers"]["pct_jump"]["down"])[0] == "FADER"

    def test_flat_symbol_not_in_trend_groups(self, ladder_panel: pd.DataFrame) -> None:
        res = ba.aggregate_batch(ladder_panel, dates=DATES, horizon_days=10, top_k=3)
        assert "FLAT3" not in _symbols(res["groups"]["rising"])
        assert "FLAT3" not in _symbols(res["groups"]["fading"])


class TestCoveragePenalty:
    def test_single_day_high_scorer_excluded_from_consensus(self) -> None:
        """只出现 1 天且当天分数最高的股票不得进 consensus_long。"""
        score_map: dict[str, dict[str, float]] = {
            f"BASE{i}": {d: float(i) for d in DATES} for i in range(5)
        }
        score_map["STEADY"] = dict.fromkeys(DATES, 99.0)
        score_map["FLASH"] = {DATES[-1]: 999.0}

        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=3
        )
        rows = _by_symbol(res)

        assert rows["FLASH"]["appear_days"] == 1
        assert rows["FLASH"]["coverage"] == pytest.approx(0.2)
        assert rows["FLASH"]["weighted_pct"] == pytest.approx(1.0)
        consensus = _symbols(res["groups"]["consensus_long"])
        assert "FLASH" not in consensus
        assert "STEADY" in consensus
        # 覆盖率惩罚必须体现在信念分上
        assert rows["FLASH"]["conviction_long"] < rows["STEADY"]["conviction_long"]


class TestMissingDaysAreNaNNotZero:
    def test_absent_days_do_not_drag_mean_pct(self) -> None:
        """只在首末日出现的高分股，mean_pct 必须只由这两天决定。"""
        score_map: dict[str, dict[str, float]] = {
            f"BASE{i}": {d: float(i) for d in DATES} for i in range(4)
        }
        score_map["HALTED"] = {DATES[0]: 100.0, DATES[-1]: 100.0}

        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=3
        )
        halted = _by_symbol(res)["HALTED"]

        assert halted["appear_days"] == 2
        assert halted["coverage"] == pytest.approx(0.4)
        # 两天都是当日最高分 → pct 均为 1.0，均值必须仍是 1.0
        assert halted["mean_pct"] == pytest.approx(1.0)
        assert halted["median_pct"] == pytest.approx(1.0)
        assert halted["std_pct"] == pytest.approx(0.0)
        assert halted["weighted_pct"] == pytest.approx(1.0)
        assert halted["best_rank"] == 1
        assert halted["worst_rank"] == 1
        assert halted["first_seen"] == DATES[0]
        assert halted["last_seen"] == DATES[-1]

    def test_fully_missing_date_yields_placeholder_row(self) -> None:
        score_map = {f"BASE{i}": {d: float(i) for d in DATES[:3]} for i in range(4)}
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=2
        )

        daily = {row["trade_date"]: row for row in res["daily"]}
        assert len(res["daily"]) == len(DATES)
        assert daily[DATES[3]]["missing"] is True
        assert daily[DATES[3]]["count"] == 0
        assert daily[DATES[0]]["missing"] is False
        assert res["meta"]["missing_dates"] == DATES[3:]

    def test_trend_p_none_for_small_sample(self) -> None:
        score_map = {
            "A": {DATES[0]: -1.0, DATES[1]: 1.5, DATES[2]: 3.5},
            "C0": dict.fromkeys(DATES[:3], 0.0),
            "C1": dict.fromkeys(DATES[:3], 1.0),
            "C2": dict.fromkeys(DATES[:3], 3.0),
        }
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=2
        )
        rows = _by_symbol(res)
        # A 的截面分位 3 天严格上升 → C(3,2)=3 对全为上升
        assert rows["A"]["is_monotonic_up"] is True
        assert rows["A"]["mk_s"] == 3
        # 3 个观测点 → p 值不可信，必须为 None 而非假值
        assert rows["A"]["trend_p"] is None
        assert rows["A"]["trend_rho"] == pytest.approx(1.0)


class TestMovers:
    def test_raw_score_and_pct_jump_disagree_on_broad_rally(self) -> None:
        """普涨日：BETA 原始分升但截面分位降 —— 两口径必须给出相反结论。"""
        rows: list[dict[str, Any]] = []
        for k, date in enumerate(DATES):
            drift = 10.0 * k  # 全市场整体上移
            rows.append(
                {"trade_date": date, "symbol": "BETA", "fusion_score": 1.0 + drift}
            )
            for i in range(5):
                # 其他股票涨得更凶，把 BETA 的分位一路挤下去
                rows.append(
                    {
                        "trade_date": date,
                        "symbol": f"ALPHA{i}",
                        "fusion_score": -5.0 + i + drift + 3.0 * k,
                    }
                )
        res = ba.aggregate_batch(_panel(rows), dates=DATES, horizon_days=10, top_k=6)

        movers = res["movers"]

        def value_of(metric: str, symbol: str) -> float:
            board = movers[metric]
            hit = next(r for r in board["up"] + board["down"] if r["symbol"] == symbol)
            return hit["value"]

        assert value_of("raw_score_change", "BETA") > 0  # 原始分数明显上升
        assert value_of("pct_jump", "BETA") < 0  # 截面分位实则下滑
        assert value_of("rank_change", "BETA") < 0  # 名次同样后退
        assert movers["raw_score_change"]["warning"]
        assert movers["pct_jump"]["warning"] is None

    def test_rank_change_sign_and_endpoints(self, ladder_panel: pd.DataFrame) -> None:
        res = ba.aggregate_batch(ladder_panel, dates=DATES, horizon_days=10, top_k=3)
        rank_up = {r["symbol"]: r for r in res["movers"]["rank_change"]["up"]}

        riser = rank_up["RISER"]
        assert riser["rank_from"] == 9  # 首日垫底（9 只股票）
        assert riser["rank_to"] == 1  # 末日登顶
        assert riser["value"] == 8
        assert riser["from_date"] == DATES[0]
        assert riser["to_date"] == DATES[-1]
        assert _symbols(res["movers"]["rank_change"]["down"])[0] == "FADER"

    def test_movers_endpoints_use_actual_appearance_dates(self) -> None:
        score_map: dict[str, dict[str, float]] = {
            f"BASE{i}": {d: float(i) for d in DATES} for i in range(4)
        }
        score_map["LATE"] = {DATES[1]: -1.0, DATES[3]: 99.0}
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=3
        )
        late = next(r for r in res["movers"]["pct_jump"]["up"] if r["symbol"] == "LATE")
        assert late["from_date"] == DATES[1]
        assert late["to_date"] == DATES[3]
        assert late["value"] == pytest.approx(1.0)

    def test_daily_max_jump_locates_the_break_day(self) -> None:
        """SPIKE 只在第 4 天（索引 3）突变，change_date 必须指向该日。"""
        score_map: dict[str, dict[str, float]] = {
            f"BASE{i}": {d: float(i) for d in DATES} for i in range(5)
        }
        score_map["SPIKE"] = {
            DATES[0]: -1.0,
            DATES[1]: -1.0,
            DATES[2]: -1.0,
            DATES[3]: 99.0,
            DATES[4]: 99.0,
        }
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=3
        )
        spike = next(
            r for r in res["movers"]["daily_max_jump"]["up"] if r["symbol"] == "SPIKE"
        )
        assert spike["change_date"] == DATES[3]
        assert spike["prev_date"] == DATES[2]
        assert spike["value"] == pytest.approx(1.0)
        assert spike["pct_from"] == pytest.approx(0.0)
        assert spike["pct_to"] == pytest.approx(1.0)


class TestShortSideMirror:
    def test_flipping_scores_swaps_long_and_short_results(
        self, ladder_panel: pd.DataFrame
    ) -> None:
        """分数取负 → 截面分位变 1-pct，long 与 short 结论应互换。"""
        flipped = ladder_panel.copy()
        flipped["fusion_score"] = -flipped["fusion_score"]
        flipped = _panel(
            flipped[["trade_date", "symbol", "fusion_score"]].to_dict("records")
        )

        base = ba.aggregate_batch(ladder_panel, dates=DATES, horizon_days=10, top_k=3)
        flip = ba.aggregate_batch(flipped, dates=DATES, horizon_days=10, top_k=3)
        base_rows, flip_rows = _by_symbol(base), _by_symbol(flip)

        for symbol in base_rows:
            b, f = base_rows[symbol], flip_rows[symbol]
            assert f["weighted_pct"] == pytest.approx(1.0 - b["weighted_pct"])
            assert f["mean_pct"] == pytest.approx(1.0 - b["mean_pct"])
            assert f["topk_hits"] == b["bottomk_hits"]
            assert f["bottomk_hits"] == b["topk_hits"]
            assert f["conviction_long"] == pytest.approx(b["conviction_short"])
            assert f["conviction_short"] == pytest.approx(b["conviction_long"])

        assert _symbols(flip["groups"]["consensus_short"]) == _symbols(
            base["groups"]["consensus_long"]
        )
        assert _symbols(flip["groups"]["consensus_long"]) == _symbols(
            base["groups"]["consensus_short"]
        )
        # 多头分位持续下滑的 FADER 应出现在空头恶化榜
        assert "FADER" in _symbols(base["groups"]["deteriorating_short"])
        assert "RISER" in _symbols(flip["groups"]["deteriorating_short"])

    def test_side_filter_limits_group_keys(self, ladder_panel: pd.DataFrame) -> None:
        long_only = ba.aggregate_batch(
            ladder_panel, dates=DATES, horizon_days=10, top_k=3, side="long"
        )
        short_only = ba.aggregate_batch(
            ladder_panel, dates=DATES, horizon_days=10, top_k=3, side="short"
        )
        assert "consensus_short" not in long_only["groups"]
        assert "consensus_long" in long_only["groups"]
        assert "consensus_long" not in short_only["groups"]
        assert "consensus_short" in short_only["groups"]

        with pytest.raises(ValueError):
            ba.aggregate_batch(
                ladder_panel, dates=DATES, horizon_days=10, side="sideways"
            )


class TestDailyTurnover:
    def test_identical_topk_gives_zero_turnover(self) -> None:
        score_map = {f"S{i}": {d: float(i) for d in DATES} for i in range(6)}
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=3
        )
        daily = res["daily"]

        assert daily[0]["topk_jaccard"] is None  # 首日无前一日
        for row in daily[1:]:
            assert row["topk_jaccard"] == pytest.approx(1.0)
            assert row["topk_turnover"] == pytest.approx(0.0)

    def test_disjoint_topk_gives_full_turnover(self) -> None:
        """每日 Top-2 完全换血 → jaccard=0, turnover=1。"""
        rows: list[dict[str, Any]] = []
        for k, date in enumerate(DATES):
            for i in range(4):
                # 每日轮转：分数按 (i - k) mod 4 排序，Top-2 每日整组替换
                score = float((i - 2 * k) % 4)
                rows.append(
                    {"trade_date": date, "symbol": f"S{i}", "fusion_score": score}
                )
        res = ba.aggregate_batch(_panel(rows), dates=DATES, horizon_days=10, top_k=2)
        for row in res["daily"][1:]:
            assert row["topk_jaccard"] == pytest.approx(0.0)
            assert row["topk_turnover"] == pytest.approx(1.0)

    def test_daily_reuses_score_distribution_helper(self) -> None:
        score_map = {f"S{i}": {d: float(i) - 2.0 for d in DATES} for i in range(6)}
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=3
        )
        first = res["daily"][0]

        assert first["count"] == 6
        assert first["buy_count"] == 0
        assert first["hold_count"] == 6
        assert first["consensus_overlap"] == 3
        dist = first["distribution"]
        assert dist["count"] == 6
        assert dist["negative_count"] == 2  # -2, -1
        assert dist["positive_count"] == 3  # 1, 2, 3
        assert dist["zero_count"] == 1
        assert "histogram" in dist


class TestMetaHonesty:
    @pytest.mark.parametrize(
        ("window", "horizon", "expected"),
        [(5, 10, 1), (10, 10, 1), (20, 10, 2), (1, 10, 1)],
    )
    def test_effective_independent_bets(
        self, window: int, horizon: int, expected: int
    ) -> None:
        dates = pd.bdate_range("2026-06-01", periods=window).strftime("%Y-%m-%d")
        dates = dates.tolist()
        score_map = {f"S{i}": {d: float(i) for d in dates} for i in range(3)}
        res = ba.aggregate_batch(
            _grid(score_map), dates=dates, horizon_days=horizon, top_k=2
        )
        meta = res["meta"]
        assert meta["window_days"] == window
        assert meta["horizon_days"] == horizon
        assert meta["effective_independent_bets"] == expected
        assert meta["anchor_date"] == dates[-1]

    def test_warning_when_window_exceeds_horizon(self) -> None:
        dates = pd.bdate_range("2026-06-01", periods=12).strftime("%Y-%m-%d").tolist()
        score_map = {f"S{i}": {d: float(i) for d in dates} for i in range(3)}
        res = ba.aggregate_batch(_grid(score_map), dates=dates, horizon_days=5, top_k=2)
        joined = " ".join(res["meta"]["warnings"])
        assert "跨轮次" in joined

    def test_warning_when_window_shorter_than_horizon(
        self, ladder_panel: pd.DataFrame
    ) -> None:
        res = ba.aggregate_batch(ladder_panel, dates=DATES, horizon_days=10, top_k=3)
        joined = " ".join(res["meta"]["warnings"])
        assert "持有期" in joined
        assert res["meta"]["signal_autocorr"] is not None

    def test_empty_panel_returns_placeholder_structure(self) -> None:
        empty = pd.DataFrame(
            columns=["trade_date", "symbol", "fusion_score", "signal_side", "rk", "pct"]
        )
        res = ba.aggregate_batch(empty, dates=DATES, horizon_days=10)

        assert res["per_symbol"] == []
        assert res["groups"] == {}
        assert res["movers"] == {}
        assert all(row["missing"] for row in res["daily"])
        assert res["meta"]["symbol_count"] == 0

    def test_missing_required_column_raises(self) -> None:
        with pytest.raises(ValueError, match="fusion_score"):
            ba.aggregate_batch(
                pd.DataFrame({"trade_date": DATES, "symbol": ["A"] * 5}),
                dates=DATES,
                horizon_days=10,
            )


class TestWeightedPctAndMembership:
    def test_weighted_pct_matches_manual_decay_formula(self) -> None:
        """手算校验时间衰减加权：仅两只股票时 pct 只取 0/1。"""
        decay = 0.5
        score_map = {
            "UP": {DATES[0]: 0.0, DATES[1]: 0.0, DATES[2]: 9.0},
            "DOWN": {DATES[0]: 1.0, DATES[1]: 1.0, DATES[2]: 1.0},
        }
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES[:3], horizon_days=3, top_k=1, decay=decay
        )
        up = _by_symbol(res)["UP"]

        weights = [decay**2, decay**1, decay**0]
        pcts = [0.0, 0.0, 1.0]
        expected = sum(w * p for w, p in zip(weights, pcts, strict=True)) / sum(weights)
        assert up["weighted_pct"] == pytest.approx(expected)
        assert up["weighted_pct"] > up["mean_pct"]  # 近端高分被加权放大

    def test_membership_labels(self) -> None:
        score_map: dict[str, dict[str, float]] = {
            f"BASE{i}": {d: float(i) for d in DATES} for i in range(6)
        }
        score_map["CORE"] = dict.fromkeys(DATES, 100.0)
        score_map["ENTRANT"] = {
            DATES[0]: -9.0,
            DATES[1]: -9.0,
            DATES[2]: -9.0,
            DATES[3]: 90.0,
            DATES[4]: 90.0,
        }
        score_map["DROPOUT"] = {
            DATES[0]: 90.0,
            DATES[1]: 90.0,
            DATES[2]: 90.0,
            DATES[3]: -9.0,
            DATES[4]: -9.0,
        }
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=2
        )
        rows = _by_symbol(res)

        assert rows["CORE"]["membership"] == "core"
        assert rows["ENTRANT"]["membership"] == "new_entrant"
        assert rows["DROPOUT"]["membership"] == "dropout"
        assert "CORE" in _symbols(res["groups"]["stable_core"])
        assert "ENTRANT" in _symbols(res["groups"]["new_entrants"])
        assert "DROPOUT" in _symbols(res["groups"]["dropouts"])
        assert rows["CORE"]["topk_hits"] == 5
        assert rows["CORE"]["first_topk_day"] == DATES[0]
        assert rows["DROPOUT"]["last_topk_day"] == DATES[2]

    def test_signal_side_counts(self) -> None:
        rows = []
        for k, date in enumerate(DATES):
            rows.append(
                {
                    "trade_date": date,
                    "symbol": "A",
                    "fusion_score": 1.0,
                    "signal_side": "BUY" if k < 3 else "SELL",
                    "stock_name": "甲股",
                }
            )
            rows.append(
                {
                    "trade_date": date,
                    "symbol": "B",
                    "fusion_score": 0.0,
                    "signal_side": "HOLD",
                    "stock_name": "",
                }
            )
        res = ba.aggregate_batch(pd.DataFrame(rows), dates=DATES, horizon_days=10)
        a = _by_symbol(res)["A"]

        assert (a["buy_days"], a["sell_days"], a["hold_days"]) == (3, 2, 0)
        assert a["stock_name"] == "甲股"
        # rk/pct 缺列时的防御性补算
        assert a["weighted_pct"] == pytest.approx(1.0)
        assert res["daily"][0]["buy_count"] == 1
        assert res["daily"][-1]["sell_count"] == 1


class TestConvictionBounds:
    def test_conviction_in_zero_to_hundred(self, ladder_panel: pd.DataFrame) -> None:
        res = ba.aggregate_batch(ladder_panel, dates=DATES, horizon_days=10, top_k=3)
        for row in res["per_symbol"]:
            for key in ("conviction_long", "conviction_short"):
                assert 0.0 <= row[key] <= 100.0
                assert math.isfinite(row[key])

    def test_per_symbol_sorted_by_conviction_long(
        self, ladder_panel: pd.DataFrame
    ) -> None:
        res = ba.aggregate_batch(ladder_panel, dates=DATES, horizon_days=10, top_k=3)
        scores = [r["conviction_long"] for r in res["per_symbol"]]
        assert scores == sorted(scores, reverse=True)
