#!/usr/bin/env python3

import os
from tqdm import tqdm


def copy_file_progress(src, dst, buffersize=512*1024):
    total_size = os.path.getsize(src)
    if not os.path.exists(dst) and dst.endswith("/"):
        os.mkdir(dst)
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.basename(src))

    # Load tqdm with size counter instead of files counter
    with tqdm(total=total_size, unit='B', unit_scale=True, ncols=0) as pbar, \
            open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            buf = fsrc.read(buffersize)
            if not buf:
                break
            fdst.write(buf)
            pbar.update(len(buf))
