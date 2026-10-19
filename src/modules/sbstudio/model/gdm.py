"""Blender-independent helpers for the `.gdm` export (ADR 0002).

Kept free of `bpy` so that they can be unit-tested outside Blender.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

__all__ = (
    "OVERSHOOTING_EASINGS",
    "OvershootingEasing",
    "explain_gdm_refusal",
    "find_overshooting_easings",
    "format_overshooting_easings_warning",
    "is_motion_data_path",
)


#############################################################################
# Overshooting easings (ADR 0002 §8)
#############################################################################

OVERSHOOTING_EASINGS: dict[str, str] = {
    "BACK": "Back",
    "BOUNCE": "Bounce",
    "ELASTIC": "Elastic",
}
"""Blender keyframe interpolation modes that overshoot their end value on
purpose, mapped to the names Blender shows in the UI.
"""

_MOTION_DATA_PATH_PREFIXES = (
    "location",
    "rotation_",
    "scale",
    "delta_",
    "constraints[",
)


def is_motion_data_path(data_path: str) -> bool:
    """Returns whether an F-curve with the given data path can move an object.

    Colors, visibility and custom properties do not move drones, so an
    overshooting easing on them is not worth a warning.
    """
    return data_path.startswith(_MOTION_DATA_PATH_PREFIXES)


@dataclass(frozen=True)
class OvershootingEasing:
    """A keyframe segment that uses an overshooting easing."""

    object_name: str
    """Name of the animated object."""

    data_path: str
    """Data path of the F-curve, e.g. ``location``."""

    frame: float
    """Frame of the keyframe whose interpolation applies to the segment."""

    interpolation: str
    """Blender interpolation mode, e.g. ``BACK``."""

    @property
    def easing_name(self) -> str:
        return OVERSHOOTING_EASINGS.get(self.interpolation, self.interpolation)


KeyframeCurve = tuple[str, str, Sequence[tuple[float, str]]]
"""An F-curve as ``(object name, data path, [(frame, interpolation), ...])``,
keyframes in time order.
"""


def find_overshooting_easings(
    curves: Iterable[KeyframeCurve], frame_range: tuple[float, float] | None = None
) -> list[OvershootingEasing]:
    """Finds keyframe segments that use an overshooting easing.

    The interpolation of a keyframe applies from that keyframe to the next
    one, so the last keyframe of a curve never counts. Curves that cannot
    move an object are skipped.

    Parameters:
        curves: the F-curves to scan
        frame_range: when given, only segments overlapping this inclusive
            frame range are reported

    Returns:
        the segments found, at most one per object, data path and frame
    """
    found: set[OvershootingEasing] = set()

    for object_name, data_path, keyframes in curves:
        if not is_motion_data_path(data_path):
            continue

        for (frame, interpolation), (next_frame, _) in zip(
            keyframes, keyframes[1:], strict=False
        ):
            if interpolation not in OVERSHOOTING_EASINGS:
                continue
            if frame_range is not None and (
                next_frame <= frame_range[0] or frame >= frame_range[1]
            ):
                continue
            found.add(
                OvershootingEasing(
                    object_name=object_name,
                    data_path=data_path,
                    frame=frame,
                    interpolation=interpolation,
                )
            )

    return sorted(found, key=lambda e: (e.object_name, e.frame, e.data_path))


def format_overshooting_easings_warning(
    found: Sequence[OvershootingEasing], *, max_items: int = 5
) -> str:
    """Formats a user-facing warning about overshooting easings."""
    if not found:
        return ""

    names = sorted({item.easing_name for item in found})
    objects = sorted({item.object_name for item in found})
    items = [
        f"{item.object_name} {item.data_path} at frame {item.frame:g} "
        f"({item.easing_name})"
        for item in found[:max_items]
    ]
    if len(found) > max_items:
        items.append(f"{len(found) - max_items} more")

    return (
        f"{len(found)} keyframe segment(s) on {len(objects)} object(s) use "
        f"overshooting easings ({', '.join(names)}): {'; '.join(items)}. "
        "The .gdm trajectory follows that overshoot on purpose; it is the "
        "animation, not the fitter."
    )


#############################################################################
# Engine refusals
#############################################################################

_UNSUPPORTED_FORMAT = re.compile(
    r"(format|renderer|output)\b.*\bgdm\b.*\b(not supported|unsupported|unknown|invalid)"
    r"|\b(unknown|unsupported|invalid)\b.*\b(format|renderer|output)\b.*\bgdm\b",
    re.IGNORECASE | re.DOTALL,
)

_YAW = re.compile(r"auto-yaw|yaw program|yaw fit", re.IGNORECASE)

_C2 = re.compile(r"acceleration steps|requires C²|C² tolerance", re.IGNORECASE)


def explain_gdm_refusal(
    message: str,
    *,
    output_fps: float | None = None,
    scene_fps: float | None = None,
) -> str | None:
    """Turns a `render` refusal for ``format: gdm`` into a message that says
    what the designer can do about it.

    Parameters:
        message: the error message from the API client, which carries the
            server's ``detail`` verbatim
        output_fps: the trajectory sampling rate used for the export
        scene_fps: the frame rate of the scene

    Returns:
        the explained message, or `None` if the refusal is not one of the
        known `.gdm` cases (the caller then shows it as it is)
    """
    if _YAW.search(message):
        return (
            ".gdm export refused: the engine supports only a constant heading "
            "per drone in .gdm until it can fit smooth (C¹) yaw. Turn off "
            '"Export yaw", or keep each drone\'s yaw constant. '
            f"Engine said: {message}"
        )

    if _UNSUPPORTED_FORMAT.search(message):
        return (
            "This trajectory engine cannot write .gdm. Export .gdm needs an "
            "Axio trajectory engine with .gdm output; update the engine, or "
            f"use Export .skyc with this one. Engine said: {message}"
        )

    if "certification" in message.lower():
        hint = ""
        if (
            _C2.search(message)
            and output_fps is not None
            and scene_fps is not None
            and output_fps < scene_fps
        ):
            hint = (
                f" Trajectory FPS is {output_fps:g}, below the scene rate "
                f"({scene_fps:g}); the C² fitter needs scene-rate samples to "
                'follow velocity steps. Enable "Sample at scene frame rate".'
            )
        return (
            ".gdm export refused: the show failed safety certification, so "
            f"no file was written.{hint} Engine said: {message}"
        )

    return None
