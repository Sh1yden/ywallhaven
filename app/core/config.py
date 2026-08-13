"""Application config manager: load, validate and persist config.json."""

import json
from pathlib import Path

from pydantic import ValidationError

from app.core import LoggerMixin, setup_logging
from app.schemas import ConfigSchema


class Config(LoggerMixin):
    """Application configuration manager.

    Loads config.json on startup, creates a default one when the file
    is missing or corrupted, and exposes the validated data.
    """

    def __init__(self, mode: str) -> None:
        self._path = Path("config.json")

        self._mode = mode
        self._log_lvl = "DEBUG" if mode == "dev" else "WARN"

        if self._path.exists():
            raw = self.load(self._path)
            self._mode = raw.get("MODE", "dev")
            self._log_lvl = raw.get("LOG_LVL", "DEBUG")

        setup_logging(level=self._log_lvl, console=(self._mode == "dev"))

        super().__init__()

        self.data: ConfigSchema = self._load_or_create()

    # Loading and validation
    def _load_or_create(self) -> ConfigSchema:
        # File not found
        if not self._path.exists():
            self._lg.warning("Config not found. Trying to create defult config...")
            default_config = ConfigSchema()
            self.save(self._path, default_config)
            self._lg.debug("Success ;)")
            return default_config

        # File found
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

    # Read / save
    def load(self, path: Path | str) -> dict:
        """Read raw JSON content from a file.

        Args:
            path: Path to the JSON file.

        Returns:
            Parsed JSON content as a dict.
        """
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(
        self,
        path: Path | str | None = None,
        config_obj: ConfigSchema | None = None,
    ) -> bool:
        """Persist a config object to a file.

        Args:
            path: Path to the JSON file; falls back to self._path.
            config_obj: Config to save; falls back to self.data.

        Returns:
            True on success, False otherwise.
        """
        to_save = config_obj or self.data
        target = path or self._path
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(to_save.model_dump_json(indent=4))
                return True
        except Exception as e:
            self._lg.critical(f"Failed to save config: {e}.")
            return False


config = Config("dev")
