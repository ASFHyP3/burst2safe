from collections import namedtuple
from unittest.mock import patch

import pytest

from burst2safe import search


@pytest.fixture()
def product():
    properties = {
        'burst': {
            'relativeBurstID': 10,
            'fullBurstID': '001_000010_IW1',
        },
        'polarization': 'VV',
        'orbit': '000001',
    }
    BurstProduct = namedtuple('BurstProduct', ['properties'])
    return BurstProduct(properties=properties)


def test_add_surrounding_bursts(product):
    with patch('burst2safe.search.asf_search.search') as mock_search:
        search.add_surrounding_bursts([product], 3)
        burst_ids = ['001_000009_IW1', '001_000010_IW1', '001_000011_IW1']
        mock_search.assert_called_once_with(
            dataset='SLC-BURST', absoluteOrbit=1, polarization='VV', fullBurstID=burst_ids
        )

    with patch('burst2safe.search.asf_search.search') as mock_search:
        search.add_surrounding_bursts([product], 4)
        burst_ids = ['001_000009_IW1', '001_000010_IW1', '001_000011_IW1', '001_000012_IW1']
        mock_search.assert_called_once_with(
            dataset='SLC-BURST', absoluteOrbit=1, polarization='VV', fullBurstID=burst_ids
        )


def test_sanitize_group_search_inputs():
    pols, swaths = search.sanitize_group_search_inputs()
    assert pols == ['VV']
    assert swaths == [None]

    assert search.sanitize_group_search_inputs(polarizations=['HH'])[0] == ['HH']
    assert search.sanitize_group_search_inputs(swaths=['IW2'])[1] == ['IW2']

    with pytest.raises(ValueError, match='Invalid polarization*'):
        search.sanitize_group_search_inputs(polarizations=['VV', 'BB'])

    with pytest.raises(ValueError, match='Invalid swath*'):
        search.sanitize_group_search_inputs(swaths=['IW1'], mode='EW')

    with pytest.raises(ValueError, match='Invalid swath*'):
        search.sanitize_group_search_inputs(swaths=['EW1'], mode='IW')
