from abc import ABC, abstractmethod
import logging
import yaml


logger = logging.getLogger("virt_backup")


def convert_warn(config):
    converters = (ToV0_4,)
    for c in converters:
        c().convert_warn(config)


class ConfigConverter(ABC):
    @abstractmethod
    def convert_warn(self, config):
        pass

    @abstractmethod
    def convert(self, config):
        pass


class ToV0_4(ConfigConverter):
    """
    Convert from v0.1 to v0.4
    """

    def convert_warn(self, config):
        for m in self.convert(config):
            logger.warning("%s\n", m)

    def convert(self, config):
        warnings = []
        for group, group_config in config["groups"].items():
            convertion = self.convert_group(group_config)
            msg = convertion["msg"]
            changed = convertion["changed"]

            if msg:
                warnings.append(
                    'Action needed for group "{}": {}.\nAdapt its config for:\n\t{}'.format(
                        group, msg, yaml.safe_dump(changed, default_flow_style=False)
                    )
                )

        return warnings

    def convert_group(self, group):
        if not ("compression" in group or "compression_lvl" in group):
            return {"changed": {}, "msg": ""}

        changed = {}

        if "compression" in group:
            old_compression = group.pop("compression")
            new_packager = ""
            new_packager_opts = {}

            if old_compression is None:
                new_packager = "directory"
            else:
                new_packager = "tar"
                if old_compression != "tar":
                    new_packager_opts["compression"] = old_compression

            for d in (group, changed):
                d["packager"] = new_packager
                if new_packager_opts:
                    d["packager_opts"] = new_packager_opts

        if "compression_lvl" in group:
            compression_lvl = group.pop("compression_lvl")

            for d in (group, changed):
                packager_opts = d.get("packager_opts", {})
                packager_opts["compression_lvl"] = compression_lvl
                d["packager_opts"] = packager_opts

        msg = (
            "current config uses 'compress' and 'compression_lvl' options. "
            "It has been deprecated in favor of 'packager' and 'packager_opts'"
        )
        return {"changed": changed, "msg": msg}
