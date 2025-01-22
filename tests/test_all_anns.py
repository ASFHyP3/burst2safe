import lxml.etree as ET
import pytest

from burst2safe.burst2safe import burst2safe


@pytest.mark.integration()
def test_all_anns(tmp_path):
    safe_path = burst2safe(granules=['S1_088916_IW3_20240605T140826_VV_36F4-BURST'], all_anns=True, work_dir=tmp_path)
    products = list((safe_path / 'annotation').glob('*.xml'))
    assert len(products) == 3

    for swath in ['iw1', 'iw2']:
        prod = [p for p in products if swath in p.name][0]
        xml = ET.parse(prod).getroot()

        burst_list = xml.find('.//burstList')
        assert burst_list is not None
        assert burst_list.attrib['count'] == '0'
        assert len(burst_list) == 0

        geolocation_grid = xml.find('.//geolocationGridPointList')
        assert geolocation_grid is not None
        assert geolocation_grid.attrib['count'] == '0'
        assert len(geolocation_grid) == 0

    prod_real = [p for p in products if 'iw3' in p.name][0]
    xml_real = ET.parse(prod_real).getroot()

    burst_list = xml_real.find('.//burstList')
    assert burst_list is not None
    assert int(burst_list.attrib['count']) > 0
    assert len(burst_list) > 0

    geolocation_grid = xml_real.find('.//geolocationGridPointList')
    assert geolocation_grid is not None
    assert int(geolocation_grid.attrib['count']) > 0
    assert len(geolocation_grid) > 0
