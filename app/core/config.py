import json
from pathlib import Path

from pydantic import ValidationError

from app.core import LoggerMixin, setup_logging
from app.schemas import ConfigSchema


class Config(LoggerMixin):
    def __init__(self, log_lvl: str) -> None:
        super().__init__()
        setup_logging(log_lvl)

        self._path = Path("config.json")
        self.data: ConfigSchema = self._load_or_create()

    # Start class method
    def _load_or_create(self) -> ConfigSchema:
        # IF File not found
        if not self._path.exists():
            self._lg.warn("Config not found. Trying to create defult config...")
            default_config = ConfigSchema()
            self.save(self._path, default_config)
            self._lg.debug("Success ;)")
            return default_config

        # IF File found
        try:
            raw_dict = self.load(self._path)
            return ConfigSchema(**raw_dict)
        except (json.JSONDecodeError, ValidationError) as e:
            self._lg.warn(f"Config corrupted ({e}). Recreating default...")
            default_config = ConfigSchema()
            self.save(self._path, default_config)
            return default_config
            self._lg.debug("Success ;)")
        except Exception as e:
            self._lg.critical(f"Internal error: {e}.")
            raise e

    # Read / Save
    def load(self, path: Path | str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, path: Path | str, config_obj: ConfigSchema | None = None) -> bool:
        to_save = config_obj or self.data
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(to_save.model_dump_json(indent=4))
                return True
        except Exception as e:
            self._lg.critical(f"Failed to save config: {e}.")
            return False


config = Config("DEBUG")
