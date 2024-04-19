from enum import IntEnum
from typing import Literal

# https://github.com/openatv/enigma2/blob/a0979a6091df64d9f1e7283fa9bd40ca3f64d9d8/doc/SERVICEREF#L131


class ServiceType(IntEnum):
    TV = 0x01  # digital television
    MPEG2HDTV = 0x11  # MPEG-2 HD digital television service
    SDTV = 0x16  # H.264/AVC SD digital television service
    HDTV = 0x19  # H.264/AVC HD digital television service
    HEVC = 0x1F  # HEVC digital television service
    HEVCUHD = 0x20  # HEVC UHD digital television service
    UNKNOWN = -1


class Namespace(IntEnum):
    # anything else is a valid satellite position
    DVB_C = 0xFFFF0000
    DVB_T = 0xEEEE0000


# %d:%d:%x:%x:%x:%x:%x:%x:%x:%x:%d:%s:%s
SREF_FMT = "1:0:{:x}:{:x}:{:x}:{:x}:{:x}:0:0:0:"

# 3600 - west_sat_position
def build_namespace(pos: float, cardinal: Literal["E", "W"]) -> int:
    pos = int(pos * 10)
    if cardinal == "W":
        pos = 3600 - pos
    return pos << 16


def pos_from_namespace(ns: int) -> str:
    pos = ns >> 16
    if pos > 1800:
        return f"{(3600 - pos) / 10}W"
    return f"{pos / 10}E"


# REFTYPE:FLAGS:STYPE:SID:TSID:ONID:NS:PARENT_SID:PARENT_TSID:UNUSED:PATH:NAME
# we only care about DVB here
def build_sref(service_type, sid, tsid, onid, ns):
    return SREF_FMT.format(service_type, sid, tsid, onid, ns).upper()


def parse_sref(sref):
    parts = sref.split(":")

    service_type = ServiceType._value2member_map_.get((int(parts[2], 16)))
    if not service_type:
        service_type = ServiceType.UNKNOWN

    pos = pos_from_namespace(int(parts[6], 16))

    return {
        "service_type": service_type.name,
        "sid": int(parts[3], 16),  # Stream ID
        "tsid": int(parts[4], 16),  # Transport stream ID (tp xx -> xx00 or TID in ONID-TID)
        "onid": int(parts[5], 16),  # Originating network ID (ONID in ONIT-TID)
        "sat_pos": pos,
    }
