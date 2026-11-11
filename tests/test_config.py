from pitwh import config


def test_repo_root_contains_spec():
    assert (config.REPO_ROOT / "SPEC.md").is_file()


def test_dbt_project_lives_under_repo_root():
    assert (config.DBT_DIR / "dbt_project.yml").is_file()


def test_universe_has_room_for_departed_names():
    assert 0 < config.MIN_DEPARTED_SECURITIES < config.UNIVERSE_SIZE
