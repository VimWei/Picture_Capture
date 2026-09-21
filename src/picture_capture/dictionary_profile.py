from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json
import re


PROFILE_FILENAME = "dictionary_profile.json"
PROFILE_FORMAT_V2 = "picture-capture-dictionary-profile-v2"
PROFILE_LIBRARY_FORMAT_V2 = "picture-capture-profile-library-v2"
DEFAULT_PROFILE_ID = "latin_structured_symbols"


@dataclass(frozen=True, slots=True)
class ProfileExample:
    dictionary: str
    image: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class DictionaryProfilePreset:
    key: str
    display_name: str
    family: str
    description: str
    examples: tuple[ProfileExample, ...]
    supported_languages: tuple[str, ...]
    default_language: str
    default_paddle_language: str
    paddle_language_by_language: dict[str, str]
    parser_modes: tuple[str, ...]
    settings: dict[str, Any]
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DictionaryProfile:
    """Resolved dictionary grammar + layout metadata for one OCR run.

    ``DictionaryProfile`` remains the lightweight object consumed by the OCR
    parser.  v2 adds a stable layout preset key and parser modes while keeping
    the v1 grammar fields intact for project compatibility.
    """

    name: str
    pos_labels: tuple[str, ...]
    usage_labels: tuple[str, ...]
    domain_labels: tuple[str, ...]
    relation_labels: tuple[str, ...]
    internal_leading_symbols: tuple[str, ...]
    entry_leading_symbols: tuple[str, ...]
    symbol_meanings: dict[str, str]
    key: str = DEFAULT_PROFILE_ID
    family: str = "latin_structured_symbols"
    parser_modes: tuple[str, ...] = ("latin",)
    description: str = ""
    examples: tuple[ProfileExample, ...] = ()

    @property
    def metadata_labels(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.usage_labels + self.domain_labels))

    def pos_regex(self) -> str:
        # Longer labels must win over their prefixes (s.amb. before s.).
        alternatives = sorted(self.pos_labels, key=len, reverse=True)
        if not alternatives:
            # Never match when the active profile deliberately has no POS system.
            return r"(?!)"
        return r"(?:" + "|".join(_label_to_regex(value) for value in alternatives) + r")"

    def uses_parser(self, name: str) -> bool:
        return name in self.parser_modes


def _label_to_regex(value: str) -> str:
    pieces: list[str] = []
    for char in value.strip():
        if char.isspace():
            pieces.append(r"\s*")
        elif char == ".":
            pieces.append(r"\.?" )
        elif char == "/":
            pieces.append(r"\s*/\s*")
        else:
            pieces.append(re.escape(char))
    return "".join(pieces)


def _base_language(language: str | None) -> str:
    text = str(language or "").strip()
    if not text:
        return ""
    return next((part.strip() for part in text.split("+") if part.strip()), "")


def _values(block: dict[str, Any], name: str) -> tuple[str, ...]:
    return tuple(str(x).strip() for x in block.get(name, []) if str(x).strip())


def _grammar_profile_from_blocks(
    *,
    name: str,
    key: str,
    family: str,
    parser_modes: Iterable[str],
    description: str,
    examples: tuple[ProfileExample, ...],
    abbreviations: dict[str, Any],
    symbols: dict[str, Any],
) -> DictionaryProfile:
    return DictionaryProfile(
        name=name,
        pos_labels=_values(abbreviations, "part_of_speech"),
        usage_labels=_values(abbreviations, "usage_and_region"),
        domain_labels=_values(abbreviations, "subject_domains"),
        relation_labels=_values(abbreviations, "article_relations"),
        internal_leading_symbols=tuple(str(x) for x in symbols.get("internal_not_new_entry", [])),
        entry_leading_symbols=tuple(str(x) for x in symbols.get("entry_markers", [])),
        symbol_meanings={str(k): str(v) for k, v in (symbols.get("meanings", {}) or {}).items()},
        key=key,
        family=family,
        parser_modes=tuple(str(x) for x in parser_modes if str(x)),
        description=description,
        examples=examples,
    )


def _profile_from_legacy_dict(raw: dict[str, Any]) -> DictionaryProfile:
    abbreviations = raw.get("abbreviations", {}) or {}
    symbols = raw.get("symbols", {}) or {}
    return _grammar_profile_from_blocks(
        name=str(raw.get("name") or "Custom dictionary profile"),
        key="legacy_custom",
        family="legacy_custom",
        parser_modes=("latin", "cjk_bracketed", "cjk_single_visual"),
        description=str(raw.get("source_note") or "Legacy v1 project profile"),
        examples=(),
        abbreviations=abbreviations,
        symbols=symbols,
    )


def bundled_profile_path() -> Path:
    """Compatibility path for the original v1 bundled grammar profile."""
    return Path(__file__).resolve().parent / "data" / "default_dictionary_profile.json"


def profile_library_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "dictionary_profiles_v2.json"


def profile_preview_dir() -> Path:
    return Path(__file__).resolve().parent / "data" / "profile_previews"


def profile_preview_path(filename: str) -> Path:
    return profile_preview_dir() / Path(filename).name


def _load_profile_library_raw() -> dict[str, Any]:
    path = profile_library_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"内置 Profile 库无法读取：{path}（{exc}）") from exc
    if not isinstance(raw, dict) or raw.get("format") != PROFILE_LIBRARY_FORMAT_V2:
        raise ValueError(f"内置 Profile 库格式无效：{path}")
    return raw


def available_dictionary_profiles() -> tuple[DictionaryProfilePreset, ...]:
    raw = _load_profile_library_raw()
    result: list[DictionaryProfilePreset] = []
    for key, item in (raw.get("profiles") or {}).items():
        if not isinstance(item, dict):
            continue
        examples = tuple(
            ProfileExample(
                dictionary=str(example.get("dictionary") or ""),
                image=str(example.get("image") or ""),
                note=str(example.get("note") or ""),
            )
            for example in (item.get("examples") or [])
            if isinstance(example, dict)
        )
        result.append(
            DictionaryProfilePreset(
                key=str(key),
                display_name=str(item.get("display_name") or key),
                family=str(item.get("family") or key),
                description=str(item.get("description") or ""),
                examples=examples,
                supported_languages=tuple(str(x) for x in item.get("supported_languages", []) if str(x)),
                default_language=str(item.get("default_language") or ""),
                default_paddle_language=str(item.get("default_paddle_language") or ""),
                paddle_language_by_language={
                    str(k): str(v) for k, v in (item.get("paddle_language_by_language") or {}).items()
                },
                parser_modes=tuple(str(x) for x in item.get("parser_modes", ["latin"]) if str(x)),
                settings=dict(item.get("settings") or {}),
                raw=item,
            )
        )
    return tuple(result)


def dictionary_profile_preset(key: str | None) -> DictionaryProfilePreset:
    wanted = str(key or DEFAULT_PROFILE_ID)
    profiles = available_dictionary_profiles()
    for profile in profiles:
        if profile.key == wanted:
            return profile
    for profile in profiles:
        if profile.key == DEFAULT_PROFILE_ID:
            return profile
    if not profiles:
        raise ValueError("内置 Profile 库为空")
    return profiles[0]


def dictionary_profile_labels() -> dict[str, str]:
    """Return UI label -> stable preset key mapping in library order."""
    return {profile.display_name: profile.key for profile in available_dictionary_profiles()}


def managed_profile_setting_names() -> tuple[str, ...]:
    names: set[str] = {"ocr_language", "paddle_language"}
    for profile in available_dictionary_profiles():
        names.update(profile.settings)
    return tuple(sorted(names))


def profile_effective_settings(key: str | None, current_language: str | None = None) -> dict[str, Any]:
    """Resolve preset defaults for a project without hiding the language choice.

    If the current OCR language belongs to the preset's supported language
    family (e.g. ``ita`` for the shared Portuguese/Italian classic layout), it
    is retained.  Otherwise the preset's recommended language is selected.
    """
    profile = dictionary_profile_preset(key)
    settings = dict(profile.settings)
    current_base = _base_language(current_language)
    if current_base and current_base in profile.supported_languages:
        language = str(current_language)
    else:
        language = profile.default_language
    if language:
        settings["ocr_language"] = language
    base = _base_language(language)
    paddle_language = profile.paddle_language_by_language.get(base, profile.default_paddle_language)
    if paddle_language:
        settings["paddle_language"] = paddle_language
    return settings


def _grammar_block_from_preset(profile: DictionaryProfilePreset, language: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    item = profile.raw
    base_language = _base_language(language)
    grammar = item.get("grammar") or {}
    by_language = item.get("grammar_by_language") or {}
    if base_language and isinstance(by_language, dict) and isinstance(by_language.get(base_language), dict):
        grammar = by_language[base_language]
    grammar = grammar if isinstance(grammar, dict) else {}
    abbreviations = {
        "part_of_speech": list(grammar.get("part_of_speech") or []),
        "usage_and_region": list(grammar.get("usage_and_region") or []),
        "subject_domains": list(grammar.get("subject_domains") or []),
        "article_relations": list(grammar.get("article_relations") or []),
    }
    symbols = {
        "internal_not_new_entry": list(grammar.get("internal_not_new_entry") or []),
        "entry_markers": list(grammar.get("entry_markers") or []),
        "meanings": dict(grammar.get("meanings") or {}),
    }
    return abbreviations, symbols


def _merge_list_override(original: list[Any], override: Any) -> list[Any]:
    if override is None:
        return original
    if isinstance(override, list):
        return override
    return original


def _apply_grammar_overrides(
    abbreviations: dict[str, Any], symbols: dict[str, Any], overrides: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    overrides = overrides or {}
    ab_override = overrides.get("abbreviations") if isinstance(overrides, dict) else None
    sym_override = overrides.get("symbols") if isinstance(overrides, dict) else None
    ab_override = ab_override if isinstance(ab_override, dict) else {}
    sym_override = sym_override if isinstance(sym_override, dict) else {}
    for name in ("part_of_speech", "usage_and_region", "subject_domains", "article_relations"):
        abbreviations[name] = _merge_list_override(list(abbreviations.get(name) or []), ab_override.get(name))
    for name in ("internal_not_new_entry", "entry_markers"):
        symbols[name] = _merge_list_override(list(symbols.get(name) or []), sym_override.get(name))
    if isinstance(sym_override.get("meanings"), dict):
        symbols["meanings"] = {**dict(symbols.get("meanings") or {}), **sym_override["meanings"]}
    return abbreviations, symbols


def load_dictionary_profile(
    path: Path | None = None,
    *,
    preset: str | None = None,
    language: str | None = None,
) -> DictionaryProfile:
    """Load a v2 preset/project override or a legacy v1 grammar file.

    ``preset`` normally comes from ``AppSettings.dictionary_profile_id``.  A v2
    project file can override that selection; a v1 project file remains fully
    supported and is interpreted exactly as before.
    """
    raw: dict[str, Any] | None = None
    if path is not None and path.exists():
        try:
            candidate = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(f"词典配置无法读取：{path}（{exc}）") from exc
        if not isinstance(candidate, dict):
            raise ValueError(f"词典配置顶层必须是 JSON 对象：{path}")
        raw = candidate
        if candidate.get("format") != PROFILE_FORMAT_V2:
            return _profile_from_legacy_dict(candidate)

    selected = str((raw or {}).get("preset") or preset or DEFAULT_PROFILE_ID)
    profile = dictionary_profile_preset(selected)
    selected_language = str(language or (raw or {}).get("language") or profile.default_language)
    abbreviations, symbols = _grammar_block_from_preset(profile, selected_language)
    overrides = ((raw or {}).get("overrides") or {}).get("grammar") if raw else None
    abbreviations, symbols = _apply_grammar_overrides(abbreviations, symbols, overrides)
    return _grammar_profile_from_blocks(
        name=profile.display_name,
        key=profile.key,
        family=profile.family,
        parser_modes=profile.parser_modes,
        description=profile.description,
        examples=profile.examples,
        abbreviations=abbreviations,
        symbols=symbols,
    )


def project_profile_preset_id(path: Path | None, fallback: str = DEFAULT_PROFILE_ID) -> str:
    if path is None or not path.exists():
        return fallback
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return fallback
    if not isinstance(raw, dict) or raw.get("format") != PROFILE_FORMAT_V2:
        return fallback
    key = str(raw.get("preset") or fallback)
    return dictionary_profile_preset(key).key


def profile_settings_overrides(settings: Any, key: str | None) -> dict[str, Any]:
    current_language = str(getattr(settings, "ocr_language", "") or "")
    defaults = profile_effective_settings(key, current_language=current_language)
    overrides: dict[str, Any] = {}
    for name in managed_profile_setting_names():
        if not hasattr(settings, name) or name not in defaults:
            continue
        actual = getattr(settings, name)
        if actual != defaults[name]:
            overrides[name] = actual
    return overrides


def write_project_profile(
    path: Path, settings: Any, key: str | None = None, *, force: bool = False,
) -> None:
    selected = dictionary_profile_preset(key or getattr(settings, "dictionary_profile_id", DEFAULT_PROFILE_ID)).key
    if path.exists() and not force:
        try:
            existing = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            existing = None
        # Opening/saving an old project must not silently destroy a hand-edited
        # v1 grammar profile. It remains authoritative until the user explicitly
        # chooses one of the v2 layout Profiles in the UI.
        if isinstance(existing, dict) and existing.get("format") != PROFILE_FORMAT_V2:
            return
    payload = {
        "format": PROFILE_FORMAT_V2,
        "preset": selected,
        "language": str(getattr(settings, "ocr_language", "") or ""),
        "overrides": {
            "settings": profile_settings_overrides(settings, selected),
            "grammar": {},
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def starts_with_internal_article_symbol(text: str, profile: DictionaryProfile) -> str:
    stripped = text.lstrip()
    for symbol in sorted(profile.internal_leading_symbols, key=len, reverse=True):
        if stripped.startswith(symbol):
            return symbol
    return ""


def leading_relation_label(text: str, profile: DictionaryProfile) -> str:
    stripped = text.lstrip()
    for label in sorted(profile.relation_labels, key=len, reverse=True):
        pattern = _label_to_regex(label)
        if re.match(pattern + r"(?=\s|\[|→|$)", stripped, flags=re.IGNORECASE | re.UNICODE):
            return label
    return ""
