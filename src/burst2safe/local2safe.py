# mypy: disable-error-code="union-attr"
"""Generate a SAFE file from local burst extractor outputs"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, cast

from burst2safe import utils
from burst2safe.burst_id import calculate_burstid
from burst2safe.safe import Safe


def burst_info_from_local(
    tiff_path: Path, xml_path: Path, slc_name: str, swath: str, polarization: str, burst_index: int
) -> utils.BurstInfo:
    """Create a BurstInfo object from a local copy of the burst extractor output

    Args:
        xml_path: The path to the XML file
        swath: The name of the swath
        burst_index: The index of the burst within the swath
    """
    extractor_url = 'https://sentinel1-burst.asf.alaska.edu'
    burst_url_base = f'{extractor_url}/{slc_name}/{swath}/{polarization}/{burst_index}'
    data_url = f'{burst_url_base}.tiff'
    metadata_url = f'{burst_url_base}.xml'

    manifest = utils.get_subxml_from_metadata(xml_path, 'manifest', swath, polarization)
    xml_orbit_path = './/{*}metadataObject[@ID="measurementOrbitReference"]/metadataWrap/xmlData/{*}orbitReference'
    meta_orbit = manifest.find(xml_orbit_path)
    abs_orbit_start, abs_orbit_stop = [int(x.text) for x in meta_orbit.findall('{*}orbitNumber')]  # type: ignore[arg-type]
    rel_orbit_start, rel_orbit_stop = [int(x.text) for x in meta_orbit.findall('{*}relativeOrbitNumber')]  # type: ignore[arg-type]
    direction = meta_orbit.find('{*}extension/{*}orbitProperties/{*}pass').text.upper()

    product = utils.get_subxml_from_metadata(xml_path, 'product', swath, polarization)
    sensing_time_str = product.findall('swathTiming/burstList/burst')[burst_index].find('sensingTime').text
    anx_time_str = meta_orbit.find('{*}extension/{*}orbitProperties/{*}ascendingNodeTime').text
    assert sensing_time_str is not None
    assert anx_time_str is not None
    burst_id, rel_orbit = calculate_burstid(sensing_time_str, anx_time_str, rel_orbit_start, rel_orbit_stop, swath)
    info = utils.BurstInfo(
        granule='',
        slc_granule=slc_name,
        swath=swath,
        polarization=polarization,
        burst_id=burst_id,
        burst_index=burst_index,
        direction=direction,
        absolute_orbit=abs_orbit_start,
        relative_orbit=rel_orbit_start,
        date=None,
        data_url=data_url,
        data_path=tiff_path,
        metadata_url=metadata_url,
        metadata_path=xml_path,
    )
    info.add_shape_info()
    info.add_start_stop_utc()
    date_format = '%Y%m%dT%H%M%S'
    start_utc_str = datetime.strftime(cast(datetime, info.start_utc), date_format)
    info.date = datetime.strptime(datetime.strftime(cast(datetime, info.start_utc), date_format), date_format)
    info.granule = f'S1_{burst_id}_{swath}_{start_utc_str}_{polarization}_{slc_name.split("_")[-1]}-BURST'
    return info


def load_burst_infos(slc_dict: dict) -> list[utils.BurstInfo]:
    """Load the burst infos from the SLC tree

    Args:
        slc_dict: SLC tree dict with format: {slc_name: {swath: {polarization: {burst_index: {DATA:tiff_path, METADATA:xml_path}}}}}
                Can contain an abitrary number of bursts as long as they are a valid merge group

    Returns:
        A list of BurstInfo objects
    """
    valid_swaths = ['IW1', 'IW2', 'IW3', 'EW1', 'EW2', 'EW3', 'EW4', 'EW5']
    valid_pols = ['VV', 'VH', 'HV', 'HH']
    burst_infos = []
    for slc_name in slc_dict:
        slc_name = slc_name.upper()
        swath_dict = slc_dict[slc_name]

        for swath in swath_dict:
            swath = swath.upper()
            if swath not in valid_swaths:
                raise ValueError(f'Invalid swath: {swath}')

            polarization_dict = swath_dict[swath]

            for polarization in polarization_dict:
                polarization = polarization.upper()
                if polarization not in valid_pols:
                    raise ValueError(f'Invalid polarization: {polarization}')

                burst_dict = polarization_dict[polarization]
                for burst_index in burst_dict:
                    burst_info = burst_info_from_local(
                        Path(burst_dict[burst_index]['DATA']),
                        Path(burst_dict[burst_index]['METADATA']),
                        slc_name,
                        swath,
                        polarization,
                        int(burst_index),
                    )
                    burst_infos.append(burst_info)

    return burst_infos


def local2safe(
    slc_dict: dict,
    all_anns: bool = False,
    keep_files: bool = False,
    work_dir: Optional[Union[Path, str]] = None,
) -> Path:
    """Convert a set of burst granules to the ESA SAFE format using local files

    Args:
        slc_dict: SLC tree dict with format: {slc_name: {swath: {polarization: {burst_index: {DATA:tiff_path, METADATA:xml_path}}}}}
                  Can contain an abitrary number of bursts as long as they are a valid merge group
        all_anns: Include product annotation files for all swaths, regardless of included bursts
        keep_files: Keep the intermediate files
        work_dir: The directory to store temporary files

    Returns:
        The path to the created SAFE
    """
    work_dir = utils.optional_wd(work_dir)

    burst_infos = load_burst_infos(slc_dict)
    print(f'Found {len(burst_infos)} burst(s).')

    print('Check burst group validity...')
    Safe.check_group_validity(burst_infos)
    print('Creating SAFE...')

    safe = Safe(burst_infos, all_anns, work_dir)
    safe_path = safe.create_safe()
    print('SAFE created!')

    if not keep_files:
        safe.cleanup()

    return safe_path


def main():
    """Entrypoint for the local2safe script
    Example:

    local2safe /path/to/slc_tree.json --all_anns --work_dir /path/to/work_dir
    """
    parser = argparse.ArgumentParser(description='Generate a SAFE file from local burst extractor outputs')
    parser.add_argument(
        'json_tree_path',
        type=Path,
        help='Path to the SLC tree JSON file with format: {slc_name: {swath: {polarization: {burst_index: {DATA:tiff_path, METADATA:xml_path}}}}}',
    )
    parser.add_argument('--all_anns', action='store_true', help='Include all annotations')
    parser.add_argument('--work_dir', type=Path, help='The directory to store temporary files')
    args = parser.parse_args()
    slc_tree = json.loads(args.json_tree_path.read_text())

    local2safe(
        slc_tree,
        args.all_anns,
        args.work_dir,
    )
