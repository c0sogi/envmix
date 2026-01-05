# envmix

Typed environment loader for Pydantic v2 models.

## Install
```bash
pip install envmix
```
## Usage
1. Import `EnvMixModel` from the envmix package.
2. Define a model that extends `EnvMixModel`.
3. Instantiate the model with either `.from_dotenv()` or `.from_env()` factory methods.

### Quick start
```python
from pydantic import BaseModel
from envmix import EnvMixModel

class Settings(EnvMixModel):
    __env_prefix__ = "APP_"
    host: str = "127.0.0.1"  # APP_HOST
    port: int = 8000  # APP_PORT
    debug: bool = False  # APP_DEBUG

# export APP_PORT=5000 APP_DEBUG=true
s = Settings.from_dotenv()  # or Settings.from_env() to ignore .env file
print(s.host)  # 127.0.0.1
print(s.port)  # 5000
print(s.debug) # True
```

### Custom env key per field
```python
from pydantic import Field
from envmix import EnvMixModel

class Settings(EnvMixModel):
    __env_prefix__ = "APP_"
    host: str = Field("127.0.0.1", json_schema_extra={"env": "SERVER_HOST"})  # APP_SERVER_HOST
    port: int = Field(8000, json_schema_extra={"prefix": False})  # PORT
    debug: bool = Field(False, json_schema_extra={"env": "TEST", "prefix": False})  # TEST

# export APP_SERVER_HOST=0.0.0.0 PORT=3000 TEST=true
s = Settings.from_dotenv()  # or Settings.from_env() to ignore .env file
print(s.host)  # 0.0.0.0
print(s.port)  # 3000
print(s.debug)  # True
```


### License
MIT
