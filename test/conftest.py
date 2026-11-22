from dataclasses import replace

import pytest

import main
from storage import Store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    settings = replace(main.settings, database=tmp_path / "test.sqlite3", visitor_limit=100)
    store = Store(settings.database, settings.retention_days)
    monkeypatch.setattr(main, "settings", settings)
    main.app.dependency_overrides[main.get_store] = lambda: store
    yield
    main.app.dependency_overrides.clear()
