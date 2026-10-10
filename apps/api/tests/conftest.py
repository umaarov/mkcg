import os
import tempfile

# isolate the database/keys of the test run before the app modules read their settings
os.environ["CG_DATA_DIR"] = tempfile.mkdtemp(prefix="cg-test-")

import pytest  # noqa: E402

from app.db import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db()
