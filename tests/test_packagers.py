from abc import ABC
import os
import random
import threading
import pytest

from virt_backup.exceptions import CancelledError, ImageNotFoundError
from virt_backup.backups.packagers import ReadBackupPackagers, WriteBackupPackagers


@pytest.fixture()
def new_image(tmpdir, name="test", content=None):
    image = tmpdir.join(name)
    if content is None:
        # Generate a content of around 5MB.
        content = "{:016d}".format(random.randrange(16)) * int(5 * 2 ** 20 / 16)
    image.write(content)
    return image


@pytest.fixture()
def cancel_flag():
    return threading.Event()


class _BaseTestBackupPackager(ABC):
    def test_add(self, write_packager, new_image):
        with write_packager:
            write_packager.add(str(new_image))
            assert new_image.basename in write_packager.list()

    def test_add_custom_name(self, write_packager, new_image):
        name = "another_test"

        with write_packager:
            write_packager.add(str(new_image), name=name)
            assert name in write_packager.list()

    def test_add_cancelled(self, write_packager, new_image, cancel_flag):
        with write_packager:
            cancel_flag.set()
            with pytest.raises(CancelledError):
                write_packager.add(str(new_image), stop_event=cancel_flag)

    def test_restore(self, tmpdir, write_packager, read_packager, new_image):
        name = new_image.basename

        with write_packager:
            write_packager.add(str(new_image))
        with read_packager:
            tmpdir = tmpdir.mkdir("extract")
            read_packager.restore(name, str(tmpdir))

            extracted_image = tmpdir.join(name)
            assert extracted_image.check()
            assert tmpdir.join(name).read() == new_image.read()

    def test_restore_unexisting(self, tmpdir, write_packager, read_packager):
        with write_packager:
            pass
        with read_packager:
            tmpdir = tmpdir.mkdir("extract")
            with pytest.raises(ImageNotFoundError):
                read_packager.restore("test", str(tmpdir))

    def test_restore_cancelled(
        self, tmpdir, write_packager, read_packager, new_image, cancel_flag
    ):
        name = new_image.basename

        with write_packager:
            write_packager.add(str(new_image))
        with read_packager:
            tmpdir = tmpdir.mkdir("extract")
            cancel_flag.set()
            with pytest.raises(CancelledError):
                read_packager.restore(name, str(tmpdir), stop_event=cancel_flag)

    def test_remove_package(self, write_packager):
        with write_packager:
            pass
        write_packager.remove_package()
        assert not os.path.exists(write_packager.complete_path)

    def test_remove_package_cancelled(self, write_packager, cancel_flag):
        with write_packager:
            pass
        cancel_flag.set()
        with pytest.raises(CancelledError):
            write_packager.remove_package()


class TestBackupPackagerDir(_BaseTestBackupPackager):
    @pytest.fixture()
    def read_packager(self, tmpdir):
        return ReadBackupPackagers.directory.value("test", str(tmpdir.join("packager")))

    @pytest.fixture()
    def write_packager(self, tmpdir):
        return WriteBackupPackagers.directory.value(
            "test", str(tmpdir.join("packager"))
        )

    def test_remove(self, tmpdir, write_packager, new_image):
        name = new_image.basename

        with write_packager:
            write_packager.add(str(new_image))
            write_packager.remove(name)
            assert not write_packager.list()

    def test_remove_package_cancelled(self, write_packager, cancel_flag):
        """
        Atomic for the directory package, so cancel it will not fail.
        """
        with write_packager:
            pass
        cancel_flag.set()
        write_packager.remove_package()
        assert not os.path.exists(write_packager.complete_path)


class TestBackupPackagerTar(_BaseTestBackupPackager):
    @pytest.fixture()
    def read_packager(self, tmpdir):
        return ReadBackupPackagers.tar.value(
            "test", str(tmpdir.join("packager")), "test_package.tar"
        )

    @pytest.fixture()
    def write_packager(self, tmpdir):
        return WriteBackupPackagers.tar.value(
            "test", str(tmpdir.join("packager")), "test_package.tar"
        )

    def test_remove_package_cancelled(self, write_packager, cancel_flag):
        """
        Atomic for the tar package, so cancel it will not fail.
        """
        with write_packager:
            pass
        cancel_flag.set()
        write_packager.remove_package()
        assert not os.path.exists(write_packager.complete_path)


@pytest.mark.extra
class TestBackupPackagerZSTD(_BaseTestBackupPackager):
    @pytest.fixture()
    def read_packager(self, tmpdir):
        return ReadBackupPackagers.zstd.value(
            "test", str(tmpdir.join("packager")), "test_package"
        )

    @pytest.fixture()
    def write_packager(self, tmpdir):
        return WriteBackupPackagers.zstd.value(
            "test", str(tmpdir.join("packager")), "test_package"
        )

    def test_remove_package(self, write_packager, new_image):
        with write_packager:
            write_packager.add(str(new_image), name="another_test")
            backups = write_packager.list()

        # Try to create a .zst file in the same directory, to check #29.
        other_file = os.path.join(write_packager.complete_path, "test.zst")
        with open(other_file, "w") as f:
            f.write("")

        write_packager.remove_package()

        for b in backups:
            assert not os.path.exists(write_packager.archive_path(b))

        # Checks that remove_package only removed the wanted backups.
        assert os.path.exists(other_file)

    def test_remove_package_cancelled(self, write_packager, new_image, cancel_flag):
        with write_packager:
            write_packager.add(str(new_image), name="another_test")

        # Try to create a .zst file in the same directory, to check #29.
        other_file = os.path.join(write_packager.complete_path, "test.zst")
        with open(other_file, "w") as f:
            f.write("")

        cancel_flag.set()
        with pytest.raises(CancelledError):
            write_packager.remove_package(cancel_flag)
