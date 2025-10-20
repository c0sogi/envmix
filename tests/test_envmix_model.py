import os
import unittest
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from envmix import EnvMixModel


class TestEnvMixModel(unittest.TestCase):
    def test_from_env(self) -> None:
        class DBConfig(BaseModel):
            host: str
            port: int

        class AppConfig(EnvMixModel):
            __env_prefix__ = "APP_"  # Optional prefix for env keys
            host: str = "127.0.0.1"
            port: int = 8080
            debug: bool = False
            tags: list[str] = ["api", "v1"]
            size: tuple[int, int] = (640, 480)  # CSV or JSON
            limits: tuple[int, int] = (10, 100)  # JSON also supported
            matrix: list[list[int]] = [[0, 0]]  # requires JSON
            meta: dict[str, int] = {}  # "k=v,k=v" or JSON
            keys: set[str] = set()  # CSV or JSON
            mode: Literal["dev", "prod"] = "dev"  # JSON("prod") or raw "prod"
            db: DBConfig = DBConfig(host="localhost", port=5432)  # requires JSON
            log_path: Optional[Path] = None
            server_host: str = Field("0.0.0.0", json_schema_extra={"env": "SERVER_HOST"})  # custom env name

        # ---- Env var injection (sample) ----
        os.environ["APP_PORT"] = "5000"  # int
        os.environ["APP_DEBUG"] = "true"  # bool truthy
        os.environ["APP_TAGS"] = "api,v1,test"  # list[str] CSV
        os.environ["APP_SIZE"] = "800,600"  # tuple[int,int] CSV
        os.environ["APP_LIMITS"] = "[100, 200]"  # tuple[int,int] JSON
        os.environ["APP_MATRIX"] = "[[1,2],[3,4]]"  # list[list[int]] JSON
        os.environ["APP_META"] = "a=1,b=2"  # dict[str,int] k=v CSV
        os.environ["APP_KEYS"] = "alpha,beta,alpha"  # set[str] CSV (dedupe)
        os.environ["APP_MODE"] = "prod"  # Literal (원문)
        os.environ["APP_DB"] = '{"host":"db.local","port":15432}'  # nested BaseModel JSON
        os.environ["APP_LOG_PATH"] = '"/var/log/app.log"'  # JSON string (with quotes)
        os.environ["APP_SERVER_HOST"] = "10.0.0.1"  # custom env name

        print("\n--- from_env() output ---")
        cfg = AppConfig.from_env()
        print(cfg)
        print(cfg.model_dump())

        # Type checks (quick assertions)
        assert cfg.port == 5000
        assert cfg.debug is True
        assert cfg.tags == ["api", "v1", "test"]
        assert cfg.size == (800, 600)
        assert cfg.limits == (100, 200)
        assert cfg.matrix == [[1, 2], [3, 4]]
        assert cfg.meta == {"a": 1, "b": 2}
        assert cfg.keys == {"alpha", "beta"}
        assert cfg.mode == "prod"
        assert cfg.db.host == "db.local" and cfg.db.port == 15432
        assert str(cfg.log_path) == str(Path("/var/log/app.log"))
        assert cfg.server_host == "10.0.0.1"

        # overrides take precedence over env
        print("\n--- override precedence (port=9000) ---")
        cfg2 = AppConfig.from_env(port=9000)
        print(cfg2.port)  # 9000
        assert cfg2.port == 9000

        print("\n✅ ALL TESTS PASSED")


if __name__ == "__main__":
    unittest.main()
