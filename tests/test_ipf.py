import shutil
from pathlib import Path

import asf_search
import pytest

from burst2safe.safe import Safe
from burst2safe.utils import get_burst_infos
from helpers import create_test_geotiff, validate_xml


BURSTS = [
    ('S1_249405_IW2_20150318T170523_VV_DBBC-BURST', '2.37'),
    ('S1_249405_IW2_20150610T170527_VV_68B3-BURST', '2.43'),
    ('S1_249405_IW2_20160229T170529_VV_61EF-BURST', '2.60'),
    ('S1_249405_IW2_20180624T170504_VV_A271-BURST', '2.90'),
    ('S1_249405_IW2_20220317T170605_VV_F3AB-BURST', '3.40'),
    ('S1_249405_IW2_20240610T170617_VV_9A40-BURST', '3.71'),
    ('S1_249405_IW2_20241113T170616_VV_17D6-BURST', '3.80'),
]


@pytest.mark.integration()
@pytest.mark.parametrize('version,burst', BURSTS)
def test_versions(version, burst, tmp_path):
    products = asf_search.granule_search([burst])
    burst_infos = get_burst_infos(products, tmp_path)

    ipf_dir = Path(__file__).parent / 'test_data' / 'ipf'
    shutil.copy(ipf_dir / burst_infos[0].metadata_path.name, burst_infos[0].metadata_path)

    [info.add_shape_info() for info in burst_infos]
    [info.add_start_stop_utc() for info in burst_infos]

    create_test_geotiff(burst_infos[0].data_path, 'cfloat', shape=(burst_infos[0].length, burst_infos[0].width, 1))
    safe = Safe(burst_infos, work_dir=tmp_path)
    safe.create_safe()

    xsd_dir = Path(__file__).parent.parent / 'src' / 'burst2safe' / 'data' / f'support_{version.replace(".", "")}'
    support_source_dir = safe.support_dir
    assert xsd_dir.name == support_source_dir.name

    support_dir = safe.safe_path / 'support'

    assert safe.kml is not None
    validate_xml(safe.kml.path, support_dir / 's1-map-overlay.xsd')
    assert safe.preview.path is not None
    validate_xml(safe.preview.path, support_dir / 's1-product-preview.xsd')
    for swath in safe.swaths:
        validate_xml(swath.product.path, support_dir / 's1-level-1-product.xsd')
        validate_xml(swath.noise.path, support_dir / 's1-level-1-noise.xsd')
        validate_xml(swath.calibration.path, support_dir / 's1-level-1-calibration.xsd')
        if swath.has_rfi:
            validate_xml(swath.rfi.path, support_dir / 's1-level-1-rfi.xsd')
