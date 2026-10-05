import pytest

from app.services.redcap import (
    ALLOWED_REDCAP_API_URLS,
    assert_allowed_redcap_api_url,
    is_allowed_redcap_api_url,
)


@pytest.mark.parametrize("api_url", ALLOWED_REDCAP_API_URLS)
def test_allowed_redcap_api_urls_are_accepted(api_url: str) -> None:
    assert is_allowed_redcap_api_url(api_url)
    assert assert_allowed_redcap_api_url(api_url) == api_url


@pytest.mark.parametrize(
    "api_url, expected",
    [
        ("https://apps.ovg.ox.ac.uk/redcap/api", "https://apps.ovg.ox.ac.uk/redcap/api/"),
        ("HTTPS://APPS.OVG.OX.AC.UK/redcap/api/", "https://apps.ovg.ox.ac.uk/redcap/api/"),
        ("http://localhost:8888/redcap/api", "http://localhost:8888/redcap/api/"),
    ],
)
def test_allowed_redcap_api_urls_normalize_to_allowlisted_form(api_url: str, expected: str) -> None:
    assert is_allowed_redcap_api_url(api_url)
    assert assert_allowed_redcap_api_url(api_url) == expected


@pytest.mark.parametrize(
    "api_url",
    [
        "https://example.com/api/",
        "https://apps.ovg.ox.ac.uk/other/api/",
        "http://localhost:8888/api/",
        "https://evil.example/redcap/api/",
    ],
)
def test_unauthorized_redcap_api_urls_are_rejected(api_url: str) -> None:
    assert not is_allowed_redcap_api_url(api_url)
    with pytest.raises(ValueError, match="not approved for this app"):
        assert_allowed_redcap_api_url(api_url)
