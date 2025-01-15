import asyncio
import os
from pathlib import Path
from typing import Iterable

import aiohttp
from tenacity import retry, retry_if_result, stop_after_attempt, stop_after_delay, wait_random

from burst2safe.auth import TOKEN_ENV_VAR, check_earthdata_credentials
from burst2safe.utils import BurstInfo


COOKIE_URL = 'https://sentinel1.asf.alaska.edu/METADATA_RAW/SA/S1A_IW_RAW__0SSV_20141229T072718_20141229T072750_003931_004B96_B79F.iso.xml'


def get_url_dict(burst_infos: Iterable[BurstInfo], force: bool = False) -> dict:
    """Get a dictionary of URLs to download. Keys are save paths, and values are download URLs.

    Args:
        burst_infos: A list of BurstInfo objects
        force: If True, download even if the file already exists

    Returns:
        A dictionary of URLs to download
    """
    url_dict = {}
    for burst_info in burst_infos:
        assert burst_info.data_path is not None
        if force or not burst_info.data_path.exists():
            url_dict[burst_info.data_path] = burst_info.data_url
        if force or not burst_info.metadata_path.exists():
            url_dict[burst_info.metadata_path] = burst_info.metadata_url
    return url_dict


@retry(
    reraise=True, retry=retry_if_result(lambda r: r.status == 202), wait=wait_random(0, 1), stop=stop_after_delay(120)
)
async def get_async(session: aiohttp.ClientSession, url: str) -> aiohttp.ClientResponse:
    """Retry a GET request until a non-202 response is received

    Args:
        session: An aiohttp ClientSession
        url: The URL to download

    Returns:
        The response object
    """
    response = await session.get(url)
    response.raise_for_status()
    return response


@retry(reraise=True, stop=stop_after_attempt(3))
async def download_burst_url_async(session: aiohttp.ClientSession, url: str, file_path: Path) -> None:
    """Retry a burst URL GET request until a non-202 response is received, then download the file.

    Args:
        session: An aiohttp ClientSession
        url: The URL to download
        file_path: The path to save the downloaded data to
    """
    response = await get_async(session, url)
    assert response.content_disposition is not None
    if file_path.suffix in ['.tif', '.tiff']:
        returned_filename = response.content_disposition.filename
    elif file_path.suffix == '.xml':
        url_parts = str(response.url).split('/')
        assert response.content_disposition.filename is not None
        ext = response.content_disposition.filename.split('.')[-1]
        returned_filename = f'{url_parts[3]}_{url_parts[5]}.{ext}'
    else:
        raise ValueError(f'Invalid file extension: {file_path.suffix}')

    if file_path.name != returned_filename:
        raise ValueError(f'Race condition encountered, incorrect url returned for file: {file_path.name}')

    try:
        with open(file_path, 'wb') as f:
            async for chunk in response.content.iter_chunked(2**14):
                f.write(chunk)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise e
    finally:
        response.close()


async def download_bursts_async(url_dict: dict) -> None:
    """Download a dictionary of URLs asynchronously.

    Args:
        url_dict: A dictionary of URLs to download
    """
    auth_type = check_earthdata_credentials(append=True)
    headers = {'Authorization': f'Bearer {os.getenv(TOKEN_ENV_VAR)}'} if auth_type == 'token' else {}
    async with aiohttp.ClientSession(headers=headers, trust_env=True) as session:
        if auth_type == 'token':
            # FIXME: Needed while burst extractor API doesn't support EDL tokens
            cookie_response = await session.get(COOKIE_URL)
            cookie_response.raise_for_status()
            cookie_response.close()

        tasks = []
        for file_path, url in url_dict.items():
            tasks.append(download_burst_url_async(session, url, file_path))
        await asyncio.gather(*tasks)


def download_bursts(burst_infos: Iterable[BurstInfo]) -> None:
    """Download the burst data and metadata files using an async queue.

    Args:
        burst_infos: A list of BurstInfo objects
    """
    url_dict = get_url_dict(burst_infos)
    asyncio.run(download_bursts_async(url_dict))
    full_dict = get_url_dict(burst_infos, force=True)
    missing_data = [x for x in full_dict.keys() if not x.exists]
    if missing_data:
        raise ValueError(f'Error downloading, missing files: {", ".join([x.name for x in missing_data])}')
