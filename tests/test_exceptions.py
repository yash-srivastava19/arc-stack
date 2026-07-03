import pytest

from arc.exceptions import (
    ArcError,
    BranchConflictError,
    ConfigError,
    GitError,
    GitHubError,
    HookFailedError,
    NotInitializedError,
    StateVersionError,
)


def test_all_subclass_arc_error():
    for cls in [
        NotInitializedError,
        ConfigError,
        BranchConflictError,
        GitError,
        GitHubError,
        StateVersionError,
    ]:
        assert issubclass(cls, ArcError), f"{cls.__name__} must subclass ArcError"


def test_hook_failed_error_attributes():
    err = HookFailedError("pre-submit", 1)
    assert err.event == "pre-submit"
    assert err.exit_code == 1
    assert "pre-submit" in str(err)
    assert "1" in str(err)


def test_hook_failed_is_arc_error():
    assert issubclass(HookFailedError, ArcError)


def test_catchable_as_arc_error():
    for cls in [
        NotInitializedError,
        ConfigError,
        BranchConflictError,
        GitError,
        GitHubError,
        StateVersionError,
    ]:
        with pytest.raises(ArcError):
            raise cls("test message")
    with pytest.raises(ArcError):
        raise HookFailedError("pre-land", 2)


def test_arc_error_is_exception():
    assert issubclass(ArcError, Exception)
