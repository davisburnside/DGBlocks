import sys
import os
import site
import importlib
import subprocess
import threading
import shutil
import platform
from enum import Enum
from datetime import datetime
from addon_helpers.generic_helpers import get_addon_preferences
import bpy

from ...addon_config import Documentation_URLs, addon_name

from ...blocks_natively_included._block_core.core_feature_runtime_cache import (
        Wrapper_Runtime_Cache.get_cache, 
        Wrapper_Runtime_Cache.set_cache)
from ...blocks_natively_included._block_core.core_helper_uilayouts import uilayout_draw_block_panel_header
from ...blocks_natively_included._block_core.core_helper_functions import force_redraw_ui
from ...blocks_natively_included._block_core.core_feature_logs import get_logger

from ..block_constants import (
        CACHE_KEY_LIBRARY_INSTALL_REGISTRY, 
        CACHE_KEY_LIBRARY_MODULE_CACHE, 
        CACHE_KEY_LIBRARY_PATH_REGISTERED, 
        Block_Logger_Definitions, 
        Python_Library_Dependencies)

#================================================================
# REGISTRY HELPERS
#================================================================

def _get_install_registry():
    """Get the install registry from cache, creating if needed."""
    registry = Wrapper_Runtime_Cache.get_cache(CACHE_KEY_LIBRARY_INSTALL_REGISTRY)
    if registry is None:
        registry = {}
        Wrapper_Runtime_Cache.set_cache(CACHE_KEY_LIBRARY_INSTALL_REGISTRY, registry)
    return registry

def _get_library_data(library_name):
    """Get data for a specific library from the registry."""
    registry = _get_install_registry()
    return registry.get(library_name)

def _set_library_data(library_name, data):
    """Set data for a specific library in the registry."""
    registry = _get_install_registry()
    registry[library_name] = data
    Wrapper_Runtime_Cache.set_cache(CACHE_KEY_LIBRARY_INSTALL_REGISTRY, registry)

def _update_library_data(library_name, **kwargs):
    """Update specific fields in library data."""
    data = _get_library_data(library_name)
    if data:
        data.update(kwargs)
        _set_library_data(library_name, data)

def _get_module_cache():
    """Get the module cache from runtime cache."""
    cache = Wrapper_Runtime_Cache.get_cache(CACHE_KEY_LIBRARY_MODULE_CACHE)
    if cache is None:
        cache = {}
        Wrapper_Runtime_Cache.set_cache(CACHE_KEY_LIBRARY_MODULE_CACHE, cache)
    return cache

#================================================================
# LIBRARY INSTALLATION WRAPPER
#================================================================

class Library_Installation_Wrapper:
    """
    Manages optional library imports and custom installation paths.
    """

    @classmethod
    def _get_library_home_path(cls):
        """Retrieves the custom path from Addon Preferences."""
        try:
            prefs = get_addon_preferences(bpy.context)
            path = prefs.addon_saved_data_folder
            library_subpath = [bpy.app.version_string, "site_packages"]
            
            if path:
                path = os.path.join(path, *library_subpath)
                return os.path.abspath(os.path.expanduser(path))
            return None
        except (AttributeError, KeyError):
            return None

    @classmethod
    def _is_path_registered(cls):
        """Check if custom path has been registered."""
        return Wrapper_Runtime_Cache.get_cache(CACHE_KEY_LIBRARY_PATH_REGISTERED) or False

    @classmethod
    def _set_path_registered(cls, value):
        """Set the path registered flag."""
        Wrapper_Runtime_Cache.set_cache(CACHE_KEY_LIBRARY_PATH_REGISTERED, value)

    @classmethod
    def _ensure_library_home_path(cls):
        """Adds the custom library folder to sys.path if not already present."""
        if cls._is_path_registered():
            return
        
        logger = get_logger(Block_Logger_Definitions.PIP)
        custom_path = cls._get_library_home_path()
        if custom_path and os.path.isdir(custom_path):
            if custom_path not in sys.path:
                logger.info(f"Registering custom site-packages: {custom_path}")
                site.addsitedir(custom_path)
            cls._set_path_registered(True)
        elif custom_path:
            logger.debug(f"Custom path defined but does not exist yet: {custom_path}")

    @classmethod
    def get_module(cls, lib_name):
        """Attempts to import a library."""
        cls._ensure_library_home_path()
        
        module_cache = _get_module_cache()

        if lib_name in module_cache:
            return module_cache[lib_name]

        try:
            module = importlib.import_module(lib_name)
            module_cache[lib_name] = module
            Wrapper_Runtime_Cache.set_cache(CACHE_KEY_LIBRARY_MODULE_CACHE, module_cache)
            return module
        except ImportError:
            module_cache[lib_name] = None
            Wrapper_Runtime_Cache.set_cache(CACHE_KEY_LIBRARY_MODULE_CACHE, module_cache)
            return None

    @classmethod
    def is_installed(cls, lib_name):
        """Returns True if the library is installed."""
        return cls.get_module(lib_name) is not None
    
    @classmethod
    def invalidate_cache(cls, lib_name=None):
        """Invalidates the import cache for a specific library or all libraries."""
        module_cache = _get_module_cache()
        
        if lib_name:
            module_cache.pop(lib_name, None)
            # Remove from sys.modules and any submodules
            modules_to_remove = [
                key for key in sys.modules 
                if key == lib_name or key.startswith(f"{lib_name}.")
            ]
            for mod in modules_to_remove:
                del sys.modules[mod]
        else:
            module_cache.clear()
        
        Wrapper_Runtime_Cache.set_cache(CACHE_KEY_LIBRARY_MODULE_CACHE, module_cache)
        
        # Reset path registration so it re-checks on next import attempt
        cls._set_path_registered(False)
        
        importlib.invalidate_caches()

    @classmethod
    def safe_decorator(cls, lib_name, decorator_name):
        """Returns the real decorator or a dummy pass-through."""
        module = cls.get_module(lib_name)
        
        if module and hasattr(module, decorator_name):
            return getattr(module, decorator_name)
            
        def dummy_decorator(*args, **kwargs):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]
            def inner(func):
                return func
            return inner
            
        return dummy_decorator

#================================================================
# TEXT DATABLOCK LOG MANAGEMENT
#================================================================

def _get_log_text_name(library_name, action):
    """Generate a unique text datablock name for the log."""
    timestamp = datetime.now().strftime("%Y.%m.%d.%H.%M.%S")
    return f"{timestamp}_pip_{action}_{library_name}.log"

def _create_log_text(library_name, action):
    """Create a new Text datablock for logging."""
    text_name = _get_log_text_name(library_name, action)
    text_block = bpy.data.texts.new(text_name)
    text_block.use_fake_user = False
    return text_block

def _append_log(library_name, line):
    """Append to both in-memory log and text datablock."""
    data = _get_library_data(library_name)
    if data:
        data['log'].append(line)
        text_block = data.get('text_block')
        if text_block and text_block.name in bpy.data.texts:
            text_block.write(line + "\n")

#================================================================
# FOLDER OPERATIONS
#================================================================

def open_folder_in_explorer(path):
    """Opens a folder in the native file manager (cross-platform)."""
    if not os.path.exists(path):
        return False, f"Path does not exist: {path}"
    
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":  # macOS
            subprocess.Popen(["open", path])
        else:  # Linux and other Unix-like
            subprocess.Popen(["xdg-open", path])
        return True, ""
    except Exception as e:
        return False, str(e)

def get_library_install_paths(library_name, target_path):
    """
    Get the installation paths for a specific library.
    Returns list of paths that exist for this package.
    """
    possible_paths = []
    normalized_name = library_name.replace("-", "_")
    
    if not os.path.isdir(target_path):
        return []
    
    for item in os.listdir(target_path):
        item_lower = item.lower()
        name_lower = normalized_name.lower()
        
        # Match package folder
        if item_lower == name_lower or item_lower == library_name.lower():
            possible_paths.append(os.path.join(target_path, item))
        # Match single-file modules (e.g., six.py)
        elif item_lower == f"{name_lower}.py" or item_lower == f"{library_name.lower()}.py":
            possible_paths.append(os.path.join(target_path, item))
        # Match .dist-info
        elif item_lower.startswith(name_lower) and ".dist-info" in item_lower:
            possible_paths.append(os.path.join(target_path, item))
        # Match .egg-info
        elif item_lower.startswith(name_lower) and ".egg-info" in item_lower:
            possible_paths.append(os.path.join(target_path, item))
    
    return [p for p in possible_paths if os.path.exists(p)]

#================================================================
# PIP OPERATIONS (THREADED)
#================================================================

def run_pip_install(library_name, target_path, text_block_name):
    """Run pip install in a background thread."""
    logger = get_logger(Block_Logger_Definitions.PIP)
    
    text_block = bpy.data.texts.get(text_block_name)
    
    _set_library_data(library_name, {
        'status': 'RUNNING',
        'action': 'install',
        'log': [f"Starting install for {library_name}..."],
        'text_block': text_block,
        'process': None,
        'cancelled': False
    })
    
    os.makedirs(target_path, exist_ok=True)
    
    python_exe = sys.executable
    cmd = [
        python_exe, "-m", "pip", "install", 
        library_name, 
        "--target", target_path,
        "--no-user",
        "--no-warn-script-location"
    ]
    
    logger.info(f"Running command: {cmd}")
    _append_log(library_name, f"Command: {' '.join(cmd)}")
    _append_log(library_name, f"Target: {target_path}")
    _append_log(library_name, "-" * 40)
    
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True, 
            universal_newlines=True, 
            bufsize=1
        )
        _update_library_data(library_name, process=process)
        
        for line in process.stdout:
            data = _get_library_data(library_name)
            if data and data.get('cancelled'):
                process.kill()
                _append_log(library_name, ">>> CANCELLED BY USER <<<")
                _update_library_data(library_name, status='CANCELLED')
                _cleanup_partial_install(library_name, target_path)
                return
            
            clean = line.strip()
            if clean:
                _append_log(library_name, clean)
        
        process.wait()
        
        if process.returncode == 0:
            _update_library_data(library_name, status='FINISHED')
            _append_log(library_name, "-" * 40)
            _append_log(library_name, f"SUCCESS: {library_name} installed successfully")
            logger.info(f"Installation of {library_name} finished successfully")
        else:
            _update_library_data(library_name, status='ERROR')
            _append_log(library_name, "-" * 40)
            _append_log(library_name, f"ERROR: Installation failed with code {process.returncode}")
            logger.error(f"Installation of {library_name} failed")
            
    except Exception as e:
        _append_log(library_name, f"EXCEPTION: {str(e)}")
        _update_library_data(library_name, status='ERROR')
        logger.error(f"Installation of {library_name} failed: {e}")

def run_pip_uninstall(library_name, target_path, text_block_name):
    """Run pip uninstall by removing package files."""
    logger = get_logger(Block_Logger_Definitions.PIP)
    
    text_block = bpy.data.texts.get(text_block_name)
    
    _set_library_data(library_name, {
        'status': 'RUNNING',
        'action': 'uninstall',
        'log': [f"Starting uninstall for {library_name}..."],
        'text_block': text_block,
        'process': None,
        'cancelled': False
    })
    
    _append_log(library_name, f"Target directory: {target_path}")
    _append_log(library_name, "-" * 40)
    
    try:
        paths_to_remove = get_library_install_paths(library_name, target_path)
        
        if not paths_to_remove:
            _append_log(library_name, f"No files found for {library_name}")
            _update_library_data(library_name, status='FINISHED')
            return
        
        for path in paths_to_remove:
            data = _get_library_data(library_name)
            if data and data.get('cancelled'):
                _append_log(library_name, ">>> CANCELLED BY USER <<<")
                _update_library_data(library_name, status='CANCELLED')
                return
            
            _append_log(library_name, f"Removing: {path}")
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                _append_log(library_name, f"  Removed successfully")
            except Exception as e:
                _append_log(library_name, f"  Failed: {e}")
        
        Library_Installation_Wrapper.invalidate_cache(library_name)
        
        _update_library_data(library_name, status='FINISHED')
        _append_log(library_name, "-" * 40)
        _append_log(library_name, f"SUCCESS: {library_name} uninstalled")
        logger.info(f"Uninstallation of {library_name} finished")
        
    except Exception as e:
        _append_log(library_name, f"EXCEPTION: {str(e)}")
        _update_library_data(library_name, status='ERROR')
        logger.error(f"Uninstallation of {library_name} failed: {e}")

def _cleanup_partial_install(library_name, target_path):
    """Clean up partially installed files after cancellation."""
    logger = get_logger(Block_Logger_Definitions.PIP)
    paths = get_library_install_paths(library_name, target_path)
    for path in paths:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            _append_log(library_name, f"Cleaned up: {path}")
        except Exception as e:
            logger.warning(f"Failed to clean up {path}: {e}")

#================================================================
# OPERATORS
#================================================================

class DGBLOCKS_OT_Library_Manager(bpy.types.Operator):
    """Unified operator for install/uninstall/refresh operations."""
    bl_idname = "dgblocks.library_manager"
    bl_label = "Library Manager"
    bl_description = "Manage Python library installation"
    bl_options = {'REGISTER', 'INTERNAL'}

    library_name: bpy.props.StringProperty()  # type: ignore
    action: bpy.props.EnumProperty(  # type: ignore
        items=[
            ('INSTALL', "Install", "Install the library"),
            ('UNINSTALL', "Uninstall", "Uninstall the library"),
            ('REFRESH', "Refresh", "Refresh library status"),
        ],
        default='INSTALL'
    )

    _timer = None

    @classmethod
    def description(cls, context, properties):
        action = properties.action
        lib = properties.library_name
        target_path = Library_Installation_Wrapper._get_library_home_path()
        if target_path:
            if action == 'INSTALL':
                return f"Install '{lib}' package to {target_path}"
            elif action == 'UNINSTALL':
                return f"Remove {lib} from {target_path}"
            elif action == 'REFRESH':
                return f"Re-check if {lib} is installed to {target_path}"
        return ""

    def invoke(self, context, event):
        if self.action == 'REFRESH':
            return self.execute(context)
        
        target_path = Library_Installation_Wrapper._get_library_home_path()
        if not target_path:
            self.report({'ERROR'}, "Library folder not set in Preferences")
            return {'CANCELLED'}
        
        popup_header = f'Install Library "{self.library_name}"?' if self.action == 'INSTALL' else f"Uninstall {self.library_name}?" # Ignore "refresh", not relevant here
        return context.window_manager.invoke_props_dialog(self, width=450, title = popup_header)

    def draw(self, context):
        """Draw the confirmation dialog."""
        layout = self.layout
        target_path = Library_Installation_Wrapper._get_library_home_path()
        python_exe = sys.executable
        
        # Build the command that will be run
        if self.action == 'INSTALL':
            cmd_parts = [
                python_exe, "-m", "pip", "install",
                self.library_name,
                "--target", target_path,
                "--no-user",
                "--no-warn-script-location"
            ]
        else:  # UNINSTALL
            cmd_parts = None  # Uninstall doesn't use pip command
 
        # Command section (only for install)
        if cmd_parts:
            single_str_cmd = " ".join(cmd_parts)
            panel_header, panel_body = layout.panel(idname="_dummy_dgblocks_popup_pip_install_confirm_cmd", default_closed=True)
            row = panel_header.row()
            row.alignment = "LEFT"
            row.label(text="View Command", icon='CONSOLE')
            op = row.operator("dgblocks.copy_to_clipboard", text="", icon='COPYDOWN')
            op.text = single_str_cmd
            if panel_body:
                box = panel_body.box()
                col = box.column(align=True)
                col.scale_y = 0.8
                
                # Format command nicely - show key parts on separate lines
                col.label(text=f"{python_exe}")
                col.label(text=f"  -m pip install {self.library_name}")
                col.label(text=f"  --target {target_path}")
        else:
            # Uninstall info
            box = layout.box()
            box.label(text="Action:", icon='INFO')
            col = box.column(align=True)
            col.scale_y = 0.8
            col.label(text=f"Remove {self.library_name} package files")
            col.label(text="from target folder")

    def execute(self, context):
        if self.action == 'REFRESH':
            Library_Installation_Wrapper.invalidate_cache(self.library_name)
            Library_Installation_Wrapper._set_path_registered(False)
            Library_Installation_Wrapper._ensure_library_home_path()
            
            if Library_Installation_Wrapper.is_installed(self.library_name):
                self.report({'INFO'}, f"{self.library_name} is installed")
            else:
                self.report({'WARNING'}, f"{self.library_name} is not installed")
            return {'FINISHED'}
        
        target_path = Library_Installation_Wrapper._get_library_home_path()
        
        text_block = _create_log_text(self.library_name, self.action.lower())
        text_block_name = text_block.name
        
        if self.action == 'INSTALL':
            thread = threading.Thread(
                target=run_pip_install,
                args=(self.library_name, target_path, text_block_name)
            )
        else:  # UNINSTALL
            thread = threading.Thread(
                target=run_pip_uninstall,
                args=(self.library_name, target_path, text_block_name)
            )
        
        thread.daemon = True
        thread.start()
        
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        context.window.cursor_modal_set('WAIT')
        
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        
        # Allow user to cancel install with ESC key
        if event.value == "PRESS" and event.type == "ESC":
            data = _get_library_data(self.library_name)
            data["cancelled"] = True
            return {'PASS_THROUGH'}
        
        if event.type == 'TIMER':
            data = _get_library_data(self.library_name)
            
            if not data:
                return {'PASS_THROUGH'}
            
            if data['log']:
                last_line = data['log'][-1][:60]
                context.workspace.status_text_set(f"{self.action.title()}ing {self.library_name}: {last_line}")
            
            if data['status'] in ['FINISHED', 'ERROR', 'CANCELLED']:
                context.window_manager.event_timer_remove(self._timer)
                context.window.cursor_modal_restore()
                context.workspace.status_text_set(None)
                
                Library_Installation_Wrapper.invalidate_cache(self.library_name)
                bpy.ops.dgblocks.show_library_result('INVOKE_DEFAULT', library_name=self.library_name)
                force_redraw_ui(context)
                return {'FINISHED'}
        
        return {'PASS_THROUGH'}

class DGBLOCKS_OT_Cancel_Library_Operation(bpy.types.Operator):
    """Cancel ongoing library operation."""
    bl_idname = "dgblocks.cancel_library_operation"
    bl_label = "Cancel"
    bl_description = "Cancel the current operation"

    library_name: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        data = _get_library_data(self.library_name)
        if data:
            data['cancelled'] = True
            process = data.get('process')
            if process:
                try:
                    process.kill()
                except:
                    pass
            self.report({'WARNING'}, f"Cancelling {self.library_name} operation...")
        return {'FINISHED'}

class DGBLOCKS_OT_Show_Library_Result(bpy.types.Operator):
    """Show the result of a library operation."""
    bl_idname = "dgblocks.show_library_result"
    bl_label = "Operation Report"
    bl_options = {'REGISTER', 'INTERNAL'}

    library_name: bpy.props.StringProperty()  # type: ignore

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=550)

    def draw(self, context):
        layout = self.layout
        data = _get_library_data(self.library_name) or {}
        status = data.get('status', 'UNKNOWN')
        action = data.get('action', 'operation')
        log = data.get('log', [])
        text_block = data.get('text_block')
        
        # Header
        row = layout.row()
        if status == 'FINISHED':
            row.label(text=f"Successfully {action}ed {self.library_name}", icon='CHECKMARK')
        else:
            row.label(text=f"Failed to {action} {self.library_name}", icon='ERROR')
        
        layout.separator()
        
        # Log panel
        panel_header, panel_body = layout.panel(idname="DGBLOCKS_PT_LIBRARY_RESULT_LOG", default_closed=True)
        panel_header.label(text="View Log Summary", icon='TEXT')
        
        if panel_body is not None:
            col = panel_body.column(align=True)
            
            recent_logs = log[-12:] if len(log) > 12 else log
            for line in recent_logs:
                display_line = line[:80] + "..." if len(line) > 80 else line
                col.label(text=display_line)
            
            if len(log) > 12:
                col.label(text="...")
            
        # Link to full log
        if text_block and text_block.name in bpy.data.texts:
            layout.separator()
            layout.label(text=f"Full log: Text Editor → {text_block.name}")

    def execute(self, context):
        Library_Installation_Wrapper._ensure_library_home_path()
        importlib.invalidate_caches()
        return {'FINISHED'}

class DGBLOCKS_OT_Open_Folder(bpy.types.Operator):
    """Open a folder in the system file manager."""
    bl_idname = "dgblocks.open_folder"
    bl_label = "Open Folder"
    bl_description = "Open folder in file manager"

    folder_path: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        path = self.folder_path
        
        if not os.path.exists(path):
            parent = os.path.dirname(path)
            if os.path.exists(parent):
                path = parent
            else:
                self.report({'ERROR'}, f"Path does not exist: {self.folder_path}")
                return {'CANCELLED'}
        
        success, error = open_folder_in_explorer(path)
        if not success:
            self.report({'ERROR'}, f"Failed to open folder: {error}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

#================================================================
# UI DRAWING
#================================================================

def ui_draw_panel_for_required_libraries(context, container):
    """Draw the library management panel."""
    
    panel_header, panel_body = container.panel(idname="DGBLOCKS_PT_DEPENDENCY_MGMT_PANEL")
    uilayout_draw_block_panel_header(
        context, panel_header, "3rd-party Libraries", 
        Documentation_URLs.MY_PLACEHOLDER_URL_1
    )
    
    if panel_body is None:
        return
    
    box = container.box()
    
    header_row = box.row()
    header_row.label(text="Required Python Libraries")
    
    lib_path = Library_Installation_Wrapper._get_library_home_path()
    if lib_path:
        op = header_row.operator(
            "dgblocks.open_folder", 
            text="", 
            icon='FILE_FOLDER'
        )
        op.folder_path = lib_path
    
    box.separator()
    
    libraries = [lib for lib in Python_Library_Dependencies]
    
    for library_data in libraries:
        library_name = library_data.value[0]
        import_name = library_data.value[1]
        
        op_data = _get_library_data(library_name) or {}
        is_running = op_data.get('status') == 'RUNNING'
        
        row = box.row()
        split = row.split(factor=0.5)
        col_left = split.column()
        col_right = split.column()
        
        is_installed = Library_Installation_Wrapper.is_installed(import_name)
        
        if is_running:
            action = op_data.get('action', 'operation')
            col_left.label(text=f"{library_name} ({action}ing...)", icon='TIME')
            
            op = col_right.operator(
                "dgblocks.cancel_library_operation",
                text="Cancel",
                icon='CANCEL'
            )
            op.library_name = library_name
            
        elif is_installed:
            col_left.label(text=f"{library_name}", icon='CHECKMARK')
            
            button_row = col_right.row(align=True)
            
            op = button_row.operator(
                "dgblocks.library_manager",
                text="",
                icon='FILE_REFRESH'
            )
            op.library_name = library_name
            op.action = 'REFRESH'
            
            op = button_row.operator(
                "dgblocks.library_manager",
                text="Uninstall",
                icon='TRASH'
            )
            op.library_name = library_name
            op.action = 'UNINSTALL'
            
        else:
            row.alert = True
            col_left.label(text=f"{library_name} (not installed)", icon='ERROR')
            
            button_row = col_right.row(align=True)
            
            op = button_row.operator(
                "dgblocks.library_manager",
                text="",
                icon='FILE_REFRESH'
            )
            op.library_name = library_name
            op.action = 'REFRESH'
            
            op = button_row.operator(
                "dgblocks.library_manager",
                text="Install",
                icon='IMPORT'
            )
            op.library_name = library_name
            op.action = 'INSTALL'
    
    box.separator()
    if lib_path:
        row = box.row()
        row.scale_y = 0.8
        row.label(text=f"Path: {lib_path}", icon='INFO')
