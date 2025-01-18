# mypy: disable-error-code="union-attr"
from copy import deepcopy
from typing import Optional

import lxml.etree as ET
import numpy as np

from burst2safe.base import Annotation
from burst2safe.utils import BurstInfo, flatten


class Noise(Annotation):
    """Class representing a Noise XML."""

    def __init__(self, burst_infos: list[BurstInfo], ipf_version: str, image_number: int):
        """Create a Noise object.

        Args:
            burst_infos: List of BurstInfo objects.
            ipf_version: The IPF version of the annotation (i.e. 3.71).
            image_number: Image number.
        """
        super().__init__(burst_infos, 'noise', ipf_version, image_number)
        self.noise_vector_list: Optional[ET._Element] = None  # Only used in version < 2.90
        self.range_vector_list: Optional[ET._Element] = None
        self.azimuth_vector_list: Optional[ET._Element] = None

    def create_range_vector_list(self):
        """Create the range vector list."""
        self.range_vector_list = self.merge_lists('noiseRangeVectorList')

    def create_noise_vector_list(self):
        """Create the range vector list."""
        self.noise_vector_list = self.merge_lists('noiseVectorList')

    @staticmethod
    def _get_start_stop_indexes(lines: np.ndarray, last_line: int, first_line: int = 0) -> tuple[int, int]:
        """Get the indexes of the first and last lines in the range of lines.

        Args:
            lines: Array of lines.
            last_line: Last line of the range.
            first_line: First line of the range. Defaults to 0.

        Returns:
            Tuple of the indexes of the first and last lines in the range.
        """
        if np.any(lines <= first_line):
            first_index = np.where(lines == lines[lines <= first_line].max())[0][0]
        else:
            first_index = 0

        if np.any(lines >= last_line):
            last_index = np.where(lines == lines[lines >= last_line].min())[0][0]
        else:
            last_index = lines.shape[0] - 1

        return first_index, last_index

    @staticmethod
    def _update_azimuth_vector(
        az_vector: ET._Element, line_offset: int, start_line: int, stop_line: int
    ) -> ET._Element:
        """Update the azimuth vector to match the new line range. Subset noiseAzimuthLut to match.

        Args:
            az_vector: Azimuth vector.
            line_offset: Line offset.
            start_line: Start line.
            stop_line: Stop line.

        Returns:
            Updated azimuth vector.
        """
        new_az_vector = deepcopy(az_vector)

        line_element = new_az_vector.find('line')
        lines = np.array([int(x) for x in line_element.text.split(' ')])
        lines += line_offset

        first_index, last_index = Noise._get_start_stop_indexes(lines, stop_line - start_line - 1)
        slice = np.s_[first_index : last_index + 1]
        count = str(last_index - first_index + 1)

        new_az_vector.find('firstAzimuthLine').text = str(lines[first_index])
        new_az_vector.find('lastAzimuthLine').text = str(lines[last_index])

        line_element.text = ' '.join([str(x) for x in lines[slice]])
        line_element.set('count', count)

        az_lut_element = new_az_vector.find('noiseAzimuthLut')
        az_lut_element.text = ' '.join(az_lut_element.text.split(' ')[slice])
        az_lut_element.set('count', count)
        return new_az_vector

    def create_azimuth_vector_list(self):
        """Create the azimuth vector list. ListOfListElements class can't be used here because the
        noiseAzimuthVectorList has a different structure than the other lists elements.
        """
        az_vectors: list = [noise.find('noiseAzimuthVectorList') for noise in self.inputs]
        updated_az_vectors = []
        for i, az_vector_set in enumerate(az_vectors):
            slc_offset = sum(self.slc_lengths[:i])
            az_vectors = az_vector_set.findall('noiseAzimuthVector')
            updated_az_vector_set = []
            for az_vector in az_vectors:
                line_offset = slc_offset - self.start_line
                assert az_vector is not None
                updated_az_vector = self._update_azimuth_vector(az_vector, line_offset, self.start_line, self.stop_line)
                updated_az_vector_set.append(updated_az_vector)
            updated_az_vectors.append(updated_az_vector_set)

        updated_az_vectors_flattened = flatten(updated_az_vectors)

        new_az_vector_list = ET.Element('noiseAzimuthVectorList')
        new_az_vector_list.set('count', str(len(updated_az_vectors_flattened)))
        for az_vector in updated_az_vectors_flattened:
            new_az_vector_list.append(az_vector)
        self.azimuth_vector_list = new_az_vector_list

    def assemble(self):
        """Assemble the Noise object from its components."""
        self.create_ads_header()

        noise = ET.Element('noise')
        assert self.ads_header is not None
        noise.append(self.ads_header)

        if self.major_version >= 3 or self.minor_version >= 90:
            self.create_range_vector_list()
            self.create_azimuth_vector_list()
            assert self.range_vector_list is not None
            assert self.azimuth_vector_list is not None
            noise.append(self.range_vector_list)
            noise.append(self.azimuth_vector_list)
        else:
            self.create_noise_vector_list()
            assert self.noise_vector_list is not None
            noise.append(self.noise_vector_list)

        noise_tree = ET.ElementTree(noise)

        ET.indent(noise_tree, space='  ')
        self.xml = noise_tree
