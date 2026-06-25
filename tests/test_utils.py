from collections import namedtuple
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import lxml
import lxml.etree as ET
import pytest

from burst2safe import utils


def test_add_shape_info(tmp_path, burst_info1):
    tmp_burst = deepcopy(burst_info1)
    tmp_burst.length = None
    tmp_burst.width = None
    tmp_burst.add_shape_info()
    assert tmp_burst.length == 1508
    assert tmp_burst.width == 25470


def test_add_start_stop_utc(burst_info1):
    test_elem = ET.Element('product')
    az_time_interval = ET.SubElement(test_elem, 'azimuthTimeInterval')
    az_time_interval.text = '1'
    start = datetime.fromisoformat('2020-01-01T00:00:00')
    for i in range(9):
        burst_elem = ET.SubElement(test_elem, 'burst')
        az_time = ET.SubElement(burst_elem, 'azimuthTime')
        burst_time = (start + timedelta(seconds=i * 5)).isoformat()
        az_time.text = burst_time

    with patch('burst2safe.utils.get_subxml_from_metadata', return_value=test_elem):
        tmp_burst = deepcopy(burst_info1)
        tmp_burst.burst_index = 2
        tmp_burst.length = 10
        tmp_burst.add_start_stop_utc()
        assert tmp_burst.start_utc == datetime.fromisoformat('2020-01-01T00:00:10')
        assert tmp_burst.stop_utc == datetime.fromisoformat('2020-01-01T00:00:19')


def test_create_burst_info(tmp_path, search_result1):
    burst_granule = 'S1_136231_IW2_20200604T022312_VV_7C85-BURST'
    slc_granule = 'S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85'
    burst = utils.create_burst_info(search_result1, tmp_path)

    assert burst.granule == burst_granule
    assert burst.slc_granule == slc_granule
    assert burst.swath == 'IW2'
    assert burst.polarization == 'VV'
    assert burst.burst_id == 123456
    assert burst.burst_index == 7
    assert burst.direction == 'ASCENDING'
    assert burst.absolute_orbit == 123
    assert burst.relative_orbit == 456
    assert burst.data_url == 'https://example.com/foo.zip'
    assert burst.metadata_url == 'https://example.com/foo.xml'
    assert burst.data_path == tmp_path / f'{burst_granule}.tiff'
    assert burst.metadata_path == tmp_path / f'{slc_granule}_VV.xml'


def test_get_burst_infos(burst_info1):
    with patch.object(utils, 'create_burst_info') as mock_create:
        mock_create.return_value = burst_info1
        infos = utils.get_burst_infos(['granule1', 'granule2'], Path())

    assert isinstance(infos, list)
    assert len(infos) == 2


def test_sort_burst_infos():
    StubInfo = namedtuple('StubInfo', ['swath', 'polarization', 'burst_id'])
    info1 = StubInfo('IW1', 'VV', 1)
    info2 = StubInfo('IW1', 'HH', 1)
    info3 = StubInfo('IW2', 'VV', 1)
    info4 = StubInfo('IW2', 'HH', 1)
    info5 = StubInfo('IW1', 'VV', 2)
    info6 = StubInfo('IW1', 'HH', 2)
    info7 = StubInfo('IW2', 'VV', 2)
    info8 = StubInfo('IW2', 'HH', 2)
    infos = [info1, info3, info5, info2, info8, info4, info6, info7]

    sorted_infos = utils.sort_burst_infos(infos)  # type: ignore[arg-type]

    assert sorted_infos['IW1']['VV'] == [info1, info5]
    assert sorted_infos['IW1']['HH'] == [info2, info6]
    assert sorted_infos['IW2']['VV'] == [info3, info7]
    assert sorted_infos['IW2']['HH'] == [info4, info8]


def test_optional_wd():
    wd = utils.optional_wd()
    assert isinstance(wd, Path)
    assert wd == Path.cwd()

    existing_dir = 'working'
    wd = utils.optional_wd(existing_dir)
    assert isinstance(wd, Path)
    assert wd == Path(existing_dir).resolve()


def test_calculate_crc16(tmp_path, test_data_dir):
    manifest_file = test_data_dir / 'manifest_7C85.safe'
    crc = utils.calculate_crc16(manifest_file)
    assert crc == '7C85'


@pytest.mark.parametrize('xml_type, swath', [('product', 'IW1'), ('noise', 'IW2'), ('calibration', 'IW3')])
def test_get_subxml_from_metadata(xml_type, swath, test_data1_xml):
    result = utils.get_subxml_from_metadata(test_data1_xml, xml_type, swath, 'VV')
    assert isinstance(result, lxml.etree._Element)
    assert result.find('adsHeader/swath').text == swath  # type: ignore[union-attr]
    assert result.find('adsHeader/polarisation').text == 'VV'  # type: ignore[union-attr]
    assert result.tag == 'content'


def test_get_subxml_from_metadata_invalid(test_data1_xml):
    with pytest.raises(ValueError):
        utils.get_subxml_from_metadata(test_data1_xml, 'invalid', 'IW1', 'VV')

    result = utils.get_subxml_from_metadata(test_data1_xml, 'product', 'invalid', 'VV')
    assert result is None

    result = utils.get_subxml_from_metadata(test_data1_xml, 'product', 'IW1', 'invalid')
    assert result is None


def test_get_subxml_from_metadata_manifest(test_data1_xml):
    result = utils.get_subxml_from_metadata(test_data1_xml, 'manifest')
    assert isinstance(result, lxml.etree._Element)
    assert result.tag == '{urn:ccsds:schema:xfdu:1}XFDU'


def test_flatten():
    assert utils.flatten([[1, 2], [3, 4], [5, 6]]) == [1, 2, 3, 4, 5, 6]


def test_drop_duplicates():
    assert utils.drop_duplicates([1, 2, 3, 4, 4, 5, 6, 6]) == [1, 2, 3, 4, 5, 6]
