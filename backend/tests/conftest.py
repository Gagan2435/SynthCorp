import os
import tempfile

# Must be set before the app is imported: it builds its DB engine at import time.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import MetaData  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    # Drop everything, including the per-run r<id>_ tables, so run ids can restart at 1 next test.
    md = MetaData()
    md.reflect(bind=engine)
    md.drop_all(engine)


@pytest.fixture()
def saas_yaml():
    from pathlib import Path

    return (Path(__file__).parent.parent / "app" / "templates" / "saas.yaml").read_text()
