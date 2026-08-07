"""batch_aggregator 纯函数聚合的单元测试。

守护的核心口径：跨日主排序键必须是截面分位而非原始分数；缺席日是 NaN 而非 0 分。
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
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


class TestConsensusBandGate:
    """共识门槛必须 scale-free：绝对 Top-K 在 5500 只全市场下不可满足。"""

    def _rotating_universe(self, n_symbols: int = 1000) -> pd.DataFrame:
        """高换手宽 universe：ANCHOR 稳居分位带顶部但从不进 Top-3。

        ANCHOR 恒为 1.8，标准正态下约 3.6% 超过它 → 每日约 36 只压在其上，
        故 rank≈37（pct≈0.96，稳居 0.95 带内）而 Top-3 命中恒为 0。
        """
        rng = np.random.default_rng(11)
        rows: list[dict[str, Any]] = []
        for date in DATES:
            for i in range(n_symbols):
                rows.append(
                    {
                        "trade_date": date,
                        "symbol": f"N{i:04d}",
                        "fusion_score": float(rng.normal()),
                    }
                )
            rows.append({"trade_date": date, "symbol": "ANCHOR", "fusion_score": 1.8})
        return _panel(rows)

    def test_band_gate_makes_consensus_nonempty_where_topk_gate_cannot(self) -> None:
        panel = self._rotating_universe()
        res = ba.aggregate_batch(
            panel, dates=DATES, horizon_days=10, top_k=3, consensus_band=0.95
        )
        anchor = _by_symbol(res)["ANCHOR"]

        # 前提：Top-3 命中次数不足 hit_gate=3，旧口径下必然落选
        assert anchor["topk_hits"] < 3
        assert anchor["band_hits"] == len(DATES)
        assert anchor["coverage"] == pytest.approx(1.0)
        assert "ANCHOR" in _symbols(res["groups"]["consensus_long"])

    def test_band_hits_counts_days_above_band(self) -> None:
        score_map: dict[str, dict[str, float]] = {
            f"B{i:02d}": dict.fromkeys(DATES, float(i)) for i in range(20)
        }
        # 20 只股票 → pct 步长 1/19；B19=1.0, B18≈0.947, B17≈0.895
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, consensus_band=0.9
        )
        rows = _by_symbol(res)

        assert rows["B19"]["band_hits"] == len(DATES)
        assert rows["B18"]["band_hits"] == len(DATES)  # 0.947 >= 0.9
        assert rows["B17"]["band_hits"] == 0  # 0.895 < 0.9
        # 空头侧镜像：pct <= 1 - band = 0.1
        assert rows["B00"]["band_hits_short"] == len(DATES)
        assert rows["B01"]["band_hits_short"] == len(DATES)
        assert rows["B02"]["band_hits_short"] == 0

    def test_consensus_short_uses_mirrored_band(self) -> None:
        flipped = self._rotating_universe().copy()
        flipped["fusion_score"] = -flipped["fusion_score"]
        flipped = _panel(
            flipped[["trade_date", "symbol", "fusion_score"]].to_dict("records")
        )
        res = ba.aggregate_batch(
            flipped, dates=DATES, horizon_days=10, top_k=3, consensus_band=0.95
        )
        anchor = _by_symbol(res)["ANCHOR"]

        assert anchor["band_hits_short"] == len(DATES)
        assert anchor["bottomk_hits"] < 3
        assert "ANCHOR" in _symbols(res["groups"]["consensus_short"])

    def test_band_is_configurable(self) -> None:
        panel = self._rotating_universe()
        strict = ba.aggregate_batch(
            panel, dates=DATES, horizon_days=10, top_k=3, consensus_band=0.999
        )
        loose = ba.aggregate_batch(
            panel, dates=DATES, horizon_days=10, top_k=3, consensus_band=0.80
        )
        assert strict["meta"]["consensus_band"] == pytest.approx(0.999)
        assert _by_symbol(strict)["ANCHOR"]["band_hits"] == 0  # pct≈0.96 < 0.999
        assert _by_symbol(loose)["ANCHOR"]["band_hits"] == len(DATES)
        assert len(loose["groups"]["consensus_long"]) >= len(
            strict["groups"]["consensus_long"]
        )


class TestHitterBoards:
    """用户原话「前20出现次数最多的股票」是排行榜，不是阈值筛选。"""

    def test_top_hitters_sorted_by_hit_count_desc(self) -> None:
        score_map: dict[str, dict[str, float]] = {
            f"BASE{i}": dict.fromkeys(DATES, float(i)) for i in range(6)
        }
        # HIT5 全 5 天进 Top-2；HIT3 只有 3 天；HIT1 只有 1 天
        score_map["HIT5"] = dict.fromkeys(DATES, 100.0)
        score_map["HIT3"] = {
            DATES[0]: 90.0,
            DATES[1]: 90.0,
            DATES[2]: 90.0,
            DATES[3]: -9.0,
            DATES[4]: -9.0,
        }
        score_map["HIT1"] = {
            **dict.fromkeys(DATES, -9.0),
            DATES[4]: 90.0,
        }
        # top_k 同时决定「什么算上榜」和「榜单返回几条」，故取 2 判定命中、
        # 另跑一次 top_k=9 拿到完整榜单验证排序
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=2
        )
        assert len(res["groups"]["top_hitters"]) == 2

        full = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=2, side="long"
        )
        rows = _by_symbol(full)
        assert rows["HIT5"]["topk_hits"] == 5
        assert rows["HIT3"]["topk_hits"] == 3
        assert rows["HIT1"]["topk_hits"] == 1

        board = res["groups"]["top_hitters"]
        hits = [r["topk_hits"] for r in board]
        assert hits == sorted(hits, reverse=True)
        assert _symbols(board)[0] == "HIT5"
        assert board[0]["topk_hits"] == 5

    def test_top_hitters_breaks_ties_by_weighted_pct(self) -> None:
        score_map: dict[str, dict[str, float]] = {
            f"BASE{i}": dict.fromkeys(DATES, float(i)) for i in range(6)
        }
        score_map["STRONG"] = dict.fromkeys(DATES, 200.0)
        score_map["WEAKER"] = dict.fromkeys(DATES, 100.0)
        res = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=5
        )
        board = res["groups"]["top_hitters"]

        assert board[0]["topk_hits"] == board[1]["topk_hits"] == 5
        assert _symbols(board)[:2] == ["STRONG", "WEAKER"]

    def test_bottom_hitters_mirrors_top_hitters(self) -> None:
        score_map: dict[str, dict[str, float]] = {
            f"BASE{i}": dict.fromkeys(DATES, float(i)) for i in range(6)
        }
        score_map["WORST"] = dict.fromkeys(DATES, -100.0)
        panel = _grid(score_map)
        flipped = panel.copy()
        flipped["fusion_score"] = -flipped["fusion_score"]
        flipped = _panel(
            flipped[["trade_date", "symbol", "fusion_score"]].to_dict("records")
        )

        base = ba.aggregate_batch(panel, dates=DATES, horizon_days=10, top_k=2)
        flip = ba.aggregate_batch(flipped, dates=DATES, horizon_days=10, top_k=2)

        assert _symbols(base["groups"]["bottom_hitters"])[0] == "WORST"
        assert base["groups"]["bottom_hitters"][0]["bottomk_hits"] == 5
        assert _symbols(flip["groups"]["top_hitters"]) == _symbols(
            base["groups"]["bottom_hitters"]
        )

    def test_hitter_boards_respect_side_filter(self) -> None:
        score_map = {f"S{i}": dict.fromkeys(DATES, float(i)) for i in range(6)}
        long_only = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=2, side="long"
        )
        short_only = ba.aggregate_batch(
            _grid(score_map), dates=DATES, horizon_days=10, top_k=2, side="short"
        )
        assert "top_hitters" in long_only["groups"]
        assert "bottom_hitters" not in long_only["groups"]
        assert "bottom_hitters" in short_only["groups"]
        assert "top_hitters" not in short_only["groups"]


class TestMonotonicNoiseWarning:
    def test_small_window_monotonic_noise_is_flagged(self) -> None:
        """N=3 纯随机下约 1/6 股票偶然单调 —— 必须警告用户这是噪声。"""
        rng = np.random.default_rng(5)
        short_dates = DATES[:3]
        rows: list[dict[str, Any]] = []
        for date in short_dates:
            for i in range(400):
                rows.append(
                    {
                        "trade_date": date,
                        "symbol": f"R{i:03d}",
                        "fusion_score": float(rng.normal()),
                    }
                )
        res = ba.aggregate_batch(
            _panel(rows), dates=short_dates, horizon_days=10, top_k=20
        )

        ratio = res["meta"]["monotonic_up_ratio"]
        assert 0.10 < ratio < 0.25  # 理论期望 1/6
        joined = " ".join(res["meta"]["warnings"])
        assert "严格单调" in joined
        assert "噪声" in joined
        assert "up_streak" in joined
        assert "trend_rho" in joined

    def test_long_window_has_no_monotonic_noise_warning(self) -> None:
        rng = np.random.default_rng(6)
        dates = pd.bdate_range("2026-06-01", periods=10).strftime("%Y-%m-%d").tolist()
        rows: list[dict[str, Any]] = []
        for date in dates:
            for i in range(200):
                rows.append(
                    {
                        "trade_date": date,
                        "symbol": f"R{i:03d}",
                        "fusion_score": float(rng.normal()),
                    }
                )
        res = ba.aggregate_batch(_panel(rows), dates=dates, horizon_days=10, top_k=20)

        # N=10 时 1/10! ≈ 2.8e-6，实际恒为 0
        assert res["meta"]["monotonic_up_ratio"] == pytest.approx(0.0)
        assert "严格单调" not in " ".join(res["meta"]["warnings"])

    def test_deterministic_monotonic_ladder_still_flagged_and_kept(self) -> None:
        """字段本身保留可用：构造的真单调股仍被正确标记。

        4 只股票 3 日，pct ∈ {0, 1/3, 2/3, 1}。UP 名次 4→3→2（pct 0→1/3→2/3），
        DOWN 名次 1→2→3，WOBBLE 名次 3→4→4 作非单调对照。
        """
        ranks_by_day = [
            {"DOWN": 4.0, "WOBBLE": 2.0, "TOP": 3.0, "UP": 1.0},
            {"TOP": 4.0, "DOWN": 3.0, "UP": 2.0, "WOBBLE": 1.0},
            {"TOP": 4.0, "UP": 3.0, "DOWN": 2.0, "WOBBLE": 1.0},
        ]
        rows = [
            {"trade_date": date, "symbol": sym, "fusion_score": score}
            for date, scores in zip(DATES[:3], ranks_by_day, strict=True)
            for sym, score in scores.items()
        ]
        res = ba.aggregate_batch(
            _panel(rows), dates=DATES[:3], horizon_days=10, top_k=2
        )
        rows_map = _by_symbol(res)

        assert rows_map["UP"]["mean_pct"] == pytest.approx(1.0 / 3.0)
        assert rows_map["UP"]["is_monotonic_up"] is True
        assert rows_map["UP"]["up_streak"] == 3
        assert rows_map["DOWN"]["is_monotonic_down"] is True
        assert rows_map["WOBBLE"]["is_monotonic_up"] is False
        assert rows_map["WOBBLE"]["is_monotonic_down"] is False


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


class TestDataIntegrityWarnings:
    """取数层口径错误必须吵出来 —— 静默失败会让聚合结论看似正常实则失真。"""

    def _base_rows(self, dates: list[str], n: int = 6) -> list[dict[str, Any]]:
        return [
            {"trade_date": d, "symbol": f"S{i}", "fusion_score": float(i)}
            for d in dates
            for i in range(n)
        ]

    def test_out_of_window_dates_are_reported_not_silently_dropped(self) -> None:
        """T+1 未归一化时会出现窗口外日期 —— 剔除但必须报出。"""
        rows = self._base_rows(DATES)
        rows += [
            {"trade_date": "2026-07-23", "symbol": "S0", "fusion_score": 9.0},
            {"trade_date": "2026-07-24", "symbol": "S1", "fusion_score": 9.0},
        ]
        res = ba.aggregate_batch(_panel(rows), dates=DATES, horizon_days=10, top_k=2)

        joined = " ".join(res["meta"]["warnings"])
        assert "dates 之外的 trade_date" in joined
        assert "2026-07-23" in joined
        assert "T+1" in joined
        # 窗口外数据确实未参与聚合
        assert all(row["trade_date"] in DATES for row in res["daily"])
        assert res["per_symbol"][0]["appear_days"] <= len(DATES)

    def test_clean_panel_has_no_integrity_warning(self) -> None:
        res = ba.aggregate_batch(
            _panel(self._base_rows(DATES)), dates=DATES, horizon_days=10, top_k=2
        )
        joined = " ".join(res["meta"]["warnings"])
        assert "trade_date" not in joined
        assert "重复" not in joined
        assert "中位数" not in joined

    def test_duplicate_symbol_day_deduped_not_averaged(self) -> None:
        """同日多 run 混入：按首次出现去重，绝不对两个模型的分数求平均。"""
        rows = self._base_rows(DATES)
        for row in rows:
            row["run_id"] = "run_A"
        # run_B 对 S0 给出完全相反的高分；若被平均则 S0 分数会被抬高
        dup = [
            {
                "trade_date": d,
                "symbol": "S0",
                "fusion_score": 100.0,
                "run_id": "run_B",
            }
            for d in DATES
        ]
        res = ba.aggregate_batch(
            pd.DataFrame(rows + dup), dates=DATES, horizon_days=10, top_k=2
        )

        joined = " ".join(res["meta"]["warnings"])
        assert "重复" in joined
        assert "run_B" in joined
        assert "run_id 精确限定" in joined
        # 每日行数应为去重后的 6，而非 11
        assert all(row["count"] == 6 for row in res["daily"])
        # S0 保留 run_A 的 0.0 分 → 仍是当日最低，未被 run_B 的 100 分污染
        s0 = _by_symbol(res)["S0"]
        assert s0["appear_days"] == len(DATES)
        assert s0["mean_pct"] == pytest.approx(0.0)
        assert s0["best_rank"] == 6

    def test_dedupe_recomputes_rank_and_pct_on_survivors(self) -> None:
        """去重改变了当日截面，调用方基于混合集算的 rk/pct 必须废弃重算。"""
        rows = self._base_rows(DATES, n=3)
        dup = [{"trade_date": d, "symbol": "S2", "fusion_score": 2.0} for d in DATES]
        panel = _panel(rows + dup)  # rk/pct 按 4 行/日 算出
        res = ba.aggregate_batch(panel, dates=DATES, horizon_days=10, top_k=2)

        rowmap = _by_symbol(res)
        assert all(row["count"] == 3 for row in res["daily"])
        # 3 只股票的截面：pct 必须是 0 / 0.5 / 1，而非 4 行时的 0 / 1/3 / 1
        assert rowmap["S1"]["mean_pct"] == pytest.approx(0.5)
        assert rowmap["S2"]["mean_pct"] == pytest.approx(1.0)
        assert rowmap["S2"]["best_rank"] == 1
        assert rowmap["S0"]["worst_rank"] == 3

    def test_sparse_day_is_flagged(self) -> None:
        """某日信号被重跑部分清理 → 行数远低于中位数，必须报出。"""
        rows = self._base_rows(DATES, n=50)
        # 只保留 DATES[2] 的 3 行（远低于中位数 50 的 20%）
        rows = [
            r for r in rows if r["trade_date"] != DATES[2] or int(r["symbol"][1:]) < 3
        ]
        res = ba.aggregate_batch(_panel(rows), dates=DATES, horizon_days=10, top_k=5)

        joined = " ".join(res["meta"]["warnings"])
        assert "中位数" in joined
        assert DATES[2] in joined
        assert "重跑" in joined

    def test_moderately_thin_day_not_flagged(self) -> None:
        """略少于中位数（停牌等正常波动）不应误报。"""
        rows = self._base_rows(DATES, n=50)
        rows = [
            r for r in rows if r["trade_date"] != DATES[2] or int(r["symbol"][1:]) < 40
        ]
        res = ba.aggregate_batch(_panel(rows), dates=DATES, horizon_days=10, top_k=5)
        assert "中位数" not in " ".join(res["meta"]["warnings"])

    def test_null_scores_reported(self) -> None:
        rows = self._base_rows(DATES)
        rows += [
            {"trade_date": DATES[0], "symbol": "SNULL", "fusion_score": float("nan")}
        ]
        res = ba.aggregate_batch(
            pd.DataFrame(rows), dates=DATES, horizon_days=10, top_k=2
        )
        assert "fusion_score 为空" in " ".join(res["meta"]["warnings"])
        assert "SNULL" not in _by_symbol(res)


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
