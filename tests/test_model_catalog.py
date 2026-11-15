# -*- coding: utf-8 -*-
"""آزمون‌های کاتالوگ و رتبه‌بندیِ مدل‌های رایگان.

این تست‌ها **شبکه نمی‌زنند**: دادهٔ خامِ OpenRouter به‌صورتِ fixture در
فایل است. اگر به شبکه وابسته بودند، با هر تغییرِ فهرستِ مدل‌ها می‌شکستند و
سیگنالِ واقعی را از دست می‌دادند.
"""
from __future__ import annotations

import pytest

from ai.model_catalog import (
    MIN_CONTEXT_TOKENS,
    is_free,
    is_text_model,
    rank_models,
    score_model,
)


def _entry(
    model_id="vendor/model:free",
    *,
    context=200_000,
    json_mode=True,
    reasoning=True,
    intelligence=None,
    moderated=False,
    created=None,
    output_modalities=("text",),
    pricing=None,
):
    params = []
    if json_mode:
        params.append("response_format")
    if reasoning:
        params.append("reasoning")
    benchmarks = {}
    if intelligence is not None:
        benchmarks["artificial_analysis"] = {"intelligence_index": intelligence}
    return {
        "id": model_id,
        "name": model_id,
        "context_length": context,
        "supported_parameters": params,
        "benchmarks": benchmarks,
        "top_provider": {"is_moderated": moderated},
        "created": created if created is not None else 1_700_000_000,
        "pricing": pricing or {"prompt": "0", "completion": "0"},
        "architecture": {
            "output_modalities": list(output_modalities),
            "modality": "text+image->text",
        },
    }


# ---------------------------------------------------------------------------
# رایگان بودن
# ---------------------------------------------------------------------------
def test_free_by_id_suffix():
    assert is_free(_entry("foo/bar:free", pricing={"prompt": "0.5"})) is True


def test_free_by_zero_pricing():
    assert is_free(_entry("foo/bar", pricing={"prompt": "0", "completion": "0"})) is True


def test_paid_model_rejected():
    assert is_free(_entry("foo/bar", pricing={"prompt": "0.0001", "completion": "0"})) is False


def test_missing_pricing_is_not_free():
    assert is_free({"id": "foo/bar"}) is False


# ---------------------------------------------------------------------------
# فیلترِ خروجیِ متنی
# ---------------------------------------------------------------------------
def test_audio_model_is_rejected():
    """مدلِ موسیقی هم متن تولید می‌کند، ولی برای آزمون بی‌فایده است."""
    assert is_text_model(_entry(output_modalities=("text", "audio"))) is False


def test_image_output_rejected():
    assert is_text_model(_entry(output_modalities=("text", "image"))) is False


def test_pure_text_model_accepted():
    assert is_text_model(_entry(output_modalities=("text",))) is True


def test_modality_string_fallback():
    entry = _entry()
    entry["architecture"] = {"modality": "text+image->text+audio"}
    assert is_text_model(entry) is False


# ---------------------------------------------------------------------------
# امتیازدهی
# ---------------------------------------------------------------------------
def test_json_mode_outweighs_everything():
    """مدلِ بدونِ JSON نباید از مدلِ با JSON جلو بزند، حتی با شاخصِ هوشِ بالاتر."""
    with_json = score_model(_entry("a/with-json:free", json_mode=True, intelligence=10))
    without_json = score_model(_entry("b/no-json:free", json_mode=False, intelligence=60))
    assert with_json.score > without_json.score


def test_higher_intelligence_scores_higher():
    low = score_model(_entry("a/low:free", intelligence=10))
    high = score_model(_entry("b/high:free", intelligence=40))
    assert high.score > low.score


def test_moderated_model_penalized():
    plain = score_model(_entry("a/plain:free"))
    moderated = score_model(_entry("b/moderated:free", moderated=True))
    assert moderated.score < plain.score


def test_large_context_bonus():
    small = score_model(_entry("a/small:free", context=MIN_CONTEXT_TOKENS))
    large = score_model(_entry("b/large:free", context=500_000))
    assert large.score > small.score


def test_router_penalized():
    real = score_model(_entry("vendor/model:free"))
    router = score_model(_entry("openrouter/free"))
    assert router.score < real.score


def test_reasons_explain_the_score():
    model = score_model(_entry(json_mode=True, intelligence=30, context=500_000))
    assert any("JSON" in r for r in model.reasons)
    assert any("هوش" in r for r in model.reasons)


# ---------------------------------------------------------------------------
# رتبه‌بندی
# ---------------------------------------------------------------------------
def test_ranking_is_stable_and_complete():
    entries = [
        _entry("a/one:free", intelligence=10),
        _entry("b/two:free", intelligence=40),
        _entry("c/three:free", intelligence=25),
    ]
    ranked = rank_models(entries)
    assert [m.id for m in ranked] == ["b/two:free", "c/three:free", "a/one:free"]
    assert [m.rank for m in ranked] == [1, 2, 3]


def test_ranking_puts_non_json_models_last():
    entries = [
        _entry("a/json:free", json_mode=True),
        _entry("b/nojson:free", json_mode=False, intelligence=50),
    ]
    ranked = rank_models(entries)
    assert ranked[0].id == "a/json:free"


def test_ranking_excludes_non_text_models():
    entries = [
        _entry("a/music:free", output_modalities=("text", "audio")),
        _entry("b/text:free"),
    ]
    ranked = rank_models(entries)
    assert [m.id for m in ranked] == ["b/text:free"]


def test_ranking_excludes_paid_models():
    entries = [
        _entry("a/paid", pricing={"prompt": "0.01", "completion": "0.02"}),
        _entry("b/free:free"),
    ]
    ranked = rank_models(entries)
    assert [m.id for m in ranked] == ["b/free:free"]


def test_ranking_empty_input():
    assert rank_models([]) == []


def test_ranking_survives_malformed_entries():
    """خروجیِ API می‌تواند ناقص باشد؛ رتبه‌بندی نباید بشکند."""
    entries = [None, {}, {"id": ""}, _entry("ok/model:free")]  # type: ignore[list-item]
    ranked = rank_models(entries)
    assert [m.id for m in ranked] == ["ok/model:free"]
