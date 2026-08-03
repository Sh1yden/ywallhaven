import json
from pathlib import Path

from pydantic import ValidationError

from app.core import LoggerMixin, setup_logging
from app.schemas import ConfigSchema


class Config(LoggerMixin):
    def __init__(self, log_lvl: str) -> None:
        self._path = Path("config.json")

        self._mode = "dev"
        self._log_lvl = log_lvl

        if self._path.exists():
            raw = self.load(self._path)
            self._mode = raw.get("MODE", "dev")
            self._log_lvl = raw.get("LOG_LVL", "DEBUG")

        setup_logging(level=self._log_lvl, console=(self._mode == "dev"))

        super().__init__()

        self.data: ConfigSchema = self._load_or_create()

    # Start class method
    def _load_or_create(self) -> ConfigSchema:
        # IF File not found
        if not self._path.exists():
            self._lg.warning("Config not found. Trying to create defult config...")
            default_config = ConfigSchema()
            self.save(self._path, default_config)
            self._lg.debug("Success ;)")
            return default_config

        # IF File found
        try:
            raw_dict = self.load(self._path)
            return ConfigSchema(**raw_dict)
        except (json.JSONDecodeError, ValidationError) as e:
            self._lg.warning(f"Config corrupted ({e}). Recreating default...")
            default_config = ConfigSchema()
            self.save(self._path, default_config)
            self._lg.debug("Success ;)")
            return default_config
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
