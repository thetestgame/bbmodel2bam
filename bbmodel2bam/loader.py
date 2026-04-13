"""
Panda3D Python file loader for .bbmodel files.

Register via panda3d.loaders entry point so that
``loader.load_model('model.bbmodel')`` works transparently.
Requires Panda3D 1.10.4+.
"""

import os
import tempfile

import panda3d.core as p3d

from .converter import convert


class BbmodelLoader:
    name = 'Bbmodel'
    extensions = ['bbmodel']
    supports_compressed = False

    @staticmethod
    def load_file(path, options, _record=None):
        loader = p3d.Loader.get_global_ptr()
        with tempfile.TemporaryDirectory() as tmpdir:
            bam_path = os.path.join(tmpdir, 'out.bam')
            convert(
                p3d.Filename.to_os_specific(path),
                bam_path,
            )
            opts = p3d.LoaderOptions(options)
            opts.flags |= p3d.LoaderOptions.LF_no_cache
            return loader.load_sync(
                p3d.Filename.from_os_specific(bam_path), options=opts,
            )
