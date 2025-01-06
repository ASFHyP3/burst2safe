from pathlib import Path

import pytest

from burst2safe import auth


def test_get_netrc(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(auth, 'system', lambda: 'Windows')
        assert auth.get_netrc() == Path.home() / '_netrc'

    with monkeypatch.context() as m:
        m.setattr(auth, 'system', lambda: 'Linux')
        assert auth.get_netrc() == Path.home() / '.netrc'


def test_find_creds_in_env(monkeypatch):
    with monkeypatch.context() as m:
        m.setenv('TEST_USERNAME', 'foo')
        m.setenv('TEST_PASSWORD', 'bar')
        assert auth.find_creds_in_env('TEST_USERNAME', 'TEST_PASSWORD') == ('foo', 'bar')

    with monkeypatch.context() as m:
        m.delenv('TEST_USERNAME', raising=False)
        m.delenv('TEST_PASSWORD', raising=False)
        assert auth.find_creds_in_env('TEST_USERNAME', 'TEST_PASSWORD') == (None, None)


def test_find_creds_in_netrc(tmp_path, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(auth, 'get_netrc', lambda: tmp_path / '.netrc')
        (tmp_path / '.netrc').write_text('machine test login foo password bar')
        assert auth.find_creds_in_netrc('test') == ('foo', 'bar')

    with monkeypatch.context() as m:
        m.setattr(auth, 'get_netrc', lambda: tmp_path / '.netrc')
        (tmp_path / '.netrc').write_text('')
        assert auth.find_creds_in_netrc('test') == (None, None)


def test_write_credentials_to_netrc_file(tmp_path, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(auth, 'get_netrc', lambda: tmp_path / '.netrc')
        auth.write_credentials_to_netrc_file('foo', 'bar')
    assert (tmp_path / '.netrc').read_text() == 'machine urs.earthdata.nasa.gov login foo password bar\n'


def test_check_earthdata_credentials_token(tmp_path, monkeypatch):
    with monkeypatch.context() as m:
        m.setenv('EARTHDATA_TOKEN', 'foo')
        assert auth.check_earthdata_credentials() == 'token'


def test_check_earthdata_credentials_netrc(tmp_path, monkeypatch):
    netrc_path = tmp_path / '.netrc'
    netrc_path.touch()
    netrc_path.write_text('machine urs.earthdata.nasa.gov login foo password bar\n')
    with monkeypatch.context() as m:
        m.delenv('EARTHDATA_TOKEN', raising=False)
        m.setenv('EARTHDATA_USERNAME', 'baz')
        m.setenv('EARTHDATA_PASSWORD', 'buzz')
        m.setattr(auth, 'get_netrc', lambda: netrc_path)
        assert auth.check_earthdata_credentials() == 'netrc'
        netrc_path.read_text() == 'machine urs.earthdata.nasa.gov login foo password bar\n'


def test_check_earthdata_credentials_env(tmp_path, monkeypatch):
    netrc_path = tmp_path / '.netrc'
    with monkeypatch.context() as m:
        m.delenv('EARTHDATA_TOKEN', raising=False)
        m.setenv('EARTHDATA_USERNAME', 'baz')
        m.setenv('EARTHDATA_PASSWORD', 'buzz')
        m.setattr(auth, 'get_netrc', lambda: netrc_path)

        with pytest.raises(ValueError, match='NASA Earthdata credentials only found in environment variables*'):
            auth.check_earthdata_credentials()

        assert auth.check_earthdata_credentials(append=True) == 'netrc'
        netrc_path.read_text() == 'machine urs.earthdata.nasa.gov login baz password buzz\n'


def test_check_earthdata_credentials_none(tmp_path, monkeypatch):
    netrc_path = tmp_path / '.netrc'
    with monkeypatch.context() as m:
        m.delenv('EARTHDATA_TOKEN', raising=False)
        m.delenv('EARTHDATA_USERNAME', raising=False)
        m.delenv('EARTHDATA_PASSWORD', raising=False)
        m.setattr(auth, 'get_netrc', lambda: netrc_path)
        with pytest.raises(ValueError, match='Please provide NASA Earthdata credentials*'):
            auth.check_earthdata_credentials()
