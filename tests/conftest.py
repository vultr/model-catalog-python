import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def load():
    return lambda name: json.loads((FIXTURES / name).read_text(encoding="utf-8"))
