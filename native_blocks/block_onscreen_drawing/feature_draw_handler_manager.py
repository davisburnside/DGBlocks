
# ==============================================================================================================================
# DEPRECATED — this file has been superseded by feature_shader_manager.py
# The FWC was renamed Wrapper_Shader_Manager to reflect its new primary concern:
# managing a registry of Shader_Instance objects.  Draw handler assignment is
# downstream plumbing handled privately inside the new wrapper.
#
# This re-export exists for any tooling that references the old module path.
# All new code should import from feature_shader_manager directly.
# ==============================================================================================================================

from .feature_shader_manager import Wrapper_Shader_Manager as Wrapper_Draw_Handlers  # noqa: F401
