from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import cast

from shapely.geometry import MultiPoint, Polygon

from burst2safe.calibration import Calibration
from burst2safe.measurement import Measurement
from burst2safe.noise import Noise
from burst2safe.product import Product
from burst2safe.rfi import Rfi
from burst2safe.utils import BurstInfo


class Swath:
    """Class representing a single swath (and polarization) of a SAFE file."""

    def __init__(
        self,
        burst_infos: Iterable[BurstInfo],
        safe_path: Path,
        version: str,
        creation_time: datetime,
        image_number: int,
    ):
        """Initialize a Swath object.

        Args:
            burst_infos: A list of BurstInfo objects
            safe_path: The path to the SAFE directory
            version: The IPF version of the SAFE file
            creation_time: The creation time of the SAFE file
            image_number: The image number of the swath
        """
        self.check_burst_group_validity(burst_infos)
        self.burst_infos = sorted(burst_infos, key=lambda x: cast(int, x.burst_id))
        self.safe_path = safe_path
        self.version = version
        self.creation_time = creation_time
        self.image_number = image_number
        self.swath = self.burst_infos[0].swath
        self.polarization = self.burst_infos[0].polarization

        self.name = self.get_swath_name(self.burst_infos, self.safe_path, self.image_number)
        self.major_version, self.minor_version = [int(x) for x in self.version.split('.')]

        self.measurement_name = self.safe_path / 'measurement' / f'{self.name}.tiff'
        self.product_name = self.safe_path / 'annotation' / f'{self.name}.xml'
        self.noise_name = self.safe_path / 'annotation' / 'calibration' / f'noise-{self.name}.xml'
        self.calibration_name = self.safe_path / 'annotation' / 'calibration' / f'calibration-{self.name}.xml'

        self.rfi_name = None
        self.has_rfi = False
        if self.major_version >= 3 and self.minor_version >= 40:
            self.has_rfi = True
            self.rfi_name = self.safe_path / 'annotation' / 'rfi' / f'rfi-{self.name}.xml'

        # Set on write
        self.bbox = None

    @staticmethod
    def check_burst_group_validity(burst_infos: Iterable[BurstInfo]):
        """Check that the burst group is valid.

        The burst group must:
        - Not contain duplicate granules
        - Have the same absolute orbit
        - Be from the same swath
        - Have the same polarization
        - Have consecutive burst IDs

        Args:
            burst_infos: A list of BurstInfo objects
        """
        granules = [x.granule for x in burst_infos]
        duplicates = list(set([x for x in granules if granules.count(x) > 1]))
        if duplicates:
            raise ValueError(f'Found duplicate granules: {duplicates}.')

        orbits = set([x.absolute_orbit for x in burst_infos])
        if len(orbits) != 1:
            raise ValueError(f'All bursts must have the same absolute orbit. Found: {orbits}.')

        swaths = set([x.swath for x in burst_infos])
        if len(swaths) != 1:
            raise ValueError(f'All bursts must be from the same swath. Found: {swaths}.')

        polarizations = set([x.polarization for x in burst_infos])
        if len(polarizations) != 1:
            raise ValueError(f'All bursts must have the same polarization. Found: {polarizations}.')

        burst_ids = [cast(int, x.burst_id) for x in burst_infos]
        burst_ids.sort()
        if burst_ids != list(range(min(burst_ids), max(burst_ids) + 1)):
            raise ValueError(f'All bursts must have consecutive burst IDs. Found: {burst_ids}.')

    @staticmethod
    def get_swath_name(burst_infos: list[BurstInfo], safe_path: Path, image_number: int) -> str:
        """Get the name of the swath. Will be used to name constituent output files.

        Args:
            burst_infos: A list of BurstInfo objects
            safe_path: The path to the SAFE directory
            image_number: The image number of the swath

        Returns:
            The name of the swath
        """
        swath = burst_infos[0].swath.lower()
        pol = burst_infos[0].polarization.lower()
        start = datetime.strftime(min(cast(datetime, x.start_utc) for x in burst_infos), '%Y%m%dt%H%M%S')
        stop = datetime.strftime(max(cast(datetime, x.stop_utc) for x in burst_infos), '%Y%m%dt%H%M%S')

        safe_name = safe_path.name
        platfrom, _, _, _, _, _, _, orbit, data_take, _ = safe_name.lower().split('_')
        swath_name = f'{platfrom}-{swath}-slc-{pol}-{start}-{stop}-{orbit}-{data_take}-{image_number:03d}'
        return swath_name

    def get_bbox(self):
        """Get the bounding box of the swath using the Product GCPs.

        Returns:
            The bounding box of the swath
        """
        points = MultiPoint([(gcp.x, gcp.y) for gcp in self.product.gcps])
        min_rotated_rect = points.minimum_rotated_rectangle
        bbox = Polygon(min_rotated_rect.exterior)
        return bbox

    def assemble(self):
        """Assemble the components of the Swath."""
        self.product = Product(self.burst_infos, self.version, self.image_number)
        self.noise = Noise(self.burst_infos, self.version, self.image_number)
        self.calibration = Calibration(self.burst_infos, self.version, self.image_number)
        self.annotations = [self.product, self.noise, self.calibration]

        if self.has_rfi:
            self.rfi = Rfi(self.burst_infos, self.version, self.image_number)
            self.annotations.append(self.rfi)

        for component in self.annotations:
            component.assemble()

        self.measurement = Measurement(
            self.burst_infos, self.product.gcps, self.creation_time, self.version, self.image_number
        )

    def write(self, update_info: bool = True):
        """Write the Swath componets to the SAFE directory.

        Args:
            update_info: Whether to update the bounding box of the Swath
        """
        self.measurement.write(self.measurement_name)
        assert self.measurement.data_mean is not None
        assert self.measurement.data_std is not None
        self.product.update_data_stats(self.measurement.data_mean, self.measurement.data_std)
        self.product.update_burst_byte_offsets(self.measurement.byte_offsets)
        self.product.write(self.product_name)
        self.noise.write(self.noise_name)
        self.calibration.write(self.calibration_name)
        if self.has_rfi:
            assert self.rfi_name is not None
            self.rfi.write(self.rfi_name)

        if update_info:
            self.bbox = self.get_bbox()

    def update_paths(self, safe_path: Path):
        """Update the paths of the Swath components based on a SAFE path.

        Args:
            safe_path: The new SAFE path
        """
        for component in self.annotations:
            parts = component.path.parts
            parent_index = parts.index(safe_path.parent.name)
            component.path = safe_path / Path(*parts[parent_index + 2 :])

        parts = self.measurement.path.parts
        parent_index = parts.index(safe_path.parent.name)
        self.measurement.path = safe_path / Path(*parts[parent_index + 2 :])

    def create_manifest_components(self):
        """Create the manifest components for the Swath."""
        self.manifest_components: dict[str, list] = {
            'content_unit': [],
            'metadata_object': [],
            'data_object': [],
            'content_unit_measurement': [],
            'data_object_measurement': [],
        }
        for annotation in self.annotations:
            content, metadata, data = annotation.create_manifest_components()
            self.manifest_components['content_unit'].append(content)
            self.manifest_components['metadata_object'].append(metadata)
            self.manifest_components['data_object'].append(data)

        content, data = self.measurement.create_manifest_components()
        self.manifest_components['content_unit_measurement'].append(content)
        self.manifest_components['data_object_measurement'].append(data)
