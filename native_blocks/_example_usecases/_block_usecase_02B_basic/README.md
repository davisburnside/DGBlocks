# block-usecase-mirror-02b

A demo block showing a complete BL↔RTC data-mirror with a custom PropertyGroup and UIList.

- Depends on `block-core` and `block-debug-console-print`
- Defines a Feature Wrapper Class (`Wrapper_Example_Mirror_02B`) with full data sync
- Provides a mirrored `PropertyGroup` (`DGBLOCKS_PG_Example_Mirror_Item`) and RTC dataclass (`RTC_Example_Mirror_Item`)
- Includes a UIList in a developer panel, plus add/remove operators
- Demonstrates the standard pattern for two-way BL↔RTC collection sync

Use this as a reference when building a block that needs persistent, user-editable list data with runtime caching.
