import pytest

# This test is intentionally skipped in CI because it makes real network calls to LinkedIn.
@pytest.mark.skip(reason="Network call to LinkedIn – skip in CI")
def test_placeholder():
    assert True
