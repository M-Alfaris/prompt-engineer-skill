"""Jinja2-powered prompt template loading and rendering."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, StrictUndefined, UndefinedError

from scripts.utils.config import load_yaml

logger = logging.getLogger(__name__)

# One shared Jinja2 environment; StrictUndefined surfaces missing variables
# immediately rather than silently rendering empty strings.
_jinja_env = Environment(
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PromptTemplate:
    """A reusable prompt template backed by a YAML definition file.

    Attributes:
        id: Unique slug used to reference the template inside experiment plans
            (e.g. ``"chain-of-thought"``).
        name: Human-readable display name.
        description: One-sentence summary of what the template does.
        system_prompt: Jinja2 template string for the system turn.
        user_prompt: Jinja2 template string for the user turn.
        variables: Ordered list of variable names that must be supplied at
            render time (serves as documentation / validation hint).
    """

    id: str
    name: str
    description: str
    system_prompt: str
    user_prompt: str
    variables: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_template(path: Path) -> PromptTemplate:
    """Load a single :class:`PromptTemplate` from a YAML file.

    The YAML file is expected to conform to the following schema::

        id: template_id
        name: "Template Name"
        description: "What this template does"
        system_prompt: |
          You are a {{ role }}.
        user_prompt: |
          {{ input }}
        variables:
          - role
          - input

    Args:
        path: Absolute or relative path to a ``.yaml`` template file.

    Returns:
        A populated :class:`PromptTemplate` instance.

    Raises:
        KeyError: If a required YAML key (``id``, ``system_prompt``, or
            ``user_prompt``) is missing from the file.
        FileNotFoundError: If ``path`` does not exist.
    """
    raw = load_yaml(path)

    missing = [k for k in ("id", "system_prompt", "user_prompt") if k not in raw]
    if missing:
        raise KeyError(
            f"Template file '{path}' is missing required key(s): {missing}"
        )

    return PromptTemplate(
        id=raw["id"],
        name=raw.get("name", raw["id"]),
        description=raw.get("description", ""),
        system_prompt=raw["system_prompt"],
        user_prompt=raw["user_prompt"],
        variables=raw.get("variables", []),
    )


def load_templates(directory: Path) -> dict[str, PromptTemplate]:
    """Load every ``*.yaml`` file in *directory* as a :class:`PromptTemplate`.

    Files that fail to parse are logged as warnings and skipped so that one
    malformed template does not block the entire experiment.

    Args:
        directory: Path to a directory containing YAML template files.

    Returns:
        A mapping of ``template.id -> PromptTemplate`` for every file that
        loaded successfully.

    Raises:
        NotADirectoryError: If ``directory`` exists but is not a directory.
    """
    if not directory.is_dir():
        raise NotADirectoryError(f"Template directory not found: '{directory}'")

    templates: dict[str, PromptTemplate] = {}
    yaml_files = sorted(directory.glob("*.yaml"))

    if not yaml_files:
        logger.warning("No YAML files found in template directory '%s'.", directory)
        return templates

    for yaml_path in yaml_files:
        try:
            template = load_template(yaml_path)
            if template.id in templates:
                logger.warning(
                    "Duplicate template id '%s' in '%s'. Overwriting previous entry.",
                    template.id,
                    yaml_path.name,
                )
            templates[template.id] = template
            logger.debug("Loaded template '%s' from '%s'.", template.id, yaml_path.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Skipping template file '%s': %s", yaml_path.name, exc
            )

    return templates


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_template(
    template: PromptTemplate,
    variables: dict[str, str],
) -> dict[str, str]:
    """Render a :class:`PromptTemplate` with the supplied variable bindings.

    Both ``system_prompt`` and ``user_prompt`` are rendered independently
    using the same *variables* mapping.

    Args:
        template: A loaded :class:`PromptTemplate` instance.
        variables: Key/value pairs that satisfy the Jinja2 placeholders
            declared in ``template.variables``.

    Returns:
        A ``{"system": str, "user": str}`` dict ready to be passed to a
        provider's ``complete()`` call.

    Raises:
        jinja2.UndefinedError: If a variable referenced in the template is
            absent from *variables*.
        jinja2.TemplateSyntaxError: If the template contains invalid Jinja2
            syntax.

    Example::

        rendered = render_template(template, {"role": "tutor", "input": "Explain gravity."})
        messages = [
            {"role": "system", "content": rendered["system"]},
            {"role": "user",   "content": rendered["user"]},
        ]
    """
    try:
        system_rendered = _jinja_env.from_string(template.system_prompt).render(
            **variables
        )
        user_rendered = _jinja_env.from_string(template.user_prompt).render(
            **variables
        )
    except UndefinedError as exc:
        raise UndefinedError(
            f"Template '{template.id}' is missing a required variable: {exc}"
        ) from exc

    return {
        "system": system_rendered,
        "user": user_rendered,
    }
