"""Resume an unconfigured source install, but never invent secrets for old data."""

import os
import subprocess

import pytest
from test_shell_bootstrap import BASH, ROOT, shell_path

pytestmark = pytest.mark.skipif(
    not BASH or (os.name != "nt" and os.geteuid() == 0), reason="Requires Bash as a non-root user"
)


@pytest.mark.parametrize("system", ["Linux", "Darwin"])
@pytest.mark.parametrize("data_path", [None, "backend/aiteams.db", "backend/data/uploads/keep.bin"])
def test_shell_resumes_missing_backend_env_only_when_no_old_data(tmp_path, system, data_path):
    target = tmp_path / "unfinished installation"
    for name in ("scripts/install/run.py", "scripts/install/install.py", "backend/uv.lock"):
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("existing source")
    if data_path:
        path = target / data_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("preserve existing data")
    installer = target / "scripts/install" / ("linux.sh" if system == "Linux" else "macos.sh")
    installer.write_text(
        """#!/bin/bash
set -eu
[[ "$1" == --no-start ]]
printf 'REPAIR_CALLED\\n'
mkdir -p backend/.venv/bin
printf 'JWT_SECRET=generated-for-new-install\\n' > backend/.env
cat > backend/.venv/bin/python <<'PYTHON'
#!/bin/bash
printf 'LATEST_UPDATER_CALLED\\n'
exit 0
PYTHON
chmod +x backend/.venv/bin/python
""",
        encoding="utf-8",
    )
    before = {file.relative_to(target): file.read_bytes() for file in target.rglob("*") if file.is_file()}
    result = subprocess.run(
        [
            BASH,
            "-c",
            'uname() { printf "%s\\n" "$BOOTSTRAP_TEST_SYSTEM"; }\n'
            + (ROOT / "install.sh").read_text(encoding="utf-8"),
        ],
        env={**os.environ, "ONEDEVTEAMS_INSTALL_DIR": shell_path(target), "BOOTSTRAP_TEST_SYSTEM": system},
        capture_output=True,
        text=True,
        timeout=30,
    )
    if data_path:
        assert result.returncode != 0
        assert "Restore the original backend/.env" in result.stderr
        assert "REPAIR_CALLED" not in result.stdout
        assert {
            file.relative_to(target): file.read_bytes() for file in target.rglob("*") if file.is_file()
        } == before
    else:
        assert result.returncode == 0, result.stderr
        assert "REPAIR_CALLED" in result.stdout
        assert "LATEST_UPDATER_CALLED" in result.stdout
        assert (target / "backend/.env").is_file()
