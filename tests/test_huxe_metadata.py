"""tests for huxe_bridge.huxe_metadata"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

import huxe_bridge.core as core
import huxe_bridge.huxe_metadata as hm


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """既存 categories.yaml を huxe ブロック無しの状態で tmp にコピーしてパッチ。"""
    src = Path(core.CONFIG)
    tmp_cfg = tmp_path / "categories.yaml"
    shutil.copy(src, tmp_cfg)
    cfg = yaml.safe_load(tmp_cfg.read_text(encoding="utf-8"))
    for c in cfg.get("categories", []):
        c.pop("huxe", None)
    tmp_cfg.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(core, "CONFIG", tmp_cfg)
    monkeypatch.setattr(hm, "CONFIG", tmp_cfg)
    return tmp_cfg


def test_get_metadata_returns_none_when_unset(temp_config):
    assert hm.get_metadata("aws-infra") is None


def test_get_metadata_unknown_category_raises(temp_config):
    with pytest.raises(ValueError, match="category not found"):
        hm.get_metadata("no-such-cat")


def test_set_metadata_writes_all_three_fields(temp_config):
    res = hm.set_metadata(
        "aws-infra",
        show_title="t",
        show_description="d",
        custom_instructions="ci",
    )
    assert res["category_id"] == "aws-infra"
    assert res["huxe"]["show_title"] == "t"
    assert res["huxe"]["show_description"] == "d"
    assert res["huxe"]["custom_instructions"] == "ci"


def test_set_metadata_partial_update_preserves_existing(temp_config):
    hm.set_metadata("aws-infra", show_title="t1", show_description="d1", custom_instructions="ci1")
    hm.set_metadata("aws-infra", show_title="t2")  # description / instructions は据え置き
    got = hm.get_metadata("aws-infra")
    assert got == {"show_title": "t2", "show_description": "d1", "custom_instructions": "ci1"}


def test_set_metadata_round_trip_via_yaml(temp_config):
    hm.set_metadata("fido-auth", show_title="FIDO", show_description="WA", custom_instructions="X")
    raw = yaml.safe_load(temp_config.read_text(encoding="utf-8"))
    cat = next(c for c in raw["categories"] if c["id"] == "fido-auth")
    assert cat["huxe"]["show_title"] == "FIDO"
    # 既存キー (name/description/tags/sources) は壊れていない
    assert cat["name"] == "FIDO認証"
    assert "tags" in cat


def test_set_metadata_unknown_category_raises(temp_config):
    with pytest.raises(ValueError, match="category not found"):
        hm.set_metadata("no-such-cat", show_title="t")


def test_build_setup_with_metadata(temp_config):
    hm.set_metadata("aws-infra", show_title="t", show_description="d", custom_instructions="ci")
    setup = hm.build_setup("aws-infra", "https://example.com/huxe-bridge/")
    assert setup == {
        "category_id": "aws-infra",
        "feed_url": "https://example.com/huxe-bridge/aws-infra.xml",
        "show_title": "t",
        "show_description": "d",
        "custom_instructions": "ci",
    }


def test_build_setup_without_metadata_returns_nulls(temp_config):
    setup = hm.build_setup("aws-infra", "https://example.com/huxe-bridge")
    assert setup["category_id"] == "aws-infra"
    assert setup["feed_url"] == "https://example.com/huxe-bridge/aws-infra.xml"
    assert setup["show_title"] is None
    assert setup["show_description"] is None
    assert setup["custom_instructions"] is None


def test_build_setup_unknown_category_raises(temp_config):
    with pytest.raises(ValueError, match="category not found"):
        hm.build_setup("no-such-cat", "https://example.com/")
