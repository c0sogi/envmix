import os
from typing import Any, ClassVar, TypeVar, Union, get_args, get_origin

from pydantic import BaseModel, TypeAdapter

_truthy = {"1", "true", "yes", "on", "y", "t"}
_falsy = {"0", "false", "no", "off", "n", "f"}

T = TypeVar("T", bound="EnvMixModel")


class EnvMixModel(BaseModel):
    """
    A Pydantic v2 model mixin that populates fields from environment variables.

    Resolution order in `from_env()`:
    1) explicit keyword overrides
    2) matching environment variables (UPPERCASE field name) or with class `__env_prefix__`
    3) model defaults / validation rules

    Casting strategy uses Pydantic TypeAdapter for broad compatibility:
    - First, try JSON decoding when the env value looks like JSON
    - Otherwise, apply pragmatic fallbacks: truthy/falsey for bool, CSV for lists/sets,
      "k=v,k=v" for dicts, and tuple CSV mapping
    - Finally, defer to `validate_python` for types like Enum/Path/date-time
    """

    __env_prefix__: ClassVar[str] = ""  # Optional: e.g. "APP_"

    @classmethod
    def from_env(cls: type[T], **overrides: object) -> T:
        vals: dict[str, object] = {}

        fields = cls.model_fields
        for name, finfo in fields.items():
            # 1) explicit overrides take precedence
            if name in overrides:
                vals[name] = overrides[name]
                continue

            # 2) decide env var key (Field.json_schema_extra["env"] can override)
            env_name = name
            extra = finfo.json_schema_extra
            if isinstance(extra, dict):
                custom = extra.get("env")
                if isinstance(custom, str) and custom:
                    env_name = custom

            env_key = (cls.__env_prefix__ + env_name).upper()
            if env_key in os.environ:
                ann = finfo.annotation or str
                vals[name] = _cast(os.environ[env_key], ann)

        # Remaining fields are handled by Pydantic defaults/validation
        known_overrides = {k: v for k, v in overrides.items() if k in fields}
        return cls(**(vals | known_overrides))


def _strip_optional(tp: object) -> tuple[object, bool]:
    """Return inner type and flag if Optional[T] (Union[T, None]) was unwrapped."""
    origin = get_origin(tp)
    if origin is Union:
        args = [a for a in get_args(tp) if a is not type(None)]  # noqa: E721
        if len(args) == 1:
            return args[0], True
    return tp, False


def _try_typeadapter_json(value: str, tp: object) -> Any:
    """Attempt JSON parsing via TypeAdapter first."""
    adapter = TypeAdapter(tp)
    return adapter.validate_json(value)


def _try_typeadapter_python(value: Any, tp: object) -> Any:
    """Validate as Python value via TypeAdapter (e.g., str -> target type)."""
    adapter = TypeAdapter(tp)
    return adapter.validate_python(value)


def _cast(value: str, tp: object) -> object:
    """
    Cast an environment string to the annotated field type.
    1) Prefer JSON via TypeAdapter
    2) If not JSON, apply idiomatic fallbacks (bool/int/float/CSV/dict k=v, etc.)
    3) Finally, delegate to TypeAdapter.validate_python
    """
    tp, _ = _strip_optional(tp)
    origin = get_origin(tp)

    # 1) Prefer JSON for nested models/collections/Enum/datetime, etc.
    try:
        return _try_typeadapter_json(value, tp)
    except Exception:
        pass

    # 2) Idiomatic fallbacks for non-JSON plain strings
    # 2-1) bool
    if tp is bool:
        v = value.strip().lower()
        if v in _truthy:
            return True
        if v in _falsy:
            return False
        # Numeric and other strings: best-effort handling
        return bool(int(v)) if v.isdigit() else bool(v)

    # 2-2) Scalars
    if tp is int:
        return int(value)
    if tp is float:
        return float(value)
    if tp is str:
        return value

    # 2-3) Collections: CSV helper
    if origin in (list, tuple, set):
        args = list(get_args(tp))
        # Fixed-length tuple: e.g., tuple[int, int, str]
        parts = [p.strip() for p in value.split(",") if p.strip() != ""]
        if origin is tuple and args and len(args) > 1:
            # Map by position; if lengths differ, use last type for remaining
            casted = [_cast(parts[i], args[i] if i < len(args) else args[-1]) for i in range(len(parts))]
            return tuple(casted)
        # Single-arg generics (list[T], tuple[T], set[T])
        inner = args[0] if args else str
        items = [_cast(p, inner) for p in parts]
        return origin(items)

    # 2-4) dict[str, T]: support "k=v,k=v"
    if origin is dict:
        k_t, v_t = get_args(tp) or (str, str)

        def parse_pair(p: str) -> tuple[object, object]:
            k, v = p.split("=", 1)
            return _cast(k.strip(), k_t), _cast(v.strip(), v_t)

        pairs = [parse_pair(p) for p in value.split(",") if "=" in p]
        return {k: v for k, v in pairs}

    # 3) Last resort: let TypeAdapter validate (Enum/Path, etc.)
    try:
        return _try_typeadapter_python(value, tp)
    except Exception:
        # If it still fails, return raw string; Pydantic will raise on validation
        return value
