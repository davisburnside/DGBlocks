
* 2/1/26 If you reload a script that holds a reference to a gpu.types.GPUBatch, and you don't properly release that batch during the reload, you will leak VRAM.
I Need to ensure my shaders arent doing this

# 1: Core-Block
    A: perform version check during _BLOCK_DEPENDENCIES validation
    B: !! RTC needs to store all data underneat a scene-based filter. Otherwise, multi-scene files are broken


# Developer Guide Updates

* Block Structure Standard
    * 1.namingConvention.classes: "UP" for prefs panels should be "AP"
    * 4.blockMetadata.dependencies: should include version (after fix 1.A)
    * 6 update RTC info (after fix 1.B)
    * 11.typeHints: "= None" is shorthand for Optional
    * 16.modalReturn: aggregate method unknown yet