import warnings
from collections.abc import Iterable
from datetime import datetime
from itertools import product
from typing import List, Optional, Tuple

import asf_search
import numpy as np
from asf_search.Products.S1BurstProduct import S1BurstProduct
from shapely.geometry import Polygon


warnings.filterwarnings('ignore')


def find_granules(granules: Iterable[str]) -> List[S1BurstProduct]:
    """Find granules by name using ASF Search.

    Args:
        granules: A list of granule names

    Returns:
        A list of S1BurstProduct objects
    """
    results = asf_search.search(product_list=granules)
    found_granules = [result.properties['fileID'] for result in results]
    missing_granules = list(set(granules) - set(found_granules))
    if missing_granules:
        granule_str = ', '.join(missing_granules)
        raise ValueError(f'Failed to find granule(s) {granule_str}. Check search parameters on Vertex.')
    return list(results)


def add_surrounding_bursts(bursts: List[S1BurstProduct], min_bursts: int) -> List[S1BurstProduct]:
    """Add bursts to the list to ensure each swath has at least `min_bursts` bursts.
    All bursts must be from the same absolute orbit, swath, and polarization.

    Args:
        bursts: A list of S1BurstProduct objects
        min_bursts: The minimum number of bursts

    Returns:
        An extended list of S1BurstProduct objects
    """
    ids = [int(burst.properties['burst']['relativeBurstID']) for burst in bursts]
    relative_orbit, _, swath = bursts[0].properties['burst']['fullBurstID'].split('_')
    polarization = bursts[0].properties['polarization']
    absolute_orbit = int(bursts[0].properties['orbit'])

    min_id, max_id = min(ids), max(ids)
    extra = np.floor((min_bursts - (max_id - min_id + 1)) / 2).astype(int)
    min_id -= extra
    max_id += extra
    if max_id - min_id + 1 != min_bursts:
        max_id += 1

    full_burst_ids = [f'{relative_orbit}_{id:06}_{swath}' for id in range(min_id, max_id + 1)]
    search_results = asf_search.search(
        dataset=asf_search.constants.DATASET.SLC_BURST,
        absoluteOrbit=absolute_orbit,
        polarization=polarization,
        fullBurstID=full_burst_ids,
    )
    return search_results


def get_burst_group(
    search_results: List[S1BurstProduct],
    pol: str,
    swath: Optional[str] = None,
    orbit: Optional[int] = None,
    min_bursts: int = 0,
) -> List[S1BurstProduct]:
    """Find a group of bursts with the same polarization, swath and optionally orbit.
    Add surrounding bursts if the group is too small.

    Args:
        search_results: A list of S1BurstProduct objects
        pol: The polarization to search for
        swath: The swath to search for
        orbit: The absolute orbit number of the bursts
        min_bursts: The minimum number of bursts per swath

    Returns:
        An updated list of S1BurstProduct objects
    """
    params = []
    if orbit:
        search_results = [result for result in search_results if result.properties['orbit'] == orbit]
        params.append(f'orbit {orbit}')
    if swath:
        search_results = [result for result in search_results if result.properties['burst']['subswath'] == swath]
        params.append(f'swath {swath}')
    search_results = [result for result in search_results if result.properties['polarization'] == pol]
    params.append(f'polarization {pol}')
    param_str = ', '.join(params)

    if not search_results:
        raise ValueError(f'No bursts found for {param_str}. Check search parameters on Vertex.')

    if len(search_results) < min_bursts:
        search_results = add_surrounding_bursts(search_results, min_bursts)

    if len(search_results) < min_bursts:
        raise ValueError(f'Less than {min_bursts} bursts found for {param_str}. Check search parameters on Vertex.')

    return search_results


def sanitize_group_search_inputs(
    polarizations: Optional[list] = None, swaths: Optional[list] = None, mode: str = 'IW'
) -> Tuple[list[str], list[str]]:
    """Sanitize inputs for group search.

    Args:
        polarizations: List of polarizations to include (default: VV)
        swaths: List of swaths to include (default: all)
        mode: The collection mode to use (IW or EW) (default: IW)

    Returns:
        A tuple of sanitized polarizations and swaths
    """
    if polarizations is None:
        polarizations = ['VV']
    bad_pols = set(polarizations) - set(['VV', 'VH', 'HV', 'HH'])
    if bad_pols:
        raise ValueError(f'Invalid polarizations: {" ".join(bad_pols)}')

    if mode not in ['IW', 'EW']:
        raise ValueError('Invalid mode: must be IW or EW')
    elif mode == 'IW':
        valid_swaths = ['IW1', 'IW2', 'IW3']
    elif mode == 'EW':
        valid_swaths = ['EW1', 'EW2', 'EW3', 'EW4', 'EW5']

    if swaths is None:
        swaths = [None]
    else:
        bad_swaths = set(swaths) - set(valid_swaths)
        if bad_swaths:
            raise ValueError(f'Invalid swaths: {" ".join(bad_swaths)}')

    return polarizations, swaths


def add_missing_bursts(
    search_results: List[S1BurstProduct],
    polarizations: List[str],
    swaths: List[str],
    min_bursts: int,
    use_relative_orbit: bool,
) -> List[S1BurstProduct]:
    """Add missing bursts to the search results to ensure each swath/pol combo has at least `min_bursts` bursts.

    Args:
        search_results: A list of S1BurstProduct objects
        polarizations: List of polarizations to include
        swaths: List of swaths to include
        min_bursts: The minimum number of bursts per swath (default: 1)
        use_relative_orbit: Use relative orbit number instead of absolute orbit number (default: False)

    Returns:
        A list of S1BurstProduct objects
    """
    grouped_results = []
    if use_relative_orbit:
        absolute_orbits = list(set([int(result.properties['orbit']) for result in search_results]))
        group_definitions: product = product(polarizations, swaths, absolute_orbits)
    else:
        group_definitions = product(polarizations, swaths)

    for group_definition in group_definitions:
        # false-positive mypy error: "get_burst_group" gets multiple values for keyword argument "min_bursts"
        # https://github.com/python/mypy/issues/6799
        sub_results = get_burst_group(search_results, *group_definition, min_bursts=min_bursts)  # type: ignore[misc]
        grouped_results.extend(sub_results)
    return grouped_results


def find_group(
    orbit: Optional[int],
    footprint: Polygon,
    polarizations: Optional[list[str]] = None,
    swaths: Optional[list[str]] = None,
    mode: str = 'IW',
    min_bursts: int = 1,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    use_relative_orbit: bool = False,
) -> List[S1BurstProduct]:
    """Find burst groups using ASF Search.

    Args:
        orbit: The absolute orbit number of the bursts
        footprint: The bounding box of the bursts
        polarizations: List of polarizations to include (default: VV)
        swaths: List of swaths to include (default: all)
        mode: The collection mode to use (IW or EW) (default: IW)
        min_bursts: The minimum number of bursts per swath (default: 1)
        start_date: The start date for relative orbit search
        end_date: The end date for relative orbit search
        use_relative_orbit: Use relative orbit number instead of absolute orbit number (default: False)

    Returns:
        A list of S1BurstProduct objects
    """
    if use_relative_orbit and not (start_date and end_date):
        raise ValueError('You must provide start and end dates when using relative orbit number.')

    polarizations, swaths = sanitize_group_search_inputs(polarizations, swaths, mode)
    opts = dict(dataset=asf_search.constants.DATASET.SLC_BURST, intersectsWith=footprint.wkt, beamMode=mode)
    if use_relative_orbit:
        assert start_date is not None
        assert end_date is not None
        opts['relativeOrbit'] = orbit
        opts['start'] = (f'{start_date.strftime("%Y-%m-%d")}T00:00:00Z',)
        opts['end'] = (f'{end_date.strftime("%Y-%m-%d")}T23:59:59Z',)
    else:
        opts['absoluteOrbit'] = orbit
    search_results = asf_search.geo_search(**opts)

    final_results = add_missing_bursts(search_results, polarizations, swaths, min_bursts, use_relative_orbit)
    return final_results


def find_bursts(
    granules: Optional[Iterable[str]] = None,
    orbit: Optional[int] = None,
    footprint: Optional[Polygon] = None,
    polarizations: Optional[list[str]] = None,
    swaths: Optional[list[str]] = None,
    mode: str = 'IW',
    min_bursts: int = 1,
) -> list[S1BurstProduct]:
    """Find bursts using ASF Search.

    Args:
        granules: A list of burst granules to convert to SAFE
        orbit: The absolute orbit number of the bursts
        footprint: The geographic extent of the bursts
        polarizations: List of polarizations to include
        swaths: List of swaths to include
        mode: The collection mode to use (IW or EW) (default: IW)
        min_bursts: The minimum number of bursts per swath (default: 1)
    """
    if granules:
        print('Using granule search...')
        results = find_granules(granules)
    elif orbit and footprint:
        print('Using burst group search...')
        results = find_group(orbit, footprint, polarizations, swaths, mode, min_bursts)
    else:
        raise ValueError(
            'You must provide either a list of granules or minimum set of group parameters (orbit, and footprint).'
        )
    return results
