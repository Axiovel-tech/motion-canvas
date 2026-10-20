"""Headless Blender test for Export .gdm (ADR 0002 §3, §8).

Runs the real operator against a stub trajectory engine that records each
`operations/render` request and answers with a canned response, so it needs
neither a network nor an engine with .gdm output.

Run from the repository root:

    blender --background --factory-startup --python-exit-code 1 \\
        --python tests/blender/test_gdm_export.py

`natsort` must be importable; the script adds this repository's `uv` virtual
environment (`uv sync`) to the path if Blender's Python lacks it.
"""

import gzip
import json
import logging
import site
import struct
import sys
import tempfile
import threading
import traceback
from base64 import b64decode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for path in (REPO / "src" / "modules", REPO / "src" / "addons"):
    sys.path.insert(0, str(path))
try:
    import natsort  # noqa: F401
except ImportError:
    for venv_site in (REPO / ".venv").glob("lib/python*/site-packages"):
        site.addsitedir(str(venv_site))

import addon_utils  # noqa: E402
import bpy  # noqa: E402

SCENE_FPS = 25
GDM_BYTES = b"PK\x05\x06" + b"\x00" * 18  # an empty ZIP stands in for a .gdm

# Engine `detail` texts, verbatim from axio-trajectory-engine
UNSUPPORTED = (
    'output format "gdm" is not supported by this server (supported: skyc, csv, report)'
)
# An engine before feature/gdm-yaw, which carried constant headings only.
YAW_CONSTANT_ONLY = (
    "unsupported .skyc feature: drone Drone 1: yaw programs need a C¹ yaw "
    "fit for .gdm (not implemented yet)"
)
YAW_STEP = (
    "cannot export to .gdm: drone Drone 2: yaw turns 90.0° in 0.040 s at "
    "t=1.00s (2250°/s), above the yaw-rate limit 30.0°/s; .gdm yaw stays "
    "within the limit and a turn (or a yaw step) is not moved in time to "
    "get there, so spread it over at least 3.00 s, or raise the limit"
)
CERT_C2 = (
    "show failed safety certification:\ndrone Drone 1: acceleration steps by "
    "4.210 m/s² at the joint at t=1.00s (C² tolerance 0.050); the artifact "
    "requires C² trajectories"
)


#############################################################################
# Stub trajectory engine
#############################################################################


class StubEngine(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), StubHandler)
        self.requests: list[dict] = []
        self.refusal: str | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"


class StubHandler(BaseHTTPRequestHandler):
    server: StubEngine

    def log_message(self, format, *args):
        pass

    def _reply(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("queries/version"):
            self._reply(200, b'{"version": "2.99.0+axio"}', "application/json")
        elif self.path.endswith("queries/limits"):
            self._reply(200, b'{"num_drones": 300, "features": []}', "application/json")
        else:
            self._reply(404, b"{}", "application/json")

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        self.server.requests.append(json.loads(body))

        if self.server.refusal:
            detail = json.dumps({"detail": self.server.refusal}).encode("utf-8")
            self._reply(400, detail, "application/json")
        else:
            self._reply(200, GDM_BYTES, "application/zip")


#############################################################################
# Scene
#############################################################################


def setup_scene() -> None:
    from sbstudio.plugin.constants import Collections

    scene = bpy.context.scene
    scene.render.fps = SCENE_FPS
    scene.frame_start = 0
    scene.frame_end = 50

    drones = Collections.find_drones(create=True)
    for index in range(2):
        drone = bpy.data.objects.new(f"Drone {index + 1}", None)
        drones.objects.link(drone)
        drone.location = (index * 3.0, 0.0, 1.0)
        drone.keyframe_insert("location", frame=0)
        drone.location = (index * 3.0, 0.0, 3.0)
        drone.keyframe_insert("location", frame=50)

    # Drone 2 turns 45° about z over the 2 s (22.5°/s, under the 30°/s limit)
    drone = bpy.data.objects["Drone 2"]
    drone.keyframe_insert("rotation_euler", frame=0)
    drone.rotation_euler[2] = 0.785398
    drone.keyframe_insert("rotation_euler", frame=50)

    # Drone 1 climbs with a "Back" easing, which overshoots on purpose
    from sbstudio.plugin.actions import iter_all_f_curves

    for fcurve in iter_all_f_curves(bpy.data.objects["Drone 1"].animation_data):
        fcurve.keyframe_points[0].interpolation = "BACK"


#############################################################################
# Helpers
#############################################################################


class Reports(logging.Handler):
    """Captures the warnings of the .gdm exporter (it logs what it reports)
    and the error that Blender raises when an operator reports one.
    """

    def __init__(self):
        super().__init__(logging.WARNING)
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.warnings.append(record.getMessage())

    def run(self, operator, **kwargs) -> set[str]:
        """Runs an operator; in background mode Blender raises the reported
        error as a RuntimeError after the operator has been cancelled.
        """
        try:
            return operator(**kwargs)
        except RuntimeError as ex:
            self.errors.append(str(ex))
            return {"CANCELLED"}


def sample_times(request: dict, drone_index: int = 0) -> list[float]:
    trajectory = request["input"]["data"]["swarm"]["drones"][drone_index]["settings"][
        "trajectory"
    ]
    assert trajectory["version"] == 2, trajectory["version"]
    raw = b64decode(trajectory["points"])
    floats = struct.unpack(f"<{len(raw) // 4}f", raw)
    return [floats[i] for i in range(0, len(floats), 4)]


def assert_close(actual: float, expected: float, what: str) -> None:
    assert abs(actual - expected) < 1e-4, f"{what}: {actual} != {expected}"


#############################################################################
# Tests
#############################################################################


def test_gdm_is_registered_and_offered(engine, reports, out):
    from sbstudio.model.file_formats import FileFormat, get_supported_file_formats

    assert FileFormat.GDM in get_supported_file_formats()
    assert hasattr(bpy.ops.export_scene, "axio_gdm")


def test_export_samples_at_scene_rate(engine, reports, out):
    path = out / "show.gdm"
    result = reports.run(bpy.ops.export_scene.axio_gdm, filepath=str(path))

    assert result == {"FINISHED"}, (result, reports.errors)
    assert path.read_bytes() == GDM_BYTES
    request = engine.requests[-1]
    assert request["output"]["format"] == "gdm", request["output"]

    times = sample_times(request, 1)
    assert len(times) == 51, len(times)
    assert_close(times[1] - times[0], 1 / SCENE_FPS, "sample spacing")


def test_export_warns_about_overshooting_easings(engine, reports, out):
    reports.run(bpy.ops.export_scene.axio_gdm, filepath=str(out / "show.gdm"))

    warnings = reports.warnings
    assert len(warnings) == 1, warnings
    assert "Drone 1 location at frame 0 (Back)" in warnings[0], warnings
    assert "Drone 2" not in warnings[0], warnings


def test_trajectory_fps_override(engine, reports, out):
    reports.run(
        bpy.ops.export_scene.axio_gdm,
        filepath=str(out / "show.gdm"),
        use_scene_fps=False,
        output_fps=5,
    )
    times = sample_times(engine.requests[-1], 1)
    assert_close(times[1] - times[0], 1 / 5, "sample spacing")


def test_engine_without_gdm(engine, reports, out):
    engine.refusal = UNSUPPORTED
    path = out / "refused.gdm"
    result = reports.run(bpy.ops.export_scene.axio_gdm, filepath=str(path))

    assert result == {"CANCELLED"}, result
    assert not path.exists()
    errors = reports.errors
    assert len(errors) == 1, errors
    assert "cannot write .gdm" in errors[0], errors
    assert UNSUPPORTED in errors[0], errors


def test_changing_yaw_is_exported(engine, reports, out):
    path = out / "yaw.gdm"
    result = reports.run(
        bpy.ops.export_scene.axio_gdm,
        filepath=str(path),
        use_yaw_control=True,
    )

    assert result == {"FINISHED"}, (result, reports.errors)
    assert path.read_bytes() == GDM_BYTES
    settings = engine.requests[-1]["input"]["data"]["swarm"]["drones"][1]["settings"]
    angles = [angle for _, angle in settings["yawControl"]["setpoints"]]
    assert abs((angles[-1] - angles[0]) - (-45.0)) < 0.01, angles


def test_engine_without_gdm_yaw(engine, reports, out):
    engine.refusal = YAW_CONSTANT_ONLY
    result = reports.run(
        bpy.ops.export_scene.axio_gdm,
        filepath=str(out / "refused.gdm"),
        use_yaw_control=True,
    )

    assert result == {"CANCELLED"}, result
    errors = reports.errors
    assert "only a constant heading" in errors[0], errors
    assert "Update the Axio trajectory engine" in errors[0], errors


def test_yaw_step(engine, reports, out):
    engine.refusal = YAW_STEP
    result = reports.run(
        bpy.ops.export_scene.axio_gdm,
        filepath=str(out / "refused.gdm"),
        use_yaw_control=True,
    )

    assert result == {"CANCELLED"}, result
    errors = reports.errors
    assert "Maximum yaw rate" in errors[0], errors
    assert YAW_STEP in errors[0], errors


def test_certification_failure_hints_at_sampling(engine, reports, out):
    engine.refusal = CERT_C2
    result = reports.run(
        bpy.ops.export_scene.axio_gdm,
        filepath=str(out / "refused.gdm"),
        use_scene_fps=False,
        output_fps=4,
    )

    assert result == {"CANCELLED"}, result
    errors = reports.errors
    assert "failed safety certification" in errors[0], errors
    assert "below the scene rate (25)" in errors[0], errors


def test_skyc_export_is_unchanged(engine, reports, out):
    engine.refusal = UNSUPPORTED  # a .skyc refusal is shown as it is
    result = reports.run(bpy.ops.export_scene.skybrush, filepath=str(out / "show.skyc"))

    assert result == {"CANCELLED"}, result
    request = engine.requests[-1]
    assert request["output"]["format"] == "skyc", request["output"]
    times = sample_times(request, 1)
    assert_close(times[1] - times[0], 6 / SCENE_FPS, "default .skyc spacing")
    errors = reports.errors
    assert "cannot write .gdm" not in errors[0], errors
    assert not reports.warnings, reports.warnings


def main() -> int:
    if addon_utils.enable("ui_skybrush_studio", default_set=True) is None:
        print("failed to enable the ui_skybrush_studio add-on")
        return 1

    bpy.context.preferences.system.use_online_access = True
    prefs = bpy.context.preferences.addons["ui_skybrush_studio"].preferences

    engine = StubEngine()
    threading.Thread(target=engine.serve_forever, daemon=True).start()
    prefs.server_url = engine.url
    prefs.api_key = ""

    setup_scene()
    exporter_log = logging.getLogger("sbstudio.plugin.operators.export_to_gdm")

    tests = [value for name, value in globals().items() if name.startswith("test_")]
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for test in tests:
            engine.refusal = None
            reports = Reports()
            exporter_log.addHandler(reports)
            out = Path(tmp) / test.__name__
            out.mkdir()
            try:
                test(engine, reports, out)
            except Exception:
                failures += 1
                print(f"FAIL {test.__name__}")
                traceback.print_exc()
            else:
                print(f"ok   {test.__name__}")
            finally:
                exporter_log.removeHandler(reports)

    engine.shutdown()
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if main():
    raise SystemExit(1)
