import asyncio
import logging
import os
from collections.abc import Iterable
from pathlib import Path

import aiohttp
from aiohttp import ClientResponseError
from tenacity import retry, retry_if_exception_type, retry_if_result, stop_after_attempt, stop_after_delay, wait_random

from burst2safe.auth import TOKEN_ENV_VAR, check_earthdata_credentials
from burst2safe.utils import BurstInfo


log_dir = Path(__file__).resolve().parent
log_file = log_dir / 'download.log'

# logging.basicConfig(level=logging.INFO, filename=str(log_file), format="%(asctime)s|%(levelname)s|%(name)s|%(message)s", force=True)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# create formatters
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')

# File handler
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)


COOKIE_URL = 'https://sentinel1.asf.alaska.edu/METADATA_RAW/SA/S1A_IW_RAW__0SSV_20141229T072718_20141229T072750_003931_004B96_B79F.iso.xml'

# set EARTHDATA_CONCURRENT_DOWNLOADS in your system environment variables.
num_concurrent_downloads = int(os.getenv('EARTHDATA_CONCURRENT_DOWNLOADS', 150))

semaphore = asyncio.Semaphore(num_concurrent_downloads)  # number of concurrent downloads (too many causes a crash)


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
            logger.info(f'Queuing data file for download: {burst_info.data_path}')
        if force or not burst_info.metadata_path.exists():
            url_dict[burst_info.metadata_path] = burst_info.metadata_url
            logger.info(f'Queueing metadata file for download: {burst_info.metadata_path}')

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
    logger.info(f'Requesting URL: {url}')
    response = await session.get(url)
    logger.info(f'Received response: {response.status} for {url}')
    response.raise_for_status()
    return response


@retry(
    reraise=True, stop=stop_after_attempt(3), retry=retry_if_exception_type((ClientResponseError, asyncio.TimeoutError))
)
async def download_burst_url_async(session: aiohttp.ClientSession, url: str, file_path: Path) -> None:
    """Retry a burst URL GET request until a non-202 response is received, then download the file.

    Args:
        session: An aiohttp ClientSession
        url: The URL to download
        file_path: The path to save the downloaded data to
    """
    logger.info(f'Starting download for: {file_path} from {url}')
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
        logger.info(f'Successfully downloaded: {file_path}')
    except asyncio.TimeoutError as e:
        logger.error(f'Timeout error while downloading: {file_path}: {e}')
        file_path.unlink(missing_ok=True)
        raise
    except Exception:
        logger.error(f'Download failed for {file_path}')
        file_path.unlink(missing_ok=True)
        raise
    finally:
        response.close()


async def throttled_download(session, url, file_path):
    async with semaphore:
        await download_burst_url_async(session, url, file_path)


async def download_bursts_async(url_dict: dict) -> None:
    """Download a dictionary of URLs asynchronously.

    Args:
        url_dict: A dictionary of URLs to download
    """
    auth_type = check_earthdata_credentials(append=True)
    logger.info(f'Authentication type: {auth_type}')
    headers = {'Authorization': f'Bearer {os.getenv(TOKEN_ENV_VAR)}'} if auth_type == 'token' else {}
    timeout = aiohttp.ClientTimeout(sock_read=30, sock_connect=30)
    async with aiohttp.ClientSession(headers=headers, trust_env=True, timeout=timeout) as session:
        # Skip cookie request if using EDL token
        if auth_type != 'token':
            logger.info('Requesting cookie for session...')
            cookie_response = await session.get(COOKIE_URL)
            cookie_response.raise_for_status()
            cookie_response.close()

        tasks = []
        for file_path, url in url_dict.items():
            logger.info(f'Scheduling download: {file_path}')
            tasks.append(throttled_download(session, url, file_path))
        await asyncio.gather(*tasks)


def download_bursts(burst_infos: Iterable[BurstInfo]) -> None:
    """Download the burst data and metadata files using an async queue.

    Args:
        burst_infos: A list of BurstInfo objects
    """
    logger.info('Starting burst downloads...')
    url_dict = get_url_dict(burst_infos)
    asyncio.run(download_bursts_async(url_dict))
    full_dict = get_url_dict(burst_infos, force=True)
    missing_data = [x for x in full_dict.keys() if not x.exists]
    if missing_data:
        logger.error(f'Missing files after download: {", ".join([x.name for x in missing_data])}')
        raise ValueError(f'Error downloading, missing files: {", ".join([x.name for x in missing_data])}')
    else:
        logger.info('All files downloaded successfully')
