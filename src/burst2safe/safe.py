import bisect
import shutil
from collections.abc import Iterable
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import List, Optional, Tuple, Union, cast

import numpy as np
from shapely.geometry import MultiPolygon, Polygon

from burst2safe.base import create_content_unit, create_data_object, create_metadata_object
from burst2safe.manifest import Kml, Manifest, Preview
from burst2safe.product import Product
from burst2safe.swath import Swath
from burst2safe.utils import BurstInfo, drop_duplicates, flatten, get_subxml_from_metadata, optional_wd


class Safe:
    """Class representing a SAFE file."""

    def __init__(
        self, burst_infos: list[BurstInfo], all_anns: bool = False, work_dir: Optional[Union[Path, str]] = None
    ):
        """Initialize a Safe object.

        Args:
            burst_infos: A list of BurstInfo objects
            all_anns: Include product annotation files for all swaths, regardless of included bursts
            work_dir: The directory to create the SAFE in
        """
        self.burst_infos = burst_infos
        self.all_anns = all_anns
        self.work_dir = optional_wd(work_dir)

        self.check_group_validity(self.burst_infos)

        self.grouped_burst_infos = self.group_burst_infos(self.burst_infos)
        self.name = self.get_name()
        self.safe_path = self.work_dir / self.name
        self.swaths: list = []
        self.blank_products: list = []
        self.manifest: Optional[Manifest] = None
        self.kml: Optional[Kml] = None

        self.version = self.get_ipf_version(self.burst_infos[0].metadata_path)
        self.major_version, self.minor_version = [int(x) for x in self.version.split('.')]
        self.support_dir = self.get_support_dir()
        self.creation_time = self.get_creation_time()

    def get_creation_time(self) -> datetime:
        """Get the creation time of the SAFE file.
        Always set to the latest SLC processing stop time.

        Returns:
            The creation time of the SAFE file
        """
        metadata_paths = list(set([x.metadata_path for x in self.burst_infos]))
        manifests = [get_subxml_from_metadata(metadata_path, 'manifest') for metadata_path in metadata_paths]
        manifest = manifests[0]
        desired_tag = './/{http://www.esa.int/safe/sentinel-1.0}processing'
        creation_times = []
        for manifest in manifests:
            slc_processing = [elem for elem in manifest.findall(desired_tag) if elem.get('name') == 'SLC Processing'][0]  # type: ignore[union-attr]
            creation_times.append(datetime.strptime(slc_processing.get('stop'), '%Y-%m-%dT%H:%M:%S.%f'))  # type: ignore[arg-type]
        creation_time = max(creation_times)
        return creation_time

    def get_support_dir(self) -> Path:
        """Find the support directory version closest to but not exceeding the IPF major.minor verion"""
        data_dir = Path(__file__).parent / 'data'
        support_dirs = sorted([x for x in data_dir.iterdir() if x.is_dir()])
        support_versions = sorted([int(x.name.split('_')[1]) for x in support_dirs])
        safe_version = (self.major_version * 100) + self.minor_version

        if safe_version in support_versions:
            support_version = safe_version
        else:
            support_version = support_versions[bisect.bisect_left(support_versions, safe_version) - 1]

        return data_dir / f'support_{support_version}'

    @staticmethod
    def check_group_validity(burst_infos: Iterable[BurstInfo]) -> None:
        """Check that the burst group is valid.

        A valid burst group must:
        - Have the same acquisition mode
        - Be from the same absolute orbit
        - Be contiguous in time and space
        - Have the same footprint for all included polarizations

        Args:
            burst_infos: A list of BurstInfo objects
        """
        swaths = sorted(list(set([info.swath for info in burst_infos])))
        polarizations = sorted(list(set([info.polarization for info in burst_infos])))
        burst_range: dict = {}
        for swath in swaths:
            burst_range[swath] = {}
            for pol in polarizations:
                burst_subset = [info for info in burst_infos if info.swath == swath and info.polarization == pol]
                if len(burst_subset) == 0:
                    burst_range[swath][pol] = [0, 0]
                    continue
                Swath.check_burst_group_validity(burst_subset)

                burst_ids = [cast(int, info.burst_id) for info in burst_subset]
                burst_range[swath][pol] = [min(burst_ids), max(burst_ids)]

            start_ids = [id_range[0] for id_range in burst_range[swath].values()]
            if len(set(start_ids)) != 1:
                raise ValueError(
                    f'Polarization groups in swath {swath} do not have same start burst id. Found {start_ids}'
                )

            end_ids = [id_range[1] for id_range in burst_range[swath].values()]
            if len(set(end_ids)) != 1:
                raise ValueError(f'Polarization groups in swath {swath} do not have same end burst id. Found {end_ids}')

        if len(swaths) == 1:
            return

        swath_combos = [[swaths[i], swaths[i + 1]] for i in range(len(swaths) - 1)]
        working_pol = polarizations[0]
        for swath1, swath2 in swath_combos:
            min_diff = burst_range[swath1][working_pol][0] - burst_range[swath2][working_pol][0]
            if np.abs(min_diff) > 1:
                raise ValueError(f'Products from swaths {swath1} and {swath2} do not overlap')
            max_diff = burst_range[swath1][working_pol][1] - burst_range[swath2][working_pol][1]
            if np.abs(max_diff) > 1:
                raise ValueError(f'Products from swaths {swath1} and {swath2} do not overlap')

    def get_name(self, unique_id: str = '0000') -> str:
        """Create a name for the SAFE file.

        Args:
            burst_infos: A list of BurstInfo objects
            unique_id: A unique identifier for the SAFE file

        Returns:
            The name of the SAFE file
        """
        assert self.burst_infos[0].slc_granule is not None
        platform, beam_mode, product_type = self.burst_infos[0].slc_granule.split('_')[:3]

        pol_codes = {'HH': 'SH', 'VV': 'SV', 'VH': 'VH', 'HV': 'HV', 'HH_HV': 'DH', 'VH_VV': 'DV'}
        pols = sorted(list(set([x.polarization for x in self.burst_infos])))
        pol_code = pol_codes['_'.join(pols)]
        product_info = f'1S{pol_code}'

        min_date = min(cast(datetime, x.date) for x in self.burst_infos).strftime('%Y%m%dT%H%M%S')
        max_date = max(cast(datetime, x.date) for x in self.burst_infos).strftime('%Y%m%dT%H%M%S')
        absolute_orbit = f'{self.burst_infos[0].absolute_orbit:06d}'
        mission_data_take = self.burst_infos[0].slc_granule.split('_')[-2]
        product_name = f'{platform}_{beam_mode}_{product_type}__{product_info}_{min_date}_{max_date}_{absolute_orbit}_{mission_data_take}_{unique_id}.SAFE'
        return product_name

    @staticmethod
    def group_burst_infos(burst_infos: Iterable[BurstInfo]) -> dict:
        """Group burst infos by swath and polarization.

        Args:
            burst_infos: A list of BurstInfo objects

        Returns:
            A dictionary of burst infos grouped by swath, then polarization
        """
        burst_dict: dict = {}
        for burst_info in burst_infos:
            if burst_info.swath not in burst_dict:
                burst_dict[burst_info.swath] = {}

            if burst_info.polarization not in burst_dict[burst_info.swath]:
                burst_dict[burst_info.swath][burst_info.polarization] = []

            burst_dict[burst_info.swath][burst_info.polarization].append(burst_info)

        swaths = list(burst_dict.keys())
        polarizations = list(burst_dict[swaths[0]].keys())
        for swath, polarization in zip(swaths, polarizations):
            burst_dict[swath][polarization] = sorted(burst_dict[swath][polarization], key=lambda x: x.burst_id)

        return burst_dict

    @staticmethod
    def get_ipf_version(metadata_path: Path) -> str:
        """Get the IPF version from the parent manifest file.

        Returns:
            The IPF version as a string
        """
        manifest = get_subxml_from_metadata(metadata_path, 'manifest')
        version_xml = [elem for elem in manifest.findall('.//{*}software') if elem.get('name') == 'Sentinel-1 IPF'][0]  # type: ignore[union-attr]
        version_str = version_xml.get('version')
        assert version_str is not None
        return version_str

    def get_bbox(self) -> Polygon:
        """Get the bounding box for the SAFE file.

        Returns:
            A Polygon object representing the bounding box
        """
        bboxs = MultiPolygon([swath.bbox for swath in self.swaths])
        min_rotated_rect = bboxs.minimum_rotated_rectangle
        bbox = Polygon(min_rotated_rect.exterior)
        return bbox

    def create_dir_structure(self) -> None:
        """Create a directory for the SAFE file.

        Returns:
            None
        """
        measurements_dir = self.safe_path / 'measurement'
        annotations_dir = self.safe_path / 'annotation'
        preview_dir = self.safe_path / 'preview'
        icon_dir = preview_dir / 'icons'
        calibration_dir = annotations_dir / 'calibration'
        rfi_dir = annotations_dir / 'rfi'

        calibration_dir.mkdir(parents=True, exist_ok=True)
        measurements_dir.mkdir(parents=True, exist_ok=True)
        icon_dir.mkdir(parents=True, exist_ok=True)
        if self.major_version >= 3 and self.minor_version >= 40:
            rfi_dir.mkdir(parents=True, exist_ok=True)

        shutil.copytree(self.support_dir, self.safe_path / 'support', dirs_exist_ok=True)
        shutil.copy(self.support_dir.parent / 'logo.png', icon_dir / 'logo.png')

    @staticmethod
    def create_representative_burst_set(template_bursts: Iterable[BurstInfo], swath: str, pol: str) -> List[BurstInfo]:
        """Create a representative burst set for a blank product.

        Args:
            template_bursts: A list of BurstInfo objects
            swath: The swath of the blank product
            pol: The polarization of the blank product
        """
        unique_slcs = list(set([x.slc_granule for x in template_bursts]))
        representative_bursts = []
        for slc in unique_slcs:
            slc_bursts = [x for x in template_bursts if x.slc_granule == slc]
            start_utc = min(cast(datetime, x.start_utc) for x in slc_bursts)
            stop_utc = max(cast(datetime, x.stop_utc) for x in slc_bursts)
            slc_template = slc_bursts[0]
            new_burst = BurstInfo(
                None,
                None,
                swath,
                pol,
                None,
                0,
                slc_template.direction,
                slc_template.absolute_orbit,
                slc_template.relative_orbit,
                None,
                None,
                None,
                None,
                slc_template.metadata_path,
                start_utc,
                stop_utc,
            )
            new_burst.add_shape_info()
            representative_bursts.append(new_burst)
        return representative_bursts

    def create_blank_products(self, image_number: int) -> List[Product]:
        """Create blank product annotation for missing swaths.

        Args:
            image_number: The starting image number for the annotation products

        Returns:
            A list of blank Product objects
        """
        swaths = list(set([burst.swath for burst in self.burst_infos]))
        missing_swaths = list(set(['IW1', 'IW2', 'IW3']) - set(swaths))
        if not self.all_anns or len(missing_swaths) == 0:
            return []

        pols = list(set([burst.polarization for burst in self.burst_infos]))

        blank_products = []
        for swath, pol in product(missing_swaths, pols):
            image_number += 1
            relevant_bursts = flatten([self.grouped_burst_infos[s][pol] for s in swaths])
            rep_bursts = self.create_representative_burst_set(relevant_bursts, swath, pol)
            annotation = Product(rep_bursts, self.version, image_number, dummy=True)
            blank_products.append(annotation)
        return blank_products

    def create_safe_components(self) -> None:
        """Create the components (data and metadata files) of the SAFE file."""
        swaths = list(self.grouped_burst_infos.keys())
        polarizations = list(self.grouped_burst_infos[swaths[0]].keys())
        image_number = 0
        for swath, polarization in product(swaths, polarizations):
            image_number += 1
            burst_infos = self.grouped_burst_infos[swath][polarization]
            swath = Swath(burst_infos, self.safe_path, self.version, self.creation_time, image_number)
            swath.assemble()
            swath.write()
            self.swaths.append(swath)

        for blank_product in self.create_blank_products(image_number):
            blank_product.assemble()
            swath_name = Swath.get_swath_name(blank_product.burst_infos, self.safe_path, blank_product.image_number)
            product_name = self.safe_path / 'annotation' / f'{swath_name}.xml'
            blank_product.write(product_name)
            self.blank_products.append(blank_product)

    def add_preview_components(
        self, content_units: list, metadata_objects: list, data_objects: list
    ) -> tuple[list, list, list]:
        """Add the preview components to unit lists.

        Args:
            content_units: A list of content units
            metadata_objects: A list of metadata objects
            data_objects: A list of data objects

        Returns:
            The updated content_units, metadata_objects, and data_objects lists
        """
        overlay_repid = 's1Level1MapOverlaySchema'
        preview_repid = 's1Level1ProductPreviewSchema'
        quicklook_repid = 's1Level1QuicklookSchema'
        overlay_content_unit = create_content_unit('mapoverlay', 'Metadata Unit', overlay_repid)
        preview_content_unit = create_content_unit('productpreview', 'Metadata Unit', preview_repid)
        quicklook_content_unit = create_content_unit('quicklook', 'Measurement Data Unit', quicklook_repid)
        content_units += [overlay_content_unit, preview_content_unit, quicklook_content_unit]

        metadata_objects += [create_metadata_object('mapoverlay'), create_metadata_object('productpreview')]

        assert self.kml is not None
        assert self.kml.size_bytes is not None
        assert self.kml.md5 is not None
        # TODO: add quicklook data object someday
        overlay_data_object = create_data_object(
            'mapoverlay',
            './preview/map-overlay.kml',
            overlay_repid,
            'text/xml',
            self.kml.size_bytes,
            self.kml.md5,
        )
        preview_data_object = create_data_object(
            'productpreview',
            './preview/product-preview.html',
            preview_repid,
            'text/html',
            self.preview.size_bytes,
            self.preview.md5,
        )
        data_objects += [overlay_data_object, preview_data_object]

        return content_units, metadata_objects, data_objects

    def compile_manifest_components(self) -> Tuple[List, List, List]:
        """Compile the manifest components for all files within the SAFE file.

        Returns:
            A list of content units, metadata objects, and data objects for the manifest file
        """
        content_units = []
        metadata_objects = []
        data_objects = []
        for swath in self.swaths:
            for annotation in swath.annotations:
                content_unit, metadata_object, date_object = annotation.create_manifest_components()
                content_units.append(content_unit)
                metadata_objects.append(metadata_object)
                data_objects.append(date_object)
            measurement_content, measurement_data = swath.measurement.create_manifest_components()
            content_units.append(measurement_content)
            data_objects.append(measurement_data)

        for blank_product in self.blank_products:
            content_unit, metadata_object, date_object = blank_product.create_manifest_components()
            content_units.append(content_unit)
            metadata_objects.append(metadata_object)
            data_objects.append(date_object)

        content_units, metadata_objects, data_objects = self.add_preview_components(
            content_units, metadata_objects, data_objects
        )
        return content_units, metadata_objects, data_objects

    def create_manifest(self) -> None:
        """Create the manifest.safe file for the SAFE file."""
        manifest_name = self.safe_path / 'manifest.safe'
        content_units, metadata_objects, data_objects = self.compile_manifest_components()
        template_manifest = get_subxml_from_metadata(self.burst_infos[0].metadata_path, 'manifest')
        assert template_manifest is not None
        manifest = Manifest(content_units, metadata_objects, data_objects, self.get_bbox(), template_manifest)
        manifest.assemble()
        manifest.write(manifest_name)
        self.manifest = manifest

    def create_preview(self):
        """Create the support files for the SAFE file."""
        kml = Kml(self.get_bbox())
        kml.assemble()
        kml.write(self.safe_path / 'preview' / 'map-overlay.kml')
        self.kml = kml

        product_names = [s.product_name.name for s in self.swaths]
        calibration_names = [s.noise_name.name for s in self.swaths] + [s.calibration_name.name for s in self.swaths]
        measurement_names = [s.measurement_name.name for s in self.swaths]
        rfi_names = [s.rfi_name.name for s in self.swaths if s.has_rfi]
        preview = Preview(self.name, product_names, calibration_names, measurement_names, rfi_names)
        preview.assemble()
        preview.write(self.safe_path / 'preview' / 'product-preview.html')
        self.preview = preview

    def update_product_identifier(self) -> None:
        """Update the product identifier using the CRC of the manifest file."""
        assert self.manifest is not None
        assert self.manifest.crc is not None
        new_new = self.get_name(unique_id=self.manifest.crc)
        new_path = self.work_dir / new_new
        if new_path.exists():
            shutil.rmtree(new_path)
        shutil.move(self.safe_path, new_path)

        self.name = new_new
        self.safe_path = new_path

        assert self.kml is not None
        self.kml.update_path(self.safe_path)
        self.preview.update_path(self.safe_path)
        for swath in self.swaths:
            swath.update_paths(self.safe_path)

    def create_safe(self) -> Path:
        """Create the SAFE file."""
        self.create_dir_structure()
        self.create_safe_components()
        self.create_preview()
        self.create_manifest()
        self.update_product_identifier()
        return self.safe_path

    def cleanup(self) -> None:
        """Remove unneeded files after SAFE creation"""
        to_delete = [burst_info.data_path for burst_info in self.burst_infos]
        to_delete += [burst_info.metadata_path for burst_info in self.burst_infos]
        to_delete = drop_duplicates(to_delete)
        for file in to_delete:
            assert file is not None
            file.unlink()
