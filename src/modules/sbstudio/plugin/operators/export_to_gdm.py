import logging
from typing import Any

from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Context

from sbstudio.model.file_formats import FileFormat
from sbstudio.model.gdm import (
    find_overshooting_easings,
    format_overshooting_easings_warning,
)
from sbstudio.plugin.props.frame_range import resolve_frame_range
from sbstudio.plugin.utils.easings import iter_keyframe_curves_moving

from .base import ExportOperator
from .utils import get_drones_to_export

__all__ = ("GDMExportOperator",)


log = logging.getLogger(__name__)


#############################################################################
# Operator that allows the user to invoke the .gdm export operation
#############################################################################


class GDMExportOperator(ExportOperator):
    """Export object trajectories and light animation into the Axiovel .gdm show format (C² curves)"""

    bl_idname = "export_scene.axio_gdm"
    bl_label = "Export .gdm"
    bl_options = {"REGISTER"}

    # List of file extensions that correspond to .gdm files
    filter_glob = StringProperty(default="*.gdm", options={"HIDDEN"})
    filename_ext = ".gdm"

    # sample trajectories at the scene frame rate (ADR 0002 §8): the C²
    # fitter needs scene-rate samples to follow velocity steps
    use_scene_fps = BoolProperty(
        name="Sample at scene frame rate",
        default=True,
        description=(
            "Sample trajectories at every frame of the scene. The .gdm fitter "
            "builds C² curves from these samples, so it needs the motion as "
            "it was animated"
        ),
    )

    # output trajectory frame rate, used only when use_scene_fps is off
    output_fps = IntProperty(
        name="Trajectory FPS",
        default=24,
        min=1,
        description=(
            "Number of samples to take from trajectories per second when not "
            "sampling at the scene frame rate"
        ),
    )

    # output light program frame rate
    light_output_fps = IntProperty(
        name="Light FPS",
        default=4,
        description="Number of samples to take from light programs per second",
    )

    # pyro control enable/disable
    use_pyro_control = BoolProperty(
        name="Export pyro (PRO)",
        description="Specifies whether the pyro program of each drone should be included in the show",
        default=False,
    )

    # yaw control enable/disable
    use_yaw_control = BoolProperty(
        name="Export yaw (PRO)",
        description=(
            "Specifies whether the yaw angle of each drone should be controlled "
            "during the show. .gdm currently supports a constant heading only"
        ),
        default=False,
    )

    # export cameras enable/disable
    export_cameras = BoolProperty(
        name="Export cameras",
        description="Specifies whether cameras defined in Blender should be exported into the show file",
        default=False,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        layout.prop(self, "export_selected")
        layout.prop(self, "frame_range")
        layout.prop(self, "redraw")
        layout.prop(self, "use_scene_fps")
        row = layout.row()
        row.active = not self.use_scene_fps
        row.prop(self, "output_fps")
        layout.prop(self, "light_output_fps")

        layout.separator()

        column = layout.column(align=True)
        column.prop(self, "export_cameras")
        column.prop(self, "use_pyro_control")
        column.prop(self, "use_yaw_control")

    def execute(self, context: Context):
        warning = self._check_overshooting_easings(context)
        result = super().execute(context)

        # Reported after the export so that it is not hidden behind the
        # success or error message of the export itself
        if warning:
            self.report({"WARNING"}, warning)

        return result

    def get_format(self) -> FileFormat:
        return FileFormat.GDM

    def get_operator_name(self) -> str:
        return ".gdm exporter"

    def get_settings(self) -> dict[str, Any]:
        return {
            "use_scene_fps": self.use_scene_fps,
            "output_fps": self.output_fps,
            "light_output_fps": self.light_output_fps,
            "use_pyro_control": self.use_pyro_control,
            "use_yaw_control": self.use_yaw_control,
            "export_cameras": self.export_cameras,
        }

    def _check_overshooting_easings(self, context: Context) -> str:
        """Returns a warning if the exported animation uses easings that
        overshoot on purpose (ADR 0002 §8), or an empty string otherwise.

        Never fails the export: the scan is advisory.
        """
        try:
            frame_range = resolve_frame_range(self.frame_range, context=context)
            drones = list(get_drones_to_export(selected_only=self.export_selected))
            found = find_overshooting_easings(
                iter_keyframe_curves_moving(drones), frame_range
            )
        except Exception:
            log.exception("Could not scan the animation for overshooting easings")
            return ""

        warning = format_overshooting_easings_warning(found)
        if warning:
            log.warning(warning)
        return warning
