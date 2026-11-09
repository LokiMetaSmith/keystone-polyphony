import copy
import io
import json
import urllib.error

import pytest

from src.liminal_bridge import model_picker as picker


def model(identifier="vendor/model-40b:free", **updates):
    result = {
        "id": identifier,
        "name": identifier,
        "created": 100,
        "context_length": 256000,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["tools"],
    }
    result.update(updates)
    return result


@pytest.mark.parametrize(
    "entry,expected",
    [
        (model(description="55B active parameters out of 550B total"), 550e9),
        (model(description="25.2B total parameters, 3.8B activate per token"), 25.2e9),
        (model(description="A 30.7B dense multimodal model with 256K context"), 30.7e9),
        (model(description="A compact 1.7B-parameter text model"), 1.7e9),
        (model("vendor/model-550b-a55b:free"), 550e9),
        (model("vendor/model-1.2t-a42b:free"), 1.2e12),
        (
            model("vendor/unknown", description="1M context and 55B active parameters"),
            0,
        ),
        (model("vendor/unknown", description="55B parameters are active"), 0),
        (model("vendor/unknown", description="1M context and 256K tokens"), 0),
        (model("vendor/unknown", parameter_count=123), 123),
        (model("vendor/unknown", description="9" * 400 + "B total parameters"), 0),
        (model("vendor/" + "9" * 400 + "b"), 0),
    ],
)
def test_documented_total_parameters_not_context_or_active(entry, expected):
    assert picker.parameter_count(entry) == expected


def test_ranking_size_then_newest_then_context_and_unknown_last():
    entries = [
        model("vendor/unknown", created=9999, context_length=1000000),
        model("vendor/small-30b", created=9999),
        model("vendor/old-550b", created=1),
        model("vendor/new-550b", created=2),
        model("vendor/wide-550b", created=2, context_length=1000000),
    ]
    assert picker.rank_candidates({"data": entries}, "review") == [
        "vendor/wide-550b",
        "vendor/new-550b",
        "vendor/old-550b",
        "vendor/small-30b",
        "vendor/unknown",
    ]


@pytest.mark.parametrize(
    "price",
    ["0.01", "-1", "NaN", "Infinity", "oops", None, True, {}, []],
)
def test_reject_any_pricing_charge_or_invalid_price(price):
    entry = model(pricing={"prompt": "0", "completion": "0", "request": price})
    assert picker.rank_candidates([entry], "review") == []


@pytest.mark.parametrize(
    "updates",
    [
        {"pricing": {}},
        {"pricing": {"prompt": "0"}},
        {"context_length": 255999},
        {"context_length": True},
        {"context_length": "NaN"},
        {"supported_parameters": []},
        {
            "architecture": {
                "input_modalities": ["text"],
                "output_modalities": ["audio"],
            }
        },
        {
            "architecture": {
                "input_modalities": ["image"],
                "output_modalities": ["text"],
            }
        },
        {"expiration_date": "2000-01-01"},
        {"expiration_date": "unknown"},
        {"endpoints": []},
        {"endpoints": "/api/v1/chat/completions"},
        {"id": "bad\nmodel"},
    ],
)
def test_review_eligibility_fails_closed(updates):
    assert picker.rank_candidates([model(**updates)], "review") == []


def test_decisions_have_separate_modality_and_no_chat_context_minimum():
    decision = model(
        "vendor/decision:free",
        context_length=32000,
        architecture={"input_modalities": ["text"], "output_modalities": ["decisions"]},
        supported_parameters=[],
        endpoints=["/api/alpha/decisions"],
    )
    assert picker.rank_candidates([model(), decision], "decision") == [decision["id"]]
    assert picker.rank_candidates([decision], "review") == []
    unknown_context = copy.deepcopy(decision)
    unknown_context["context_length"] = 0
    assert picker.rank_candidates([unknown_context], "decision") == [decision["id"]]


def test_same_canonical_model_only_attempted_once_preferring_free_route():
    base = model("vendor/model", canonical_slug="vendor/model-20261108")
    free = model("vendor/model:free", canonical_slug=base["canonical_slug"])
    assert picker.rank_candidates([base, free, free], "review") == [free["id"]]


def test_free_route_preference_precedes_alias_metadata_ranking():
    base = model(
        "vendor/model-550b", canonical_slug="vendor/model-20261108", created=200
    )
    free = model(
        "vendor/model-40b:free", canonical_slug=base["canonical_slug"], created=100
    )
    other = model("vendor/other-100b", created=150)
    assert picker.rank_candidates([base, free, other], "review") == [
        other["id"],
        free["id"],
    ]


def test_explicit_override_does_not_fetch_or_rewrite(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("explicit override fetched catalog")

    monkeypatch.setattr(picker.urllib.request, "urlopen", fail)
    assert picker.get_model_candidates("review", " paid/model ") == ["paid/model"]
    assert picker.get_model_candidates("decision", "typesafe/jev-paid") == [
        "typesafe/jev-paid"
    ]


def fake_catalog(monkeypatch, data):
    calls = []

    def fetch(request, *, timeout):
        calls.append((request, timeout))
        return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr(picker.urllib.request, "urlopen", fetch)
    return calls


def test_public_catalog_bounded_no_credentials(monkeypatch):
    calls = fake_catalog(monkeypatch, {"data": [model()]})
    assert picker.get_model_candidates("review", "auto", timeout=2) == [model()["id"]]
    request, timeout = calls[0]
    assert request.full_url == picker.MODELS_URL
    assert request.get_header("Authorization") is None
    assert timeout == 2


def test_decision_catalog_filter(monkeypatch):
    fake_catalog(monkeypatch, {"data": []})
    captured = []

    def unavailable(request, **kwargs):
        captured.append(request.full_url)
        raise urllib.error.URLError("outage")

    monkeypatch.setattr(picker.urllib.request, "urlopen", unavailable)
    with pytest.warns(RuntimeWarning, match="vetted free fallback"):
        result = picker.get_model_candidates("decision")
    assert captured == [picker.MODELS_URL + "?output_modalities=decisions"]
    assert result == list(picker.FALLBACK_MODELS["decision"])
    assert all(identifier.endswith(":free") for identifier in result)


def test_successful_empty_catalog_never_revives_retired_static_models(monkeypatch):
    fake_catalog(
        monkeypatch, {"data": [model(pricing={"prompt": "1", "completion": "1"})]}
    )
    with pytest.raises(picker.ModelSelectionError, match="no eligible free"):
        picker.get_model_candidates("review")


@pytest.mark.parametrize("catalog", [b"bad json", b"{}", b"x" * 64])
def test_malformed_and_oversized_catalog_uses_only_vetted_free_ids(
    monkeypatch, catalog
):
    monkeypatch.setattr(picker, "MAX_CATALOG_BYTES", 32)
    monkeypatch.setattr(
        picker.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(catalog)
    )
    with pytest.warns(RuntimeWarning):
        result = picker.get_model_candidates("review")
    assert result == list(picker.FALLBACK_MODELS["review"])
    assert len(result) <= 3
    assert all(identifier.endswith(":free") for identifier in result)


def test_invalid_kind_never_fetches():
    with pytest.raises(ValueError, match="kind"):
        picker.get_model_candidates("chat")
