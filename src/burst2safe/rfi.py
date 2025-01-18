from copy import deepcopy
from typing import Optional

import lxml.etree as ET

from burst2safe.base import Annotation
from burst2safe.utils import BurstInfo


class Rfi(Annotation):
    """Class representing an radio frequency interference (RFI) XML.

    Note: RFI annotations only available for IPF version 3.40 onwards.
    """

    def __init__(self, burst_infos: list[BurstInfo], ipf_version: str, image_number: int):
        """Create a calibration object.

        Args:
            burst_infos: List of BurstInfo objects.
            ipf_version: The IPF version of the annotation (i.e. 3.71).
            image_number: Image number.
        """
        super().__init__(burst_infos, 'rfi', ipf_version, image_number)
        self.rfi_mitigation_applied: Optional[ET._Element] = None
        self.rfi_detection_from_noise_report_list: Optional[ET._Element] = None
        self.rfi_burst_report_list: Optional[ET._Element] = None

    def create_rfi_mitigation_applied(self):
        """Create the rifMitigationApplied element."""
        self.rfi_mitigation_applied = deepcopy(self.inputs[0].find('rfiMitigationApplied'))  # type: ignore[union-attr]

    def create_rfi_detection_from_noise_report_list(self):
        """Create the rfiDetectionFromNoiseReportList element."""
        self.rfi_detection_from_noise_report_list = self.merge_lists('rfiDetectionFromNoiseReportList')

    def create_rfi_burst_report_list(self):
        """Create the rfiBurstReportList element."""
        self.rfi_burst_report_list = self.merge_lists('rfiBurstReportList')

    def assemble(self):
        """Assemble the RFI object components."""
        self.create_ads_header()
        self.create_rfi_mitigation_applied()
        self.create_rfi_detection_from_noise_report_list()
        self.create_rfi_burst_report_list()

        rfi = ET.Element('rfi')
        assert self.ads_header is not None
        assert self.rfi_mitigation_applied is not None
        assert self.rfi_detection_from_noise_report_list is not None
        assert self.rfi_burst_report_list is not None
        rfi.append(self.ads_header)
        rfi.append(self.rfi_mitigation_applied)
        rfi.append(self.rfi_detection_from_noise_report_list)
        rfi.append(self.rfi_burst_report_list)
        rfi_tree = ET.ElementTree(rfi)

        ET.indent(rfi_tree, space='  ')
        self.xml = rfi_tree
