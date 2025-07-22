"""Calculate the unique burst ID of a Sentinel-1 burst using ESA's convention.
Created by Ben Barton for ASF's Sentinel-1 Burst ingest utility.

Source:
https://github.com/asfadmin/rain/blob/a5cd0709d46f93de1060ddb3fc7673097a9a966d/code/util/burst.py
"""

from datetime import datetime, timedelta

import numpy as np
from dateutil import parser as dateparser


# These constants are from the Sentinel-1 Level 1 Detailed Algorithm Definition PDF
# MPC Nom: DI-MPC-IPFDPM, MPC Ref: MPC-0307, Issue/Revision: 2/4, Table 9-7
NOMINAL_ORBITAL_DURATION = timedelta(seconds=12 * 24 * 3600 / 175)
PREAMBLE_LENGTH_IW = timedelta(seconds=2.299849)
PREAMBLE_LENGTH_EW = timedelta(seconds=2.299970)
BEAM_CYCLE_TIME_IW = timedelta(seconds=2.758273)
BEAM_CYCLE_TIME_EW = timedelta(seconds=3.038376)
MODE_TIMING = {
    'EW': (
        PREAMBLE_LENGTH_EW,
        BEAM_CYCLE_TIME_EW,
    ),
    'IW': (
        PREAMBLE_LENGTH_IW,
        BEAM_CYCLE_TIME_IW,
    ),
}


class InvalidModeNameError(Exception):
    pass


def _get_mode_timing(mode_name: str) -> tuple:
    """Get the timing parameters for a given mode.

    Args:
        mode_name: Mode name (EW,IW) or subswath name (EW2 etc)

    Returns:
        PREAMBLE_LENGTH, BEAM_CYCLE_TIME for passed mode
    """
    try:
        return MODE_TIMING[mode_name[:2].upper()]
    except KeyError as e:
        raise InvalidModeNameError(e)


def _calc_start_subsw1(start_offsets: list, swath_num: int, sensing_time: datetime) -> datetime:
    """Calculates the start time of the #1 subswath given any subswath in a burst.

    Args:
        start_offsets: list of start offsets, times since IW1
        swath_num: swath number.
        sensing_time: datetime of the sensing time of the first input line of this burst [UTC]

    Returns:
        datetime of the start of the first subswath
    """
    offset = start_offsets[swath_num - 1]
    start_subsw1 = sensing_time + timedelta(seconds=offset)
    return start_subsw1


def _calc_esa_burstid(
    time_since_anx: timedelta, orbit_number_start: int, preamble_len: timedelta, beam_cycle_time: timedelta
) -> int:
    """Calculates the ESA Burst ID given the given parameters.
    Extracted from the opera function for the purposes of reuse IW & EW

    Args:
        time_since_anx: time since ascending node crossing
        orbit_number_start: Relative orbit number at the start of the acquisition
        preamble_len: Preamble length
        beam_cycle_time: Beam cycle time

    Returns:
        ESA Burst ID
    """
    # Eq. 9-89: ∆tb = tb − t_anx + (r - 1)T_orb
    # tb: mid-burst sensing time (sensing_time)
    # t_anx: ascending node time (ascending_node_dt)
    # r: relative orbit number   (relative_orbit_start)
    dt_b = time_since_anx + (orbit_number_start - 1) * NOMINAL_ORBITAL_DURATION

    # Eq. 9-91 :   1 + floor((∆tb − T_pre) / T_beam )
    esa_burst_id = 1 + int(np.floor((dt_b - preamble_len) / beam_cycle_time))
    return esa_burst_id


def calculate_burstid(
    sensing_time_iso: str,
    anx_time_iso: str,
    orbit_number_start: int,
    orbit_number_stop: int,
    subswath: str,
) -> tuple:
    """Calculate the unique burst ID of a burst. And return the
    correct orbit number.

    Accounts for equator crossing frames, where the current track number of
    a burst may change mid-frame. Uses the ESA convention defined in the
    Sentinel-1 Level 1 Detailed Algorithm Definition.

    Args:
        sensing_time_iso: Iso date of sensing time of the first input line of this burst [UTC]
        The XML tag is sensingTime in the annotation file.
        anx_time_iso: Time of the ascending node prior to the start of the scene.
        orbit_number_start: Relative orbit number at the start of the acquisition, from 1-175.
        orbit_number_stop: Relative orbit number at the end of the acquisition.
        subswath: Name of the subswath of the burst (not case sensitive).

    Returns:
        burst ID, orbit number

    Notes:
    The `orbit_number_start` and `orbit_number_stop` parameters are used to determine if the
    scene crosses the equator. They are the same if the frame does not cross
    the equator.

    References:
    ESA Sentinel-1 Level 1 Detailed Algorithm Definition
    https://sentinels.copernicus.eu/documents/247904/1877131/S1-TN-MDA-52-7445_Sentinel-1+Level+1+Detailed+Algorithm+Definition_v2-4.pdf/83624863-6429-cfb8-2371-5c5ca82907b8

    Stolen from https://github.com/opera-adt/s1-reader/blob/main/src/s1reader/s1_burst_id.py
    """
    sensing_dt = dateparser.parse(sensing_time_iso)
    asc_node_dt = dateparser.parse(anx_time_iso)
    mode = subswath[0:2].upper()
    swath_num = int(subswath[-1])
    pream, beamtime = _get_mode_timing(mode)

    # Since we only have access to the current subswath, we need to use the
    # burst-to-burst times to figure out
    #   1. if IW1 crossed the equator, and
    #   2. The mid-burst sensing time for IW2
    # IW1 -> IW2 takes ~0.83220 seconds
    # IW2 -> IW3 takes ~1.07803 seconds
    # IW3 -> IW1 takes ~0.84803 seconds
    # EW1 -> EW2 ~0.6826778977095476
    # EW2 -> EW3 ~0.558731729405626
    # EW3 -> EW4 ~0.6123389197595133
    # EW4 -> EW5 ~0.5653802400407812
    # EW5 -> EW1 ~0.619247213084539

    burst_times = {'IW': [0.832, 1.078, 0.848], 'EW': [0.683, 0.559, 0.612, 0.565, 0.619]}

    if mode == 'IW':
        iw1_start_offsets = [
            0,
            -burst_times[mode][0],
            -burst_times[mode][0] - burst_times[mode][1],
        ]

        start_iw1 = _calc_start_subsw1(iw1_start_offsets, swath_num, sensing_dt)

        # Middle of IW2 is the middle of the entire burst:
        start_iw1_to_mid_iw2 = burst_times[mode][0] + burst_times[mode][1] / 2
        mid_iw2 = start_iw1 + timedelta(seconds=start_iw1_to_mid_iw2)

        has_anx_crossing = (orbit_number_stop == orbit_number_start + 1) or (
            orbit_number_stop == 1 and orbit_number_start == 175
        )

        time_since_anx_iw1 = start_iw1 - asc_node_dt
        time_since_anx = mid_iw2 - asc_node_dt

        if (time_since_anx_iw1 - NOMINAL_ORBITAL_DURATION).total_seconds() < 0:
            # Less than a full orbit has passed
            orbit_number = orbit_number_start
        else:
            orbit_number = orbit_number_stop
            # Additional check for scenes which have a given ascending node
            # that's more than 1 orbit in the past
            if not has_anx_crossing:
                time_since_anx = time_since_anx - NOMINAL_ORBITAL_DURATION

        esa_burst_id = _calc_esa_burstid(time_since_anx, orbit_number_start, pream, beamtime)

    elif mode == 'EW':
        # EWs are always high-latitude and don't cross equator. We can always
        # use start orbit.
        orbit_number = orbit_number_start

        ew1_start_offsets = [
            0,
            -burst_times[mode][0],
            -burst_times[mode][0] - burst_times[mode][1],
            -burst_times[mode][0] - burst_times[mode][1] - burst_times[mode][2],
            -burst_times[mode][0] - burst_times[mode][1] - burst_times[mode][2] - burst_times[mode][3],
        ]

        start_ew1 = _calc_start_subsw1(ew1_start_offsets, swath_num, sensing_dt)

        # Middle of EW3 is the middle of the entire burst:
        start_ew1_to_mid_ew3 = burst_times[mode][0] + burst_times[mode][1] + burst_times[mode][2] / 2
        mid_ew3 = start_ew1 + timedelta(seconds=start_ew1_to_mid_ew3)

        time_since_anx = mid_ew3 - asc_node_dt

        esa_burst_id = _calc_esa_burstid(time_since_anx, orbit_number_start, pream, beamtime)

    else:
        raise InvalidModeNameError(f'Invalid mode name: {mode}')

    return esa_burst_id, orbit_number
