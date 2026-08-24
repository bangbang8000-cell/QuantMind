from pathlib import Path

from backend.shared import qlib_paths


def _make_ready_provider(root: Path) -> None:
    (root / "calendars").mkdir(parents=True)
    (root / "instruments").mkdir()
    (root / "features" / "sh600000").mkdir(parents=True)
    (root / "calendars" / "day.txt").write_text("2024-01-02\n")
    (root / "instruments" / "all.txt").write_text(
        "SH600000\t2024-01-02\t2024-01-02\n"
    )


def test_is_qlib_provider_ready_requires_day_layout(tmp_path: Path):
    provider = tmp_path / "cn_data"
    provider.mkdir()

    assert not qlib_paths.is_qlib_provider_ready(provider)

    _make_ready_provider(provider)

    assert qlib_paths.is_qlib_provider_ready(provider)


def test_resolve_cn_skips_incomplete_quantdb_cache(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("QLIB_PROVIDER_URI", raising=False)
    monkeypatch.setattr(qlib_paths, "_PROJECT_ROOT", tmp_path)

    incomplete_cache = tmp_path / "data" / "quantdb" / ".qlib_cache" / "cn_data"
    incomplete_cache.mkdir(parents=True)
    fallback = tmp_path / "db" / "qlib_data"
    _make_ready_provider(fallback)

    assert qlib_paths.resolve_qlib_provider_uri("CN") == str(fallback)
