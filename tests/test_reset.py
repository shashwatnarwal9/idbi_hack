"""Reset helper: table list + file wipe are safe and self-consistent."""

from aayai import reset


def test_drop_list_covers_all_serving_tables():
    # the wipe must name every app-owned serving/intent/workflow/upload table
    expected = {
        "customer_profiles",
        "prospect_scores",
        "spending_breakdown",
        "income_streams",
        "key_transactions",
        "income_by_month",
        "behaviour_signals",
        "engagement_summary",
        "intent_scores",
        "lead_scores",
        "review_status",
        "lead_contacts",
        "share_log",
        "upload_batches",
        "upload_profiles",
        "upload_streams",
        "upload_transactions",
        "merge_log",
    }
    assert expected.issubset(set(reset.DROP_TABLES))


def test_wipe_files_is_idempotent(tmp_path, monkeypatch):
    # wipe_files must not error when the directories are already gone
    from aayai import paths

    for attr in ("RAW_DIR", "BRONZE_DIR", "SILVER_DIR", "GOLD_DIR"):
        monkeypatch.setattr(reset, attr, tmp_path / attr.lower())
    reset.wipe_files()  # nothing exists -> no exception
    (tmp_path / "raw_dir").mkdir()
    reset.wipe_files()  # existing dir -> removed cleanly
    assert not (tmp_path / "raw_dir").exists()
