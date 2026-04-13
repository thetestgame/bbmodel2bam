"""Core conversion logic: Blockbench .bbmodel -> Panda3D BAM."""

import json
import base64
import os
import tempfile
from pathlib import Path

from panda3d.core import (
    NodePath, ModelRoot, GeomNode,
    Geom, GeomTriangles, GeomVertexFormat, GeomVertexData, GeomVertexWriter,
    Texture, Filename, SamplerState,
    LVector3f, TransparencyAttrib,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert(src, dst, scale=1.0, textures_mode='embed', verbose=False):
    """Convert a .bbmodel file to a .bam file.

    Parameters
    ----------
    src : str
        Path to the source .bbmodel file.
    dst : str
        Path for the output .bam file.
    scale : float
        Uniform scale factor applied to all coordinates (default 1.0).
    textures_mode : str
        'embed' to embed textures in the BAM, 'ref' to save alongside.
    verbose : bool
        Print extra info during conversion.
    """
    src = os.path.abspath(src)
    dst = os.path.abspath(dst)
    dst_dir = os.path.dirname(dst)
    os.makedirs(dst_dir or '.', exist_ok=True)

    with open(src, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if verbose:
        print(f'Loaded {src}')
        print(f'  format_version: {data.get("meta", {}).get("format_version")}')
        print(f'  elements: {len(data.get("elements", []))}')
        print(f'  textures: {len(data.get("textures", []))}')

    # Load textures from bbmodel data
    tex_map = _load_textures(data, src)

    # Configure texture output mode
    if textures_mode == 'ref':
        _export_textures_to_files(tex_map, data, dst_dir)
    else:
        for tex in tex_map.values():
            tex.set_keep_ram_image(True)
            tex.clear_filename()
            tex.clear_alpha_filename()

    # Build scene graph
    root_np = _build_scene(data, src, tex_map, scale)

    # Write BAM
    root_np.write_bam_file(Filename.from_os_specific(dst))
    if verbose:
        print(f'Wrote {dst}')
    return dst


# ---------------------------------------------------------------------------
# Coordinate conversion  (Blockbench Y-up  ->  Panda3D Z-up)
# ---------------------------------------------------------------------------

def _cv(x, y, z, s=1.0):
    """(x, y, z) Y-up  ->  (x, -z, y) Z-up, with scale."""
    return (x * s, -z * s, y * s)


# ---------------------------------------------------------------------------
# Texture loading
# ---------------------------------------------------------------------------

def _load_textures(data, src_path):
    """Return dict  {int_index: Texture}  loaded from the bbmodel."""
    textures = {}
    src_dir = os.path.dirname(src_path)

    for i, td in enumerate(data.get('textures', [])):
        tex = Texture(td.get('name', f'tex_{i}'))
        loaded = False

        # Try embedded base64 first
        source = td.get('source', '')
        if source.startswith('data:image/'):
            mime = source.split(';')[0].split('/')[-1]
            ext = '.' + mime.replace('jpeg', 'jpg')
            b64 = source.split(',', 1)[1]
            raw = base64.b64decode(b64)

            fd, tmp = tempfile.mkstemp(suffix=ext)
            try:
                os.write(fd, raw)
                os.close(fd)
                loaded = tex.read(Filename.from_os_specific(tmp))
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

        # Fall back to file path
        if not loaded and td.get('path'):
            p = td['path']
            if not os.path.isabs(p):
                p = os.path.join(src_dir, p)
            if os.path.exists(p):
                loaded = tex.read(Filename.from_os_specific(os.path.abspath(p)))

        if loaded:
            tex.set_magfilter(SamplerState.FT_nearest)
            tex.set_minfilter(SamplerState.FT_nearest)
            tex.set_wrap_u(SamplerState.WM_clamp)
            tex.set_wrap_v(SamplerState.WM_clamp)
            textures[i] = tex

    return textures


def _export_textures_to_files(tex_map, data, dst_dir):
    """Save loaded textures as PNG next to the BAM and set filenames."""
    for i, td in enumerate(data.get('textures', [])):
        if i not in tex_map:
            continue
        tex = tex_map[i]
        name = td.get('name', f'texture_{i}')
        fname = f'{name}.png'
        fpath = os.path.join(dst_dir, fname)
        tex.write(Filename.from_os_specific(fpath))
        tex.set_filename(Filename(fname))
        tex.set_fullpath(Filename.from_os_specific(fpath))


# ---------------------------------------------------------------------------
# Scene graph construction
# ---------------------------------------------------------------------------

def _build_scene(data, src_path, tex_map, scale):
    """Return a NodePath with a ModelRoot for the entire bbmodel."""
    name = data.get('name', Path(src_path).stem)
    root = NodePath(ModelRoot(name))

    res_w = data.get('resolution', {}).get('width', 64)
    res_h = data.get('resolution', {}).get('height', 64)

    elems = {e['uuid']: e for e in data.get('elements', [])}
    _build_outliner(
        root, data.get('outliner', []),
        elems, tex_map, res_w, res_h, scale,
    )
    return root


def _build_outliner(parent, items, elems, tex_map, rw, rh, sc):
    """Recursively add outliner items to the scene graph."""
    for item in items:
        if isinstance(item, str):
            # Element UUID
            elem = elems.get(item)
            if elem:
                np = _build_element(elem, tex_map, rw, rh, sc)
                if np:
                    np.reparent_to(parent)
        elif isinstance(item, dict):
            # Group / bone
            gname = item.get('name', 'group')
            gnp = parent.attach_new_node(gname)

            origin = item.get('origin', [0, 0, 0])
            rotation = item.get('rotation', [0, 0, 0])
            ox, oy, oz = _cv(*origin, sc)
            gnp.set_pos(ox, oy, oz)

            if any(r != 0 for r in rotation):
                rx, ry, rz = rotation
                gnp.set_hpr(-ry, rz, rx)

            _build_outliner(
                gnp, item.get('children', []),
                elems, tex_map, rw, rh, sc,
            )


# ---------------------------------------------------------------------------
# Element builders
# ---------------------------------------------------------------------------

def _build_element(elem, tex_map, rw, rh, sc):
    """Dispatch to mesh or cube builder."""
    if not elem.get('export', True) or not elem.get('visibility', True):
        return None
    etype = elem.get('type', 'cube')
    if etype == 'mesh':
        return _build_mesh(elem, tex_map, rw, rh, sc)
    return _build_cube(elem, tex_map, rw, rh, sc)


# ---- Mesh elements -------------------------------------------------------

def _build_mesh(elem, tex_map, rw, rh, sc):
    verts = elem.get('vertices', {})
    faces = elem.get('faces', {})
    if not verts or not faces:
        return None

    name = elem.get('name', 'mesh')
    origin = elem.get('origin', [0, 0, 0])
    rotation = elem.get('rotation', [0, 0, 0])

    # Group faces by texture index
    by_tex = {}
    for fd in faces.values():
        ti = fd.get('texture')
        if ti is None:
            ti = -1
        by_tex.setdefault(ti, []).append(fd)

    node_np = NodePath(name)

    for ti, flist in by_tex.items():
        gn = _mesh_geom(f'{name}_t{ti}', verts, flist, origin, rw, rh, sc)
        if gn:
            gnp = node_np.attach_new_node(gn)
            if ti >= 0 and ti in tex_map:
                gnp.set_texture(tex_map[ti])
                gnp.set_transparency(TransparencyAttrib.M_alpha)

    # Element transform
    ox, oy, oz = _cv(*origin, sc)
    node_np.set_pos(ox, oy, oz)
    if any(r != 0 for r in rotation):
        rx, ry, rz = rotation
        node_np.set_hpr(-ry, rz, rx)

    return node_np


def _mesh_geom(name, verts, flist, origin, rw, rh, sc):
    """Build a GeomNode from mesh-type faces."""
    vfmt = GeomVertexFormat.get_v3n3t2()
    vdata = GeomVertexData(name, vfmt, Geom.UH_static)
    vw = GeomVertexWriter(vdata, 'vertex')
    nw = GeomVertexWriter(vdata, 'normal')
    tw = GeomVertexWriter(vdata, 'texcoord')
    tris = GeomTriangles(Geom.UH_static)
    idx = 0

    for fd in flist:
        vids = fd.get('vertices', [])
        uv_map = fd.get('uv', {})
        if len(vids) < 3:
            continue

        positions = []
        uvs = []
        ok = True
        for vid in vids:
            if vid not in verts:
                ok = False
                break
            vp = verts[vid]
            rel = (vp[0] - origin[0], vp[1] - origin[1], vp[2] - origin[2])
            positions.append(_cv(*rel, sc))
            if vid in uv_map:
                u, v = uv_map[vid]
                uvs.append((u / rw, 1.0 - v / rh))
            else:
                uvs.append((0.0, 0.0))

        if not ok or len(positions) < 3:
            continue

        normal = _face_normal(*positions[:3])
        base = idx
        for pos, uv in zip(positions, uvs):
            vw.add_data3(*pos)
            nw.add_data3(normal)
            tw.add_data2(*uv)
            idx += 1

        # Fan triangulation (reverse winding: BB is CW, Panda3D is CCW)
        for t in range(1, len(positions) - 1):
            tris.add_vertices(base, base + t + 1, base + t)

    if idx == 0:
        return None
    geom = Geom(vdata)
    geom.add_primitive(tris)
    gn = GeomNode(name)
    gn.add_geom(geom)
    return gn


# ---- Cube elements --------------------------------------------------------

def _cube_face_verts(x0, y0, z0, x1, y1, z1, face):
    """Return 4 verts (CCW from outside) for a cube face in BB Y-up space."""
    F = {
        'north': [(x1,y1,z0),(x0,y1,z0),(x0,y0,z0),(x1,y0,z0)],
        'south': [(x0,y1,z1),(x1,y1,z1),(x1,y0,z1),(x0,y0,z1)],
        'east':  [(x1,y1,z1),(x1,y1,z0),(x1,y0,z0),(x1,y0,z1)],
        'west':  [(x0,y1,z0),(x0,y1,z1),(x0,y0,z1),(x0,y0,z0)],
        'up':    [(x0,y1,z0),(x1,y1,z0),(x1,y1,z1),(x0,y1,z1)],
        'down':  [(x0,y0,z1),(x1,y0,z1),(x1,y0,z0),(x0,y0,z0)],
    }
    return F.get(face, [])


def _build_cube(elem, tex_map, rw, rh, sc):
    name = elem.get('name', 'cube')
    fr = elem.get('from', [0, 0, 0])
    to = elem.get('to', [16, 16, 16])
    origin = elem.get('origin', [0, 0, 0])
    rotation = elem.get('rotation', [0, 0, 0])
    inflate = elem.get('inflate', 0)
    faces_data = elem.get('faces', {})

    x0, y0, z0 = fr[0] - inflate, fr[1] - inflate, fr[2] - inflate
    x1, y1, z1 = to[0] + inflate, to[1] + inflate, to[2] + inflate

    # Group cube faces by texture
    by_tex = {}
    for fname, fd in faces_data.items():
        if fname not in ('north', 'south', 'east', 'west', 'up', 'down'):
            continue
        ti = fd.get('texture')
        if ti is None:
            ti = -1
        by_tex.setdefault(ti, []).append((fname, fd))

    node_np = NodePath(name)

    for ti, face_list in by_tex.items():
        gn = _cube_geom(
            f'{name}_t{ti}', x0, y0, z0, x1, y1, z1,
            face_list, origin, rw, rh, sc,
        )
        if gn:
            gnp = node_np.attach_new_node(gn)
            if ti >= 0 and ti in tex_map:
                gnp.set_texture(tex_map[ti])
                gnp.set_transparency(TransparencyAttrib.M_alpha)

    ox, oy, oz = _cv(*origin, sc)
    node_np.set_pos(ox, oy, oz)
    if any(r != 0 for r in rotation):
        rx, ry, rz = rotation
        node_np.set_hpr(-ry, rz, rx)

    return node_np


def _cube_geom(name, x0, y0, z0, x1, y1, z1, face_list, origin, rw, rh, sc):
    vfmt = GeomVertexFormat.get_v3n3t2()
    vdata = GeomVertexData(name, vfmt, Geom.UH_static)
    vw = GeomVertexWriter(vdata, 'vertex')
    nw = GeomVertexWriter(vdata, 'normal')
    tw = GeomVertexWriter(vdata, 'texcoord')
    tris = GeomTriangles(Geom.UH_static)
    idx = 0

    for fname, fd in face_list:
        corners_bb = _cube_face_verts(x0, y0, z0, x1, y1, z1, fname)
        if not corners_bb:
            continue

        # Convert positions: make relative to origin, then Y-up -> Z-up
        positions = []
        for c in corners_bb:
            rel = (c[0] - origin[0], c[1] - origin[1], c[2] - origin[2])
            positions.append(_cv(*rel, sc))

        normal = _face_normal(*positions[:3])

        # UV rect [u0, v0, u1, v1] in pixel coords
        uv = fd.get('uv', [0, 0, rw, rh])
        if not isinstance(uv, list) or len(uv) != 4:
            uv = [0, 0, rw, rh]
        u0, v0, u1, v1 = uv
        face_uvs = [
            (u0 / rw, 1.0 - v0 / rh),
            (u1 / rw, 1.0 - v0 / rh),
            (u1 / rw, 1.0 - v1 / rh),
            (u0 / rw, 1.0 - v1 / rh),
        ]

        # Apply face UV rotation
        rot = fd.get('rotation', 0)
        if rot:
            steps = rot // 90
            face_uvs = face_uvs[-steps:] + face_uvs[:-steps]

        base = idx
        for pos, fuv in zip(positions, face_uvs):
            vw.add_data3(*pos)
            nw.add_data3(normal)
            tw.add_data2(*fuv)
            idx += 1
        # Reverse winding: BB is CW, Panda3D is CCW
        tris.add_vertices(base, base + 2, base + 1)
        tris.add_vertices(base, base + 3, base + 2)

    if idx == 0:
        return None
    geom = Geom(vdata)
    geom.add_primitive(tris)
    gn = GeomNode(name)
    gn.add_geom(geom)
    return gn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _face_normal(p0, p1, p2):
    """Compute face normal from three points (reversed for CW->CCW flip)."""
    v0 = LVector3f(*p0)
    v1 = LVector3f(*p1)
    v2 = LVector3f(*p2)
    n = (v2 - v0).cross(v1 - v0)
    n.normalize()
    return n
