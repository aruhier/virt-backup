from abc import ABC
import pytest

from virt_backup.exceptions import ImageNotFoundError
from virt_backup.backups.packager import (
    ReadBackupPackagers, WriteBackupPackagers
)


@pytest.fixture()
def new_image(tmpdir, name="test", content="test"):
    image = tmpdir.join(name)
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


class TestBackupPackagerDir(_BaseTestBackupPackager):

    @pytest.fixture()
    def read_packager(self, tmpdir):
        return ReadBackupPackagers.directory.value(
            "test", str(tmpdir.join("packager"))
        )

    @pytest.fixture()
    def write_packager(self, tmpdir):
        return WriteBackupPackagers.directory.value(
            "test", str(tmpdir.join("packager"))
        )


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
