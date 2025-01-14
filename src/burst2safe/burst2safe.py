"""A tool for converting ASF burst SLCs to the SAFE format"""

from argparse import ArgumentParser
from collections.abc import Iterable
from pathlib import Path
from typing import Optional

from shapely.geometry import Polygon

from burst2safe import utils
from burst2safe.download import download_bursts
from burst2safe.safe import Safe
from burst2safe.search import find_bursts


DESCRIPTION = """Convert a set of ASF burst SLCs to the ESA SAFE format.
You can either provide a list of burst granules, or define a burst group by
providing the absolute orbit number, extent, and polarizations arguments.
"""


def burst2safe(
    granules: Optional[Iterable[str]] = None,
    orbit: Optional[int] = None,
    extent: Optional[Polygon] = None,
    polarizations: Optional[list[str]] = None,
    swaths: Optional[list[str]] = None,
    mode: str = 'IW',
    min_bursts: int = 1,
    all_anns: bool = False,
    keep_files: bool = False,
    work_dir: Optional[Path] = None,
) -> Path:
    """Convert a set of burst granules to the ESA SAFE format.

    To be eligible for conversions, all burst granules must:
    - Have the same acquisition mode
    - Be from the same absolute orbit
    - Be contiguous in time and space
    - Have the same footprint for all included polarizations

    Args:
        granules: A list of burst granules to convert to SAFE
        orbit: The absolute orbit number of the bursts
        extent: The bounding box of the bursts
        polarizations: List of polarizations to include
        swaths: List of swaths to include
        mode: The collection mode to use (IW or EW)
        min_bursts: The minimum number of bursts per swath (default: 1)
        all_anns: Include product annotation files for all swaths, regardless of included bursts
        keep_files: Keep the intermediate files
        work_dir: The directory to create the SAFE in (default: current directory)
    """
    work_dir = utils.optional_wd(work_dir)

    products = find_bursts(granules, orbit, extent, polarizations, swaths, mode, min_bursts)
    burst_infos = utils.get_burst_infos(products, work_dir)
    print(f'Found {len(burst_infos)} burst(s).')

    print('Check burst group validity...')
    Safe.check_group_validity(burst_infos)

    print('Downloading data...')
    download_bursts(burst_infos)
    print('Download complete.')

    print('Creating SAFE...')
    [info.add_shape_info() for info in burst_infos]
    [info.add_start_stop_utc() for info in burst_infos]

    safe = Safe(burst_infos, all_anns, work_dir)
    safe_path = safe.create_safe()
    print('SAFE created!')

    if not keep_files:
        safe.cleanup()

    return safe_path


def main() -> None:
    parser = ArgumentParser(description=DESCRIPTION)
    parser.add_argument('granules', nargs='*', help='List of bursts to convert to SAFE')
    parser.add_argument('--orbit', type=int, help='Absolute orbit number of the bursts')
    parser.add_argument(
        '--extent',
        type=str,
        nargs='+',
        help='Bounds (W S E N in lat/lon) or geometry file describing spatial extent',
    )
    parser.add_argument('--pols', type=str, nargs='+', help='Polarizations to include (i.e., VV VH). Default: VV')
    parser.add_argument(
        '--swaths', type=str, nargs='+', help='Swaths to include (i.e., IW1 IW2 IW3). Defaults to all swaths.'
    )
    parser.add_argument('--mode', type=str, default='IW', help='Collection mode to use (IW or EW). Default: IW')
    parser.add_argument('--min-bursts', type=int, default=1, help='Minimum # of bursts per swath/polarization.')
    parser.add_argument(
        '--all-anns',
        action='store_true',
        default=False,
        help='Include product annotations files for all swaths, regardless of included bursts.',
    )
    parser.add_argument('--output-dir', type=str, default=None, help='Output directory to save to')
    parser.add_argument('--keep-files', action='store_true', default=False, help='Keep the intermediate files')

    args = utils.reparse_args(parser.parse_args(), tool='burst2safe')

    burst2safe(
        granules=args.granules,
        orbit=args.orbit,
        extent=args.extent,
        polarizations=args.pols,
        swaths=args.swaths,
        mode=args.mode,
        min_bursts=args.min_bursts,
        all_anns=args.all_anns,
        keep_files=args.keep_files,
        work_dir=args.output_dir,
    )
