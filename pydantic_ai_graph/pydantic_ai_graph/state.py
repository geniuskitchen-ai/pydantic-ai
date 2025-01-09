from __future__ import annotations as _annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Generic, Literal, Self, Union

from typing_extensions import Never, TypeVar

from . import _utils

__all__ = 'AbstractState', 'StateT', 'NextNodeEvent', 'EndEvent', 'InterruptEvent', 'HistoryStep'

if TYPE_CHECKING:
    from pydantic_ai_graph import BaseNode
    from pydantic_ai_graph.nodes import End, RunInterrupt


class AbstractState(ABC):
    """Abstract class for a state object."""

    @abstractmethod
    def serialize(self) -> bytes | None:
        """Serialize the state object."""
        raise NotImplementedError

    def deep_copy(self) -> Self:
        """Create a deep copy of the state object."""
        return copy.deepcopy(self)


RunEndT = TypeVar('RunEndT', default=None)
NodeRunEndT = TypeVar('NodeRunEndT', covariant=True, default=Never)
StateT = TypeVar('StateT', bound=Union[None, AbstractState], default=None)


@dataclass
class NextNodeEvent(Generic[StateT, RunEndT]):
    """History step describing the execution of a step of a graph."""

    state: StateT
    node: BaseNode[StateT, RunEndT]
    start_ts: datetime = field(default_factory=_utils.now_utc)
    duration: float | None = None

    kind: Literal['step'] = 'step'

    def __post_init__(self):
        # Copy the state to prevent it from being modified by other code
        self.state = _deep_copy_state(self.state)

    def node_summary(self) -> str:
        return str(self.node)


@dataclass
class InterruptEvent(Generic[StateT]):
    """History step describing the interruption of a graph run."""

    state: StateT
    result: RunInterrupt[StateT]
    ts: datetime = field(default_factory=_utils.now_utc)

    kind: Literal['interrupt'] = 'interrupt'

    def __post_init__(self):
        # Copy the state to prevent it from being modified by other code
        self.state = _deep_copy_state(self.state)

    def node_summary(self) -> str:
        return str(self.result)


@dataclass
class EndEvent(Generic[StateT, RunEndT]):
    """History step describing the end of a graph run."""

    state: StateT
    result: End[RunEndT]
    ts: datetime = field(default_factory=_utils.now_utc)

    kind: Literal['end'] = 'end'

    def __post_init__(self):
        # Copy the state to prevent it from being modified by other code
        self.state = _deep_copy_state(self.state)

    def node_summary(self) -> str:
        return str(self.result)


def _deep_copy_state(state: StateT) -> StateT:
    if state is None:
        return None  # pyright: ignore[reportReturnType]
    else:
        return state.deep_copy()


HistoryStep = Union[NextNodeEvent[StateT, RunEndT], InterruptEvent[StateT], EndEvent[StateT, RunEndT]]
