import os
import platform
import subprocess
from pathlib import Path

import bpy

from ...addon_helpers.generic_tools import force_redraw_ui
from .common_declarations import Block_RTC_Members
from .data_structures import Library_Operation_Status, Library_Source_Policy, Library_Status
from .feature_pip_library_manager import Wrapper_Pip_Library_Manager


_ACTIVE_OPERATION_STATUSES = {
    Library_Operation_Status.PREPARING,
    Library_Operation_Status.INSTALLING,
    Library_Operation_Status.VERIFYING,
    Library_Operation_Status.ACTIVATING,
}


def _wrap_text(text: str, width: int = 82) -> list[str]:
    words = str(text).split()
    lines, current = [], []
    for word in words:
        if current and len(" ".join(current + [word])) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def _draw_requirement_summary(layout, info) -> None:
    declaration = info.declaration
    box = layout.box()
    box.label(text=declaration.feature_label, icon="IMPORT")
    for line in _wrap_text(declaration.reason):
        box.label(text=line)

    details = layout.box()
    details.label(text=f"Package: {declaration.distribution_name}")
    details.label(text=f"Required version: {declaration.required_version}")
    details.label(text=f"Installed version: {info.installed_version or 'Not installed'}")
    details.label(text=f"Requested by: {info.requesting_block_id}")
    details.label(text=f"Source policy: {declaration.source_policy.value.replace('_', ' ').title()}")

    path_state = Wrapper_Pip_Library_Manager._ensure_managed_path()
    target = str(path_state)
    path_box = layout.box()
    path_box.label(text="Files will be installed to:", icon="FILE_FOLDER")
    for line in _wrap_text(target, 75):
        path_box.label(text=line)

    warning = layout.box()
    warning.alert = True
    warning.label(text="Python wheels may contain executable native code.", icon="ERROR")
    if declaration.source_policy != Library_Source_Policy.BUNDLED_ONLY:
        warning.label(text="An internet connection may be used to contact the package index.")


def _draw_operation(layout, operation) -> None:
    icon = "TIME" if operation.status in _ACTIVE_OPERATION_STATUSES else (
        "CHECKMARK" if operation.status == Library_Operation_Status.FINISHED else "ERROR"
    )
    layout.label(
        text=f"{operation.distribution_name} {operation.required_version}: "
             f"{operation.status.value.replace('_', ' ').title()}",
        icon=icon,
    )
    if operation.error_summary:
        box = layout.box()
        box.alert = True
        for line in _wrap_text(operation.error_summary):
            box.label(text=line)
    log_box = layout.box()
    log_box.label(
        text=f"Recent output ({len(operation.recent_log_lines)} of "
             f"{operation.total_log_line_count} lines)",
        icon="CONSOLE",
    )
    for line in operation.recent_log_lines:
        log_box.label(text=(line[:105] + "…") if len(line) > 106 else line)

    row = layout.row(align=True)
    open_log = row.operator("dgblocks.pip_library_open_path", text="Open Log", icon="TEXT")
    open_log.path = operation.log_path
    open_folder = row.operator(
        "dgblocks.pip_library_open_path", text="Open Folder", icon="FILE_FOLDER"
    )
    open_folder.path = operation.target_path
    if operation.status in _ACTIVE_OPERATION_STATUSES:
        cancel = row.operator("dgblocks.pip_library_cancel", text="Cancel", icon="CANCEL")
        cancel.operation_uid = operation.operation_uid


class DGBLOCKS_OT_Pip_Library_Confirm_Install(bpy.types.Operator):
    bl_idname = "dgblocks.pip_library_confirm_install"
    bl_label = "Download & Install"
    bl_description = "Download and install this exact wheel requirement"
    bl_options = {"INTERNAL"}

    request_uid: bpy.props.StringProperty(options={"HIDDEN"})  # type: ignore

    def invoke(self, context, event):
        request = Wrapper_Pip_Library_Manager._requests().get(self.request_uid)
        info = Wrapper_Pip_Library_Manager._requirement_infos().get(
            request.namespaced_requirement_uid if request else ""
        )
        if info is None:
            self.report({"ERROR"}, "Library request is no longer available")
            return {"CANCELLED"}
        title = (
            f"Download & Replace {info.declaration.distribution_name}?"
            if info.status == Library_Status.VERSION_MISMATCH
            else f"Download {info.declaration.distribution_name}?"
        )
        confirm_text = (
            "Download & Replace"
            if info.status == Library_Status.VERSION_MISMATCH
            else "Download & Install"
        )
        return context.window_manager.invoke_props_dialog(
            self, width=620, title=title, confirm_text=confirm_text
        )

    def draw(self, context):
        request = Wrapper_Pip_Library_Manager._requests().get(self.request_uid)
        info = Wrapper_Pip_Library_Manager._requirement_infos().get(
            request.namespaced_requirement_uid if request else ""
        )
        if info:
            _draw_requirement_summary(self.layout, info)

    def execute(self, context):
        result = bpy.ops.dgblocks.pip_library_progress(
            "INVOKE_DEFAULT", request_uid=self.request_uid
        )
        return {"FINISHED"} if "CANCELLED" not in result else {"CANCELLED"}


class DGBLOCKS_OT_Pip_Library_Progress(bpy.types.Operator):
    bl_idname = "dgblocks.pip_library_progress"
    bl_label = "Python Library Installation"
    bl_options = {"INTERNAL"}

    request_uid: bpy.props.StringProperty(options={"HIDDEN"})  # type: ignore
    operation_uid: bpy.props.StringProperty(options={"HIDDEN"})  # type: ignore
    _timer = None

    def invoke(self, context, event):
        operation = Wrapper_Pip_Library_Manager.start_install(self.request_uid)
        if operation is None:
            self.report({"ERROR"}, "Unable to start Python library installation")
            return {"CANCELLED"}
        self.operation_uid = operation.operation_uid
        self._timer = context.window_manager.event_timer_add(0.15, window=context.window)
        context.window_manager.modal_handler_add(self)
        # A popup is a convenient live view; the manager panel remains the fallback if it is closed.
        context.window_manager.invoke_popup(self, width=700)
        return {"RUNNING_MODAL"}

    def draw(self, context):
        operation = Wrapper_Pip_Library_Manager.poll_operation(self.operation_uid)
        if operation:
            _draw_operation(self.layout, operation)

    def modal(self, context, event):
        if event.type == "TIMER":
            operation = Wrapper_Pip_Library_Manager.poll_operation(self.operation_uid)
            force_redraw_ui(context, only_3Dviewport=False)
            if operation is None or operation.status not in _ACTIVE_OPERATION_STATUSES:
                self._cleanup(context)
                if operation and operation.status == Library_Operation_Status.FINISHED:
                    self.report({"INFO"}, f"Installed {operation.distribution_name}")
                elif operation and operation.status == Library_Operation_Status.RESTART_REQUIRED:
                    self.report({"WARNING"}, "Library installed; restart Blender before using it")
                elif operation and operation.status == Library_Operation_Status.ERROR:
                    self.report({"ERROR"}, operation.error_summary or "Installation failed")
                return {"FINISHED"}
        return {"PASS_THROUGH"}

    def cancel(self, context):
        # Closing the popup does not cancel pip; progress remains visible in the manager panel.
        return None

    def _cleanup(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None


class DGBLOCKS_OT_Pip_Library_Cancel(bpy.types.Operator):
    bl_idname = "dgblocks.pip_library_cancel"
    bl_label = "Cancel Python Library Installation"
    bl_options = {"INTERNAL"}

    operation_uid: bpy.props.StringProperty(options={"HIDDEN"})  # type: ignore

    def execute(self, context):
        if not Wrapper_Pip_Library_Manager.cancel_operation(self.operation_uid):
            self.report({"WARNING"}, "Installation operation no longer exists")
            return {"CANCELLED"}
        return {"FINISHED"}


class DGBLOCKS_OT_Pip_Library_Refresh(bpy.types.Operator):
    bl_idname = "dgblocks.pip_library_refresh"
    bl_label = "Refresh Python Libraries"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        Wrapper_Pip_Library_Manager.repoll()
        self.report({"INFO"}, "Python library status refreshed")
        return {"FINISHED"}


class DGBLOCKS_OT_Pip_Library_Open_Path(bpy.types.Operator):
    bl_idname = "dgblocks.pip_library_open_path"
    bl_label = "Open Path"
    bl_options = {"INTERNAL"}

    path: bpy.props.StringProperty(options={"HIDDEN"})  # type: ignore

    def execute(self, context):
        path = Path(self.path)
        target = path if path.is_dir() else path.parent
        if not target.exists():
            self.report({"ERROR"}, f"Path does not exist: {target}")
            return {"CANCELLED"}
        try:
            if platform.system() == "Windows":
                os.startfile(str(target))
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:
            self.report({"ERROR"}, f"Unable to open path: {exc}")
            return {"CANCELLED"}
        return {"FINISHED"}


def ui_draw_pip_library_manager(context, layout) -> None:
    header = layout.row(align=True)
    header.operator("dgblocks.pip_library_refresh", icon="FILE_REFRESH")
    state = Wrapper_Pip_Library_Manager._ensure_managed_path()
    open_folder = header.operator("dgblocks.pip_library_open_path", text="Open Environment")
    open_folder.path = str(state)

    from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
    managed_state = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MANAGED_PATH_STATE)
    if managed_state and managed_state.warning:
        warning = layout.box()
        warning.alert = True
        for line in _wrap_text(managed_state.warning):
            warning.label(text=line, icon="ERROR")

    infos = Wrapper_Pip_Library_Manager.get_all_library_infos()
    if not infos:
        layout.label(text="No Python library requirements declared", icon="INFO")
    for info in infos:
        box = layout.box()
        row = box.row()
        row.label(text=info.distribution_name)
        row.label(text=info.status.value.replace("_", " ").title())
        box.label(text=f"Installed: {info.installed_version or '—'}")
        box.label(text=f"Required: {', '.join(info.required_versions) or '—'}")
        box.label(text=f"Requested by: {', '.join(info.requesting_block_ids)}")
        if info.error_summary:
            box.alert = True
            box.label(text=info.error_summary, icon="ERROR")

    operations = Wrapper_Pip_Library_Manager._operations()
    if operations:
        layout.separator()
        layout.label(text="Install Operations", icon="CONSOLE")
        for operation in operations.values():
            box = layout.box()
            _draw_operation(box, Wrapper_Pip_Library_Manager.poll_operation(operation.operation_uid))
