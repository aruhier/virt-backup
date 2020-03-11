import logging
import os
import re
import shutil
import sys
import tarfile


def copy_file(src, dst, buffersize=None):
    if not os.path.exists(dst) and dst.endswith("/"):
        os.makedirs(dst)
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))

    with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        shutil.copyfileobj(fsrc, fdst, buffersize)
    return dst


class InfoFilter(logging.Filter):
    def filter(self, record):
        return record.levelno in (logging.DEBUG, logging.INFO)
