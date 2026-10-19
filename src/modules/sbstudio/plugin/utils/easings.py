"""Collects keyframe interpolation modes from the objects that move drones."""

from collections.abc import Iterable, Iterator

from bpy.types import Object

from sbstudio.model.gdm import KeyframeCurve
from sbstudio.plugin.actions import iter_all_f_curves

__all__ = ("iter_keyframe_curves_moving",)


def _objects_moving(drones: Iterable[Object]) -> Iterator[Object]:
    """Yields the given drones and every object that can move them: their
    parents and constraint targets (formation markers), transitively, each
    object once.
    """
    seen: set[str] = set()
    queue: list[Object] = list(drones)

    while queue:
        obj = queue.pop()
        if obj is None or obj.name in seen:
            continue
        seen.add(obj.name)
        yield obj

        if obj.parent is not None:
            queue.append(obj.parent)
        for constraint in getattr(obj, "constraints", ()):
            target = getattr(constraint, "target", None)
            if isinstance(target, Object):
                queue.append(target)


def iter_keyframe_curves_moving(drones: Iterable[Object]) -> Iterator[KeyframeCurve]:
    """Yields the F-curves of the given drones and of the objects that move
    them, as ``(object name, data path, [(frame, interpolation), ...])``.
    """
    for obj in _objects_moving(drones):
        for fcurve in iter_all_f_curves(obj.animation_data):
            keyframes = [
                (point.co.x, point.interpolation) for point in fcurve.keyframe_points
            ]
            yield obj.name, fcurve.data_path, keyframes
