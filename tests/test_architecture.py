from pathlib import Path


def test_expected_project_directories_exist() -> None:
    expected = [
        "app/bot",
        "app/core",
        "app/database",
        "app/domain/entities",
        "app/domain/repositories",
        "app/integrations/marketplaces",
        "app/services/browser",
        "app/services/notifications",
        "app/services/scheduler",
        "app/observability",
    ]
    for directory in expected:
        assert Path(directory).is_dir()
