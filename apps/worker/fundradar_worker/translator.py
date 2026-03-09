"""
Shared translation infrastructure for the Fundradar signal pipeline.

Provides:
  - Language detection (Italian, French, English)
  - DeepL translation with automatic quota management and key rotation
  - OpenAI translation fallback
  - In-place signal translation with idempotency (skips already-translated signals)

Primary consumer: scripts/translate_signals.py (pipeline step between rss and filter).
Secondary consumer: scripts/enrich_signals_openai.py (safety-net pass for LLM summaries).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

from fundradar_worker.paths import OPENAI_MODEL
DATA_DIR = PROJECT_ROOT / "data" / "derived"
DEEPL_QUOTA_FILE = DATA_DIR / "deepl_quota_state.json"

# ── Language detection ─────────────────────────────────────────────────────────

_LANG_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ']+")
_IT_STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "da", "del", "della", "dello",
    "dei", "degli", "delle", "nel", "nella", "nello", "nei", "negli", "nelle", "sul", "sulla",
    "sullo", "sui", "sugli", "sulle", "che", "per", "con", "come", "tra", "fra", "e", "ed",
    "o", "ma", "non", "si", "ha", "hanno", "è", "sono", "era", "alla", "alle", "agli", "al",
    "ai", "dopo", "prima", "dal", "dai", "dalle", "dagli", "nella", "dell", "nell", "all",
}
_EN_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "from", "of", "to", "in", "on", "at", "by",
    "as", "that", "this", "is", "are", "was", "were", "has", "have", "had", "will", "would",
    "it", "its", "their", "his", "her", "be", "been", "after", "before", "into", "over", "about",
}
_IT_STRONG_RE = re.compile(
    r"\b(?:annuncia|annunciato|annunciata|chiude|chiuso|chiusa|raccoglie|raccolta|acquisisce|acquisita"
    r"|acquisito|cede|cessione|investe|finanziamento|nomina|partnership|accordo|milioni"
    r"|cartolarizzazione|partecipazione|sottoscritto|sottoscrive)\b",
    re.IGNORECASE,
)
_FR_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "en", "au", "aux",
    "pour", "par", "sur", "avec", "dans", "que", "qui", "se", "est", "sont", "cette",
    "son", "sa", "ses", "leur", "leurs",
}
_FR_STRONG_RE = re.compile(
    r"\b(?:annonce|annoncé|acquiert|acquisition|lève|atteint|franchit|investissement|financement"
    r"|fonds|milliard|million|clôture|closing|réalise|cède|cession)\b",
    re.IGNORECASE,
)
_EN_STRONG_RE = re.compile(
    r"\b(?:announced|announces|closed|closing|raised|acquired|acquires|acquisition|sold|sale|invested"
    r"|investment|appointed|appointment|agreement|partnership|million|debt|financing|launched|launch)\b",
    re.IGNORECASE,
)
_TRANSLATION_NETWORK_ERROR_HINTS = (
    "name or service not known",
    "nodename nor servname",
    "temporary failure in name resolution",
    "failed to resolve",
    "connection error",
    "connection failed",
    "max retries exceeded",
    "connecterror",
    "dns",
)


def is_network_error_message(message: str) -> bool:
    text = (message or "").lower()
    return any(hint in text for hint in _TRANSLATION_NETWORK_ERROR_HINTS)


def _language_token_scores(text: str) -> tuple[int, int, int]:
    words = [
        w.lower().replace("\u2019", "'").strip("'")
        for w in _LANG_WORD_RE.findall(text or "")
    ]
    if not words:
        return 0, 0, 0
    it_score = sum(1 for w in words if w in _IT_STOPWORDS)
    en_score = sum(1 for w in words if w in _EN_STOPWORDS)
    lowered = (text or "").lower()
    if _IT_STRONG_RE.search(lowered):
        it_score += 2
    if _EN_STRONG_RE.search(lowered):
        en_score += 2
    if re.search(r"[àèéìòù]", lowered):
        it_score += 1
    return it_score, en_score, len(words)


def is_italian_text(text: str) -> bool:
    """Detect if text is predominantly Italian (robust for short finance snippets).

    Tuned for PE/VC signal text which often contains Italian proper nouns (fund names,
    company names, newspaper names) and accented characters inside otherwise-English text.
    The accent-only check requires Italian dominance to avoid false positives on names
    like Demattè, Chloé, Aksìa. Short texts (< 4 tokens) like "Corriere della Sera"
    require at least 2 Italian markers to avoid triggering on proper noun fragments.
    """
    if not text:
        return False
    it_score, en_score, token_count = _language_token_scores(text)
    if token_count < 4:
        # Very short text: require stronger evidence (2+ Italian markers, no English)
        # Prevents false positives on "PM&Partners I", "Corriere della Sera"
        return it_score >= 2 and en_score == 0
    if it_score >= 2 and it_score > en_score:
        return True
    if it_score >= 3 and en_score == 0:
        return True
    # Accented characters strengthen Italian detection only when Italian already dominates.
    # Prevents false positives on English text with accented proper nouns (Demattè, Chloé, Aksìa).
    if re.search(r"[àèéìòù]", text) and it_score >= 2 and it_score > en_score:
        return True
    return False


def is_french_text(text: str) -> bool:
    """Detect if text is predominantly French."""
    if not text:
        return False
    words = [w.lower().strip("'") for w in _LANG_WORD_RE.findall(text)]
    if len(words) < 4:
        return False
    fr_score = sum(1 for w in words if w in _FR_STOPWORDS)
    en_score = sum(1 for w in words if w in _EN_STOPWORDS)
    lowered = text.lower()
    if _FR_STRONG_RE.search(lowered):
        fr_score += 2
    if _EN_STRONG_RE.search(lowered):
        en_score += 2
    if re.search(r"[êîûôœ]", lowered):
        fr_score += 2
    return fr_score >= 2 and fr_score > en_score


# ── DeepL quota management ─────────────────────────────────────────────────────

def _load_quota_state() -> dict:
    if DEEPL_QUOTA_FILE.exists():
        try:
            with open(DEEPL_QUOTA_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_quota_state(state: dict) -> None:
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(DEEPL_QUOTA_FILE.parent), suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, str(DEEPL_QUOTA_FILE))
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def get_available_deepl_keys() -> list[tuple[str, str]]:
    """Return (env_name, api_key) pairs for DeepL keys not exhausted this month.

    Supports DEEPL_API_KEY and DEEPL_API_KEY_2. Exhausted keys are auto-skipped
    until the next calendar month.
    """
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    state = _load_quota_state()
    keys = []
    for env_name in ("DEEPL_API_KEY", "DEEPL_API_KEY_2"):
        key = os.environ.get(env_name, "").strip()
        if not key:
            continue
        key_state = state.get(env_name) or {}
        if key_state.get("exhausted_month") == current_month:
            print(f"  DeepL {env_name}: quota exhausted for {current_month}, skipping")
            continue
        keys.append((env_name, key))
    return keys


def mark_deepl_key_exhausted(env_name: str) -> None:
    """Mark a DeepL key as quota-exhausted for this calendar month.

    If ALL configured keys are now exhausted, sends a Telegram alert.
    """
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    state = _load_quota_state()
    state[env_name] = {
        "exhausted_month": current_month,
        "exhausted_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_quota_state(state)
    print(f"  DeepL {env_name}: quota exhausted — marked for month {current_month}")

    all_exhausted = all(
        (state.get(k) or {}).get("exhausted_month") == current_month
        for k in ("DEEPL_API_KEY", "DEEPL_API_KEY_2")
        if os.environ.get(k, "").strip()
    )
    if not all_exhausted:
        return

    print("  ⚠ All DeepL keys exhausted — sending Telegram alert")
    try:
        from fundradar_worker.alerting import AlertConfig, AlertManager, Alert
        config = AlertConfig.from_env()
        if not config.telegram_enabled:
            return
        manager = AlertManager(config)
        manager.add_alert(Alert(
            title="DeepL quota exhausted — falling back to Azure/OpenAI",
            message=(
                f"Both DeepL keys hit their monthly quota ({current_month}).\n"
                "Translation will fall back to Azure Translator (free, 2M chars/month), "
                "then OpenAI (paid) if Azure also fails.\n"
                "Add a new key to DEEPL_API_KEY or DEEPL_API_KEY_2 in .env to avoid costs."
            ),
            level="warning",
            source="deepl_quota",
        ))
        manager.send_pending_alerts()
    except Exception as e:
        print(f"  Could not send DeepL exhaustion alert: {e}")


# ── Translation helpers ────────────────────────────────────────────────────────

DEEPL_BATCH_TIMEOUT = 30  # seconds per DeepL batch call


def translate_batch_with_deepl(texts: list[str], api_key: str) -> list[str]:
    """Translate a batch of texts to English via DeepL.

    Raises deepl.exceptions.QuotaExceededException when monthly quota is hit.
    Raises deepl.exceptions.AuthorizationException on invalid key.
    Raises ImportError if the deepl package is not installed.
    Raises TimeoutError if the call takes longer than DEEPL_BATCH_TIMEOUT.
    """
    import deepl  # optional dependency
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

    def _call():
        translator = deepl.Translator(api_key)
        return translator.translate_text(texts, target_lang="EN-US")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_call)
        try:
            results = future.result(timeout=DEEPL_BATCH_TIMEOUT)
        except FutureTimeout:
            future.cancel()
            raise TimeoutError(f"DeepL batch call timed out after {DEEPL_BATCH_TIMEOUT}s")
    if isinstance(results, list):
        return [r.text for r in results]
    return [results.text]


def translate_batch_with_azure(texts: list[str], api_key: str, region: str | None = None) -> list[str]:
    """Translate a batch of texts to English via Azure Translator REST API.

    Free tier: 2M chars/month. Uses the global endpoint by default.
    Raises requests.HTTPError on API errors.
    """
    import requests

    url = "https://api.cognitive.microsofttranslator.com/translate"
    params = {"api-version": "3.0", "to": "en"}
    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Content-Type": "application/json",
    }
    if region:
        headers["Ocp-Apim-Subscription-Region"] = region

    body = [{"Text": t} for t in texts]
    resp = requests.post(url, params=params, headers=headers, json=body, timeout=30)
    resp.raise_for_status()

    results = resp.json()
    return [item["translations"][0]["text"] for item in results]


def translate_text_with_openai(client: Any, text: str) -> str:
    """Translate a single non-English PE/VC signal text to English via OpenAI."""
    if not text:
        return ""
    prompt = (
        "Translate the following PE/VC news text into concise, factual English. "
        "The source may be Italian, French, or another European language. "
        "Preserve names, numbers, dates, currencies, and deal terms exactly. "
        "Return only the translated text — no quotes, no explanation.\n\n"
        f"{text}"
    )
    max_completion_tokens = 512
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise financial translator. Return only the translated text."},
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=max_completion_tokens,
            )
            out = ((resp.choices[0].message.content or "").strip() if resp.choices else "").strip()
            if out.startswith("```"):
                out = out.strip("`").replace("text", "", 1).strip()
            return re.sub(r"\s{2,}", " ", out).strip()
        except Exception as e:
            err_text = str(e).lower()
            if ("max_tokens" in err_text or "output limit" in err_text or "maxtokens" in err_text) and attempt == 0:
                max_completion_tokens = 1024
                continue
            raise
    return ""


def translate_batch_with_openai(client: Any, texts: list[str]) -> list[str]:
    """Translate a batch of non-English PE/VC texts to English in a single OpenAI call."""
    if not texts:
        return []
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    prompt = (
        f"Translate the following {len(texts)} PE/VC news texts to English. "
        "Each is numbered. Source may be Italian, French, or another European language. "
        "Preserve names, numbers, currencies, and deal terms exactly. "
        "Return a JSON array of translated strings in the same order.\n\n"
        f"{numbered}"
    )
    max_completion_tokens = 2000
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise financial translator. Return only a JSON array of translated strings."},
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=max_completion_tokens,
            )
            raw = (resp.choices[0].message.content or "").strip() if resp.choices else ""
            if raw.startswith("```"):
                raw = raw.strip("`").lstrip("json").strip()
            result = json.loads(raw)
            if isinstance(result, list) and len(result) == len(texts):
                return [re.sub(r"\s{2,}", " ", str(r)).strip() for r in result]
        except Exception as e:
            err_text = str(e).lower()
            if ("max_tokens" in err_text or "output limit" in err_text or "maxtokens" in err_text) and attempt == 0:
                max_completion_tokens = 4000
                print(f"  Translation batch output limit, retrying with higher tokens...")
                continue
            print(f"  Translation batch error (OpenAI): {e}")
            break
    # Fall back to individual translations
    return [translate_text_with_openai(client, t) for t in texts]


# ── Main entry point ───────────────────────────────────────────────────────────

# Fields to translate and where to store the original
_TEXT_FIELDS: list[tuple[str, str]] = [
    ("enriched_summary", "enriched_summary_original"),
    ("what_changed", "what_changed_original"),
    ("title", "title_original"),
]


def translate_signals_inplace(
    signals: list[dict],
    openai_api_key: str | None = None,
    azure_translator_key: str | None = None,
    azure_translator_region: str | None = None,
    slugs_filter: str | None = None,
) -> dict[str, Any]:
    """Translate non-English signal text fields to English in-place.

    Uses DeepL (primary, cheap) → Azure Translator (fallback, 2M chars/month free)
    → OpenAI (last resort, paid).
    Idempotent: signals whose *_original fields are already set and whose
    current text looks English are skipped to avoid re-translation.

    Args:
        signals: list of signal dicts, modified in-place.
        openai_api_key: optional override; falls back to OPENAI_API_KEY env var.
        azure_translator_key: optional override; falls back to AZURE_TRANSLATOR_KEY env var.
        azure_translator_region: optional Azure region (not needed for free tier global endpoint).
        slugs_filter: comma-separated fund slugs for partial runs (for logging only).

    Returns:
        Stats dict with keys: italian_fields_detected, signals_needing_translation,
        translated_fields, translated_signals, unresolved_fields, network_error_count,
        skipped_reason, sample_errors.
    """
    openai_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
    azure_key = azure_translator_key or os.environ.get("AZURE_TRANSLATOR_KEY", "")
    azure_region = azure_translator_region or os.environ.get("AZURE_TRANSLATOR_REGION") or None
    stats: dict[str, Any] = {
        "italian_fields_detected": 0,
        "signals_needing_translation": 0,
        "translated_fields": 0,
        "translated_signals": 0,
        "unresolved_fields": 0,
        "openai_configured": bool(openai_key),
        "openai_translation_errors": 0,
        "network_error_count": 0,
        "sample_errors": [],
        "skipped_reason": "",
    }

    def _record_error(message: str) -> None:
        msg = (message or "").strip()
        if is_network_error_message(msg):
            stats["network_error_count"] += 1
        if msg and len(stats["sample_errors"]) < 3:
            stats["sample_errors"].append(msg[:280])

    # Collect (signal, field, orig_field, text) tuples that need translation
    to_translate: list[tuple[dict, str, str, str]] = []
    signals_needing_work: set[int] = set()
    for idx, s in enumerate(signals):
        for field, orig_field in _TEXT_FIELDS:
            text = s.get(field) or ""
            if not text:
                continue
            # Skip if already translated and current text is English
            if s.get(orig_field) and not (is_italian_text(text) or is_french_text(text)):
                continue
            if is_italian_text(text) or is_french_text(text):
                to_translate.append((s, field, orig_field, text))
                signals_needing_work.add(idx)

    stats["italian_fields_detected"] = len(to_translate)
    stats["signals_needing_translation"] = len(signals_needing_work)

    if not to_translate:
        print("  No non-English fields to translate", flush=True)
        return stats

    # Determine providers
    deepl_keys = get_available_deepl_keys()
    has_azure = bool(azure_key)
    has_openai = bool(openai_key)
    stats["deepl_keys_available"] = len(deepl_keys)
    stats["azure_configured"] = has_azure

    if not deepl_keys and not has_azure and not has_openai:
        print(f"  Skipping translation: no provider configured ({len(to_translate)} fields pending)")
        stats["unresolved_fields"] = len(to_translate)
        stats["skipped_reason"] = "no_provider"
        return stats

    provider_desc = ([f"DeepL ({len(deepl_keys)} key(s))"] if deepl_keys else []) + (["Azure Translator"] if has_azure else []) + (["OpenAI fallback"] if has_openai else [])
    scope = f" [{slugs_filter}]" if slugs_filter else ""
    print(f"  Translating {len(to_translate)} non-English fields across {len(signals_needing_work)} signals via {', '.join(provider_desc)}{scope}...", flush=True)

    openai_client: Any = None
    if has_openai:
        try:
            from openai import OpenAI
            openai_client = OpenAI(api_key=openai_key, timeout=90.0)
        except ImportError:
            print("  openai package not installed — DeepL-only mode")

    translated_fields = 0
    unresolved: list[tuple[dict, str, str, str]] = []

    BATCH_SIZE = 5
    total_batches = (len(to_translate) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(to_translate), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch = to_translate[i: i + BATCH_SIZE]
        texts = [item[3] for item in batch]
        translated_texts = None

        if batch_num % 10 == 1 or batch_num == total_batches:
            print(f"  Batch {batch_num}/{total_batches} ({translated_fields} translated so far)...", flush=True)

        # Try DeepL keys in order
        for env_name, deepl_key in list(deepl_keys):
            try:
                translated_texts = translate_batch_with_deepl(texts, deepl_key)
                break
            except ImportError:
                print("  deepl SDK not installed — falling back to OpenAI for all batches")
                deepl_keys = []
                break
            except Exception as e:
                err_name = type(e).__name__
                if "QuotaExceeded" in err_name or "quota" in str(e).lower():
                    mark_deepl_key_exhausted(env_name)
                    deepl_keys = [k for k in deepl_keys if k[0] != env_name]
                    print(f"  DeepL quota exceeded for {env_name} — trying next provider", flush=True)
                elif "Authorization" in err_name or "auth" in str(e).lower():
                    print(f"  DeepL auth error for {env_name}: {e} — skipping key", flush=True)
                    deepl_keys = [k for k in deepl_keys if k[0] != env_name]
                elif isinstance(e, TimeoutError):
                    print(f"  DeepL timeout for {env_name} — falling back to next provider", flush=True)
                    break
                else:
                    print(f"  DeepL error ({env_name}): {e} — falling back to next provider", flush=True)
                    break  # non-quota errors: try next provider this batch

        # Fall back to Azure Translator
        if translated_texts is None and has_azure:
            try:
                translated_texts = translate_batch_with_azure(texts, azure_key, azure_region)
            except Exception as e:
                err_str = str(e).lower()
                if "401" in err_str or "403" in err_str:
                    print(f"  Azure Translator auth error: {e} — disabling for this run")
                    has_azure = False
                elif "429" in err_str or "quota" in err_str:
                    print(f"  Azure Translator quota exceeded — disabling for this run")
                    has_azure = False
                else:
                    print(f"  Azure Translator error: {e} — falling back to OpenAI")
                _record_error(f"Azure Translator error: {e}")

        # Fall back to OpenAI
        if translated_texts is None:
            if openai_client:
                try:
                    translated_texts = translate_batch_with_openai(openai_client, texts)
                except Exception as e:
                    print(f"  Translation batch error (OpenAI): {e}")
                    stats["openai_batch_errors"] = stats.get("openai_batch_errors", 0) + 1
                    _record_error(f"OpenAI batch translation error: {e}")
                    unresolved.extend(batch)
                    time.sleep(0.5)
                    continue
            else:
                unresolved.extend(batch)
                continue

        for (s, field, orig_field, original), translated_text in zip(batch, translated_texts):
            if not translated_text:
                unresolved.append((s, field, orig_field, original))
                continue
            if translated_text == original:
                # Translator detected text is already English — trust it, don't retry.
                continue
            s[orig_field] = original
            s[field] = translated_text
            translated_fields += 1
        time.sleep(0.2)

    # Retry unresolved fields via Azure (batch), then OpenAI (individual)
    if unresolved and has_azure:
        print(f"  Retrying {len(unresolved)} unresolved fields via Azure Translator...", flush=True)
        azure_unresolved: list[tuple[dict, str, str, str]] = []
        for ri in range(0, len(unresolved), BATCH_SIZE):
            azure_batch = unresolved[ri: ri + BATCH_SIZE]
            azure_texts = [item[3] for item in azure_batch]
            try:
                azure_translated = translate_batch_with_azure(azure_texts, azure_key, azure_region)
            except Exception as e:
                err_str = str(e).lower()
                if "401" in err_str or "403" in err_str or "429" in err_str or "quota" in err_str:
                    print(f"  Azure Translator error: {e} — disabling for this run", flush=True)
                    has_azure = False
                    azure_unresolved.extend(azure_batch)
                    azure_unresolved.extend(unresolved[ri + BATCH_SIZE:])
                    break
                else:
                    print(f"  Azure Translator error: {e}", flush=True)
                    azure_unresolved.extend(azure_batch)
                    continue
            for (s, field, orig_field, original), translated_text in zip(azure_batch, azure_translated):
                if not translated_text:
                    azure_unresolved.append((s, field, orig_field, original))
                    continue
                if translated_text == original:
                    # Already English — trust the translator, don't forward to OpenAI.
                    continue
                s[orig_field] = original
                s[field] = translated_text
                translated_fields += 1
        azure_resolved = len(unresolved) - len(azure_unresolved)
        if azure_resolved:
            print(f"  Azure resolved {azure_resolved}/{len(unresolved)} fields", flush=True)
        unresolved = azure_unresolved

    if unresolved and openai_client:
        print(f"  Retrying {len(unresolved)} unresolved fields via OpenAI...", flush=True)
        still_unresolved: list[tuple[dict, str, str, str]] = []
        for s, field, orig_field, original in unresolved:
            try:
                translated_text = translate_text_with_openai(openai_client, original)
            except Exception as e:
                stats["openai_translation_errors"] += 1
                _record_error(f"OpenAI translation error: {e}")
                still_unresolved.append((s, field, orig_field, original))
                continue
            if not translated_text or translated_text == original:
                still_unresolved.append((s, field, orig_field, original))
                continue
            s[orig_field] = original
            s[field] = translated_text
            translated_fields += 1
        openai_resolved = len(unresolved) - len(still_unresolved)
        if openai_resolved:
            print(f"  OpenAI resolved {openai_resolved}/{len(unresolved)} fields", flush=True)
        unresolved = still_unresolved

    translated_signals = sum(
        1 for s in signals
        if any(s.get(orig) for _, orig in _TEXT_FIELDS)
    )
    stats["translated_fields"] = translated_fields
    stats["translated_signals"] = translated_signals
    stats["unresolved_fields"] = len(unresolved)
    # Include details of unresolved signals for actionable alerting
    stats["unresolved_details"] = [
        {
            "fund_slug": s.get("fund_slug", "?"),
            "field": field,
            "text": original[:120],
        }
        for s, field, orig_field, original in unresolved
    ]
    print(f"  Translated {translated_fields} fields across {len(signals_needing_work)} signals")
    return stats
