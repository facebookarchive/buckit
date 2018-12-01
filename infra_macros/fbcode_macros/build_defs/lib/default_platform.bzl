def get_default_platform():
    """ Returns the default fbcode platform to use """
    return native.read_config("fbcode", "default_platform", "default")
