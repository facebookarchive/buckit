load(":image.bzl", "image")

# Return an image feature that masks the specified systemd units
def _mask_units(
        # list of systemd units to mask (e.g. sshd.service)
        units):
    return image.feature(
        features = [
            image.symlink_file("/dev/null", "/etc/systemd/system/" + unit)
            for unit in units
        ],
    )

# Create an image feature that enables a unit in the specified target.
def _enable_unit(
        # The name of the systemd unit to enable.  This should be in the
        # full form of the service, ie:  unit.service, unit.mount, unit.socket, etc..
        unit,

        # The target to enable the unit in.
        target):
    return image.symlink_file(
        "/usr/lib/systemd/system/" + unit,
        "/usr/lib/systemd/system/" + target + ".wants/" + unit,
    )

systemd = struct(
    enable_unit = _enable_unit,
    mask_units = _mask_units,
)
