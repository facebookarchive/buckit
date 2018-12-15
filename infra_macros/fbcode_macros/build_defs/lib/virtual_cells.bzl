# Reimplement `partial.call()` so that skylark doesn't think we're attempting
# recursion if this gets nested in another `partial.call()` (from a different
# `partial.make()`) (e.g. P60421242).
def _call(partial, *args, **kwargs):
    function_args = partial.args + args
    function_kwargs = dict(partial.kwargs)
    function_kwargs.update(kwargs)
    return partial.function(*function_args, **function_kwargs)

def _translate_target(virtual_cells, target):
    """
    Format a target, represented by a cell name, project name, and rule name,
    into a raw Buck target.
    """

    translator = virtual_cells.get(target.repo)
    if translator != None:
        target = _call(translator, target.base_path, target.name)

    return target

virtual_cells = struct(
    translate_target = _translate_target,
)
