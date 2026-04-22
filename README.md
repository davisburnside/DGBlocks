

DGBLocks is a modular, swap-in/swap-out addon (like lego blocks) framework for Blender. It is designed to be easily modified to suite a wide array of needs. 
You can also add your own packages & integrate them easily with your DGBlocks template

#================================================================

This guide assumes you are moderately familiar with Python & Blender

Terms & definitions used:

* Addon (Blender term): Installed into Blender, like software-within-software.  
  * Exists as 1 or more Python files with a certain structure that Blender expects. Always contains at least 1 __init__.py file
  * Often exists as a .zip, but a raw .py file can also be used.
  * More info:
    * https://docs.blender.org/manual/en/latest/editors/preferences/addons.html
  * Similar in purpose to an "extension: (introduced in Blender Version 4.2), but installed differently
    * more info:
        * https://youtu.be/AE56yPqZCQI?si=C-drJvTR2Q8jTD7w

* Package (Python term): a folder with 1 or more python files
  * some contain a single __init__.py file, others do not
  * "Block", "Package", "Subpackage" are interchangeable terms. 
    * However, a Block MUST have a single __init__.py in its main folder. 
    * Blocks can have subfolders, which may or may not have __init__

* Module (Python term): A single python file
  * can be imported & used into other modules

* Logger (Python term): Generates logs, either to a file or the application console
  * Rarely relevant to users, unless reporting a bug, but very useful to addon developers
  * Each logger has a "level" property, to set how often it writes. Too many logs, or too few, are both unhelpful to devs
  * DGBlocks contains loggers for different tasks, like startup events, UI-display events... 
  * A Block usually contains one or more loggers for its own logic

* Runtime Data Cache (DGBlocks term): A convenience tool for addon devs. A wrapper for your addon's state data
  * Used by every block. Read/write ( And other convenience functions ) are offered inside core-block
  * Exists outside the Blender-Data: 
    * Not tied to undo-redo
    * Not saved with file. Data must be recreated at startup
  * Atomic & Thread-safe
  * Meant to hold python data (json, raw files, numpy arrays...) that bpy.props.Propertygroups can't store
  * WARNING- Not intended not hold bpy.* data. 
    * Some Blender data, like BMesh, is volatile and can be destroyed at any time. Attempting to read an invalid memory address will cause blender to crash
    * If you must store references to Blender classes, ensure they still exist (with the same memory address) before you access

* Block (DGBlocks term): a self-contained wrapper of addon logic
  * All Blocks share the same structure & key variables, mentioned below
  * Each block contains logic to achieve a single abstract purpose. Examples:
    * UI Modal Display: A suite of tools & shaders to draw in the 3D viewport in realtime. Useful for visualization & state display, not traditional rendering
    * State enforcement: Ensuring certain Data exists in a Scene, ensuring a certain Object has always-on Modifiers...
    * Numpy Acceleration: pre-compile python functions for potentially massive effeciency gains. Very useful for math/Numpy heavy functions
  * Blocks are meant to be used by other blocks. 
    * Block-state-enforcement has a dependency of block-event-listener. Events inside b-e-v automaticallty trigger "hook" callback functions inside b-s-e
    * Dependency is always *one-directional*: b-e-v needs no changes whatsoever to invoke hook functions inside b-s-e. This is what allows DGBlocks to be fully & truly modular

* Block Hook (DGBlocks term): A callback function, triggered on certain DGBlock events
  * Inside a block, functions with a certain name will be automatically called by a certain events of other blocks. Examples:
    * Block-Core has a post-register function, when bpy.context is first ready. It triggers initialization tasks on other blocks 
    * Block-event-listener handles many Blender events, like file-save, depsgraph update, frame change... There is also builtin filter logic to avoid propagating unwanted/high-frequency events to other blocks
    * And others...
  * Blocks down the callback chain are considered "hooked" by the block that triggers the callback.
  * A Block can have 0-to-many triggers for hook events, and each trigger may have 0-to-many blocks hooked into it
  * Hook function rules:
    * Always defined in a block's __init__.py
    * Must return a Boolean (True for completion, False for exception).  
    * Function arguments for each hook type may differ. All blocks of the same hook type, receive the same args. 
    * Execution order is serial & predetermined (by the main addon file's _blocks_to_register list) 
      * For every hook event, block-2 hook does not execute until block-1 is finished
      * If Block-1 returns False, the event is halted & block-2 does not receieve
  * There is a dict in the runtime cache for fast lookup of all blocks & hooks

* DataBlock (Blender term): A Blender-owned "thing"
  * Not to be confused with DGBlock
  * DataBlock examples: Object, Mesh, Image, Scene, Armature, Camera...
  * Well-documented, feature-rich python API for controlling from an addon
  * Saved with the .blend file
  * Ties into Blender's undo/redo actions
  * More info:
    * https://docs.blender.org/manual/en/latest/files/data_blocks.html

* Property (Blender term): A unit of Blender-owned data
  * Attached to a DataBlock, carries over during file loads, appends, imports...
  * Can hold simple data, like Strings, Numbers, Vectors, Lists...
  * Can also hold references to Blender data, like Strings, Numbers, Vectors, Lists... 
  * New Properties can be defined in a bpy.props.PropertyGroup & attached to almost any DataBlock, Operator, or UI Elements (like Panel)
    * Saved with the .blend file
    * Ties into Blender's undo/redo actions
  * More info:
    * https://docs.blender.org/api/current/bpy.props.html

* Operator (Blender term): A class which peforms an action. 
  * Often triggered with a button press
  * Can also be triggered in python. Operators can act like an API-within-an-API, allowing other addons or Blender's python shell to control your addon
  * More info:
    * https://docs.blender.org/api/current/bpy.types.Operator.html

* Panel (Blender term): A class which allows the user to control Properties in the User Interface.
  * Well-documented API for customizing a user interface, but not as feature-rich as other UIs (like a webpage)
  * Lacks "polishing" features like button hover, animations, etc
  * Offers (often unused) templates for advanced UI cases, like "template_color_picker". Almost any UI element you see in standard blender can be added to your addon with 1 line.
  * Offers callback events when properties changes
  * Full list of UI customization options:
    * https://docs.blender.org/api/current/bpy.types.UILayout.html

* Scene (Blender Term): The primary "container" of your Blender data
  * Most users use a single Scene per file, but many can be held.
  * Each Scene has it's own properties, Objects, UI settings...

* Dependency (General term) 
  * Can have multiple meanings
    * DGBLOCK dependencies: Blocks depending on other Blocks
    * LIBRARY / PYTHON dependencies: anything installed with pip
    * BLENDER-DATA dependencies: Mesh, Curve, Image, NodeGroup... any Blender DataBlock
    * RAW DATA : .json, .png files...
  * More info below

#================================================================

# How to use DGBlocks

1: Remove DGBlock components you don't need. 
 * Not every addon needs extra pip-installed libraries, numba acceleration, a custom UI, etc.
 * Keeps codebases small, makes AI-assist tools more effective
 * Except for the /core package, all DGBlocks features (hotkeys, Load listeners, Numba acceleration...)  can be removed.

2: Update template names & variables
 * You may want to substitute for own addon name where "DGBlocks_" is found in the code & user interface
 * At the very least, update these names:
   * "addon_name", inside /constants.py
   * "bl_info.name", inside /__init__.py
   * "bl_info.author"
   * "bl_info.description"
   * The folder DGBLOCK_BASIC_TEMPLATE

3: Add your own packages & python files. For best the best degree of modularity & community use (if you intend to ditrubute it) is to follow the same name/module/package structure as other DGBlock features
 * Organize features into distinct packages, with one or more files in each
 * put section labels in your files, like -CONFIGURATION- and -REGISTRATION EVENTS-
 * put Registrate, Unregistrate, and Initialization (post-register) logic in distinct functions & call them during the main addon's reg & init events
 * Use DGBlock's logging system instead of print(). Create a logger for each major addon feature. This process may appear convoluted, but it pays off greatly during debugging 

More detailed guides for these actions can be found at the DGBlocks website

#================================================================

# Module & Package Structure

Each major feature is organized into a folder (AKA Package), like event_listeners or ui_display_modal

* Block structure

  * One __init__.py file must exist inside every block. Inside this file, 4 things must exist:
    * _BLOCK_ID : string
    * _BLOCK_DEPENDENCIES : list[string]
    * register_block : function
    * unregister_block : function
  
  * Also in __init__.py, optional "hook callback" functions can also be added, which are automatically called on certain events triggered by other blocks
    * post-init hook: Called immediately after all blocks & classes are registered & bpy.context is fully ready. Defined in block-core
    * Event-listener hooks: Many callbacks can be triggered by bpy.app.handlers events

  * Other helper files/packages can be added to a block.

    * Though It is beneficial to organize sub-features into their own files. 
    * ./dependency_management is an example of this: For each types of dependency, there is a single file containing all classes, variables, & functions to support that feature

  * To prevent circular dependencies, __init__ should not own any variable/functions which are used by other files in the package

* File Structure
    * bpy.types.* classes are defined in 

* Function naming conventions
    * Variables named in all uppercase (like "LOG_LEVELS" ) are considered constants. They should generally NOT be modified.
    * Having a name starting with "_" (like "_loggers") generally means "For internal use only". Generally should NOT be changed outside the file
    * Variables with names starting with "my_" (like "my_logger_definitions" ) SHOULD be modified. They will always be found near the top of a file, under the CONFIGURATION section
    * Blender Operators & Panels are expected to have an all-caps prefix before "_PT_" or "_OT_"

* Variable naming conventions


#================================================================

# Removing unwanted modules & packages

    * Core modules:
        * Contains Logging, Main UI Panels, Shared Variables/Functions/Operators
        * Most modules (both core & noncore) use the "_shared" files and logging
        * Modules under the "core" package are used in many places. I have not documented the process to remove them. It is probably less effort to ignore rather than fully remove
    * Non-Core modules
        * Requires minimal efforts to sever from the dgblocks template
        * Delete the unwanted module first
        * Remove references during register() & unregister() calls in __init__.py. 
        * Search for remaining references in the project and remove them
    * Interpackage dependencies
        * Some


#================================================================

# Dependencies

In the documentation & code, the word "dependency" is often used, and it's important to know the right context

    * DGBLOCK dependencies: 
      * Blocks which require other blocks to be installed, before they can work
      * always managed by the "_BLOCK_DEPENDENCIES" list in each block
      * Validated during startup / register
      * Invisible to the addon user
      * Examples:
        * All blocks depend on "block-core" (except block-core, obviously)
        * block-ui-display-modal depends on block-event-listener

    * LIBRARY dependencies: 
      * Python libraries (installed with pip) which your addon requires
      * Often unused. Most addons are content with python & blender's default code libraries.
      * Should be installed any time after register/init. 
      * The user should be prompted before installation
      * Example: The DGBlocks basic template offers Numba-accelerated code examples. Numba is not present in Blender 5.0, & must be installed by DGBlocks

    * BLENDER-DATA dependencies:
      * Your addon may require certain Blender DataBlocks to work, like an Image or Mesh. This data is owned by a hidden .blend files INSIDE the addon. The data is then added to your own project.
        * DGBlocks can put dependent DataBlocks in your project in multiple ways
          * Linked: Immutable inside your project. Images can't be changes, nodes can't be added to a shader, etc
          * Appended: Mutable, user can change. The source data, in the hidden .blend, is not changed
      * Examples:
        * The "Basify" addon requires Geometry-Node trees 
      * May or may not be invisible to user, depends on your preference
    

#================================================================

# Things to note:

  * Serpens integration:
      * Possible, but requires a deeper level of understanding for Python & Addon structure
      * I will not provide an example of how to integrate DGBlocks features to an existing Serpens project.
      * The easiest way to integrate is probably to merge a Serpens project into a DGBlocks project, not DGBlocks into Serpens.
          * First, export the Serpens project as a complete addon
          * Next, create a new package in your DGBlocks-based addon
          * Next, copy/paste Serpens code into the new package. 
            * You will still need to tie everything together manually (register, operator calls...)
            * You will likely want to update
          * The new addon will be incompatible with later Serpens edits, unless you manually port those over too

  * Data Persistence:
      * Data saved in the .blend file 
          * descripions may contain "permanent", "persisted", "saved"...
          * All bpy.props.* data is stored inside the .blender file
              * Persists across close / reload events
              * Can be effortlessly imported / appended into other .blend files. 
                  * For example: an Object's bpy.types.Object.dgblocks_object_props property will be iuncluded if that object is imported into another Blender project, or if that Object is used in another Scene
              * Limited to primitive data types and Blender Objects (Bools, Ints, Floats, Strings, Lists, Vectors, Colors, Images, Objects, Curves, Armatures...)
      * Data NOT saved in the .blend file
          * Any data held as python variables must be recreated every register() event
          * descripions may contain "cache", "nonpersistent", "temp"...

  * Available default UI Icons:
    * https://docs.blender.org/manual/en/latest/contribute/manual/guides/icons.html

  * Circular dependencies:
      * ensure file_A does not import anything from file_B, if file_B imports anything from file_A
  * Block Access
      * any name starting with "_" is not supposed to be used outside of its own block

  * Function/Variable Name standards:
      * don't add new "dgblocks_*" named variables. Rather, name them by your own addon.
      * If integrating with a Serpens-based addon, you may want to remove all extra tags and IDs from class names. Personal preference
      * Generalized naming standards
        * Some of these are conventions common to python, others are found in this codebase only
        * Function Names
          * get_* : Retrieve something quickly, very little computation needed. "get_" usually means "retrieve from an in-memory cache with easy & fast lookup"
          * determine_* : Like get_*, but requires more work. In DGBlocks, the result of a determine_* function is usually cached so that get_* can be used next time.
          

  * Logging:
      * Don't use "print", take full advantage of the logging framework. 
          * Add Debug statements frequently in your functions around areas of high complexity, or in areas with opaque, blackbox-like code
          * Create custom loggers for each of your addon's main component. For example, an addon for creating animations may want separate loggers for functions that deal with IK vs FK logic. Separation of log messages allows the developer to quickly gather information about an error, while filtering out unwanted logs for other events
          * Logging is mostly relevant to the developer only, during the debugging process. You may want to hide log settings from the user
      
          