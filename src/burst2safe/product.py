# mypy: disable-error-code="union-attr"
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, cast

import lxml.etree as ET
import numpy as np

from burst2safe.base import Annotation, ListOfListElements
from burst2safe.utils import BurstInfo, flatten


@dataclass
class GeoPoint:
    """A geolocation grid point."""

    x: float
    y: float
    z: float
    line: int
    pixel: int


class Product(Annotation):
    """Class representing a product XML."""

    def __init__(self, burst_infos: list[BurstInfo], ipf_version: str, image_number: int, dummy: bool = False):
        """Create a Product object.

        Args:
            burst_infos: A list of BurstInfo objects
            ipf_version: The IPF version of the annotation (i.e. 3.71).
            image_number: The image number
        """
        super().__init__(burst_infos, 'product', ipf_version, image_number)
        self.dummy = dummy
        self.qulatity_information = None
        self.general_annotation: Optional[ET._Element] = None
        self.image_annotation: Optional[ET._Element] = None
        self.doppler_centroid: Optional[ET._Element] = None
        self.antenna_pattern: Optional[ET._Element] = None
        self.swath_timing: Optional[ET._Element] = None
        self.geolocation_grid: Optional[ET._Element] = None
        self.coordinate_conversion: Optional[ET._Element] = None
        self.swath_merging: Optional[ET._Element] = None
        self.gcps: list = []

    def create_quality_information(self):
        """Create the qualityInformation element."""
        quality_information = ET.Element('qualityInformation')
        quality_information.append(deepcopy(self.inputs[0].find('qualityInformation/productQualityIndex')))  # type: ignore[arg-type]

        quality_datas = flatten([cal.findall('qualityInformation/qualityDataList/qualityData') for cal in self.inputs])
        quality_data_list = ET.Element('qualityDataList')
        quality_data_list.set('count', str(len(quality_datas)))
        for quality_data in quality_datas:
            quality_data_list.append(deepcopy(quality_data))

        quality_information.append(quality_data_list)

        self.quality_information = quality_information

    def create_general_annotation(self):
        """Create the generalAnnotation element.

        From product specification:
        The productInformation sub-record contains single value fields that
        are merged and included. All other sub-records contain lists which are
        concatenated. Details are presented in Table 3-11.
        """
        general_annotation = ET.Element('generalAnnotation')

        product_information = deepcopy(self.inputs[0].find('generalAnnotation/productInformation'))

        # TODO: productInformation/platformHeading should be calculated more accurately
        platform_heading_path = 'generalAnnotation/productInformation/platformHeading'
        platform_heading = np.mean([float(prod.find(platform_heading_path).text) for prod in self.inputs])  # type: ignore[arg-type]
        product_information.find('platformHeading').text = f'{platform_heading:.14e}'

        assert product_information is not None
        general_annotation.append(product_information)

        lists = [
            'downlinkInformationList',
            'orbitList',
            'attitudeList',
            'rawDataAnalysisList',
            'replicaInformationList',
            'noiseList',
            'terrainHeightList',
            'azimuthFmRateList',
        ]
        for list_name in lists:
            list_elements: list = [prod.find(f'generalAnnotation/{list_name}') for prod in self.inputs]
            if len(flatten([element.findall('*') for element in list_elements])) == 0:
                filtered = ET.Element(list_elements[0].tag)
                filtered.set('count', '0')
            elif list_name == 'replicaInformationList':
                lol = ListOfListElements(list_elements, self.start_line, self.slc_lengths)
                unique = lol.get_unique_elements()
                filtered = ET.Element('replicaInformationList')
                filtered.set('count', str(len(unique)))
                for element in unique:
                    filtered.append(element)
            else:
                lol = ListOfListElements(list_elements, self.start_line, self.slc_lengths)
                filtered = lol.create_filtered_list((self.min_anx, self.max_anx), buffer=timedelta(seconds=500))

            general_annotation.append(filtered)

        self.general_annotation = general_annotation

    def create_image_annotation(self):
        """Create the imageAnnotation element.

        From product specification:
        This DSR contains two records which contain only single value fields.
        The fields in the imageInformation record are included and merged
        and all the fields for the processingInformation record are included;
        except for the inputDimensionsList record, which is concatenated.
        Details are presented in Table 3-12.
        """
        image_annotation = ET.Element('imageAnnotation')

        image_information = deepcopy(self.inputs[0].find('imageAnnotation/imageInformation'))
        image_information.find('productFirstLineUtcTime').text = self.min_anx.isoformat()
        image_information.find('productLastLineUtcTime').text = self.max_anx.isoformat()
        image_information.find('productComposition').text = 'Assembled'
        image_information.find('sliceNumber').text = '0'

        slice_list = image_information.find('sliceList')
        slice_list.set('count', '0')
        for element in slice_list:
            slice_list.remove(element)

        image_information.find('numberOfLines').text = str(self.total_lines)

        az_spacing_path = 'imageAnnotation/imageInformation/azimuthPixelSpacing'
        az_spacing = np.mean([float(prod.find(az_spacing_path).text) for prod in self.inputs])  # type: ignore[arg-type]
        image_information.find('azimuthPixelSpacing').text = f'{az_spacing:.6e}'

        image_information.find('imageStatistics/outputDataMean/re').text = ''
        image_information.find('imageStatistics/outputDataMean/im').text = ''
        image_information.find('imageStatistics/outputDataStdDev/re').text = ''
        image_information.find('imageStatistics/outputDataStdDev/im').text = ''

        assert image_information is not None
        image_annotation.append(image_information)

        processing_information = deepcopy(self.inputs[0].find('imageAnnotation/processingInformation'))
        dimensions_list = processing_information.find('inputDimensionsList')
        for element in slice_list:
            dimensions_list.remove(element)

        list_elements: list = [
            prod.find('imageAnnotation/processingInformation/inputDimensionsList') for prod in self.inputs
        ]
        lol = ListOfListElements(list_elements, self.start_line, self.slc_lengths)
        filtered = lol.create_filtered_list((self.min_anx, self.max_anx))
        [dimensions_list.append(element) for element in filtered]

        assert processing_information is not None
        image_annotation.append(processing_information)
        self.image_annotation = image_annotation

    def update_data_stats(self, data_mean: complex, data_std: complex):
        """Update the data statistics in the imageAnnotation element.

        Args:
            data_mean: The complex mean of the data.
            data_std: The complex standard deviation of the data.
        """
        base_path = 'imageInformation/imageStatistics/outputData'
        data_mean_re = f'{data_mean.real:.6e}'
        data_mean_im = f'{data_mean.imag:.6e}'
        data_std_re = f'{data_std.real:.6e}'
        data_std_im = f'{data_std.imag:.6e}'

        assert self.xml is not None
        for elem in [self.image_annotation, self.xml.find('imageAnnotation')]:
            elem.find(f'{base_path}Mean/re').text = data_mean_re
            elem.find(f'{base_path}Mean/im').text = data_mean_im
            elem.find(f'{base_path}StdDev/re').text = data_std_re
            elem.find(f'{base_path}StdDev/im').text = data_std_im

    def create_doppler_centroid(self):
        """Create the dopplerCentroid element."""
        doppler_centroid = ET.Element('dopplerCentroid')
        doppler_centroid.append(self.merge_lists('dopplerCentroid/dcEstimateList'))
        self.doppler_centroid = doppler_centroid

    def create_antenna_pattern(self):
        """Create the antennaPattern element."""
        antenna_pattern = ET.Element('antennaPattern')
        antenna_pattern.append(self.merge_lists('antennaPattern/antennaPatternList'))
        self.antenna_pattern = antenna_pattern

    def create_swath_timing(self):
        """Create the swathTiming element."""
        burst_lists: list = [prod.find('swathTiming/burstList') for prod in self.inputs]
        burst_lol = ListOfListElements(burst_lists, self.start_line, self.slc_lengths)
        filtered = burst_lol.create_filtered_list((self.min_anx, self.max_anx), buffer=timedelta(seconds=0.1))

        # TODO: This is needed since we always buffer backward AND forward
        if int(filtered.get('count')) > len(self.burst_infos):  # type: ignore[arg-type]
            filtered.remove(filtered[-1])
            filtered.set('count', str(int(filtered.get('count')) - 1))  # type: ignore[arg-type]

        for burst in filtered:
            burst.find('byteOffset').text = ''

        swath_timing = ET.Element('swathTiming')
        lines_per_burst = ET.SubElement(swath_timing, 'linesPerBurst')
        lines_per_burst.text = str(max(cast(int, info.length) for info in self.burst_infos))
        samples_per_burst = ET.SubElement(swath_timing, 'samplesPerBurst')
        samples_per_burst.text = str(max(cast(int, info.width) for info in self.burst_infos))
        swath_timing.append(filtered)
        self.swath_timing = swath_timing

    def update_gcps(self):
        """Update gcp attribute using the geolocationGridPointList."""
        assert self.geolocation_grid is not None
        gcp_xmls = self.geolocation_grid.find('geolocationGridPointList').findall('*')
        for gcp_xml in gcp_xmls:
            gcp = GeoPoint(
                float(gcp_xml.find('longitude').text),  # type: ignore[arg-type]
                float(gcp_xml.find('latitude').text),  # type: ignore[arg-type]
                float(gcp_xml.find('height').text),  # type: ignore[arg-type]
                int(gcp_xml.find('line').text),  # type: ignore[arg-type]
                int(gcp_xml.find('pixel').text),  # type: ignore[arg-type]
            )
            self.gcps.append(gcp)

    def update_burst_byte_offsets(self, byte_offsets: Iterable[int]):
        """Update the byte offsets in the burstList element.

        Args:
            byte_offsets: The byte offsets to update
        """
        assert self.xml is not None
        if self.swath_timing is None or self.xml.find('swathTiming') is None:
            raise ValueError('Product must be assembled before updating burst byte offsets.')

        for swath_timing in [self.swath_timing, self.xml.find('swathTiming')]:
            burst_list = swath_timing.find('burstList')
            assert burst_list is not None
            for i, byte_offset in enumerate(byte_offsets):
                burst_list[i].find('byteOffset').text = str(byte_offset)

    def create_geolocation_grid(self):
        """Create the geolocationGrid element."""
        geolocation_grid = ET.Element('geolocationGrid')
        grid_list = self.merge_lists('geolocationGrid/geolocationGridPointList', line_bounds=(0, self.total_lines))
        geolocation_grid.append(grid_list)
        self.geolocation_grid = geolocation_grid
        self.update_gcps()

    def create_coordinate_conversion(self):
        """Create an empty coordinateConversion element."""
        coordinate_conversion = ET.Element('coordinateConversion')
        coordinate_conversion_list = ET.SubElement(coordinate_conversion, 'coordinateConversionList')
        coordinate_conversion_list.set('count', '0')
        self.coordinate_conversion = coordinate_conversion

    def create_swath_merging(self):
        """Create an empty swathMerging element."""
        swath_merging = ET.Element('swathMerging')
        swath_merge_list = ET.SubElement(swath_merging, 'swathMergeList')
        swath_merge_list.set('count', '0')
        self.swath_merging = swath_merging

    def remove_burst_data(self):
        """Remove data from burstList and geolocationGrid."""
        assert self.swath_timing is not None
        burst_list = self.swath_timing.find('burstList')
        burst_list.set('count', '0')
        for child in burst_list:
            burst_list.remove(child)

        assert self.geolocation_grid is not None
        geolocation_grid = self.geolocation_grid.find('geolocationGridPointList')
        geolocation_grid.set('count', '0')
        for child in geolocation_grid:
            geolocation_grid.remove(child)

    def assemble(self):
        """Assemble the product from its components."""
        self.create_ads_header()
        self.create_quality_information()
        self.create_general_annotation()
        self.create_image_annotation()
        self.create_doppler_centroid()
        self.create_antenna_pattern()
        self.create_swath_timing()
        self.create_geolocation_grid()
        self.create_coordinate_conversion()
        self.create_swath_merging()

        if self.dummy:
            self.remove_burst_data()

        product = ET.Element('product')

        assert self.ads_header is not None
        assert self.quality_information is not None
        assert self.general_annotation is not None
        assert self.image_annotation is not None
        assert self.doppler_centroid is not None
        assert self.antenna_pattern is not None
        assert self.swath_timing is not None
        assert self.geolocation_grid is not None
        assert self.coordinate_conversion is not None
        assert self.swath_merging is not None

        product.append(self.ads_header)
        product.append(self.quality_information)
        product.append(self.general_annotation)
        product.append(self.image_annotation)
        product.append(self.doppler_centroid)
        product.append(self.antenna_pattern)
        product.append(self.swath_timing)
        product.append(self.geolocation_grid)
        product.append(self.coordinate_conversion)
        product.append(self.swath_merging)
        product_tree = ET.ElementTree(product)

        ET.indent(product_tree, space='  ')
        self.xml = product_tree
