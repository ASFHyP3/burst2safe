"""Soucre: https://github.com/asfadmin/rain/blob/devel/tests/test_util_burst.py"""

from pytest import raises

from burst2safe import burst_id


CORRECT_GRANULE_NAME = 'S1_032322_IW2_20230422T170310_VV_ABCD'

EQUATORCROSSER = {
    'inputs': {
        'anx_time': '2023-04-22T17:03:10.235250',
        'azimuthAnxTime': float('6.208265985771300e+03'),
        'sensingTime': '2023-04-22T18:46:39.515927',
        'orbit_number_abs_start': 48213,
        'orbit_number_abs_stop': 48213,
        'orbit_number_rel_start': 16,
        'orbit_number_rel_stop': 16,
        'subswath': 'IW2',
    },
    'results': {
        'burstid_abs': 103556001,
        'burstid_rel': 32322,
        'orbit_num_abs': 48213,
        'orbit_num_rel': 16,
    },
}
EW = {
    'inputs': {
        'anx_time': '2022-10-10T14:02:11.848637',
        'azimuthAnxTime': float('1.816083970564404e+03'),
        'sensingTime': '2022-10-10T14:32:29.345783',
        'orbit_number_abs_start': 45381,
        'orbit_number_abs_stop': 45381,
        'orbit_number_rel_start': 159,
        'orbit_number_rel_stop': 159,
        'subswath': 'EW5',
    },
    'results': {
        'burstid_abs': 88487688,
        'burstid_rel': 308684,
        'orbit_num_abs': 45381,
        'orbit_num_rel': 159,
    },
}


def test_get_mode_timing():
    d = burst_id._get_mode_timing('EW1')
    assert d[0] == burst_id.PREAMBLE_LENGTH_EW
    assert d[1] == burst_id.BEAM_CYCLE_TIME_EW
    d = burst_id._get_mode_timing('IW2')
    assert d[0] == burst_id.PREAMBLE_LENGTH_IW
    assert d[1] == burst_id.BEAM_CYCLE_TIME_IW


def test_get_mode_timing_fail():
    with raises(burst_id.InvalidModeNameError):
        burst_id._get_mode_timing('NO')


def burstid_calc(vals: dict):
    bid, orbitnum = burst_id.calculate_burstid(
        vals['inputs']['sensingTime'],
        vals['inputs']['anx_time'],
        vals['inputs']['orbit_number_abs_start'],
        vals['inputs']['orbit_number_abs_stop'],
        vals['inputs']['subswath'],
    )
    assert bid == vals['results']['burstid_abs']
    assert orbitnum == vals['results']['orbit_num_abs']

    bid, orbitnum = burst_id.calculate_burstid(
        vals['inputs']['sensingTime'],
        vals['inputs']['anx_time'],
        vals['inputs']['orbit_number_rel_start'],
        vals['inputs']['orbit_number_rel_stop'],
        vals['inputs']['subswath'],
    )
    assert bid == vals['results']['burstid_rel']
    assert orbitnum == vals['results']['orbit_num_rel']


def test_calculate_burstid_opera_eqcross():
    burstid_calc(EQUATORCROSSER)


def test_calculate_burstid_opera_ew():
    burstid_calc(EW)


def test_calculate_burstid_opera_badsubsw():
    bad: dict = EQUATORCROSSER.copy()
    bad['inputs']['subswath'] = 'NO8'
    with raises(burst_id.InvalidModeNameError):
        burstid_calc(bad)
