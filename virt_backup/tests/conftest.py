
import pytest
from helper.virt_backup import MockDomain


@pytest.fixture
def fixture_build_mock_domain(mocker):
    return MockDomain(_conn=mocker.stub())
