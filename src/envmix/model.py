import os
from pathlib import Path
from typing import (
    IO,
    Any,
    ClassVar,
    Self,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

from dotenv import load_dotenv
from pydantic import BaseModel, TypeAdapter

_truthy = {"1", "true", "yes", "on", "y", "t"}
_falsy = {"0", "false", "no", "off", "n", "f"}

T = TypeVar("T")


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
    __env_registry__: ClassVar[set[Type[Self]]] = set()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Automatically register subclass to registry when created"""
        super().__init_subclass__(**kwargs)
        abstract_methods = getattr(cls, "__abstractmethods__", None)
        if abstract_methods is None or len(abstract_methods) == 0:
            cls.__env_registry__.add(cls)

    @classmethod
    def from_env(cls, **overrides: object) -> Self:
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
                prefix: bool = bool(extra.get("prefix", True))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                custom = extra.get("env")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                if isinstance(custom, str) and custom:
                    env_name = custom
            else:
                prefix = True

            env_key = ((cls.__env_prefix__ if prefix else "") + env_name).upper()
            if env_key in os.environ:
                ann = finfo.annotation or str
                vals[name] = _cast(os.environ[env_key], ann)

        # Remaining fields are handled by Pydantic defaults/validation
        known_overrides = {k: v for k, v in overrides.items() if k in fields}
        return cls(**(vals | known_overrides))

    @classmethod
    def from_dotenv(
        cls,
        dotenv_path: str | Path | None = None,
        stream: IO[str] | None = None,
        verbose: bool = False,
        override: bool = False,
        interpolate: bool = True,
        encoding: str | None = "utf-8",
        **overrides: object,
    ) -> Self:
        """
        Load configuration from a .env file using python-dotenv.

        Args:
            dotenv_path: Path to the .env file (default: ".env")
            stream: Stream to read the .env file from (default: None)
            verbose: If True, print verbose output (default: False)
            override: If True, override existing environment variables with values from .env file
            interpolate: If True, interpolate the .env file (default: True)
            encoding: Encoding to use for the .env file (default: "utf-8")
            **overrides: Explicit keyword arguments that take highest precedence

        Returns:
            Instance of the model populated from .env file and environment variables

        Resolution order:
        1) explicit keyword overrides
        2) values from .env file (if override=True, or if not already in os.environ)
        3) existing environment variables
        4) model defaults / validation rules
        """
        load_dotenv(
            dotenv_path=dotenv_path,
            stream=stream,
            verbose=verbose,
            override=override,
            interpolate=interpolate,
            encoding=encoding,
        )

        return cls.from_env(**overrides)


def get_registered_models() -> dict[Type[EnvMixModel], dict[str, str]]:
    return {
        model_cls: {
            field_name: _get_env_var_name(model_cls, field_name, finfo)
            for field_name, finfo in model_cls.model_fields.items()
        }
        for model_cls in list(EnvMixModel.__env_registry__)
    }


def get_registered_envs() -> dict[str, set[tuple[Type[EnvMixModel], str]]]:
    env_var_map: dict[str, set[tuple[Type[EnvMixModel], str]]] = {}
    for model_cls, info in get_registered_models().items():
        for field_name, env_var_name in info.items():
            if env_var_name not in env_var_map:
                env_var_map[env_var_name] = set()
            env_var_map[env_var_name].add((model_cls, field_name))
    return env_var_map


def _strip_optional(tp: type) -> tuple[type, bool]:
    """Return inner type and flag if Optional[T] (Union[T, None]) was unwrapped."""
    origin = get_origin(tp)
    if origin is Union:
        args = [a for a in get_args(tp) if a is not type(None)]  # noqa: E721
        if len(args) == 1:
            return args[0], True
    return tp, False


def _try_typeadapter_json(value: str, tp: Type[T]) -> T:
    """Attempt JSON parsing via TypeAdapter first."""
    adapter = TypeAdapter(tp)
    return adapter.validate_json(value)


def _try_typeadapter_python(value: Any, tp: Type[T]) -> T:
    """Validate as Python value via TypeAdapter (e.g., str -> target type)."""
    adapter = TypeAdapter(tp)
    return adapter.validate_python(value)


def _cast(value: str, tp: Type[T]) -> object:
    """
    Cast an environment string to the annotated field type.
    1) Prefer JSON via TypeAdapter
    2) If not JSON, apply idiomatic fallbacks (bool/int/float/CSV/dict k=v, etc.)
    3) Finally, delegate to TypeAdapter.validate_python
    """
    tp_no_optional, _ = _strip_optional(tp)
    origin = get_origin(tp_no_optional)

    # 1) Prefer JSON for nested models/collections/Enum/datetime, etc.
    try:
        return _try_typeadapter_json(value, tp_no_optional)  # pyright: ignore[reportUnknownVariableType]
    except Exception:
        pass

    # 2) Idiomatic fallbacks for non-JSON plain strings
    # 2-1) bool
    if tp_no_optional is bool:
        v = value.strip().lower()
        if v in _truthy:
            return True
        if v in _falsy:
            return False
        # Numeric and other strings: best-effort handling
        return bool(int(v)) if v.isdigit() else bool(v)

    # 2-2) Scalars
    if tp_no_optional is int:
        return int(value)
    if tp_no_optional is float:
        return float(value)
    if tp_no_optional is str:
        return value

    # 2-3) Collections: CSV helper
    if origin in (list, tuple, set):
        args = list(get_args(tp_no_optional))
        # Fixed-length tuple: e.g., tuple[int, int, str]
        parts = [p.strip() for p in value.split(",") if p.strip() != ""]
        if origin is tuple and args and len(args) > 1:
            # Map by position; if lengths differ, use last type for remaining
            casted = [
                _cast(parts[i], args[i] if i < len(args) else args[-1])
                for i in range(len(parts))
            ]
            return tuple(casted)
        # Single-arg generics (list[T], tuple[T], set[T])
        inner: type = args[0] if args else str
        return origin([_cast(p, inner) for p in parts])  # pyright: ignore[reportUnknownVariableType]

    # 2-4) dict[str, T]: support "k=v,k=v"
    if origin is dict:
        k_t, v_t = get_args(tp_no_optional) or (str, str)

        def parse_pair(p: str) -> tuple[object, object]:
            k, v = p.split("=", 1)
            return _cast(k.strip(), k_t), _cast(v.strip(), v_t)

        pairs = [parse_pair(p) for p in value.split(",") if "=" in p]
        return {k: v for k, v in pairs}

    # 3) Last resort: let TypeAdapter validate (Enum/Path, etc.)
    try:
        return _try_typeadapter_python(value, tp_no_optional)  # pyright: ignore[reportUnknownVariableType]
    except Exception:
        # If it still fails, return raw string; Pydantic will raise on validation
        return value


def _get_env_var_name(cls: Type[EnvMixModel], field_name: str, finfo: Any) -> str:
    """Helper function to determine environment variable name for a field"""
    env_name = field_name
    extra = finfo.json_schema_extra
    if isinstance(extra, dict):
        prefix: bool = bool(extra.get("prefix", True))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
        custom = extra.get("env")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if isinstance(custom, str) and custom:
            env_name = custom
    else:
        prefix = True

    env_key = ((cls.__env_prefix__ if prefix else "") + env_name).upper()
    return env_key
