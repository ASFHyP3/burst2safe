from collections import namedtuple
from datetime import datetime
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from burst2safe.product import GeoPoint
from burst2safe.swath import Swath


CREATION_TIME = datetime.now()


class TestSwath:
    def test_init(self, burst_infos):
        safe_path = Path('./S1A_IW_SLC__1SDV_20240408T015045_20240408T015113_053336_06778C_CB5D.SAFE')
        swath = Swath(burst_infos[::-1], safe_path, '003.71', CREATION_TIME, 1)
        assert swath.burst_infos == burst_infos

        name = 's1a-iw2-slc-vv-20240408t015108-20240408t015114-053336-06778c-001'

        assert swath.name == name
        assert swath.measurement_name.name == f'{name}.tiff'
        assert swath.measurement_name.parent.name == 'measurement'
        assert swath.product_name.name == f'{name}.xml'
        assert swath.product_name.parent.name == 'annotation'
        assert swath.noise_name.name == f'noise-{name}.xml'
        assert swath.noise_name.parent.name == 'calibration'
        assert swath.calibration_name.name == f'calibration-{name}.xml'
        assert swath.calibration_name.parent.name == 'calibration'

    def test_check_burst_group_validity(self):
        BurstStub = namedtuple('BurstStub', ['granule', 'absolute_orbit', 'swath', 'polarization', 'burst_id'])
        burst1 = BurstStub(granule='S1A_IW_SLC_20210101', absolute_orbit=1, swath='IW1', polarization='VV', burst_id=1)
        burst2 = BurstStub(granule='S1A_IW_SLC_20210102', absolute_orbit=1, swath='IW1', polarization='VV', burst_id=2)

        Swath.check_burst_group_validity([burst1, burst2])  # type: ignore[list-item]

        duplicates = [burst1, BurstStub(*burst2._replace(granule=burst1.granule))]
        with pytest.raises(ValueError, match='Found duplicate granules:.*'):
            Swath.check_burst_group_validity(duplicates)  # type: ignore[arg-type]

        different_orbit = [burst1, BurstStub(*burst2._replace(absolute_orbit=2))]
        with pytest.raises(ValueError, match='All bursts must have the same absolute orbit. Found:.*'):
            Swath.check_burst_group_validity(different_orbit)  # type: ignore[arg-type]

        different_swath = [burst1, BurstStub(*burst2._replace(swath='IW2'))]
        with pytest.raises(ValueError, match='All bursts must be from the same swath. Found:.*'):
            Swath.check_burst_group_validity(different_swath)  # type: ignore[arg-type]

        different_polarization = [burst1, BurstStub(*burst2._replace(polarization='VH'))]
        with pytest.raises(ValueError, match='All bursts must have the same polarization. Found:.*'):
            Swath.check_burst_group_validity(different_polarization)  # type: ignore[arg-type]

        non_consecutive_burst_ids = [burst1, BurstStub(*burst2._replace(burst_id=3))]
        with pytest.raises(ValueError, match='All bursts must have consecutive burst IDs. Found:.*'):
            Swath.check_burst_group_validity(non_consecutive_burst_ids)  # type: ignore[arg-type]

    def test_get_swath_name(self, burst_infos):
        safe_path = Path('./S1A_IW_SLC__1SDV_20240408T015045_20240408T015113_053336_06778C_CB5D.SAFE')
        assert (
            Swath.get_swath_name(burst_infos, safe_path, 1)
            == 's1a-iw2-slc-vv-20240408t015108-20240408t015114-053336-06778c-001'
        )

    def test_get_bbox(self, burst_infos):
        geo_points = [
            GeoPoint(1, 1, 0, 0, 0),
            GeoPoint(1, 2, 0, 0, 0),
            GeoPoint(1.5, 1.5, 0, 0, 0),
            GeoPoint(2, 1, 0, 0, 0),
            GeoPoint(2, 2, 0, 0, 0),
        ]
        ProductStub = namedtuple('ProductStub', ['gcps'])
        safe_path = Path('./S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.SAFE')
        swath = Swath(burst_infos, safe_path, '003.71', CREATION_TIME, 1)
        swath.product = ProductStub(geo_points)  # type: ignore[assignment]
        bbox = swath.get_bbox()
        polygon = Polygon([(1, 1), (1, 2), (2, 2), (2, 1), (1, 1)])
        assert bbox == polygon
