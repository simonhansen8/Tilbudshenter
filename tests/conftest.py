from datetime import datetime, timezone

import pytest

from tilbudshenter.categories import Categorizer
from tilbudshenter.config import Config
from tilbudshenter.storage import Storage

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def cfg():
    return Config(top_n=0)


@pytest.fixture
def categorizer():
    return Categorizer()


@pytest.fixture
def storage():
    with Storage(":memory:") as s:
        yield s
