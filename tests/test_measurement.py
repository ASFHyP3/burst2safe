from copy import deepcopy
from datetime import datetime

import numpy as np
import pytest
from osgeo import gdal

from burst2safe.measurement import Measurement
from burst2safe.product import GeoPoint
from helpers import create_test_geotiff


gdal.UseExceptions()

CREATION_TIME = datetime.now()


@pytest.fixture
def burst_datas(burst_infos, tmp_path):
    burst_datas = []
    for i, burst_info in enumerate(burst_infos):
        n = i + 1
        burst_data = deepcopy(burst_info)
        burst_data.data_path = tmp_path / f'burst{n}.tif'
        burst_data.length = 1000
        burst_data.width = 2000

        shape = (burst_data.length, burst_data.width, 1)
        create_test_geotiff(burst_data.data_path, dtype='float', value=n, shape=shape)
        burst_datas.append(burst_data)
    return burst_datas


@pytest.fixture
def gcps():
    gcps = [GeoPoint(100, 200, 300, 1, 2), GeoPoint(400, 500, 600, 3, 4)]
    return gcps


class TestMeasurement:
    def test_init(self, burst_datas, gcps):
        measurement = Measurement(burst_datas, gcps, CREATION_TIME, '003.20', 1)

        assert measurement.total_length == 1000 * 2
        assert measurement.data_mean is None
        assert measurement.data_std is None

    def test_get_data(self, burst_datas, gcps):
        measurement = Measurement(burst_datas, gcps, CREATION_TIME, '003.20', 1)
        data = measurement.get_data()
        assert data.shape == (1000 * 2, 2000)

        golden = np.ones((2000, 2000), dtype=np.complex64)
        golden[1000:, :] *= 2
        assert np.allclose(data, golden)

    def test_add_metadata(self, burst_datas, gcps):
        mem_drv = gdal.GetDriverByName('MEM')
        mem_ds = mem_drv.Create('', 20, 20, 1, gdal.GDT_CInt16)

        measurement = Measurement(burst_datas, gcps, CREATION_TIME, '003.20', 1)
        measurement.add_metadata(mem_ds)

        assert mem_ds.GetGCPCount() == len(gcps)
        assert '4326' in mem_ds.GetGCPProjection()
        assert mem_ds.GetMetadataItem('TIFFTAG_DATETIME') is not None
        assert mem_ds.GetMetadataItem('TIFFTAG_IMAGEDESCRIPTION') == 'Sentinel-1A IW SLC L1'
        assert mem_ds.GetMetadataItem('TIFFTAG_SOFTWARE') == 'Sentinel-1 IPF 003.20'

    def test_create_geotiff(self, burst_datas, gcps, tmp_path):
        out_path = tmp_path / 'test.tif'
        measurement = Measurement(burst_datas, gcps, CREATION_TIME, '003.20', 1)
        measurement.create_geotiff(out_path)

        assert out_path.exists()
        assert measurement.path == out_path
        assert measurement.data_mean is not None
        assert measurement.data_std is not None
        assert measurement.size_bytes is not None
        assert measurement.md5 is not None

    def test_create_manifest_components(self, burst_datas, gcps, tmp_path):
        measurement = Measurement(burst_datas, gcps, CREATION_TIME, '003.20', 1)
        measurement.path = tmp_path / 'foo.SAFE' / 'test.tif'
        measurement.size_bytes = 100
        measurement.md5 = 'md5'

        content_unit, data_unit = measurement.create_manifest_components()

        assert content_unit.get('unitType') == 'Measurement Data Unit'
        assert content_unit.get('repID') == 's1Level1MeasurementSchema'

        assert data_unit.find('byteStream').get('mimeType') == 'application/octet-stream'
        assert data_unit.find('byteStream').get('size') == '100'
        assert data_unit.find('byteStream/fileLocation').get('href') == './test.tif'
        assert data_unit.find('byteStream/checksum').text == 'md5'
