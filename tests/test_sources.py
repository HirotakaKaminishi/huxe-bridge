"""tests for huxe_bridge.sources"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

import huxe_bridge.core as core
import huxe_bridge.sources as sources_mod


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """既存 categories.yaml を tmp にコピーしてパッチ。"""
    src = Path(core.CONFIG)
    tmp_cfg = tmp_path / "categories.yaml"
    shutil.copy(src, tmp_cfg)
    monkeypatch.setattr(core, "CONFIG", tmp_cfg)
    # sources_mod は import 時に CONFIG を参照するのでパッチが効く形にしてある
    monkeypatch.setattr(sources_mod, "CONFIG", tmp_cfg)
    return tmp_cfg


def test_list_sources_empty_for_unconfigured_category(temp_config):
    out = sources_mod.list_sources("aws-infra")
    assert out == []


def test_list_sources_all_categories(temp_config):
    sources_mod.add_source("aws-infra", "https://example.com/feed/")
    sources_mod.add_source("anime-music", "https://example.com/anime/")
    out = sources_mod.list_sources()
    assert len(out) == 2
    assert {s["category_id"] for s in out} == {"aws-infra", "anime-music"}


def test_list_sources_unknown_category_raises(temp_config):
    with pytest.raises(ValueError, match="category not found"):
        sources_mod.list_sources("no-such-cat")


def test_add_source_basic(temp_config):
    res = sources_mod.add_source("aws-infra", "https://example.com/feed/")
    assert res["category_id"] == "aws-infra"
    assert res["added"]["url"] == "https://example.com/feed/"
    assert res["added"]["max_items_per_run"] == 5
    assert res["added"]["enabled"] is True
    out = sources_mod.list_sources("aws-infra")
    assert len(out) == 1


def test_add_source_to_unknown_category_raises(temp_config):
    with pytest.raises(ValueError, match="category not found"):
        sources_mod.add_source("no-such-cat", "https://example.com/feed/")


def test_add_source_duplicate_url_raises(temp_config):
    sources_mod.add_source("aws-infra", "https://example.com/feed/")
    with pytest.raises(ValueError, match="already exists"):
        sources_mod.add_source("aws-infra", "https://example.com/feed/")


def test_add_source_scheme_lowercased_for_dedupe(temp_config):
    sources_mod.add_source("aws-infra", "https://Example.com/feed/")
    with pytest.raises(ValueError, match="already exists"):
        sources_mod.add_source("aws-infra", "HTTPS://example.com/feed/")


def test_add_source_invalid_max_items(temp_config):
    with pytest.raises(ValueError, match="max_items_per_run"):
        sources_mod.add_source("aws-infra", "https://example.com/feed/", max_items_per_run=0)


def test_remove_source(temp_config):
    sources_mod.add_source("aws-infra", "https://example.com/feed/")
    sources_mod.remove_source("aws-infra", "https://example.com/feed/")
    assert sources_mod.list_sources("aws-infra") == []


def test_remove_unknown_source_raises(temp_config):
    with pytest.raises(ValueError, match="source not found"):
        sources_mod.remove_source("aws-infra", "https://example.com/nope/")


def test_yaml_round_trip_preserves_category_order(temp_config):
    """add_source 後も既存カテゴリ順 (aws-infra → anime-music → fido-auth) が保たれる。"""
    sources_mod.add_source("anime-music", "https://example.com/feed/")
    with temp_config.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ids = [c["id"] for c in cfg["categories"]]
    assert ids == ["aws-infra", "anime-music", "fido-auth"]


def test_add_then_remove_keeps_other_keys(temp_config):
    """add_source/remove_source で category の他のキー (name/description/tags) を壊さない。"""
    before = yaml.safe_load(temp_config.read_text(encoding="utf-8"))
    sources_mod.add_source("aws-infra", "https://example.com/feed/")
    sources_mod.remove_source("aws-infra", "https://example.com/feed/")
    after = yaml.safe_load(temp_config.read_text(encoding="utf-8"))
    # sources キーが空 list として残る可能性はあるが、name/description は不変
    for cb, ca in zip(before["categories"], after["categories"]):
        assert cb["id"] == ca["id"]
        assert cb["name"] == ca["name"]
        assert cb.get("description") == ca.get("description")
        assert cb.get("tags") == ca.get("tags")
