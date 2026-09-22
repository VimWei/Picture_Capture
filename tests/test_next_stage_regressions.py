from pathlib import Path
from dataclasses import replace

from PIL import Image

from picture_capture.app import binary_preview_image, effective_main_overlay_font_size
from picture_capture.dictionary_profile import load_dictionary_profile
from picture_capture.models import AppSettings, ProjectState
from picture_capture.paddle_headwords import (
    OCRLine, OCRRecord, _compile_patterns, _repair_multiline_headword_state_machine,
    parse_headword_text, prepare_ocr_band, run_paddle_band,
)
from picture_capture.project_storage import profile_path, settings_path
from picture_capture.recent_projects import load_recent_projects, remove_recent_project, touch_recent_project


def _project(root: Path, **settings) -> None:
    root.mkdir()
    Image.new("RGB", (8, 8), "white").save(root / "page10.jpg")
    Image.new("RGB", (8, 8), "white").save(root / "page2.jpg")
    Image.new("RGB", (8, 8), "white").save(root / "page1.jpg")
    state = ProjectState.open(root)
    for key, value in settings.items():
        setattr(state.settings, key, value)
    state.settings.to_json(settings_path(root))


def test_projects_restore_independent_settings_and_natural_order(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    _project(a, columns=1, main_entry_font_size=18, ocr_language="eng", paddle_band_width_ratio=60)
    _project(b, columns=3, main_entry_font_size=32, ocr_language="jpn", paddle_band_width_ratio=75)
    for root, expected in ((a, (1, 18, "eng", 60)), (b, (3, 32, "jpn", 75))) * 2:
        state = ProjectState.open(root)
        assert [page.name for page in state.images] == ["page1.jpg", "page2.jpg", "page10.jpg"]
        assert (state.settings.columns, state.settings.main_entry_font_size,
                state.settings.ocr_language, state.settings.paddle_band_width_ratio) == expected


def test_settings_json_beats_profile_sidecar(tmp_path):
    root = tmp_path / "project"
    _project(root, dictionary_profile_id="latin_pos_classic")
    profile_path(root).write_text('{"format":"dictionary-profile-v2","preset":"cjk_bracket_display"}', encoding="utf-8")
    assert ProjectState.open(root).settings.dictionary_profile_id == "latin_pos_classic"


def test_recent_removal_only_changes_registry(tmp_path):
    project, registry = tmp_path / "scan", tmp_path / "recent.json"
    project.mkdir(); (project / "user.jpg").write_bytes(b"user")
    touch_recent_project(project, registry)
    remove_recent_project(project, registry)
    assert load_recent_projects(registry) == []
    assert (project / "user.jpg").read_bytes() == b"user"


def test_binary_preview_and_font_scaling_are_display_only():
    source = Image.new("RGB", (2, 1)); source.putdata([(20, 20, 20), (240, 200, 160)])
    before = source.tobytes()
    preview = binary_preview_image(source)
    assert source.tobytes() == before and source.mode == "RGB"
    assert all(color in {(0, 0, 0), (255, 255, 255)} for _count, color in preview.getcolors())
    settings = AppSettings(main_entry_font_size=32, main_entry_follow_zoom=True)
    assert effective_main_overlay_font_size(1400, 1, settings) == 32
    assert effective_main_overlay_font_size(2800, .5, settings) == 32
    assert effective_main_overlay_font_size(4200, 1 / 3, settings) == 32


def test_latin_pronunciation_pos_and_cjk_rejection():
    profile = load_dictionary_profile(preset="latin_pos_classic", language="eng")
    settings = AppSettings(ocr_language="eng")
    for text in ("ab·a·cus ['æbəkəs] n. frame", "a·ban·don /ə'bændən/ v.t. leave"):
        parsed = parse_headword_text(text, settings, profile=profile)
        assert parsed is not None and parsed.has_pos
    assert parse_headword_text("中文正文", settings, profile=profile) is None


def test_multiline_pronunciation_keeps_first_line_geometry():
    settings = AppSettings(ocr_language="eng")
    profile = load_dictionary_profile(preset="latin_pos_classic", language="eng")
    patterns = _compile_patterns(settings, profile)
    first = OCRLine("a·ban·don [ə'bændən;", .9, (3, 10, 180, 30), [])
    second = OCRLine("ə'bændən] v.t. leave", .9, (8, 31, 210, 50), [])
    repaired = _repair_multiline_headword_state_machine([first, second], settings, 20, patterns)
    assert repaired[0].box == first.box
    parsed = parse_headword_text(repaired[0].text, settings, patterns, profile)
    assert parsed is not None and parsed.has_pos


def test_cjk_features_gate_parsers_and_pinyin_is_structural():
    settings = AppSettings(ocr_language="chi_sim")
    pinyin = load_dictionary_profile(preset="cjk_large_head_pinyin_2col", language="chi_sim")
    parsed = parse_headword_text("案* ān", settings, profile=pinyin)
    assert parsed is not None and parsed.normalized == "案"
    disabled = replace(load_dictionary_profile(preset="cjk_bracket_display", language="chi_sim"), headword_features=())
    assert parse_headword_text("【案件】", settings, profile=disabled) is None
    enabled = load_dictionary_profile(preset="cjk_bracket_large_head_2col", language="chi_sim")
    assert parse_headword_text("【案件】", settings, profile=enabled).normalized == "案件"


def test_ocr_resize_coordinates_round_trip():
    class Result:
        json = {"res": {"rec_texts": ["word"], "rec_scores": [.9], "rec_boxes": [[100, 200, 300, 400]]}}
    class Engine:
        def predict(self, image, **kwargs):
            assert image.shape[:2] == (1400, 700)
            return [Result()]
    band = Image.new("RGB", (1400, 2800), "white")
    prepared, scale = prepare_ocr_band(band, max_long_side=1400)
    assert prepared.size == (700, 1400) and scale == .5
    records = run_paddle_band(band, AppSettings(paddle_max_input_side=1400), Engine())
    assert records == [OCRRecord("word", .9, (200, 400, 600, 800))]
