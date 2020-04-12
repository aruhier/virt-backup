from abc import ABC
import os
import random
import pytest

from virt_backup.exceptions import ImageNotFoundError
from virt_backup.backups.packagers import ReadBackupPackagers, WriteBackupPackagers


@pytest.fixture()
def new_image(tmpdir, name="test", content=None):
    image = tmpdir.join(name)
    if content is None:
        # Generate a content of around 5MB.
        content = "{:016d}".format(random.randrange(16)) * int(5 * 2 ** 20 / 16)
    image.write(content)
    return image


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

    def test_remove_package(self, write_packager):
        with write_packager:
            pass
        write_packager.remove_package()
        assert not os.path.exists(write_packager.complete_path)


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
