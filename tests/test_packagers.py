from abc import ABC
import pytest

from virt_backup.exceptions import ImageNotFoundError
from virt_backup.backups.packager import BackupPackagers


@pytest.fixture()
def new_image(tmpdir, name="test", content="test"):
    image = tmpdir.join(name)
    image.write(content)
    return image


class _BaseTestBackupPackager(ABC):

    def test_add(self, new_packager, new_image):
        with new_packager:
            new_packager.add(str(new_image))
            assert new_image.basename in new_packager.list()

    def test_add_custom_name(self, new_packager, new_image):
        name = "another_test"

        with new_packager:
            new_packager.add(str(new_image), name=name)
            assert name in new_packager.list()

    def test_restore(self, tmpdir, new_packager, new_image):
        name = new_image.basename
        with new_packager:
            new_packager.add(str(new_image))
            new_packager.restore(name, str(tmpdir))

            extracted_image = tmpdir.join(name)
            assert extracted_image.check()
            assert tmpdir.join(name).read() == new_image.read()

    def test_restore_unexisting(self, tmpdir, new_packager):
        with new_packager:
            with pytest.raises(ImageNotFoundError):
                new_packager.restore("test", str(tmpdir))


class TestBackupPackagerDir(_BaseTestBackupPackager):

    @pytest.fixture()
    def new_packager(self, tmpdir):
        return BackupPackagers.directory.value("test", str(tmpdir))


class TestBackupPackagerTar(_BaseTestBackupPackager):

    @pytest.fixture()
    def new_packager(self, tmpdir):
        return BackupPackagers.tar.value(
            "test", str(tmpdir), "test_package.tar"
        )
