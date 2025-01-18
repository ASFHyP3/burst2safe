# mypy: disable-error-code="union-attr"
import hashlib
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Union, cast

import lxml.etree as ET

from burst2safe.utils import BurstInfo, drop_duplicates, flatten, get_subxml_from_metadata, set_text


SCHEMA = '{urn:ccsds:schema:xfdu:1}'


class ListOfListElements:
    def __init__(
        self, inputs: List[ET._Element], start_line: Optional[int] = None, slc_lengths: Optional[List[int]] = None
    ):
        """Initialize the ListOfListElements object.

        Args:
            inputs: The list of elements to be processed.
            start_line: The starting line number of the first element.
            slc_lengths: The total line lengths of the SLCs corresponding to each element.
        """
        self.inputs: list[ET._Element] = inputs
        self.start_line: Optional[int] = start_line
        self.slc_lengths: Optional[list[int]] = slc_lengths

        self.name = self.inputs[0].tag
        elements = flatten([element.findall('*') for element in self.inputs])
        if len(elements) == 0:
            raise ValueError(f'No Sub-elements contained within {self.name}.')

        names = drop_duplicates([x.tag for x in elements])
        if len(names) != 1:
            raise ValueError('Elements must contain only one type of subelement.')
        self.subelement_name = names[0]

        if self.name == 'replicaInformationList':
            self.time_field = 'referenceReplica/azimuthTime'
        elif 'azimuthTime' in [x.tag for x in elements[0].iter()]:
            self.time_field = 'azimuthTime'
        elif 'time' in [x.tag for x in elements[0].iter()]:
            self.time_field = 'time'
        elif 'noiseSensingTime' in [x.tag for x in elements[0].iter()]:
            self.time_field = 'noiseSensingTime'
        else:
            raise ValueError('Time field not found in elements.')

        self.inputs = sorted(self.inputs, key=self.get_first_time)
        self.has_line = elements[0].find('line') is not None

    def get_first_time(self, element: ET._Element) -> datetime:
        """Get first time in List element

        Args:
            element: The element to get the time from.

        Returns:
            The first time in the element.
        """
        first_time = min([datetime.fromisoformat(sub.find(self.time_field).text) for sub in element])  # type: ignore[arg-type]
        return first_time

    def get_unique_elements(self) -> List[ET._Element]:
        """Get the elements without duplicates. Adjust line number if present.

        Returns:
            The list of elements without duplicates.
        """
        list_of_element_lists = [item.findall('*') for item in self.inputs]

        last_time = datetime.fromisoformat(list_of_element_lists[0][-1].find(self.time_field).text)  # type: ignore[arg-type]
        uniques = [deepcopy(element) for element in list_of_element_lists[0]]
        if self.has_line:
            assert self.slc_lengths is not None
            previous_line_count = self.slc_lengths[0]

        for i, element_list in enumerate(list_of_element_lists[1:]):
            times = [datetime.fromisoformat(element.find(self.time_field).text) for element in element_list]  # type: ignore[arg-type]
            keep_index = [index for index, time in enumerate(times) if time > last_time]
            to_keep = [deepcopy(element_list[index]) for index in keep_index]

            if self.has_line:
                new_lines = [int(elem.find('line').text) + previous_line_count for elem in to_keep]  # type: ignore[arg-type]
                for elem, line in zip(to_keep, new_lines):
                    set_text(elem.find('line'), line)  # type: ignore[arg-type]
                assert self.slc_lengths is not None
                previous_line_count += self.slc_lengths[i]

            last_time = max([times[index] for index in keep_index])
            uniques += to_keep

        return uniques

    @staticmethod
    def filter_by_line(element_list: List[ET._Element], line_bounds: tuple[float, float]) -> List[ET._Element]:
        """Filter elements by line number.

        Args:
            line_bounds: The bounds of the line numbers.

        Returns:
            A filtered element list.
        """
        new_list = []
        for elem in element_list:
            if line_bounds[0] <= int(elem.find('line').text) <= line_bounds[1]:  # type: ignore[arg-type,operator]
                new_list.append(deepcopy(elem))
        return new_list

    def update_line_numbers(self, elements: List[ET._Element]) -> None:
        """Update the line numbers of the elements.

        Args:
            elements: The list of elements to update.
        """
        for element in elements:
            standard_line = int(element.find('line').text)  # type: ignore[arg-type]
            assert self.start_line is not None
            element.find('line').text = str(standard_line - self.start_line)

    def filter_by_time(
        self, elements: List[ET._Element], anx_bounds: tuple[datetime, datetime], buffer: timedelta
    ) -> List[ET._Element]:
        """Filter elements by time.

        Args:
            elements: The list of elements to filter.
            anx_bounds: The bounds of the ANX time.
            buffer: The buffer to add to the ANX bounds.

        Returns:
            A filtered element list.
        """
        min_anx_bound = anx_bounds[0] - buffer
        max_anx_bound = anx_bounds[1] + buffer
        filtered_elements = []
        for element in elements:
            azimuth_time = datetime.fromisoformat(element.find(self.time_field).text)  # type: ignore[arg-type]
            if min_anx_bound < azimuth_time < max_anx_bound:
                filtered_elements.append(deepcopy(element))

        return filtered_elements

    def create_filtered_list(
        self,
        anx_bounds: tuple[datetime, datetime],
        buffer: timedelta = timedelta(seconds=3),
        line_bounds: Optional[tuple[float, float]] = None,
    ) -> ET._Element:
        """Filter elements by time/line. Adjust line number if present.

        Args:
            anx_bounds: The bounds of the ANX time.
            buffer: The buffer to add to the ANX bounds.
            line_bounds: The bounds of the line numbers.

        Returns:
            A filtered list element.
        """
        elements = self.get_unique_elements()
        filtered_elements = self.filter_by_time(elements, anx_bounds, buffer)

        if self.has_line:
            self.update_line_numbers(filtered_elements)

        if line_bounds is not None:
            if not self.has_line:
                raise ValueError('Line bounds cannot be applied to elements without line numbers.')
            filtered_elements = self.filter_by_line(filtered_elements, line_bounds)

        new_element = ET.Element(self.name)
        for element in filtered_elements:
            new_element.append(element)
        new_element.set('count', str(len(filtered_elements)))
        return new_element


def create_content_unit(simple_name: str, unit_type: str, rep_id: str) -> ET._Element:
    """Create a content unit element for a manifest.safe file.

    Args:
        simple_name: The simple name of the content unit.
        unit_type: The type of the content unit.
        rep_id: The representation ID.

    Returns:
        The content unit element.
    """
    content_unit = ET.Element(f'{SCHEMA}contentUnit')
    content_unit.set('unitType', unit_type)
    content_unit.set('repID', rep_id)
    ET.SubElement(content_unit, 'dataObjectPointer', dataObjectID=simple_name)
    return content_unit


def create_metadata_object(simple_name: str) -> ET._Element:
    """Create a metadata object element for a manifest.safe file.

    Args:
        simple_name: The simple name of the metadata object.

    Returns:
        The metadata object element.
    """
    metadata_object = ET.Element('metadataObject')
    metadata_object.set('ID', f'{simple_name}Annotation')
    metadata_object.set('classification', 'DESCRIPTION')
    metadata_object.set('category', 'DMD')
    ET.SubElement(metadata_object, 'dataObjectPointer', dataObjectID=simple_name)
    return metadata_object


def create_data_object(
    simple_name: str, relative_path: Union[Path, str], rep_id: str, mime_type: str, size_bytes: int, md5: str
) -> ET._Element:
    """Create a data object element for a manifest.safe file.

    Args:
        simple_name: The simple name of the data object.
        relative_path: The relative path to the data object.
        rep_id: The representation ID.
        mime_type: The MIME type of the data object.
        size_bytes: The size of the data object in bytes.
        md5: The MD5 checksum of the data object.

    Returns:
        The data object element.
    """
    data_object = ET.Element('dataObject')
    data_object.set('ID', simple_name)
    data_object.set('repID', rep_id)
    byte_stream = ET.SubElement(data_object, 'byteStream')
    byte_stream.set('mimeType', mime_type)
    byte_stream.set('size', str(size_bytes))
    file_location = ET.SubElement(byte_stream, 'fileLocation')
    file_location.set('locatorType', 'URL')
    file_location.set('href', f'./{relative_path}')
    checksum = ET.SubElement(byte_stream, 'checksum')
    checksum.set('checksumName', 'MD5')
    checksum.text = md5
    return data_object


class Annotation:
    def __init__(self, burst_infos: list[BurstInfo], metadata_type: str, ipf_version: str, image_number: int):
        """Initialize the Annotation object.

        Args:
            burst_infos: The list of burst information objects.
            metadata_type: The type of metadata to create.
            ipf_version: The IPF version of the annotation (i.e. 3.71).
            image_number: The image number of the annotation.
        """
        self.burst_infos = burst_infos
        self.metadata_type = metadata_type
        self.image_number = image_number
        self.major_version, self.minor_version = [int(v) for v in ipf_version.split('.')]
        self.metadata_paths = drop_duplicates([x.metadata_path for x in burst_infos])
        self.swath, self.pol = burst_infos[0].swath, burst_infos[0].polarization
        assert burst_infos[0].length is not None
        self.start_line = burst_infos[0].burst_index * burst_infos[0].length
        self.total_lines = len(burst_infos) * burst_infos[0].length
        self.stop_line = self.start_line + self.total_lines
        self.min_anx = min(cast(datetime, x.start_utc) for x in burst_infos)
        self.max_anx = max(cast(datetime, x.stop_utc) for x in burst_infos)

        self.inputs = [
            get_subxml_from_metadata(path, metadata_type, self.swath, self.pol) for path in self.metadata_paths
        ]

        products = [get_subxml_from_metadata(path, 'product', self.swath, self.pol) for path in self.metadata_paths]
        slc_lengths = []
        for annotation in products:
            n_bursts = int(annotation.find('.//burstList').get('count'))  # type: ignore[arg-type]
            burst_length = int(annotation.find('.//linesPerBurst').text)  # type: ignore[arg-type]
            slc_lengths.append(n_bursts * burst_length)
        self.slc_lengths = slc_lengths

        # annotation components to be extended by subclasses
        self.ads_header: Optional[ET._Element] = None
        self.xml: Union[ET._Element, ET._ElementTree, None] = None

        # these attributes are updated when the annotation is written to a file
        self.size_bytes: Optional[int] = None
        self.md5: Optional[str] = None

    def create_ads_header(self):
        """Create the ADS header for the annotation."""
        ads_header = deepcopy(self.inputs[0].find('adsHeader'))
        ads_header.find('startTime').text = self.min_anx.isoformat()
        ads_header.find('stopTime').text = self.max_anx.isoformat()
        ads_header.find('imageNumber').text = f'{self.image_number:03d}'
        self.ads_header = ads_header

    def merge_lists(self, list_name: str, line_bounds: Optional[tuple[int, int]] = None) -> ET._Element:
        """Merge lists of elements into a single list.

        Args:
            list_name: The name of the list element.

        Returns:
            The merged list element.
        """
        list_elements: list = [input_xml.find(list_name) for input_xml in self.inputs]
        list_of_list_elements = ListOfListElements(list_elements, self.start_line, self.slc_lengths)
        merged_list = list_of_list_elements.create_filtered_list((self.min_anx, self.max_anx), line_bounds=line_bounds)
        return merged_list

    def write(self, out_path: Path, update_info=True) -> None:
        """Write the annotation to a file.

        Args:
            out_path: The path to write the annotation to.
            update_info: Whether to update the size and md5 attributes of the annotation.
        """
        assert self.xml is not None
        self.xml.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')

        if update_info:
            self.path = out_path
            with open(out_path, 'rb') as f:
                file_bytes = f.read()
                self.size_bytes = len(file_bytes)
                self.md5 = hashlib.md5(file_bytes).hexdigest()

    def __str__(self, **kwargs):
        """Return the XML string representation of the annotation.

        Args:
            kwargs: Keyword arguments to pass to the lxml
        """
        assert self.xml is not None
        xml_str = ET.tostring(self.xml, pretty_print=True, **kwargs)
        return xml_str.decode()

    def create_manifest_components(self):
        """Create the components for the manifest file."""
        unit_type = 'Metadata Unit'
        mime_type = 'text/xml'

        rep_id = f's1Level1{self.metadata_type.capitalize()}Schema'
        simple_name = self.path.with_suffix('').name.replace('-', '')
        if self.metadata_type == 'product':
            simple_name = f'product{simple_name}'

        safe_index = [i for i, x in enumerate(self.path.parts) if 'SAFE' in x][-1]
        safe_path = Path(*self.path.parts[: safe_index + 1])
        rel_path = self.path.relative_to(safe_path)

        content_unit = create_content_unit(simple_name, unit_type, rep_id)
        metadata_object = create_metadata_object(simple_name)
        assert self.size_bytes is not None
        assert self.md5 is not None
        data_object = create_data_object(simple_name, rel_path, rep_id, mime_type, self.size_bytes, self.md5)

        return content_unit, metadata_object, data_object

    def assemble(self):
        raise NotImplementedError()
