"""Per-iteration pipelines.

Each iteration is its own self-contained LangGraph app (iter1 / iter2 / iter3), built from
the shared parameterized helpers in ``common``. ``get_workflow(iteration)`` returns the
compiled chain for an iteration, building it once and caching it.
"""
from backend.iterations import iter1, iter2, iter3

_BUILDERS = {1: iter1.build_graph, 2: iter2.build_graph, 3: iter3.build_graph}
_WORKFLOWS = {}


def get_workflow(iteration: int):
    """Return the compiled LangGraph chain for the given iteration (built once, then cached)."""
    if iteration not in _BUILDERS:
        raise ValueError(f"iteration must be 1, 2, or 3 (got {iteration})")
    if iteration not in _WORKFLOWS:
        _WORKFLOWS[iteration] = _BUILDERS[iteration]()
    return _WORKFLOWS[iteration]
