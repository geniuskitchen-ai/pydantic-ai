from __future__ import annotations as _annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Concatenate, Generic, ParamSpec, Self, TypeVar, cast

from pydantic import ValidationError
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import SchemaValidator

from . import _pydantic, _utils, messages

AgentContext = TypeVar('AgentContext')
# retrieval function parameters
P = ParamSpec('P')


@dataclass
class CallInfo(Generic[AgentContext]):
    """Information about the current call."""

    context: AgentContext
    # do we allow retries within functions?
    retry: int


# Usage `RetrieverFunc[AgentContext, P]`
RetrieverFunc = Callable[Concatenate[CallInfo[AgentContext], P], str | Awaitable[str]]


@dataclass
class Retriever(Generic[AgentContext, P]):
    """A retriever function for an agent."""

    name: str
    description: str
    function: RetrieverFunc[AgentContext, P]
    is_async: bool
    takes_info: bool
    single_arg_name: str | None
    positional_fields: list[str]
    var_positional_field: str | None
    validator: SchemaValidator
    json_schema: JsonSchemaValue
    max_retries: int
    _current_retry: int = 0

    @classmethod
    def build(cls, function: RetrieverFunc[AgentContext, P], retries: int) -> Self:
        """Build a Retriever dataclass from a function."""
        f = _pydantic.function_schema(function)
        return cls(
            name=function.__name__,
            description=f['description'],
            function=function,
            is_async=inspect.iscoroutinefunction(function),
            takes_info=f['takes_info'],
            single_arg_name=f['single_arg_name'],
            positional_fields=f['positional_fields'],
            var_positional_field=f['var_positional_field'],
            validator=f['validator'],
            json_schema=f['json_schema'],
            max_retries=retries,
        )

    def reset(self) -> None:
        """Reset the current retry count."""
        self._current_retry = 0

    async def run(self, context: AgentContext, message: messages.FunctionCall) -> messages.Message:
        """Run the retriever function asynchronously."""
        try:
            args_dict = self.validator.validate_json(message.arguments)
        except ValidationError as e:
            self._current_retry += 1
            if self._current_retry > self.max_retries:
                # TODO custom error
                raise
            else:
                return messages.FunctionValidationError(
                    function_id=message.function_id,
                    function_name=message.function_name,
                    errors=e.errors(),
                )

        args, kwargs = self._call_args(context, args_dict)
        if self.is_async:
            response_content = await self.function(*args, **kwargs)  # type: ignore[reportCallIssue]
        else:
            response_content = await _utils.run_in_executor(
                self.function,
                *args,  # type: ignore[reportCallIssue]
                **kwargs,
            )

        self._current_retry = 0
        return messages.FunctionResponse(
            function_id=message.function_id,
            function_name=message.function_name,
            content=cast(str, response_content),
        )

    def _call_args(self, context: AgentContext, args_dict: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
        if self.single_arg_name:
            args_dict = {self.single_arg_name: args_dict}

        args = [CallInfo(context, self._current_retry)] if self.takes_info else []
        for positional_field in self.positional_fields:
            args.append(args_dict.pop(positional_field))
        if self.var_positional_field:
            args.extend(args_dict.pop(self.var_positional_field))

        return args, args_dict
