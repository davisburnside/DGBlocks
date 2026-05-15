import bpy
import subprocess
import json
import os
from ...native_blocks.block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache


def run_blender_test(module_path, function_name, blend_path, addon_name):
    """
    module_path: e.g. "my_addon.test_suite.mesh_tests"
    function_name: e.g. "test_vertex_count"
    blend_path: Path to the .blend file to test
    addon_name: The actual name (folder name) of your addon to ensure it's enabled
    """
    
    # 1. Construct the Python expression to run inside the child
    # This imports your addon module and executes the function
    python_expr = (
        f"import json, bpy, {module_path}; "
        f"bpy.ops.wm.open_mainfile(filepath=r'{blend_path}'); "
        f"result_data = {module_path}.{function_name}(); "
        f"print('---JSON_START---'); "
        f"print(json.dumps({{'test': '{function_name}', 'status': 'PASSED', 'data': result_data}})); "
        f"print('---JSON_END---')"
    )

    # 2. Build the command
    # --factory-startup: ensures a clean environment
    # --addon: ensures your addon is enabled regardless of user preferences
    python_path = bpy.app.binary_path
    cmd = [
        python_path,
        "--background",
        "--factory-startup",
        "--python-expr", python_expr
    ]

    try:
        # 3. Spawn and wait (kill on completion/timeout)
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )
        
        # communicate() blocks until the process exits or timeout hits
        stdout, stderr = process.communicate(timeout=60)

        # 4. Extract JSON from stdout
        if "---JSON_START---" in stdout:
            json_str = stdout.split("---JSON_START---")[1].split("---JSON_END---")[0]
            return json.loads(json_str.strip())
        else:
            return {"test": function_name, "status": "ERROR", "log": stderr or "No JSON output found."}

    except subprocess.TimeoutExpired:
        process.kill()
        return {"test": function_name, "status": "TIMEOUT", "log": "Test took too long."}
    except Exception as e:
        return {"test": function_name, "status": "CRASH", "log": str(e)}

# --- Usage Example ---
# If your addon is 'pro_modeller' and you want to run 'test_boolean' 
# located in 'pro_modeller.tests.bool_logic'
#
# result = run_blender_test(
#    module_path="pro_modeller.tests.bool_logic",
#    function_name="test_boolean",
#    blend_path="C:/tests/cube.blend",
#    addon_name="pro_modeller"
# )





import subprocess
import sys
import os

def run_operator_in_headless_blender(test_id, operator_idname="mesh.primitive_cube_add", blend_file=None):
    """
    Spawns a new headless Blender process and runs an operator inside it.
    Completely isolated from the calling Blender session.
    
    Args:
        operator_idname: The operator to run (e.g., "mesh.primitive_cube_add")
        blend_file: Optional .blend file to open before running the operator
    """
    
    # Python script to execute inside the headless Blender
    script = f'''
import bpy

# Optional: set up the scene or load addons here
# bpy.ops.preferences.addon_enable(module="your_addon_name")

# Run the operator
try:
    result = bpy.ops.{operator_idname}(test_id = "{test_id}")
    print(f"Operator result: {{result}}")
except Exception as e:
    print(f"Error running operator: {{e}}")

# Optional: save the result
# bpy.ops.wm.save_as_mainfile(filepath="/tmp/result.blend")

print("Headless operation complete")
'''
    
    # Build the command
    cmd = [sys.executable, "--background"]
    
    if blend_file:
        cmd.append(blend_file)
    
    # cmd.extend(["--python-expr", script])
    
    # Run in a completely separate process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),  # Inherit environment but isolated process
    )
    
    stdout, stderr = process.communicate()
    

    result = {
        "returncode": process.returncode,
        "stdout": stdout.decode("utf-8"),
        "stderr": stderr.decode("utf-8"),
    }

    return result


def _sample_unittest():

    print("------\n----SDFSFSDFSDFDFAS------\n----")
    obj = bpy.context.scene.objects["FLATIFY_PLANE_1"]
    print(obj.location)
    return {"a", str(obj)}





























import os
import sys
import shutil
import tempfile
import subprocess

def get_blender_binary():
    """
    Resolves the path to the Blender executable.
    Works from both inside a running Blender instance and externally via PATH.
    """
    try:
        import bpy
        # If running inside Blender, this is guaranteed to be the exact binary
        return bpy.app.binary_path
    except ImportError:
        # If running externally, search the system PATH
        blender_path = shutil.which("blender")
        if not blender_path:
            raise FileNotFoundError(
                "Could not find 'blender' in system PATH. "
                "Ensure it is installed and added to your environment variables."
            )
        return blender_path

def launch_headless_operator(addon_module_name: str, test_id: str, blend_file: str = ""):
    """
    Spawns a completely isolated, headless Blender process to run a specific operator.
    
    :param addon_module_name: The folder/module name of your addon (e.g., 'my_custom_addon')
    :param operator_id: The full ID of the operator (e.g., 'object.my_custom_operator')
    :param blend_file: Optional path to a specific .blend file to open before running.
    """
    blender_exe = get_blender_binary()

    # bpy.ops.dgblocks.run_tests(test_id = "{test_id}", is_subprocess = True)


    script = f'''
import bpy

try:
    result = bpy.ops.dgblocks.run_tests(test_id = "{test_id}", is_subprocess = True)
    print(f"Operator result: {{result}}")
except Exception as e:
    print(f"Error running operator: {{e}}")
'''
    
    cmd = [blender_exe, "--background"]
    
    if blend_file:
        cmd.append(blend_file)
    
    cmd.extend(["--python-expr", script])
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    try:
        stdout, stderr = process.communicate(timeout=6)
        print("\n OUT:", stdout)
        print("\nERR:", stderr)
        print(f"Launched isolated headless Blender (PID: {process.pid})")
        return {
            "success": True,
            "returncode": process.returncode,
            "stdout": stdout.decode("utf-8"),
            "stderr": stderr.decode("utf-8"),
        }



    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "timeout",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
    finally:
        process.kill()
        process.wait()  # Ensure zombie process is reaped