"""Rank the live OpenRouter inventory without accidentally selecting paid models.

Review models need tools and at least 256k context. Decisions use their separate
output modality; none of the currently free decision models has 256k context.
Parameter counts are a size heuristic, not a measured quality benchmark. Explicit
model overrides are deliberately left unchanged, including paid/non-OpenRouter IDs.
"""

import json
import math
import re
import urllib.error
import urllib.request
import warnings
from datetime import date
from decimal import Decimal, InvalidOperation

MODELS_URL = "https://openrouter.ai/api/v1/models"
MIN_REVIEW_CONTEXT = 256000
MAX_CATALOG_BYTES = 8 * 1024 * 1024
# Catalog-outage escape hatch, verified 2026-11-08. All use the explicitly free
# route; the caller must still obtain a successful, valid review/decision.
FALLBACK_MODELS = {
    "review": (
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "dots-studio/dots-3-note-preview:free",
        "nvidia/nemotron-3.5-super-vl:free",
    ),
    "decision": ("parallel/decisions-fast:free", "respan/span-01-lite:free"),
}


class ModelSelectionError(ValueError):
    """The catalog supplied no eligible free model."""


def _kind(kind):
    if kind not in FALLBACK_MODELS:
        raise ValueError("model kind must be review or decision")


def _number(value):
    if isinstance(value, bool):
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return number if math.isfinite(number) and number > 0 else 0


def parameter_count(model):
    """Extract documented total size; never treat active parameters as totals.

    Prefer an explicit total, then an unambiguous parameter/dense description,
    then size tokens in the model's own name/ID. Context sizes have K units and
    are never candidates. Unknown sizes sort below known sizes.
    """
    for key in ("parameter_count", "num_parameters"):
        count = _number(model.get(key))
        if count:
            return count
    description = str(model.get("description") or "")
    size = r"(\d+(?:\.\d+)?)\s*([bmt])"
    multiplier = {"m": 1e6, "b": 1e9, "t": 1e12}
    for pattern in (
        size + r"\s+total\b",
        size + r"(?:-parameter\b|\s+parameters\b(?!\s+(?:are\s+)?active\b)|\s+dense\b)",
    ):
        matches = re.findall(pattern, description, re.IGNORECASE)
        if matches:
            count = max(_number(float(n) * multiplier[u.lower()]) for n, u in matches)
            if count:
                return count
    name = " ".join(str(model.get(k) or "") for k in ("name", "id"))
    matches = re.findall(r"(?<![\w.])" + size + r"(?![\w.])", name, re.IGNORECASE)
    return max(
        (_number(float(n) * multiplier[u.lower()]) for n, u in matches), default=0
    )


def _free(model):
    pricing = model.get("pricing")
    if not isinstance(pricing, dict) or not {"prompt", "completion"} <= pricing.keys():
        return False
    # Additional per-request/image/etc charges must also be zero if advertised.
    for value in pricing.values():
        if isinstance(value, bool) or value is None:
            return False
        try:
            price = Decimal(str(value))
        except InvalidOperation:
            return False
        if not price.is_finite() or price != 0:
            return False
    return True


def _eligible(model, kind):
    if not isinstance(model, dict) or not _free(model):
        return False
    identifier = model.get("id")
    if not isinstance(identifier, str) or not re.fullmatch(r"[\w.~:/-]+", identifier):
        return False
    expiration = model.get("expiration_date")
    if expiration:
        try:
            if date.fromisoformat(expiration) <= date.today():
                return False
        except (TypeError, ValueError):
            return False
    architecture = model.get("architecture")
    if not isinstance(architecture, dict):
        return False
    output = architecture.get("output_modalities", [])
    inputs = architecture.get("input_modalities", [])
    if (
        not isinstance(output, list)
        or not isinstance(inputs, list)
        or "text" not in inputs
    ):
        return False
    modality = "text" if kind == "review" else "decisions"
    if modality not in output:
        return False
    endpoint = (
        "/api/v1/chat/completions" if kind == "review" else "/api/alpha/decisions"
    )
    if "endpoints" in model:
        endpoints = model["endpoints"]
        if not isinstance(endpoints, list) or endpoint not in endpoints:
            return False
    if kind == "review":
        parameters = model.get("supported_parameters", [])
        if not isinstance(parameters, list) or "tools" not in parameters:
            return False
        if _number(model.get("context_length")) < MIN_REVIEW_CONTEXT:
            return False
    return True


def rank_candidates(data, kind):
    """Return unique raw OpenRouter IDs, ordered by total size, release, context.

    ``data`` accepts the complete Models API response or its ``data`` list.
    Decisions aliases sharing a canonical slug are deduplicated, preferring the
    explicit :free route. A successful empty/ineligible catalog stays empty.
    """
    _kind(kind)
    models = data.get("data") if isinstance(data, dict) else data
    if not isinstance(models, list):
        raise ModelSelectionError("invalid model catalog")
    eligible = [m for m in models if _eligible(m, kind)]

    def ranking(model):
        return (
            -parameter_count(model),
            -_number(model.get("created")),
            -_number(model.get("context_length")),
            model["id"],
        )

    # Prefer the explicit free route inside each canonical group even if alias
    # metadata differs. Only then rank the distinct underlying models globally.
    eligible.sort(key=lambda m: (not m["id"].endswith(":free"), ranking(m)))
    seen = set()
    result = []
    for model in eligible:
        canonical = model.get("canonical_slug")
        if not isinstance(canonical, str) or not canonical:
            canonical = model["id"]
        if canonical in seen:
            continue
        seen.add(canonical)
        result.append(model)
    result.sort(key=ranking)
    return [model["id"] for model in result]


def get_model_candidates(kind, override=None, *, timeout=5):
    """Read a bounded public catalog, or return an explicit singleton override.

    Outages/malformed catalogs use only the vetted :free IDs above with a warning.
    A valid live catalog with no eligible models fails closed instead of reviving
    delisted models. No API key is needed or sent to this public endpoint.
    """
    _kind(kind)
    if override is not None and not isinstance(override, str):
        raise ModelSelectionError("model override must be a string")
    override = (override or "").strip()
    if override and override.lower() != "auto":
        return [override]
    url = MODELS_URL + ("?output_modalities=decisions" if kind == "decision" else "")
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_CATALOG_BYTES + 1)
        if len(raw) > MAX_CATALOG_BYTES:
            raise ModelSelectionError("model catalog is too large")
        models = rank_candidates(json.loads(raw), kind)
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        warnings.warn(
            f"OpenRouter {kind} catalog unavailable ({type(exc).__name__}); "
            "trying vetted free fallback models",
            RuntimeWarning,
            stacklevel=2,
        )
        return list(FALLBACK_MODELS[kind])
    if not models:
        raise ModelSelectionError(f"no eligible free {kind} models in live catalog")
    return models
