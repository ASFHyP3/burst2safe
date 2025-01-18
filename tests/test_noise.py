# mypy: disable-error-code="union-attr"
import xml.etree.ElementTree as ET

import numpy as np

from burst2safe.noise import Noise
from helpers import validate_xml


class TestNoise:
    def test_get_start_stop_indexes(self):
        lines = np.array([0, 2, 4, 6, 8, 10])

        start, stop = Noise._get_start_stop_indexes(lines, 5)
        assert start == 0
        assert stop == 3

        start, stop = Noise._get_start_stop_indexes(lines, 5, 3)
        assert start == 1
        assert stop == 3

        start, stop = Noise._get_start_stop_indexes(lines, 12)
        assert start == 0
        assert stop == 5

    def test_update_azimuth_vector(self):
        az_vector = ET.Element('azimuthVector')
        first_az_line = ET.SubElement(az_vector, 'firstAzimuthLine')
        first_az_line.text = '0'
        last_az_line = ET.SubElement(az_vector, 'lastAzimuthLine')
        last_az_line.text = '20'
        line_element = ET.SubElement(az_vector, 'line')
        line_element.text = '0 2 4 6 8 10 12 14 16 18 20'
        az_lut_element = ET.SubElement(az_vector, 'noiseAzimuthLut')
        az_lut_element.text = '0 2 4 6 8 10 12 14 16 18 20'
        for element in (line_element, az_lut_element):
            assert element.text is not None
            element.set('count', str(len(element.text.split(' '))))

        new_az_vector = Noise._update_azimuth_vector(az_vector, 0, 10, 20)  # type: ignore[arg-type]
        assert new_az_vector.find('firstAzimuthLine').text == '0'
        assert new_az_vector.find('lastAzimuthLine').text == '10'
        assert new_az_vector.find('line').get('count') == '6'
        assert new_az_vector.find('line').text == '0 2 4 6 8 10'
        assert new_az_vector.find('noiseAzimuthLut').get('count') == '6'
        assert new_az_vector.find('noiseAzimuthLut').text == '0 2 4 6 8 10'

    def test_merge(self, burst_infos, tmp_path, xsd_dir):
        out_path = tmp_path / 'file-001.xml'
        xsd_file = xsd_dir / 's1-level-1-noise.xsd'
        noise = Noise(burst_infos, '3.71', 1)
        noise.assemble()
        noise.write(out_path)
        assert validate_xml(out_path, xsd_file)
