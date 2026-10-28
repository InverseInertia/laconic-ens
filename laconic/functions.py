"""The function registry: every built-in function, declared once.

A built-in is an `Evaluator` method named `fn_<name>`, marked with `@builtin(...)`, which gives
it its signature (shown next to it in the editor's suggestions) and, when it typesets specially,
its LaTeX form. The evaluator calls built-ins through `FUNCTIONS`, the suggestions and Rename's
reserved names list it, and the LaTeX printer reads each one's form from it. Adding a built-in
is one decorated method.

A LaTeX form is a format string over the arguments: `{0}` is the first argument as printed;
`{0:atom}` (or `add`, `mul`, `neg`, `pow`) puts it in parentheses unless it binds at least that
tightly. `binds` is how tightly the whole form binds, by the same names. A form with `args`
applies only to a call with that many arguments; any other call, and a built-in without a form,
prints as `\\mathrm{name}(...)`.

`FUNCTIONS` is filled as evaluator.py is read, so read it after importing the evaluator."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Builtin:
    name: str
    impl: object            # the Evaluator method: impl(evaluator, *args)
    signature: str          # shown next to the name in suggestions
    tex: str = None         # its LaTeX form, when it has a special one
    binds: str = "atom"     # how tightly that form binds
    args: int = None        # the number of arguments the form is for, when it is for only one


FUNCTIONS = {}   # name -> Builtin, in the order they are declared


def builtin(signature=None, tex=None, binds="atom", args=None, aliases=()):
    """Declare the `fn_<name>` method below as the built-in `name`. `aliases` are other names
    for the same function, each with the signature and form spelled with its own name."""
    def declare(method):
        name = method.__name__.removeprefix("fn_")
        for n in (name, *aliases):
            sig = (signature or name).replace(name + "(", n + "(", 1)
            FUNCTIONS[n] = Builtin(n, method, sig, tex, binds, args)
        return method
    return declare
