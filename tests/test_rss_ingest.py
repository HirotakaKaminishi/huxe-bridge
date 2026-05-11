"""tests for huxe_bridge.rss_ingest (offline, fixture-driven)."""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import huxe_bridge.core as core
import huxe_bridge.rss_ingest as ingest
import huxe_bridge.sources as sources_mod

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    """yaml + content/ をすべて tmp に閉じ込めて副作用を防ぐ。"""
    # copy config; clear sources so tests can add their own
    src_cfg = Path(core.CONFIG)
    tmp_cfg = tmp_path / "categories.yaml"
    shutil.copy(src_cfg, tmp_cfg)
    cfg = yaml.safe_load(tmp_cfg.read_text(encoding="utf-8"))
    for c in cfg.get("categories", []):
        c.pop("sources", None)
    tmp_cfg.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    tmp_content = tmp_path / "content"
    tmp_content.mkdir()

    monkeypatch.setattr(core, "CONFIG", tmp_cfg)
    monkeypatch.setattr(core, "CONTENT", tmp_content)
    monkeypatch.setattr(sources_mod, "CONFIG", tmp_cfg)
    monkeypatch.setattr(ingest, "CONFIG", tmp_cfg)
    monkeypatch.setattr(ingest, "CONTENT", tmp_content)

    # aws-infra に 1 source 登録 (RSS2)
    sources_mod.add_source("aws-infra", "https://example.com/rss2/")
    return {"cfg": tmp_cfg, "content": tmp_content}


# ---------------------------------------------------------------------------
# parse layer
# ---------------------------------------------------------------------------

def test_parse_rss2_returns_3_items():
    items = ingest._parse_feed(_load_fixture("feed_rss2.xml"))
    assert len(items) == 3
    assert items[0].guid == "guid1"
    assert items[0].title == "Item 1"


def test_parse_rdf_returns_3_items_with_link_fallback_guid():
    items = ingest._parse_feed(_load_fixture("feed_rdf.xml"))
    assert len(items) == 3
    # RDF には <guid> がない → link または rdf:about にフォールバック
    for i in items:
        assert i.guid  # 何らかの id を取れている
        assert i.guid.startswith("https://example.com/item")


def test_parse_atom_returns_3_items():
    items = ingest._parse_feed(_load_fixture("feed_atom.xml"))
    assert len(items) == 3
    assert items[0].guid == "urn:atom:1"


def test_html_entities_decoded_amp():
    items = ingest._parse_feed(_load_fixture("feed_rss2.xml"))
    # item 1 description: "First &amp; only description" → "First & only description"
    assert "&" in items[0].description_html
    assert "&amp;" not in items[0].description_html


def test_html_entities_decoded_unicode():
    items = ingest._parse_feed(_load_fixture("feed_rss2.xml"))
    # item 2 description: "音楽 &#x301c; ニュース" → "音楽 〜 ニュース" (U+301C)
    assert "〜" in items[1].description_html


def test_pubdate_parsed_to_utc():
    items = ingest._parse_feed(_load_fixture("feed_rss2.xml"))
    assert items[0].published_at.tzinfo is not None
    assert items[0].published_at.year == 2026


# ---------------------------------------------------------------------------
# ingest workflow
# ---------------------------------------------------------------------------

def _patch_fetch(monkeypatch, content_bytes: bytes):
    monkeypatch.setattr(
        ingest, "_fetch_with_retry", lambda url, **kw: content_bytes
    )


def test_bootstrap_takes_only_one_item_by_default(temp_env, monkeypatch):
    _patch_fetch(monkeypatch, _load_fixture("feed_rss2.xml"))
    r = ingest.ingest_category("aws-infra")
    assert r.fetched == 3
    assert r.added == 1  # bootstrap で最新 1 件のみ
    # 残り 2 件は index に処理済みとして記録
    idx = ingest._load_index("aws-infra")
    assert len(idx["items"]) == 3  # 1 + 2 (skipped)


def test_bootstrap_fetch_param_takes_n_items(temp_env, monkeypatch):
    _patch_fetch(monkeypatch, _load_fixture("feed_rss2.xml"))
    r = ingest.ingest_category("aws-infra", bootstrap_fetch=2)
    assert r.added == 2


def test_dedup_second_run_adds_zero(temp_env, monkeypatch):
    _patch_fetch(monkeypatch, _load_fixture("feed_rss2.xml"))
    ingest.ingest_category("aws-infra", bootstrap_fetch=3)
    # 2 回目
    r2 = ingest.ingest_category("aws-infra")
    assert r2.added == 0
    assert r2.skipped_dup == 3


def test_max_items_per_run_caps_added(temp_env, monkeypatch):
    # max_items_per_run=1 に書き換えて bootstrap_fetch=3 でも 1 件だけ
    cfg = yaml.safe_load((temp_env["cfg"]).read_text(encoding="utf-8"))
    for c in cfg["categories"]:
        if c["id"] == "aws-infra":
            c["sources"][0]["max_items_per_run"] = 1
    (temp_env["cfg"]).write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    _patch_fetch(monkeypatch, _load_fixture("feed_rss2.xml"))
    r = ingest.ingest_category("aws-infra", bootstrap_fetch=3)
    assert r.added == 1
    assert r.skipped_quota >= 1


def test_network_failure_isolated_to_source(temp_env, monkeypatch):
    """1 ソース失敗で errors に積まれ、ingest_category 自体は完走する。"""
    def boom(url, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(ingest, "_fetch_with_retry", boom)
    r = ingest.ingest_category("aws-infra")
    assert r.added == 0
    assert len(r.errors) == 1
    assert "network down" in r.errors[0]


def test_dry_run_does_not_write_md_files(temp_env, monkeypatch):
    _patch_fetch(monkeypatch, _load_fixture("feed_rss2.xml"))
    r = ingest.ingest_category("aws-infra", dry_run=True, bootstrap_fetch=3)
    assert r.added == 3
    # md ファイルが書かれていないこと
    cdir = temp_env["content"] / "aws-infra"
    assert not any(cdir.glob("*.md")) if cdir.exists() else True
    # index も書かれていない
    assert not (cdir / ".ingest-index.json").exists() if cdir.exists() else True


def test_atom_feed_ingest(temp_env, monkeypatch):
    _patch_fetch(monkeypatch, _load_fixture("feed_atom.xml"))
    r = ingest.ingest_category("aws-infra", bootstrap_fetch=3)
    assert r.added == 3


def test_rdf_feed_with_guid_fallback_to_link(temp_env, monkeypatch):
    _patch_fetch(monkeypatch, _load_fixture("feed_rdf.xml"))
    r = ingest.ingest_category("aws-infra", bootstrap_fetch=3)
    assert r.added == 3
    # md の frontmatter に source_guid が link になっていること
    cdir = temp_env["content"] / "aws-infra"
    md_files = list(cdir.glob("*.md"))
    assert len(md_files) == 3
    text = md_files[0].read_text(encoding="utf-8")
    assert "source_guid:" in text
    assert "https://example.com/item" in text


def test_md_frontmatter_contains_required_keys(temp_env, monkeypatch):
    _patch_fetch(monkeypatch, _load_fixture("feed_rss2.xml"))
    ingest.ingest_category("aws-infra", bootstrap_fetch=1)
    cdir = temp_env["content"] / "aws-infra"
    md_files = list(cdir.glob("*.md"))
    assert len(md_files) == 1
    text = md_files[0].read_text(encoding="utf-8")
    for key in ("source: rss", "source_guid:", "published_at:", "ingested_at:", "title:"):
        assert key in text, f"missing {key}"


def test_slug_format_yyyy_mm_dd_hash(temp_env, monkeypatch):
    _patch_fetch(monkeypatch, _load_fixture("feed_rss2.xml"))
    ingest.ingest_category("aws-infra", bootstrap_fetch=1)
    cdir = temp_env["content"] / "aws-infra"
    md_files = list(cdir.glob("*.md"))
    name = md_files[0].stem
    parts = name.split("-")
    # YYYY-MM-DD-<10 hex>
    assert len(parts) == 4
    assert len(parts[0]) == 4
    assert len(parts[3]) == 10  # sha1 prefix


def test_ingest_all_skips_inactive(temp_env, monkeypatch):
    """active: false のカテゴリは ingest_all でスキップされる。"""
    cfg = yaml.safe_load(temp_env["cfg"].read_text(encoding="utf-8"))
    for c in cfg["categories"]:
        if c["id"] == "aws-infra":
            c["active"] = False
    temp_env["cfg"].write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    _patch_fetch(monkeypatch, _load_fixture("feed_rss2.xml"))
    out = ingest.ingest_all()
    assert "aws-infra" not in out


def test_rebuild_index_from_md_files(temp_env, monkeypatch):
    """md ファイルから .ingest-index.json を再構築できる。"""
    _patch_fetch(monkeypatch, _load_fixture("feed_rss2.xml"))
    ingest.ingest_category("aws-infra", bootstrap_fetch=3)
    # index を消す
    idx_path = ingest._index_path("aws-infra")
    idx_path.unlink()
    res = ingest.rebuild_index("aws-infra")
    assert res["items"] == 3
    idx = ingest._load_index("aws-infra")
    assert len(idx["items"]) == 3
