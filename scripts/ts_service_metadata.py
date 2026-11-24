"""Validate service metadata shared by the modern MPEG-TS producers."""

import re


def values(cfg):
    call = cfg.get("call", "")
    name = cfg.get("service_name", "")
    if not re.fullmatch(r"[A-Z0-9/]{3,20}", call) or not re.search(r"[0-9]", call):
        raise ValueError("configure a CALLSIGN (3-20 uppercase letters, digits or /)")
    if not name.strip() or len(name.encode("utf-8")) > 64 or not name.isprintable():
        raise ValueError("configure a printable service_name (1-64 UTF-8 bytes)")
    return call, name


def ffmpeg_args(cfg):
    call, name = values(cfg)
    return ["-metadata", f"service_provider={call}",
            "-metadata", f"service_name={name}"]
