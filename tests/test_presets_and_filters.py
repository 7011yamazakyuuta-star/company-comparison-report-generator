from datetime import date

from src.assignment_filters import check_assignment_conditions
from src.company_master import select_companies
from src.config_loader import load_industry_policy, load_presets, load_rubric
from src.data_loader import load_sample_dataset


AS_OF = date(2026, 6, 17)


def _result_for_preset(preset_id: str, app_mode: str | None = None):
    dataset = load_sample_dataset()
    presets = load_presets()
    preset = presets[preset_id]
    companies = select_companies(dataset.company_master, preset["companies"])
    return check_assignment_conditions(
        companies,
        app_mode=app_mode or preset.get("default_app_mode", "assignment"),
        industry_mode=preset["industry_mode"],
        rubric=load_rubric(),
        industry_policy=load_industry_policy(),
        as_of=AS_OF,
    )


def test_friend_cafe_theme_warns_about_jpx_mismatch():
    result = _result_for_preset("friend_cafe_theme")

    assert any("JPX業種" in warning for warning in result["warnings"])
    assert "警告" in set(result["condition_table"]["判定"])


def test_strict_cafe_retail_is_selectable_without_industry_warning():
    result = _result_for_preset("strict_cafe_retail")

    assert not any("JPX業種が一致していません" in warning for warning in result["warnings"])
    assert "NG" not in set(result["condition_table"]["判定"])


def test_airline_assignment_contains_three_companies_and_jal_note():
    dataset = load_sample_dataset()
    preset = load_presets()["airline_assignment"]
    companies = select_companies(dataset.company_master, preset["companies"])
    result = _result_for_preset("airline_assignment")

    assert len(companies) == 3
    assert any("日本航空" in note and "再上場" in note for note in result["notes"])
    assert "NG" not in set(result["condition_table"]["判定"])


def test_airline_general_would_warn_in_assignment_mode_for_ana_listing_date():
    result = _result_for_preset("airline_general", app_mode="assignment")

    assert any("上場日" in warning for warning in result["warnings"])
    assert "NG" in set(result["condition_table"]["判定"])

