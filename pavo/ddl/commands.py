from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Optional, Any


@dataclass  # type: ignore
class CommandInterface(ABC):
    """Interface for a command that can be registered to the CommandManager.

    Attributes:
        name: The name of the command, also used as the name of the command that is called.
        help: The help text for the command.
        allow_outside_project: Whether the command can be called from outside a project.
    """

    name: str
    help: str
    allow_outside_project: bool

    @abstractmethod
    def run(self, args: Optional[list] = None) -> None:
        """Contains the actual logic of the command that is called.

        Args:
            args: List of arguments that might be useful to the logic inside the function.
        """
        ...


@dataclass  # type: ignore
class CommandManagerInterface(ABC):
    registered_commands: dict[str, CommandInterface] = field(default_factory=dict)

    @abstractmethod
    def register(self, command: CommandInterface) -> bool:
        ...

    @abstractmethod
    def execute(self, command_name: str, *args: Any) -> None:
        ...


# For reasons why types of the dataclass are being ignored, see: https://github.com/python/mypy/issues/5374
