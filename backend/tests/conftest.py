import os
import glob
try:
    for f in glob.glob("*.db"):
        os.remove(f)
except Exception:
    pass

os.environ["DB_PATH"] = "test_run.db"
os.environ["GEMINI_API_KEY"] = ""
# The suite makes hundreds of requests from one client; the rate limiter has its own dedicated test.
os.environ["RATE_LIMIT_PER_MIN"] = "100000"

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app import main
    main.ip_tracking.clear()
    yield
