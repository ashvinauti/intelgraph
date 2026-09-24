import importlib
import inspect
import pkgutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class Plugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...


class PluginLoader:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    @property
    def plugins(self) -> dict[str, Plugin]:
        return dict(self._plugins)

    def discover(self, *paths: str | Path) -> None:
        for path in paths:
            path = Path(path)
            if not path.is_dir():
                continue
            self._load_from_directory(path)

    def load(self, module_name: str) -> None:
        try:
            module = importlib.import_module(module_name)
            self._register_from_module(module)
        except ImportError as e:
            logger.warning("failed to load plugin module", module=module_name, error=str(e))

    def _load_from_directory(self, path: Path) -> None:
        for _importer, name, _is_pkg in pkgutil.iter_modules([str(path)]):
            try:
                spec = importlib.util.spec_from_file_location(name, str(path / f"{name}.py"))
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._register_from_module(module)
            except Exception as e:
                logger.warning("failed to load plugin", name=name, error=str(e))

    def _register_from_module(self, module: object) -> None:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Plugin) and obj is not Plugin and not inspect.isabstract(obj):
                instance = obj()
                self._plugins[instance.name] = instance
                logger.debug("plugin registered", name=instance.name)

    def initialize_all(self, config: dict[str, Any]) -> None:
        for name, plugin in self._plugins.items():
            try:
                plugin.initialize(config)
                logger.debug("plugin initialized", name=name)
            except Exception as e:
                logger.warning("plugin initialization failed", name=name, error=str(e))

    def shutdown_all(self) -> None:
        for name, plugin in self._plugins.items():
            try:
                plugin.shutdown()
                logger.debug("plugin shut down", name=name)
            except Exception as e:
                logger.warning("plugin shutdown failed", name=name, error=str(e))
