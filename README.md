envmix
=====

Typed environment loader for Pydantic v2 models.

Features
- **Simple**: `from_env()` fills fields from overrides > env vars > defaults
- **Typed**: ships `py.typed`; works nicely with type checkers
- **Robust casting**: JSON-first via TypeAdapter; CSV and k=v fallbacks

Install
```bash
pip install envmix
```

Quick start
```python
from pydantic import BaseModel
from envmix import EnvMixModel

class DB(BaseModel):
    host: str
    port: int

class Settings(EnvMixModel):
    __env_prefix__ = "APP_"
    host: str = "127.0.0.1"
    port: int = 8080
    debug: bool = False

# export APP_PORT=5000 APP_DEBUG=true
s = Settings.from_env()
print(s.port)  # 5000
print(s.debug) # True
```

Custom env key per field
```python
from pydantic import Field

class Settings(EnvMixModel):
    server_host: str = Field("0.0.0.0", json_schema_extra={"env": "SERVER_HOST"})
```

License
MIT
