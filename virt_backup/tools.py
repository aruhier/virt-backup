import os
import re
import tarfile
from tqdm import tqdm


DEFAULT_BUFFERSIZE = 512*1024


def copy_file_progress(src, dst, buffersize=DEFAULT_BUFFERSIZE):
    total_size = os.path.getsize(src)
    if not os.path.exists(dst) and dst.endswith("/"):
        os.makedirs(dst)
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))

    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        copy_stream_progress(fsrc, fdst, total_size, buffersize)
    return dst


def copy_stream_to_file_progress(src, dst, total_size,
                                 buffersize=DEFAULT_BUFFERSIZE):
    with open(dst, "wb") as fdst:
        copy_stream_progress(src, fdst, total_size, buffersize)
    return dst


def copy_stream_progress(stsrc, stdst, total_size,
                         buffersize=DEFAULT_BUFFERSIZE):
    # Load tqdm with size counter instead of files counter

    tqdm_kwargs = {
        "total": total_size, "unit": "B", "unit_scale": True,
        "ncols": 0, "mininterval": 0.5
    }
    with tqdm(**tqdm_kwargs) as pbar:
        while True:
            buf = stsrc.read(buffersize)
            if not buf:
                break
            stdst.write(buf)
            pbar.update(len(buf))


def get_progress_bar_tar(progress_bar):
    class FileProgressFileObject(tarfile.ExFileObject):
        def read(self, size, *args):
            progress_bar.update(size)
            return tarfile.ExFileObject.read(self, size, *args)
    return FileProgressFileObject
