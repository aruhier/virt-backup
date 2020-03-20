import libvirt
import logging
import re

from virt_backup.domains import search_domains_regex


logger = logging.getLogger("virt_backup")


def matching_libvirt_domains_from_config(host, conn):
    """
    Return matching domains with the host definition

    Will be mainly used by config,

    :param host: domain name or custom regex to match on multiple domains
    :param conn: connection with libvirt
    :returns {"domains": (domain_name, ), "exclude": bool}: exclude will
        indicate if the domains need to be explicitly excluded of the backup
        group or not (for example, if a user wants to exclude all domains
        starting by a certain pattern). Domains will not be libvirt.virDomain
        objects, but just domain names (easier to manage the include/exclude
        feature)
    """
    if isinstance(host, str):
        pattern = host
    else:
        try:
            pattern = host["host"]
        except KeyError as e:
            logger.error(
                "Configuration error, missing host for lines: \n" "{}".format(host)
            )
            raise e
    matches = pattern_matching_domains_in_libvirt(pattern, conn)
    # not useful to continue if no domain matches or if the host variable
    # doesn't bring any property for our domain (like which disks to backup)
    if not isinstance(host, dict) or not matches["domains"]:
        return matches

    if host.get("disks", None):
        matches["disks"] = sorted(host["disks"])
    return matches


def pattern_matching_domains_in_libvirt(pattern, conn):
    """
    Parse the host pattern as written in the config and find matching hosts

    :param pattern: pattern to match on one or several domain names
    :param conn: connection with libvirt
    """
    exclude, pattern = _handle_possible_exclusion_host_pattern(pattern)
    if pattern.startswith("r:"):
        pattern = pattern[2:]
        domains = search_domains_regex(pattern, conn)
    elif pattern.startswith("g:"):
        domains = _include_group_domains(pattern)
    else:
        try:
            # will raise libvirt.libvirtError if the domain is not found
            conn.lookupByName(pattern)
            domains = (pattern,)
        except libvirt.libvirtError as e:
            logger.error(e)
            domains = tuple()

    return {"domains": domains, "exclude": exclude}


def domains_matching_with_patterns(domains, patterns):
    include, exclude = set(), set()
    for pattern in patterns:
        for domain in domains:
            pattern_comparaison = is_domain_matching_with(domain, pattern)
            if not pattern_comparaison["matches"]:
                continue
            if pattern_comparaison["exclude"]:
                exclude.add(domain)
            else:
                include.add(domain)
    return include.difference(exclude)


def is_domain_matching_with(domain_name, pattern):
    """
    Parse the host pattern as written in the config and check if the domain
    name matches

    :param domain_name: domain name
    :param pattern: pattern to match on
    :returns: {matches: bool, exclude: bool}
    """
    exclude, pattern = _handle_possible_exclusion_host_pattern(pattern)
    if pattern.startswith("r:"):
        pattern = pattern[2:]
        matches = re.match(pattern, domain_name)
    elif pattern.startswith("g:"):
        # TODO: to implement
        matches = False
    else:
        matches = pattern == domain_name

    return {"matches": matches, "exclude": exclude}


def _handle_possible_exclusion_host_pattern(pattern):
    """
    Check if pattern starts with "!", meaning matching hosts will be excluded

    :returns: exclude, sanitized_pattern
    """
    # if the pattern starts with !, exclude the matching domains
    exclude = pattern.startswith("!")
    if exclude:
        # clean pattern to remove the '!' char
        pattern = pattern[1:]
    return exclude, pattern


def _include_group_domains(pattern):
    pattern = pattern[2:]
    # TODO: option to include another group into this one. It would
    # need to include all domains of this group.
    # domains =
    return []
