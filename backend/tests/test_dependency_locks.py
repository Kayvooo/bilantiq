from pathlib import Path

import pytest

from scripts.check_dependency_locks import check_locks


@pytest.fixture
def locked_project(tmp_path: Path) -> Path:
    pin = "sample[feature]==1.0 --hash=sha256:" + "a" * 64 + "\n"
    (tmp_path / "requirements.txt").write_text("sample[feature]==1.0\n")
    (tmp_path / "requirements-dev.txt").write_text("-r requirements.txt\n")
    (tmp_path / "requirements.lock").write_text(pin)
    (tmp_path / "requirements-dev.lock").write_text(pin)
    return tmp_path


def test_valid_locks(locked_project):
    check_locks(locked_project)


@pytest.mark.parametrize("change", ["new_version", "new_dependency", "missing_extra"])
def test_direct_requirement_change_needs_regeneration(locked_project, change):
    if change == "new_version":
        (locked_project / "requirements.txt").write_text("sample[feature]==2.0\n")
    elif change == "new_dependency":
        with (locked_project / "requirements.txt").open("a") as file:
            file.write("added==1.0\n")
    else:
        for name in ("requirements.lock", "requirements-dev.lock"):
            file = locked_project / name
            file.write_text(file.read_text().replace("[feature]", ""))
    with pytest.raises(ValueError, match="Lock passt nicht"):
        check_locks(locked_project)


@pytest.mark.parametrize("change", ["missing_hash", "unbounded", "different_version", "different_platform"])
def test_invalid_or_divergent_lock_is_rejected(locked_project, change):
    file = locked_project / "requirements-dev.lock"
    text = file.read_text()
    if change == "missing_hash":
        text = "sample[feature]==1.0\n"
    elif change == "unbounded":
        text = text.replace("==1.0", ">=1.0")
    elif change == "different_version":
        text = text.replace("==1.0", "==2.0")
    else:
        text = text.replace(" --hash", "; sys_platform == 'win32' --hash")
    file.write_text(text)
    with pytest.raises(ValueError):
        check_locks(locked_project)
