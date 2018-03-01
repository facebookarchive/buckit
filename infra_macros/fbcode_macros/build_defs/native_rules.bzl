"""
Wrappers to native buck rules.

These generally are only allowed to be used by certain pre-configured targets
"""

load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:python_typing.bzl",
     "get_typing_config_target", "gen_typing_config")

_FBCODE_UI_MESSAGE = (
    'Unsupported access to Buck rules! ' +
    'Please use supported fbcode rules (https://fburl.com/fbcode-targets) ' +
    'instead.')

def _verify_whitelisted_rule(rule_type, package_name, target_name):
    """
    Verifies that a rule is whitelisted to use native rules. If not, fail
    """
    if config.get_forbid_raw_buck_rules():
        whitelist = config.get_whitelisted_raw_buck_rules().get(rule_type, {})
        if (package_name, target_name) not in whitelist:
            fail(
                "{}\n{}(): native rule {}:{} is not whitelisted".format(
                    _FBCODE_UI_MESSAGE, rule_type, package_name, target_name))

def buck_command_alias(*args, **kwargs):
    """ Wrapper to access Buck's native command_alias rule """
    native.command_alias(*args, **kwargs)

def cxx_genrule(*args, **kwargs):
    """ Wrapper to access Buck's native cxx_genrule rule """
    native.cxx_genrule(*args, **kwargs)

def buck_genrule(*args, **kwargs):
    """ Wrapper to access Buck's native genrule rule """
    native.genrule(*args, **kwargs)

def buck_python_binary(*args, **kwargs):
    """ Wrapper to access Buck's native python_binary rule """
    native.python_binary(*args, **kwargs)

def buck_python_library(name, *args, **kwargs):
    """ Wrapper to access Buck's native python_library rule """
    if get_typing_config_target():
        gen_typing_config(name)
    native.python_library(name=name, *args, **kwargs)

def remote_file(*args, **kwargs):
    """ Wrapper to access Buck's native remote_file rule """
    native.remote_file(*args, **kwargs)

def buck_sh_binary(*args, **kwargs):
    """ Wrapper to access Buck's native sh_binary rule """
    native.sh_binary(*args, **kwargs)

def buck_sh_test(*args, **kwargs):
    """ Wrapper to access Buck's native sh_test rule """
    native.sh_test(*args, **kwargs)

def versioned_alias(*args, **kwargs):
    """ Wrapper to access Buck's native versioned_alias rule """
    native.versioned_alias(*args, **kwargs)

def buck_cxx_binary(name, **kwargs):
    """ Wrapper to access Buck's native cxx_binary rule """
    _verify_whitelisted_rule('cxx_binary', native.package_name(), name)
    native.cxx_binary(name=name, **kwargs)

def buck_cxx_library(name, **kwargs):
    """ Wrapper to access Buck's native cxx_library rule """
    _verify_whitelisted_rule('cxx_library', native.package_name(), name)
    native.cxx_library(name=name, **kwargs)

def buck_cxx_test(name, **kwargs):
    """ Wrapper to access Buck's native cxx_test rule """
    _verify_whitelisted_rule('cxx_test', native.package_name(), name)
    native.cxx_test(name=name, **kwargs)
