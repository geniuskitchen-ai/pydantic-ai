from __future__ import annotations as _annotations

from abc import ABC, ABCMeta, abstractmethod
from dataclasses import dataclass
from functools import cache
from typing import Any, ClassVar, Generic, get_args, get_origin, get_type_hints

from typing_extensions import TypeVar

from . import _utils
from .state import StateT

__all__ = (
    'NodeInputT',
    'GraphOutputT',
    'GraphContext',
    'End',
    'BaseNode',
    'NodeDef',
)

NodeInputT = TypeVar('NodeInputT', default=Any)
GraphOutputT = TypeVar('GraphOutputT', default=Any)


# noinspection PyTypeHints
@dataclass
class GraphContext(Generic[StateT]):
    """Context for a graph."""

    state: StateT


# noinspection PyTypeHints
class End(ABC, Generic[NodeInputT]):
    """Type to return from a node to signal the end of the graph."""

    __slots__ = ('data',)

    def __init__(self, input_data: NodeInputT) -> None:
        self.data = input_data


class _BaseNodeMeta(ABCMeta):
    def __repr__(cls):
        base: Any = cls.__orig_bases__[0]  # type: ignore
        args = get_args(base)
        if len(args) == 3 and args[2] is Any:
            if args[1] is Any:
                args = args[:1]
            else:
                args = args[:2]
        args = ', '.join(_utils.type_arg_name(a) for a in args)
        return f'{cls.__name__}({base.__name__}[{args}])'


# noinspection PyTypeHints
class BaseNode(Generic[StateT, NodeInputT, GraphOutputT], metaclass=_BaseNodeMeta):
    """Base class for a node."""

    node_id: ClassVar[str | None] = None
    __slots__ = ('input_data',)

    def __init__(self, input_data: NodeInputT) -> None:
        self.input_data = input_data

    @abstractmethod
    async def run(self, ctx: GraphContext[StateT]) -> BaseNode[StateT, Any, Any] | End[GraphOutputT]: ...

    @classmethod
    @cache
    def get_id(cls) -> str:
        return cls.node_id or cls.__name__

    @classmethod
    def get_node_def(cls, local_ns: dict[str, Any] | None) -> NodeDef[StateT, Any, Any]:
        type_hints = get_type_hints(cls.run, localns=local_ns)
        next_node_ids: set[str] = set()
        can_end: bool = False
        dest_any: bool = False
        for return_type in _utils.get_union_args(type_hints['return']):
            return_type_origin = get_origin(return_type) or return_type
            if return_type_origin is BaseNode:
                dest_any = True
            elif issubclass(return_type_origin, BaseNode):
                next_node_ids.add(return_type.get_id())
            elif return_type_origin is End:
                can_end = True
            else:
                raise TypeError(f'Invalid return type: {return_type}')

        return NodeDef(
            cls,
            cls.get_id(),
            next_node_ids,
            can_end,
            dest_any,
        )


# noinspection PyTypeHints
@dataclass
class NodeDef(ABC, Generic[StateT, NodeInputT, GraphOutputT]):
    """Definition of a node.

    Used by [`Graph`][pydantic_ai_graph.graph.Graph] store information about a node.
    """

    node: type[BaseNode[StateT, NodeInputT, GraphOutputT]]
    node_id: str
    next_node_ids: set[str]
    can_end: bool
    dest_any: bool
