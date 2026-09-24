from __future__ import annotations
import re


def classify_unit(name: str, organization_type: str) -> tuple[str, str]:
    if organization_type == "BCA":
        if re.match(r"^Công an (tỉnh|thành phố) ", name, re.I):
            return "PROVINCIAL", "BCA_PROVINCIAL_POLICE"
        if re.match(r"^Công an (xã|phường|đặc khu) ", name, re.I):
            return "COMMUNE", "BCA_COMMUNE_POLICE"
        return "CENTRAL_OR_PUBLIC", "BCA_CENTRAL_PUBLIC"

    if organization_type == "BQP":
        if re.match(r"^Quân khu [1-9]\b", name, re.I):
            return "MILITARY_REGION", "BQP_MILITARY_REGIONS"
        if re.match(r"^Quân đoàn \d+\b", name, re.I):
            return "ARMY_CORPS", "BQP_ARMY_CORPS"
        if re.match(r"^(Bộ Chỉ huy quân sự|Bộ Tư lệnh )", name, re.I):
            return "PROVINCIAL_COMMAND", "BQP_PROVINCIAL_COMMANDS"
        if re.match(r"^Ban Chỉ huy Bộ đội Biên phòng ", name, re.I):
            return "BORDER_GUARD_COMMAND", "BQP_BORDER_GUARD_COMMANDS"
        return "CENTRAL_OR_PUBLIC", "BQP_CENTRAL_PUBLIC"

    return "OUTSIDE_SCOPE_PUBLIC", "OTHER_TRUSTED_REFERENCE"
