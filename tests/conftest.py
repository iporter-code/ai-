from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def work_dir() -> Path:
    """A logical workspace path for Settings; does not create a temp directory.

    pytest's tmp_path uses mode 0o700, which the Windows sandbox maps to an ACL
    that blocks writes inside. These unit tests only need a path value, so no
    directory has to be created.
    """
    return Path(".testtmp") / uuid4().hex
