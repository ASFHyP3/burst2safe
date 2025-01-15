import netrc
import os
from pathlib import Path
from platform import system
from typing import Tuple, Union


EARTHDATA_HOST = 'urs.earthdata.nasa.gov'
TOKEN_ENV_VAR = 'EARTHDATA_TOKEN'


def get_netrc() -> Path:
    """Get the location of the netrc file.

    Returns:
        Path to the netrc file
    """
    netrc_name = '_netrc' if system().lower() == 'windows' else '.netrc'
    netrc_file = Path.home() / netrc_name
    return netrc_file


def find_creds_in_env(username_name, password_name) -> Union[Tuple[str, str], Tuple[None, None]]:
    """Find credentials for a service in the environment.

    Args:
        username_name: Name of the environment variable for the username
        password_name: Name of the environment variable for the password

    Returns:
        Tuple of the username and password found in the environment
    """
    if username_name in os.environ and password_name in os.environ:
        username = os.environ[username_name]
        password = os.environ[password_name]
        return username, password

    return None, None


def find_creds_in_netrc(service) -> Union[Tuple[str, str], Tuple[None, None]]:
    """Find credentials for a service in the netrc file.

    Args:
        service: Service to find credentials for

    Returns:
        Tuple of the username and password found in the netrc file
    """
    netrc_file = get_netrc()
    if netrc_file.exists():
        netrc_credentials = netrc.netrc(netrc_file)
        if service in netrc_credentials.hosts:
            username = netrc_credentials.hosts[service][0]
            password = netrc_credentials.hosts[service][2]
            assert password is not None
            return username, password

    return None, None


def write_credentials_to_netrc_file(username: str, password: str) -> None:
    """Write credentials to netrc file

    Args:
        username: NASA EarthData username
        password: NASA EarthData password
    """
    netrc_file = get_netrc()
    if not netrc_file.exists():
        netrc_file.touch()

    with open(netrc_file, 'a') as f:
        f.write(f'machine {EARTHDATA_HOST} login {username} password {password}\n')


def check_earthdata_credentials(append=False) -> str:
    """Check for NASA EarthData credentials in the netrc file or environment variables.
    Will preferentially use the netrc file, and write credentials to the netrc file if found in the environment.

    Args:
        append: Whether to append the credentials to the netrc file if creds found in the environment

    Returns:
        The location of the preferred credentials ('netrc' or 'token')
    """
    if os.getenv(TOKEN_ENV_VAR):
        return 'token'

    username, password = find_creds_in_netrc(EARTHDATA_HOST)
    if username and password:
        return 'netrc'

    username, password = find_creds_in_env('EARTHDATA_USERNAME', 'EARTHDATA_PASSWORD')
    if username and password:
        if append:
            write_credentials_to_netrc_file(username, password)
            return 'netrc'
        else:
            raise ValueError(
                'NASA Earthdata credentials only found in environment variables,'
                'but appending to netrc file not allowed. Please allow appending to netrc.'
            )

    raise ValueError(
        'Please provide NASA Earthdata credentials via your .netrc file,'
        'the EARTHDATA_USERNAME and EARTHDATA_PASSWORD environment variables,'
        'or an EDL Token via the EARTHDATA_TOKEN environment variable.'
    )
