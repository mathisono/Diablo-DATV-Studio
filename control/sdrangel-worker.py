#!/usr/bin/env python3
"""Own one local headless SDRangel session for the supervisor's TX or RX role."""
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib import request

MODES = {
    "DVB-S": ("DATVMod", {"standard": 0, "modulation": 1}),
    "DVB-S2": ("DATVMod", {"standard": 1}),
    "ANALOG_NTSC": ("ATVMod", {"atvStd": 1, "nbLines": 525, "fps": 30}),
    "ANALOG_PAL": ("ATVMod", {"atvStd": 0, "nbLines": 625, "fps": 25}),
    "NBTV": ("ATVMod", {"atvStd": 4}),
    "ANALOG_FM": ("ATVMod", {"atvModulation": 1}),
}
METRICS = {"channelPowerDB", "channelSampleRate", "dataRate", "udpByteCount",
           "tsFileBitrate", "mer", "cnr", "videoDecodeOK", "audioDecodeOK",
           "udpRunning", "symbolRate", "modcodModulation", "modcodCodeRate"}
STOP = False


def stop_signal(*_):
    global STOP
    STOP = True


def read_config(path):
    return dict(line.strip().split("=", 1) for line in Path(path).read_text().splitlines()
                if "=" in line and not line.lstrip().startswith("#"))


def profile_for(profile, role, mode):
    entry = profile["tx"][mode] if role == "tx" else profile["rx"]
    device = dict(entry["device"])
    if not device.get("hwType") or not isinstance(device["hwType"], str):
        raise ValueError("Device hwType is required")
    if set(device) - {"hwType", "serial", "sequence"}:
        raise ValueError("Unsupported device selector")
    if device["hwType"] not in {"FileOutput", "FileInput", "TestSource"} and not device.get("serial"):
        raise ValueError("Explicit hardware serial required (use the SDRangel device list)")
    direction = int(role == "tx")
    device["direction"] = direction
    if role == "tx":
        channel, forced = MODES[mode]
    else:
        channel, forced = "DATVDemod", {}
    settings = dict(entry["channelSettings"])
    if not all(isinstance(v, (int, float, str)) for v in settings.values()):
        raise ValueError("Channel settings must be scalar values")
    settings.update(forced)
    settings["useReverseAPI"] = 0
    if role == "tx":
        settings["channelMute"] = 1
        if channel == "DATVMod":
            if settings.get("tsSource") not in (1, 2):
                raise ValueError("DATV requires TS file (1) or UDP (2)")
            if settings["tsSource"] == 2 and (settings.get("udpAddress") != "127.0.0.1" or
                    not isinstance(settings.get("udpPort"), int) or not 1024 <= settings["udpPort"] <= 65535):
                raise ValueError("DATV UDP input must be loopback with a valid port")
            if settings["tsSource"] == 1:
                if not Path(settings.get("tsFileName", "")).is_file():
                    raise ValueError("TS file missing")
                settings["tsFilePlay"] = 1
            if settings.get("modulation") != 1:
                raise ValueError("Initial DATV profile supports QPSK only")
            allowed_fec = {0, 1, 2, 3, 4} if mode == "DVB-S" else {0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11}
            if settings.get("fec") not in allowed_fec or settings.get("rollOff") not in (0.2, 0.25, 0.35):
                raise ValueError("Invalid DVB FEC or roll-off")
            if mode == "DVB-S" and settings["rollOff"] != 0.35:
                raise ValueError("DVB-S requires 0.35 roll-off")
            if not isinstance(settings.get("symbolRate"), int) or settings["symbolRate"] <= 0:
                raise ValueError("Positive symbol rate required")
        else:
            if settings.get("atvModInput") not in (0, 1, 2, 3, 4, 5, 6, 7, 8):
                raise ValueError("Analog initial profile supports test patterns or local files only")
            if settings["atvModInput"] in (7, 8):
                key = "imageFileName" if settings["atvModInput"] == 7 else "videoFileName"
                if not Path(settings.get(key, "")).is_file():
                    raise ValueError("Analog input file missing")
                if settings["atvModInput"] == 8:
                    settings["videoPlay"] = 1
            if not isinstance(settings.get("nbLines"), int) or not 32 <= settings["nbLines"] <= 819:
                raise ValueError("Invalid analog line count")
            if settings.get("fps") not in (1, 2, 5, 8, 10, 12, 16, 20, 25, 30):
                raise ValueError("Unsupported analog frame rate")
        if not isinstance(settings.get("rfBandwidth"), (int, float)) or settings["rfBandwidth"] <= 0:
            raise ValueError("Positive channel bandwidth required")
    device_settings = entry["deviceSettings"]
    if not isinstance(device_settings, dict) or not device_settings:
        raise ValueError("Explicit device settings required")
    return device, device_settings, channel, settings


class API:
    def __init__(self, port):
        self.base = "http://127.0.0.1:%d/sdrangel" % port
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect())

    def call(self, path, method="GET", data=None):
        body = None if data is None else json.dumps(data, allow_nan=False).encode()
        req = request.Request(self.base + path, data=body, method=method,
                              headers={"Content-Type": "application/json"})
        with self.opener.open(req, timeout=0.6) as response:
            raw = response.read(524289)
            if len(raw) > 524288:
                raise ValueError("SDRangel response too large")
            return json.loads(raw) if raw else {}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def matches(actual, expected):
    for key, value in expected.items():
        other = actual.get(key)
        if isinstance(value, float) and isinstance(other, (int, float)):
            if not math.isclose(value, other, rel_tol=1e-6, abs_tol=1e-6):
                return False
        elif other != value:
            return False
    return True


def await_value(fn, predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not STOP and time.monotonic() < deadline:
        try:
            value = fn()
            if predicate(value):
                return value
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    raise RuntimeError("SDRangel API state not confirmed")


def snapshot(path, state, **extra):
    data = dict(state=state, pid=os.getpid(), updated=int(time.time()), **extra)
    fd, name = tempfile.mkstemp(prefix=".sdrangel-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, allow_nan=False)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def metrics_from(report, channel):
    values = report.get(channel + "Report", {})
    return {k: v for k, v in values.items() if k in METRICS and
            isinstance(v, (int, float)) and math.isfinite(v)}


def configure(api, device, device_settings, channel, settings):
    api.call("/deviceset?direction=%d" % device["direction"], "POST")
    await_value(lambda: api.call("/devicesets"), lambda v: v.get("devicesetcount") == 1)
    prefix = "/deviceset/0"
    api.call(prefix + "/device", "PUT", device)
    def selected(v):
        observed = v.get("samplingDevice", {})
        return all(observed.get(k) == val for k, val in device.items() if k != "direction")
    await_value(lambda: api.call(prefix), selected)
    run = prefix + "/device/run"
    if api.call(run).get("state") == "running":
        raise RuntimeError("Unexpected running device")
    device_path = prefix + "/device/settings"
    actual = api.call(device_path)
    if len(device_settings) != 1:
        raise ValueError("Expected exactly one hardware-specific settings object")
    key, values = next(iter(device_settings.items()))
    if not isinstance(values, dict) or not isinstance(actual.get(key), dict):
        raise ValueError("Wrong hardware settings object")
    if not values or not all(k in actual[key] and isinstance(v, (int, float, str)) for k, v in values.items()):
        raise ValueError("Unknown or non-scalar hardware setting")
    if "useReverseAPI" in actual[key]:
        values = dict(values, useReverseAPI=0)
    envelope = {k: actual[k] for k in ("deviceHwType", "direction", "tx") if k in actual}
    api.call(device_path, "PATCH", dict(envelope, **{key: values}))
    await_value(lambda: api.call(device_path), lambda v: matches(v.get(key, {}), values))
    api.call(prefix + "/channel", "POST", {"channelType": channel, "direction": device["direction"]})
    chan_path = prefix + "/channel/0/settings"
    key = channel + "Settings"
    current = await_value(lambda: api.call(chan_path), lambda v: isinstance(v.get(key), dict))
    if not all(k in current[key] for k in settings):
        raise ValueError("Plugin does not expose all requested settings")
    env = {k: current[k] for k in ("channelType", "direction", "tx", "originatorDeviceSetIndex", "originatorChannelIndex") if k in current}
    def patch(values):
        api.call(chan_path, "PATCH", dict(env, **{key: values}))
        await_value(lambda: api.call(chan_path), lambda v: matches(v.get(key, {}), values))
    patch(settings)
    if STOP:
        raise RuntimeError("Stop requested")
    api.call(run, "POST")
    await_value(lambda: api.call(run), lambda v: v.get("state") == "running")
    if STOP:
        raise RuntimeError("Stop requested")
    if device["direction"] == 1:
        patch({"channelMute": 0})
    return prefix, patch


def run(role):
    root = Path(os.environ.get("PORTSDOWN_DIR", Path(__file__).resolve().parents[1]))
    config = read_config(os.environ.get("PORTSDOWN_CONFIG", root / "scripts/portsdown_config.txt"))
    runtime = Path(os.environ.get("PORTSDOWN_RUN_DIR", "/run/portsdown"))
    out = runtime / ("sdrangel-" + role + ".json")
    process = api = None
    try:
        snapshot(out, "starting")
        if os.environ.get("PORTSDOWN_BOARD") != "sdrangel" or config.get("modeoutput") != "SDRANGEL":
            raise ValueError("SDRangel board not selected")
        if os.environ.get("PORTSDOWN_PEER_ROLE", "STANDALONE") != "STANDALONE":
            raise ValueError("SDRangel is standalone-only")
        if config.get("modeinput") != "SDRANGEL_PROFILE" or config.get("source_layout", "DIRECT") != "DIRECT":
            raise ValueError("SDRangel profile source required")
        profile = json.loads(Path(os.environ["PORTSDOWN_SDRANGEL_PROFILE"]).read_text())
        device, device_settings, channel, settings = profile_for(profile, role, config["modulation"])
        binary = os.environ.get("PORTSDOWN_SDRANGEL_BINARY", "/usr/bin/sdrangelsrv")
        if not os.path.isabs(binary) or not os.access(binary, os.X_OK):
            raise ValueError("Set PORTSDOWN_SDRANGEL_BINARY to an executable absolute path")
        with tempfile.TemporaryDirectory(prefix="sdrangel-", dir=runtime) as private:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            env = dict(os.environ, XDG_CONFIG_HOME=private, XDG_DATA_HOME=private, XDG_CACHE_HOME=private)
            process = subprocess.Popen([binary, "--scratch", "-a", "127.0.0.1", "-p", str(port)],
                                       env=env, stdin=subprocess.DEVNULL)
            api = API(port)
            def initial():
                if process.poll() is not None:
                    raise RuntimeError("SDRangel server exited")
                return api.call("/devicesets")
            await_value(initial, lambda v: v.get("devicesetcount") == 0, 15)
            prefix, _ = configure(api, device, device_settings, channel, settings)
            print("SDRangel %s device running (%s); process state is not RF measurement" % (role, channel), flush=True)
            while not STOP:
                if process.poll() is not None:
                    raise RuntimeError("SDRangel server exited")
                state = api.call(prefix + "/device/run").get("state")
                if state != "running":
                    raise RuntimeError("SDRangel device no longer running")
                try:
                    metrics = metrics_from(api.call(prefix + "/channel/0/report"), channel)
                except (OSError, ValueError):
                    metrics = {}
                snapshot(out, "running", device_state=state, channel=channel, metrics=metrics)
                time.sleep(0.5)
    finally:
        # The C supervisor also signals/kills this entire process group and
        # invokes the site-specific independent hardware safe-off hook.
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        snapshot(out, "stopped")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in {"tx", "rx"}:
            raise ValueError("Usage: sdrangel-worker.py tx|rx")
        run(sys.argv[1])
    except Exception as exc:
        print("SDRangel failed: %s" % type(exc).__name__ + ": " + str(exc)[:200], file=sys.stderr, flush=True)
        sys.exit(1)
