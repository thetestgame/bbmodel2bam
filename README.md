# bbmodel2bam

Convert Blockbench `.bbmodel` files to Panda3D `.bam` files.

Inspired by [blend2bam](https://github.com/Moguri/blend2bam).

## Features

- **Mesh elements** – free-form meshes with per-vertex UVs
- **Cube elements** – box primitives with per-face UV rects
- **Embedded textures** – base64-encoded textures decoded and embedded in BAM
- **File-referenced textures** – external texture paths resolved relative to `.bbmodel`
- **Groups / bones** – outliner hierarchy preserved as scene-graph nodes
- **Element transforms** – origin and rotation applied correctly
- **Coordinate conversion** – Blockbench Y-up → Panda3D Z-up
- **Panda3D file loader** – `loader.load_model('model.bbmodel')` works natively

## Installation

```
pip install panda3d-bbmodel2bam
```

Or install in development mode:

```
pip install -e .
```

## Usage

### CLI

```
bbmodel2bam model.bbmodel model.bam
bbmodel2bam models/ output/
bbmodel2bam --scale 0.0625 --textures ref model.bbmodel model.bam
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--scale FLOAT` | `1.0` | Uniform scale factor for coordinates |
| `--textures {embed,ref}` | `embed` | Embed textures in BAM or save as separate files |
| `--append-ext` | off | Append `.bam` instead of replacing extension (batch) |
| `-v, --verbose` | off | Print extra conversion info |

### Python

```python
from bbmodel2bam.converter import convert
convert('model.bbmodel', 'model.bam', scale=1.0)
```

### Panda3D File Loader

With the package installed, Panda3D 1.10.4+ can load `.bbmodel` files directly:

```python
model = loader.load_model('model.bbmodel')
model.reparent_to(render)
```

## Supported bbmodel features

| Feature | Status |
|---------|--------|
| Cube elements | ✅ |
| Mesh elements (free-form) | ✅ |
| Per-face UV (non-box UV) | ✅ |
| Box UV | ❌ planned |
| Embedded textures (base64) | ✅ |
| External texture files | ✅ |
| Element rotation/origin | ✅ |
| Groups / outliner hierarchy | ✅ |
| Animations | ❌ planned |
| Locators | ❌ planned |

## License

MIT
