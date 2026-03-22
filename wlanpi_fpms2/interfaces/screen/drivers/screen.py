"""Abstract base class for OLED display drivers."""

from abc import ABC, abstractmethod


class AbstractScreen(ABC):
    @abstractmethod
    def init(self) -> bool:
        pass

    @abstractmethod
    def drawImage(self, image) -> None:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass

    @abstractmethod
    def sleep(self) -> None:
        pass

    @abstractmethod
    def wakeup(self) -> None:
        pass
