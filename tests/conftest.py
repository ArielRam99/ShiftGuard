import pytest

from shiftguard import create_app


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "shiftguard-test.sqlite"),
        }
    )
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()

