from __future__ import annotations as _annotations

import base64
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from textwrap import indent
from typing import TYPE_CHECKING, Annotated, Any, Literal

from annotated_types import Ge, Le
from typing_extensions import TypeAlias, TypedDict, Unpack

from .nodes import BaseNode

if TYPE_CHECKING:
    from .graph import Graph


__all__ = 'NodeIdent', 'DEFAULT_HIGHLIGHT_CSS', 'generate_code', 'MermaidConfig', 'request_image', 'save_image'


NodeIdent: TypeAlias = 'type[BaseNode[Any, Any]] | BaseNode[Any, Any] | str'
DEFAULT_HIGHLIGHT_CSS = 'fill:#fdff32'


def generate_code(
    graph: Graph[Any, Any],
    /,
    *,
    start_node: Sequence[NodeIdent] | NodeIdent | None = None,
    highlighted_nodes: Sequence[NodeIdent] | NodeIdent | None = None,
    highlight_css: str = DEFAULT_HIGHLIGHT_CSS,
    edge_labels: bool = True,
    notes: bool = True,
) -> str:
    """Generate [Mermaid state diagram](https://mermaid.js.org/syntax/stateDiagram.html) code for a graph.

    Args:
        graph: The graph to generate the image for.
        start_node: Identifiers of nodes that start the graph.
        highlighted_nodes: Identifiers of nodes to highlight.
        highlight_css: CSS to use for highlighting nodes.
        edge_labels: Whether to include edge labels in the diagram.
        notes: Whether to include notes in the diagram.

    Returns: The Mermaid code for the graph.
    """
    start_node_ids = set(_node_ids(start_node or ()))
    for node_id in start_node_ids:
        if node_id not in graph.node_defs:
            raise LookupError(f'Start node "{node_id}" is not in the graph.')

    lines = ['stateDiagram-v2']
    for node in graph.nodes:
        node_id = node.get_id()
        node_def = graph.node_defs[node_id]

        # we use round brackets (rounded box) for nodes other than the start and end
        if node_id in start_node_ids:
            lines.append(f'  [*] --> {node_id}')
        if node_def.returns_base_node:
            for next_node_id in graph.nodes:
                lines.append(f'  {node_id} --> {next_node_id}')
        else:
            for next_node_id, edge in node_def.next_node_edges.items():
                line = f'  {node_id} --> {next_node_id}'
                if edge_labels and edge.label:
                    line += f': {edge.label}'
                lines.append(line)
        if end_edge := node_def.end_edge:
            line = f'  {node_id} --> [*]'
            if edge_labels and end_edge.label:
                line += f': {end_edge.label}'
            lines.append(line)

        if notes and node_def.note:
            lines.append(f'  note right of {node_id}')
            # mermaid doesn't like multiple paragraphs in a note, and shows if so
            clean_docs = re.sub('\n{2,}', '\n', node_def.note)
            lines.append(indent(clean_docs, '    '))
            lines.append('  end note')

    if highlighted_nodes:
        lines.append('')
        lines.append(f'classDef highlighted {highlight_css}')
        for node_id in _node_ids(highlighted_nodes):
            if node_id not in graph.node_defs:
                raise LookupError(f'Highlighted node "{node_id}" is not in the graph.')
            lines.append(f'class {node_id} highlighted')

    return '\n'.join(lines)


def _node_ids(node_idents: Sequence[NodeIdent] | NodeIdent) -> Iterable[str]:
    """Get the node IDs from a sequence of node identifiers."""
    if isinstance(node_idents, str):
        node_iter = (node_idents,)
    elif isinstance(node_idents, Sequence):
        node_iter = node_idents
    else:
        node_iter = (node_idents,)

    for node in node_iter:
        if isinstance(node, str):
            yield node
        else:
            yield node.get_id()


class MermaidConfig(TypedDict, total=False):
    """Parameters to configure mermaid chart generation."""

    start_node: Sequence[NodeIdent] | NodeIdent
    """Identifiers of nodes that start the graph."""
    highlighted_nodes: Sequence[NodeIdent] | NodeIdent
    """Identifiers of nodes to highlight."""
    highlight_css: str
    """CSS to use for highlighting nodes."""
    edge_labels: bool
    """Whether to include edge labels in the diagram."""
    notes: bool
    """Whether to include docstrings as notes in the diagram, defaults to true."""
    image_type: Literal['jpeg', 'png', 'webp', 'svg', 'pdf']
    """The image type to generate. If unspecified, the default behavior is `'jpeg'`."""
    pdf_fit: bool
    """When using image_type='pdf', whether to fit the diagram to the PDF page."""
    pdf_landscape: bool
    """When using image_type='pdf', whether to use landscape orientation for the PDF.

    This has no effect if using `pdf_fit`.
    """
    pdf_paper: Literal['letter', 'legal', 'tabloid', 'ledger', 'a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6']
    """When using image_type='pdf', the paper size of the PDF."""
    background_color: str
    """The background color of the diagram.

    If None, the default transparent background is used. The color value is interpreted as a hexadecimal color
    code by default (and should not have a leading '#'), but you can also use named colors by prefixing the
    value with `'!'`. For example, valid choices include `background_color='!white'` or `background_color='FF0000'`.
    """
    theme: Literal['default', 'neutral', 'dark', 'forest']
    """The theme of the diagram. Defaults to 'default'."""
    width: int
    """The width of the diagram."""
    height: int
    """The height of the diagram."""
    scale: Annotated[float, Ge(1), Le(3)]
    """The scale of the diagram.

    The scale must be a number between 1 and 3, and you can only set a scale if one or both of width and height are set.
    """


def request_image(
    graph: Graph[Any, Any],
    /,
    **kwargs: Unpack[MermaidConfig],
) -> bytes:
    """Generate an image of a Mermaid diagram using [mermaid.ink](https://mermaid.ink).

    Args:
        graph: The graph to generate the image for.
        **kwargs: Additional parameters to configure mermaid chart generation.

    Returns: The image data.
    """
    import httpx

    code = generate_code(
        graph,
        start_node=kwargs.get('start_node'),
        highlighted_nodes=kwargs.get('highlighted_nodes'),
        highlight_css=kwargs.get('highlight_css', DEFAULT_HIGHLIGHT_CSS),
        edge_labels=kwargs.get('edge_labels', True),
        notes=kwargs.get('notes', True),
    )
    code_base64 = base64.b64encode(code.encode()).decode()

    params: dict[str, str | bool] = {}
    if kwargs.get('image_type') == 'pdf':
        url = f'https://mermaid.ink/pdf/{code_base64}'
        if kwargs.get('pdf_fit'):
            params['fit'] = True
        if kwargs.get('pdf_landscape'):
            params['landscape'] = True
        if pdf_paper := kwargs.get('pdf_paper'):
            params['paper'] = pdf_paper
    elif kwargs.get('image_type') == 'svg':
        url = f'https://mermaid.ink/svg/{code_base64}'
    else:
        url = f'https://mermaid.ink/img/{code_base64}'

        if image_type := kwargs.get('image_type'):
            params['type'] = image_type

    if background_color := kwargs.get('background_color'):
        params['bgColor'] = background_color
    if theme := kwargs.get('theme'):
        params['theme'] = theme
    if width := kwargs.get('width'):
        params['width'] = str(width)
    if height := kwargs.get('height'):
        params['height'] = str(height)
    if scale := kwargs.get('scale'):
        params['scale'] = str(scale)

    response = httpx.get(url, params=params)
    if not response.is_success:
        raise ValueError(f'{response.status_code} error generating image:\n{response.text}')
    return response.content


def save_image(
    path: Path | str,
    graph: Graph[Any, Any],
    /,
    **kwargs: Unpack[MermaidConfig],
) -> None:
    """Generate an image of a Mermaid diagram using [mermaid.ink](https://mermaid.ink) and save it to a local file.

    Args:
        path: The path to save the image to.
        graph: The graph to generate the image for.
        **kwargs: Additional parameters to configure mermaid chart generation.
    """
    if isinstance(path, str):
        path = Path(path)

    if 'image_type' not in kwargs:
        ext = path.suffix.lower()[1:]
        # no need to check for .jpeg/.jpg, as it is the default
        if ext in ('png', 'webp', 'svg', 'pdf'):
            kwargs['image_type'] = ext

    image_data = request_image(graph, **kwargs)
    path.write_bytes(image_data)
