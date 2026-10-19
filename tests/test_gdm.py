"""Tests for the Blender-independent parts of the .gdm export (ADR 0002).

The operator itself is covered by `tests/blender/test_gdm_export.py`, which
needs Blender.
"""

import pytest
from sbstudio.model.gdm import (
    OvershootingEasing,
    explain_gdm_refusal,
    find_overshooting_easings,
    format_overshooting_easings_warning,
    is_motion_data_path,
)

# Engine `detail` texts, verbatim from axio-trajectory-engine (crates/rest and
# crates/codec on feature/c2-fitter), prefixed the way the API client does.
UNSUPPORTED = (
    'Bad Request: output format "gdm" is not supported by this server '
    "(supported: skyc, csv, report)"
)
YAW_PROGRAM = (
    "Bad Request: unsupported .skyc feature: drone Drone 3: yaw programs need "
    "a C¹ yaw fit for .gdm (not implemented yet)"
)
AUTO_YAW = (
    "Bad Request: unsupported .skyc feature: drone Drone 1: auto-yaw has no "
    ".gdm representation"
)
CERT_C2 = (
    "Bad Request: show failed safety certification:\n"
    "drone Drone 2: acceleration steps by 4.210 m/s² at the joint at t=12.50s "
    "(C² tolerance 0.050); the artifact requires C² trajectories"
)
CERT_SEPARATION = (
    "Bad Request: show failed safety certification:\n"
    "drones Drone 1 and Drone 2 are 0.50 m apart at t=3.00s (min 1.50 m)"
)


class TestExplainGdmRefusal:
    def test_server_without_gdm(self):
        message = explain_gdm_refusal(UNSUPPORTED)
        assert message is not None
        assert "cannot write .gdm" in message
        assert "Export .skyc" in message
        assert UNSUPPORTED in message

    @pytest.mark.parametrize(
        "detail",
        [
            "Bad Request: Unknown renderer: gdm",
            "Bad Request: unsupported output format 'gdm'",
        ],
    )
    def test_other_unsupported_wordings(self, detail):
        message = explain_gdm_refusal(detail)
        assert message is not None
        assert "cannot write .gdm" in message

    @pytest.mark.parametrize("detail", [YAW_PROGRAM, AUTO_YAW])
    def test_non_constant_yaw(self, detail):
        message = explain_gdm_refusal(detail)
        assert message is not None
        assert "constant heading" in message
        assert '"Export yaw"' in message
        assert detail in message

    def test_certification_failure(self):
        message = explain_gdm_refusal(CERT_SEPARATION, output_fps=25, scene_fps=25)
        assert message is not None
        assert "failed safety certification" in message
        assert "no file was written" in message
        assert "0.50 m apart" in message
        assert "scene rate" not in message

    def test_c2_failure_below_scene_rate_hints_at_sampling(self):
        message = explain_gdm_refusal(CERT_C2, output_fps=4, scene_fps=25)
        assert message is not None
        assert "Trajectory FPS is 4, below the scene rate (25)" in message
        assert "Sample at scene frame rate" in message

    def test_c2_failure_at_scene_rate_has_no_sampling_hint(self):
        message = explain_gdm_refusal(CERT_C2, output_fps=25, scene_fps=25)
        assert message is not None
        assert "scene rate" not in message

    @pytest.mark.parametrize(
        "detail",
        [
            "Request returned HTTP error code 502",
            "Bad Request: drone names must be unique",
        ],
    )
    def test_unrelated_errors_pass_through(self, detail):
        assert explain_gdm_refusal(detail) is None


class TestOvershootingEasings:
    def test_motion_data_paths(self):
        assert is_motion_data_path("location")
        assert is_motion_data_path("rotation_euler")
        assert is_motion_data_path('constraints["To Formation"].influence')
        assert not is_motion_data_path("color")
        assert not is_motion_data_path('["skybrush"]')

    def test_finds_back_elastic_and_bounce(self):
        curves = [
            ("Drone 1", "location", [(0, "BACK"), (10, "BEZIER"), (20, "LINEAR")]),
            ("Drone 2", "location", [(0, "ELASTIC"), (10, "LINEAR")]),
            ("Marker 1", "location", [(5, "BOUNCE"), (15, "BEZIER")]),
            ("Drone 3", "location", [(0, "BEZIER"), (10, "SINE")]),
        ]
        found = find_overshooting_easings(curves)
        assert [(e.object_name, e.frame, e.easing_name) for e in found] == [
            ("Drone 1", 0, "Back"),
            ("Drone 2", 0, "Elastic"),
            ("Marker 1", 5, "Bounce"),
        ]

    def test_last_keyframe_interpolation_does_not_count(self):
        curves = [("Drone 1", "location", [(0, "LINEAR"), (10, "BACK")])]
        assert find_overshooting_easings(curves) == []

    def test_non_motion_curves_are_ignored(self):
        curves = [("Drone 1", "color", [(0, "ELASTIC"), (10, "LINEAR")])]
        assert find_overshooting_easings(curves) == []

    def test_frame_range_limits_the_scan(self):
        curves = [
            (
                "Drone 1",
                "location",
                [(0, "BACK"), (10, "LINEAR"), (20, "BOUNCE"), (30, "LINEAR")],
            )
        ]
        assert [e.frame for e in find_overshooting_easings(curves, (12, 40))] == [20]
        assert [e.frame for e in find_overshooting_easings(curves, (5, 15))] == [0]
        assert find_overshooting_easings(curves, (10, 20)) == []

    def test_one_entry_per_segment_across_axes(self):
        # Blender has one F-curve per axis; the same segment on x, y and z
        # is one finding.
        keyframes = [(0, "BACK"), (10, "LINEAR")]
        curves = [("Drone 1", "location", keyframes)] * 3
        assert len(find_overshooting_easings(curves)) == 1

    def test_warning_text(self):
        found = [
            OvershootingEasing("Drone 1", "location", 0, "BACK"),
            OvershootingEasing("Drone 2", "location", 12, "ELASTIC"),
        ]
        warning = format_overshooting_easings_warning(found)
        assert warning.startswith("2 keyframe segment(s) on 2 object(s)")
        assert "(Back, Elastic)" in warning
        assert "Drone 2 location at frame 12 (Elastic)" in warning
        assert "not the fitter" in warning

    def test_warning_is_truncated(self):
        found = [
            OvershootingEasing(f"Drone {i}", "location", 0, "BOUNCE") for i in range(8)
        ]
        warning = format_overshooting_easings_warning(found, max_items=3)
        assert "5 more" in warning
        assert "Drone 3" not in warning

    def test_no_warning_without_findings(self):
        assert format_overshooting_easings_warning([]) == ""
