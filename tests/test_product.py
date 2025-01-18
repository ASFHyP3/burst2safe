# mypy: disable-error-code="union-attr"
import lxml.etree as ET

from burst2safe.product import GeoPoint, Product
from helpers import validate_xml


class TestProduct:
    def test_update_data_stats(self, burst_infos):
        base_path = 'imageInformation/imageStatistics/outputData'
        product = Product(burst_infos, '3.71', 1)
        product.assemble()
        product.update_data_stats(1 + 2j, 3 + 4j)
        assert product.xml is not None
        for elem in [product.image_annotation, product.xml.find('imageAnnotation')]:
            elem.find(f'{base_path}Mean/re').text = '1'
            elem.find(f'{base_path}Mean/im').text = '2'
            elem.find(f'{base_path}StdDev/re').text = '3'
            elem.find(f'{base_path}StdDev/im').text = '4'

    def test_update_gcps(self, burst_infos):
        geolocation_grid = ET.Element('geolocationGrid')
        grid_point_list = ET.SubElement(geolocation_grid, 'geolocationGridPointList')
        grid_point = ET.SubElement(grid_point_list, 'geolocationGridPoint')
        lon = ET.SubElement(grid_point, 'longitude')
        lon.text = '1.1'
        lat = ET.SubElement(grid_point, 'latitude')
        lat.text = '2.2'
        hgt = ET.SubElement(grid_point, 'height')
        hgt.text = '3.3'
        line = ET.SubElement(grid_point, 'line')
        line.text = '4'
        pixel = ET.SubElement(grid_point, 'pixel')
        pixel.text = '5'

        product = Product(burst_infos, '3.71', 1)
        product.geolocation_grid = geolocation_grid

        assert len(product.gcps) == 0

        product.update_gcps()
        assert len(product.gcps) == 1
        assert product.gcps[0] == GeoPoint(1.1, 2.2, 3.3, 4, 5)

    def test_merge(self, burst_infos, tmp_path, xsd_dir):
        out_path = tmp_path / 'file-001.xml'
        xsd_file = xsd_dir / 's1-level-1-product.xsd'
        product = Product(burst_infos, '3.71', 1)
        product.assemble()

        # Add back in omitted fields
        product.update_data_stats(1 + 1j, 2 + 2j)
        assert product.xml is not None
        burst_elems = product.xml.findall('.//byteOffset')
        for burst_elem in burst_elems:
            burst_elem.text = '1'
        product.xml.find('generalAnnotation/productInformation/platformHeading').text = '0.1'

        product.write(out_path)
        assert validate_xml(out_path, xsd_file)
