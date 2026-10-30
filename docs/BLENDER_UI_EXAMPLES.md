# Blender Python UI Elements — Developer Reference & Code Examples

This reference guide provides practical, copy-pasteable code examples for constructing custom user interfaces in Blender using the Python API (`bpy`). It covers basic controls, layout structures, conditional formatting, dynamic lists (`UIList`), search selectors, and advanced interactive templates.

---

## 📑 Table of Contents
1. [Core UI Primitives (Labels, Props, Operators, Separators)](#1-core-ui-primitives)
2. [Layout Grouping (Row, Column, Box, Split, Grid Flow)](#2-layout-grouping)
3. [Interactive States (Enabled, Active, Alert, Scaling)](#3-interactive-states)
4. [Property Input Variants (Sliders, Toggles, Colors, Enums)](#4-property-input-variants)
5. [Search Pickers & ID Templates (`prop_search`, `template_ID`)](#5-search-pickers--id-templates)
6. [Dynamic Scrollable Lists (`bpy.types.UIList`)](#6-dynamic-scrollable-lists-uilist)
7. [Popup Dialogs & Menus (`bpy.types.Menu`)](#7-popup-dialogs--menus)
8. [Complete Standalone Example Script](#8-complete-standalone-example-script)

---

## 1. Core UI Primitives

### Text Labels
```python
def draw(self, context):
    layout = self.layout

    # Simple plain text label
    layout.label(text="Planetary Mill Parameters")

    # Label with a standard Blender icon
    layout.label(text="Simulation Verified", icon="CHECKMARK")

    # Emphasized bold section header
    layout.label(text="Primary Kinematics:", icon="ORIENTATION_GIMBAL")
```

### Properties (`layout.prop`)
```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    # Standard property field (draws label automatically from Property definition)
    layout.prop(props, "dem_ball_count")

    # Custom override label
    layout.prop(props, "dem_ball_radius_mm", text="Radius (mm)")

    # Without text label (useful inside compact rows)
    layout.prop(props, "dem_material_preset", text="")
```

### Operators / Action Buttons (`layout.operator`)
```python
def draw(self, context):
    layout = self.layout

    # Standard button executing an operator
    layout.operator("science_blocks.run_dem_simulation", text="Run DEM Physics", icon="PARTICLES")

    # Passing execution parameters to an operator call
    op = layout.operator("science_blocks.focus_jar_view", text="Focus View", icon="VIEW_CAMERA")
    op.use_camera = True
```

### Separators
```python
def draw(self, context):
    layout = self.layout

    # Default thin separator
    layout.separator()

    # Scaled spacing separator (factor = relative height multiplier)
    layout.separator(factor=0.3)  # Small gap
    layout.separator(factor=1.5)  # Large gap
```

---

## 2. Layout Grouping

### Rows (`layout.row`)
Use rows to arrange controls horizontally side-by-side:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    # align=True snaps borders together into a unified button group
    row = layout.row(align=True)
    row.prop(props, "dem_ball_count", text="Balls")
    row.prop(props, "dem_ball_radius_mm", text="Radius")
    row.prop(props, "dem_ball_density", text="Density")
```

### Columns (`layout.column`)
Use columns to stack controls vertically with optional unified borders:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    col = layout.column(align=True)
    col.prop(props, "mill_sun_radius", text="Sun Radius (m)")
    col.prop(props, "mill_jar_radius", text="Jar Radius (m)")
    col.prop(props, "mill_jar_height", text="Jar Height (m)")
```

### Boxes (`layout.box`)
Boxes draw an indented visual container with a rounded border, ideal for grouping sub-features:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    # Create box container
    box = layout.box()

    # Sub-header label inside the box
    box.label(text="Studio Theme & Material Library:", icon="MATERIAL")

    # Content column inside box
    col = box.column(align=True)
    col.prop(props, "viewport_theme_mode", text="Theme")
    col.prop(props, "selected_studio_material", text="Material")

    row_btn = col.row(align=True)
    row_btn.operator("science_blocks.assign_studio_material", text="Assign", icon="RESTRICT_SELECT_OFF")
    row_btn.operator("science_blocks.duplicate_studio_material", text="Duplicate", icon="DUPLICATE")
```

### Split Layout (`layout.split`)
Splits a row into two or more custom-proportioned horizontal columns:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    # 35% width for left column, 65% width for right column
    split = layout.split(factor=0.35, align=True)

    col_left = split.column(align=True)
    col_left.label(text="Status:", icon="INFO")

    col_right = split.column(align=True)
    col_right.prop(props, "env_status_message", text="")
```

### Grid Flow (`layout.grid_flow`)
Arranges buttons or tiles in an automatically wrapping responsive grid:

```python
def draw(self, context):
    layout = self.layout

    # Grid with 3 fixed equal-width columns
    grid = layout.grid_flow(row_major=True, columns=3, even_columns=True, even_rows=True, align=True)
    grid.operator("science_blocks.preset_cascading", text="Cascade")
    grid.operator("science_blocks.preset_cataracting", text="Cataract")
    grid.operator("science_blocks.preset_centrifuging", text="Centrifuge")
    grid.operator("science_blocks.preset_wet_slurry", text="Wet Slurry")
    grid.operator("science_blocks.preset_horizontal", text="Horizontal")
    grid.operator("science_blocks.preset_zerog", text="Zero-G")
```

---

## 3. Interactive States

### Button Scaling (`scale_x`, `scale_y`)
Make primary call-to-action buttons taller and more prominent:

```python
def draw(self, context):
    layout = self.layout

    row = layout.row(align=True)
    row.scale_y = 1.4  # 40% taller button
    row.operator("science_blocks.run_dem_simulation", text="Run DEM Simulation (Bake Physics)", icon="PARTICLES")
```

### Disabling & Greying Out Controls (`layout.enabled`)
Prevent user interaction when prerequisites are not met:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    col = layout.column(align=True)
    # Entire column is greyed out and unclickable until simulation is run
    col.enabled = props.dem_is_simulated

    col.operator("science_blocks.generate_scientific_report", text="Generate Scientific Report", icon="DOCUMENTS")
    col.operator("science_blocks.export_telemetry", text="Export CSV / JSON", icon="EXPORT")
```

### Soft Dimming (`layout.active`)
Visually dims controls without fully locking them:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    row = layout.row(align=True)
    # Visually dims viscosity control if dry milling is selected
    row.active = (props.dem_environment == "WET_SLURRY")
    row.prop(props, "dem_slurry_viscosity", text="Viscosity (Pa·s)")
```

### High-Priority Warning Alerts (`layout.alert`)
Renders fields with a red highlighted alert background:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    row = layout.row(align=True)
    if not props.pkg_numpy_installed:
        row.alert = True  # Red background warning
        row.operator("science_blocks.install_packages", text="NumPy Missing! Click to Install", icon="ERROR")
    else:
        row.label(text="Python Environment Verified", icon="CHECKMARK")
```

---

## 4. Property Input Variants

### Push-Button Toggles (`toggle=True`)
Renders a boolean property as a push button rather than a checkbox:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    # Push button toggle (highlights blue when True)
    layout.prop(props, "live_motion_preview", text="Live Motion Preview", toggle=True, icon="PLAY")
```

### Numeric Sliders (`slider=True`)
Forces integer or float properties to display as an interactive draggable slider:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    # Horizontal draggable slider
    layout.prop(props, "dem_restitution", slider=True, text="Restitution (e)")
    layout.prop(props, "side_jar_transparency", slider=True, text="Chamber Opacity")
```

### Dynamic Icon Buttons
Change the icon dynamically based on state:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    side_active = bool(props.show_side_jar_view and bpy.data.objects.get("Jar_Chamber_SideView"))
    icon_type = "CHECKBOX_HLT" if side_active else "CHECKBOX_DEHLT"
    layout.operator("science_blocks.toggle_side_jar_view", text="Side View Active", icon=icon_type)
```

---

## 5. Search Pickers & ID Templates

### Object & Material Search Pickers (`prop_search`)
Allows the user to search through Blender data-blocks with autocomplete:

```python
def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props
    scene = context.scene

    # Searches scene.objects and writes the selected object name to props.target_object_name
    layout.prop_search(props, "target_object_name", scene, "objects", text="Chamber CAD Model")

    # Searches materials in bpy.data.materials
    layout.prop_search(props, "target_material_name", bpy.data, "materials", text="Base Material")
```

### Pointer Properties (`layout.prop` with `PointerProperty`)
Directly displays an interactive Blender data-block selector:

```python
# Defined in properties.py:
# jar_chamber_obj: PointerProperty(type=bpy.types.Object, name="Jar Chamber")

def draw(self, context):
    layout = self.layout
    props = context.scene.science_blocks_props

    # Displays an eyedropper and object list
    layout.prop(props, "jar_chamber_obj", text="Chamber / Jar")
```

---

## 6. Dynamic Scrollable Lists (`UIList`)

The `UIList` pattern allows rendering dynamic, reorderable, scrollable lists with add and remove buttons.

### 1. Define the List Item & Collection
```python
import bpy

class PlanetaryMaterialItem(bpy.types.PropertyGroup):
    """Data item in the list."""
    name: bpy.props.StringProperty(name="Material Name", default="Chrome Steel")
    density: bpy.props.FloatProperty(name="Density (kg/m³)", default=7850.0)
    restitution: bpy.props.FloatProperty(name="Restitution", default=0.82)
```

### 2. Define the Custom UIList
```python
class SCIENCE_BLOCKS_UL_material_list(bpy.types.UIList):
    """Draws each row of the scrollable list."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text="", icon="SNAP_VOLUME")
            row.prop(item, "name", text="", emboss=False)
            row.prop(item, "density", text="Density")
            row.prop(item, "restitution", text="e")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text="", icon="SNAP_VOLUME")
```

### 3. Draw the List in the Panel
```python
def draw(self, context):
    layout = self.layout
    scene = context.scene

    # Renders scrollable template_list with 4 visible rows
    row = layout.row()
    row.template_list(
        "SCIENCE_BLOCKS_UL_material_list",
        "",
        scene,
        "custom_materials_collection",
        scene,
        "custom_materials_index",
        rows=4,
    )

    # Vertical Add / Remove buttons beside the list
    col = row.column(align=True)
    col.operator("science_blocks.list_item_add", icon="ADD", text="")
    col.operator("science_blocks.list_item_remove", icon="REMOVE", text="")
```

---

## 7. Popup Dialogs & Menus

### Header & Context Dropdown Menus (`bpy.types.Menu`)
```python
class SCIENCE_BLOCKS_MT_presets_menu(bpy.types.Menu):
    bl_label = "Simulation Presets"
    bl_idname = "SCIENCE_BLOCKS_MT_presets_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("science_blocks.preset_cataracting", text="High-Impact Cataracting", icon="PARTICLES")
        layout.operator("science_blocks.preset_cascading", text="Attrition Cascading", icon="FORCE_CHARGE")
        layout.operator("science_blocks.preset_wet_slurry", text="Viscous Wet Slurry", icon="MATFLUID")
        layout.separator()
        layout.operator("science_blocks.apply_light_theme", text="Light White Studio", icon="LIGHT_SUN")

# In panel:
# layout.menu("SCIENCE_BLOCKS_MT_presets_menu", text="Load Preset", icon="DOWNARROW_HLT")
```

### Interactive Modal Dialog Confirmation (`invoke_props_dialog`)
```python
class SCIENCE_BLOCKS_OT_confirm_reset(bpy.types.Operator):
    """Operator that opens a confirmation popup before acting."""
    bl_idname = "science_blocks.confirm_reset"
    bl_label = "Reset Simulation Data?"
    bl_options = {"REGISTER", "INTERNAL"}

    confirm_purge: bpy.props.BoolProperty(name="Also Delete Generated Figures", default=True)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout
        layout.label(text="This will reset all baked trajectories.", icon="ERROR")
        layout.prop(self, "confirm_purge")

    def execute(self, context):
        # Action logic executed upon clicking OK
        self.report({"INFO"}, "Simulation data reset successfully.")
        return {"FINISHED"}
```

---

## 8. Complete Standalone Example Script

Paste this complete script into Blender's **Text Editor** and click **Run Script**. It registers a complete custom panel in the 3D Viewport sidebar (`View3D > Sidebar > UI Demo`) demonstrating all UI elements together.

```python
import bpy
from bpy.props import StringProperty, IntProperty, FloatProperty, BoolProperty, EnumProperty, PointerProperty

# 1. Properties
class DemoPanelProperties(bpy.types.PropertyGroup):
    demo_text: StringProperty(name="Experiment Name", default="Planetary Mill 01")
    demo_slider: FloatProperty(name="Intensity", default=0.75, min=0.0, max=1.0)
    demo_count: IntProperty(name="Ball Count", default=25, min=1, max=500)
    demo_toggle: BoolProperty(name="Live Preview", default=False)
    demo_color: bpy.props.FloatVectorProperty(
        name="Particle Color",
        subtype="COLOR",
        size=4,
        default=(0.95, 0.55, 0.15, 1.0),
    )
    demo_enum: EnumProperty(
        name="Solver",
        items=[
            ("YADE", "Yade DEM", "Yade Open-Source Particle Engine"),
            ("LIGGGHTS", "LIGGGHTS", "LAMMPS Granular Engine"),
            ("NATIVE", "Native Symplectic", "Embedded Velocity-Verlet"),
        ],
        default="YADE",
    )
    target_object: PointerProperty(name="Target Chamber", type=bpy.types.Object)

# 2. Operator
class DEMO_OT_test_action(bpy.types.Operator):
    bl_idname = "demo.test_action"
    bl_label = "Execute Action"
    bl_description = "Run demo action"

    def execute(self, context):
        props = context.scene.demo_panel_props
        self.report({"INFO"}, f"Executed: {props.demo_enum} with {props.demo_count} balls.")
        return {"FINISHED"}

# 3. Panel
class VIEW3D_PT_demo_showcase(bpy.types.Panel):
    bl_label = "Blender UI Elements Showcase"
    bl_idname = "VIEW3D_PT_demo_showcase"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UI Demo"

    def draw(self, context):
        layout = self.layout
        props = context.scene.demo_panel_props

        # Section 1: Standard Box Layout
        box1 = layout.box()
        box1.label(text="Input Controls & Sliders:", icon="SETTINGS")
        col1 = box1.column(align=True)
        col1.prop(props, "demo_text")
        col1.prop(props, "demo_slider", slider=True)
        col1.prop(props, "demo_count")
        col1.prop(props, "demo_color")

        layout.separator(factor=0.3)

        # Section 2: Compact Row & Push Button Toggle
        box2 = layout.box()
        box2.label(text="Horizontal Row & Toggles:", icon="VIEW3D")
        row_toggles = box2.row(align=True)
        row_toggles.prop(props, "demo_toggle", toggle=True, icon="PLAY")
        row_toggles.prop(props, "demo_enum", text="")

        # Section 3: Eyedropper Pointer Picker
        box2.separator(factor=0.2)
        box2.prop(props, "target_object")

        layout.separator(factor=0.4)

        # Section 4: Scaled Action Button
        row_btn = layout.row(align=True)
        row_btn.scale_y = 1.4  # Prominent tall button
        row_btn.operator("demo.test_action", text="Run Simulation Demo", icon="PARTICLES")

# Registration
classes = (
    DemoPanelProperties,
    DEMO_OT_test_action,
    VIEW3D_PT_demo_showcase,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.demo_panel_props = PointerProperty(type=DemoPanelProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.demo_panel_props

if __name__ == "__main__":
    register()
```

