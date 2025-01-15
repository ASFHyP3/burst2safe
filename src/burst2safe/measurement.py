import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, cast

import numpy as np
from osgeo import gdal, osr
from tifffile import TiffFile, TiffPage

from burst2safe.base import create_content_unit, create_data_object
from burst2safe.product import GeoPoint
from burst2safe.utils import BurstInfo


class Measurement:
    """Class representing a measurement GeoTIFF."""

    def __init__(
        self,
        burst_infos: list[BurstInfo],
        gcps: list[GeoPoint],
        creation_time: datetime,
        ipf_version: str,
        image_number: int,
    ):
        """Initialize a Measurement object.

        Args:
            burst_infos: A list of BurstInfo objects
            gcps: A list of GeoPoint objects
            creation_time: The creation time of the measurement
            ipf_version: The IPF version of the measurement data
            image_number: The image number of the measurement
        """
        self.burst_infos = burst_infos
        self.gcps = gcps
        self.creation_time = creation_time
        self.version = ipf_version
        self.image_number = image_number

        self.swath = self.burst_infos[0].swath
        assert self.burst_infos[0].slc_granule is not None
        self.s1_platform = self.burst_infos[0].slc_granule[2].upper()

        burst_lengths = sorted(list(set(cast(int, info.length) for info in burst_infos)))
        if len(burst_lengths) != 1:
            raise ValueError(f'All burst are not the same length. Found {" ".join([str(x) for x in burst_lengths])}')
        self.burst_length = burst_lengths[0]
        self.total_length = self.burst_length * len(self.burst_infos)

        # TODO: sometimes bursts from different SLCs have different widths. Is this an issue?
        self.total_width = max(cast(int, info.width) for info in burst_infos)

        self.data_mean: Optional[complex] = None
        self.data_std: Optional[complex] = None
        self.size_bytes: Optional[int] = None
        self.md5: Optional[str] = None
        self.byte_offsets: list = []

    def get_data(self, band: int = 1) -> np.ndarray:
        """Get the data for the measurement from ASF burst GeoTIFFs.

        Args:
            band: The GeoTIFF band to read

        Returns:
            The data from burst GeoTIFFs as a numpy array
        """
        data = np.zeros((self.total_length, self.total_width), dtype=np.complex64)
        for i, burst_info in enumerate(self.burst_infos):
            ds = gdal.Open(str(burst_info.data_path))
            burst_slice = np.s_[i * self.burst_length : (i + 1) * self.burst_length, 0 : burst_info.width]
            data[burst_slice] = ds.GetRasterBand(band).ReadAsArray()
            ds = None
        return data

    def get_burst_byte_offsets(self):
        """Get the byte offsets of each burst in the measurement GeoTIFF."""
        with TiffFile(self.path) as tif:
            if len(tif.pages) != 1:
                raise ValueError('Byte offset calculation only valid for GeoTIFFs with one band.')
            page = tif.pages[0]
            assert isinstance(page, TiffPage)

            if page.compression._name_ != 'NONE':  # type: ignore[attr-defined]
                raise ValueError('Byte offset calculation only valid for uncompressed GeoTIFFs.')

            if page.chunks != (1, page.imagewidth):
                raise ValueError('Byte offset calculation only valid for GeoTIFFs with one line per block.')

            offsets = page.dataoffsets

        byte_offsets = [offsets[self.burst_length * i] for i in range(len(self.burst_infos))]
        return byte_offsets

    def add_metadata(self, dataset: gdal.Dataset):
        """Add metadata to an existing GDAL dataset.

        Args:
            dataset: The GDAL dataset to add metadata to
        """
        gdal_gcps = [gdal.GCP(gcp.x, gcp.y, gcp.z, gcp.pixel, gcp.line) for gcp in self.gcps]
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        dataset.SetGCPs(gdal_gcps, srs.ExportToWkt())

        dataset.SetMetadataItem('TIFFTAG_DATETIME', datetime.strftime(self.creation_time, '%Y:%m:%d %H:%M:%S'))
        dataset.SetMetadataItem('TIFFTAG_IMAGEDESCRIPTION', f'Sentinel-1{self.s1_platform} IW SLC L1')
        dataset.SetMetadataItem('TIFFTAG_SOFTWARE', f'Sentinel-1 IPF {self.version}')

    def create_geotiff(self, out_path: Path, update_info=True):
        """Create a GeoTIFF of SLC data from the constituent burst SLC GeoTIFFs.
        Optionally update Measurment metadata.

        Args:
            out_path: The path to write the SLC GeoTIFF to
            update_info: Whether to update the Measurement metadata
        """
        gtiff = gdal.GetDriverByName('GTiff')
        blank_ds = gtiff.Create(str(out_path), self.total_width, self.total_length, 1, gdal.GDT_CInt16)
        blank_band = blank_ds.GetRasterBand(1)
        blank_band.SetNoDataValue(0)
        blank_band.FlushCache()
        blank_ds = None

        ds = gdal.Open(str(out_path), gdal.GA_Update)
        band = ds.GetRasterBand(1)
        data = self.get_data()
        band.WriteArray(data)
        self.add_metadata(ds)
        band.FlushCache()
        ds = None

        if update_info:
            self.path = out_path
            self.data_mean = np.mean(data[data != 0])
            self.data_std = np.std(data[data != 0])
            self.byte_offsets = self.get_burst_byte_offsets()

            with open(self.path, 'rb') as f:
                file_bytes = f.read()
                self.size_bytes = len(file_bytes)
                self.md5 = hashlib.md5(file_bytes).hexdigest()

    def create_manifest_components(self) -> Tuple:
        """Create the components of the SAFE manifest for the measurement file.

        Returns:
            A tuple of the content unit and data object for the measurement file
        """
        simple_name = self.path.with_suffix('').name.replace('-', '')
        rep_id = 's1Level1MeasurementSchema'
        unit_type = 'Measurement Data Unit'
        mime_type = 'application/octet-stream'

        safe_index = [i for i, x in enumerate(self.path.parts) if 'SAFE' in x][-1]
        safe_path = Path(*self.path.parts[: safe_index + 1])
        relative_path = self.path.relative_to(safe_path)

        content_unit = create_content_unit(simple_name, rep_id, unit_type)
        assert self.size_bytes is not None
        assert self.md5 is not None
        data_object = create_data_object(simple_name, relative_path, rep_id, mime_type, self.size_bytes, self.md5)
        return content_unit, data_object

    def write(self, out_path):
        """Write the measurement GeoTIFF to a file."""
        self.create_geotiff(out_path)
