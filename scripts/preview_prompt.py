"""Prompt preview — renders one (or all) templates with a chosen test input.

Usage:
    python scripts/preview_prompt.py \\
        --experiment experiments/{id}/ \\
        --template t01-zero-shot \\
        --input input_001

    python scripts/preview_prompt.py \\
        --experiment experiments/{id}/ \\
        --template t01-zero-shot \\
        --input input_001 \\
        --json

    python scripts/preview_prompt.py \\
        --experiment experiments/{id}/ \\
        --all-templates \\
        --input input_001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.config import load_yaml  # noqa: E402
from scripts.utils.templates import PromptTemplate, load_template, load_templates, render_template  # noqa: E402

console = Console()


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def _load_test_input(experiment_dir: Path, input_id: str) -> dict[str, Any]:
    """Return the test input dict matching *input_id*.

    Args:
        experiment_dir: Root directory of the experiment.
        input_id: The ``id`` field to look up in ``data/test_inputs.yaml``.

    Returns:
        The matching input dict containing at least ``id`` and ``text``.

    Raises:
        FileNotFoundError: If ``data/test_inputs.yaml`` is missing.
        KeyError: If no input with *input_id* exists.
    """
    inputs_path = experiment_dir / "data" / "test_inputs.yaml"
    if not inputs_path.exists():
        raise FileNotFoundError(f"Test inputs file not found: {inputs_path}")

    raw = load_yaml(inputs_path)
    inputs: list[dict[str, Any]] = raw.get("inputs", [])

    for item in inputs:
        if str(item.get("id", "")) == input_id:
            return item

    available = [str(i.get("id", "")) for i in inputs]
    raise KeyError(
        f"Input '{input_id}' not found. Available IDs: {available}"
    )


def _find_template_path(experiment_dir: Path, template_id: str) -> Path:
    """Locate the YAML file for a template by its ID.

    Scans the plan.yaml axes.templates list first (for explicit file
    mappings), then falls back to a glob over templates/*.yaml.

    Args:
        experiment_dir: Root directory of the experiment.
        template_id: The ``id`` field of the desired template.

    Returns:
        Absolute path to the template YAML file.

    Raises:
        FileNotFoundError: If no matching template file can be found.
    """
    # Try plan.yaml mapping first
    plan_path = experiment_dir / "plan.yaml"
    if plan_path.exists():
        raw_plan = load_yaml(plan_path)
        for ref in raw_plan.get("axes", {}).get("templates", []):
            if isinstance(ref, dict) and ref.get("id") == template_id:
                candidate = experiment_dir / ref["file"]
                if candidate.exists():
                    return candidate

    # Fallback: scan templates/ directory
    template_dir = experiment_dir / "templates"
    if template_dir.is_dir():
        for yaml_path in template_dir.glob("*.yaml"):
            try:
                raw = load_yaml(yaml_path)
                if raw.get("id") == template_id:
                    return yaml_path
            except Exception:  # noqa: BLE001
                continue

    raise FileNotFoundError(
        f"Template '{template_id}' not found in {experiment_dir / 'templates'}"
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _build_render_vars(test_input: dict[str, Any]) -> dict[str, Any]:
    """Build the Jinja2 variable dict from a test input record.

    The ``input`` key is always populated with the raw ``text`` field so that
    the most common ``{{ input }}`` pattern works out-of-the-box.  All other
    top-level keys from the input record are also exposed.

    Args:
        test_input: A single record from ``data/test_inputs.yaml``.

    Returns:
        Dict of variable name -> value ready for :func:`render_template`.
    """
    variables: dict[str, Any] = dict(test_input)
    # Ensure the canonical `input` variable is always available
    variables.setdefault("input", test_input.get("text", ""))
    return variables


def _render_one(
    template: PromptTemplate,
    test_input: dict[str, Any],
) -> dict[str, Any]:
    """Render *template* against *test_input* and return a preview payload.

    Args:
        template: A loaded :class:`PromptTemplate`.
        test_input: A single record from ``data/test_inputs.yaml``.

    Returns:
        Dict with keys ``template_id``, ``input_id``, ``system_prompt``,
        ``user_prompt``, and ``messages``.
    """
    variables = _build_render_vars(test_input)
    rendered = render_template(template, variables)

    messages = [
        {"role": "system", "content": rendered["system"]},
        {"role": "user", "content": rendered["user"]},
    ]

    return {
        "template_id": template.id,
        "input_id": str(test_input.get("id", "")),
        "system_prompt": rendered["system"],
        "user_prompt": rendered["user"],
        "messages": messages,
    }


# ---------------------------------------------------------------------------
# Console output helpers
# ---------------------------------------------------------------------------


def _print_rich_preview(payload: dict[str, Any]) -> None:
    """Render a single preview to the console with rich formatting."""
    console.print(
        Rule(
            f"[bold cyan]Template:[/] {payload['template_id']}  "
            f"[dim]|[/]  [bold cyan]Input:[/] {payload['input_id']}",
        )
    )

    console.print(Panel(
        Text(payload["system_prompt"].rstrip(), overflow="fold"),
        title="[bold yellow]SYSTEM PROMPT[/]",
        border_style="yellow",
        padding=(1, 2),
    ))

    console.print(Panel(
        Text(payload["user_prompt"].rstrip(), overflow="fold"),
        title="[bold green]USER PROMPT[/]",
        border_style="green",
        padding=(1, 2),
    ))

    messages_json = json.dumps(payload["messages"], indent=2, ensure_ascii=False)
    console.print(Panel(
        Syntax(messages_json, "json", theme="monokai", word_wrap=True),
        title="[bold blue]MESSAGES ARRAY (API payload)[/]",
        border_style="blue",
        padding=(1, 2),
    ))
    console.print()


def _print_json_preview(payloads: list[dict[str, Any]]) -> None:
    """Print preview(s) as JSON.  Single item is unwrapped from the list."""
    output = payloads[0] if len(payloads) == 1 else payloads
    print(json.dumps(output, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="preview_prompt",
        description="Render a template with a test input and display the exact prompts.",
    )
    parser.add_argument(
        "--experiment",
        required=True,
        metavar="DIR",
        help="Path to the experiment directory.",
    )
    parser.add_argument(
        "--template",
        metavar="TEMPLATE_ID",
        help="ID of the template to preview (required unless --all-templates is set).",
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="INPUT_ID",
        help="ID of the test input to render.",
    )
    parser.add_argument(
        "--all-templates",
        action="store_true",
        help="Render all templates in the experiment with the specified input.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output the rendered prompt(s) as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        0 on success, 1 on error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.all_templates and not args.template:
        parser.error("Provide --template TEMPLATE_ID or --all-templates.")

    experiment_dir = Path(args.experiment)
    if not experiment_dir.exists():
        console.print(f"[red]ERROR:[/] Directory not found: {experiment_dir}")
        return 1

    # Load the requested test input
    try:
        test_input = _load_test_input(experiment_dir, args.input)
    except (FileNotFoundError, KeyError) as exc:
        console.print(f"[red]ERROR:[/] {exc}")
        return 1

    # Collect templates to render
    templates_to_render: list[PromptTemplate] = []

    if args.all_templates:
        template_dir = experiment_dir / "templates"
        if not template_dir.is_dir():
            console.print(f"[red]ERROR:[/] Templates directory not found: {template_dir}")
            return 1
        try:
            templates_map = load_templates(template_dir)
            templates_to_render = list(templates_map.values())
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]ERROR:[/] Failed to load templates: {exc}")
            return 1
        if not templates_to_render:
            console.print("[yellow]WARNING:[/] No templates found in templates/ directory.")
            return 0
    else:
        try:
            tmpl_path = _find_template_path(experiment_dir, args.template)
            templates_to_render = [load_template(tmpl_path)]
        except (FileNotFoundError, KeyError) as exc:
            console.print(f"[red]ERROR:[/] {exc}")
            return 1

    # Render
    payloads: list[dict[str, Any]] = []
    for template in templates_to_render:
        try:
            payload = _render_one(template, test_input)
            payloads.append(payload)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]ERROR:[/] Rendering template '{template.id}': {exc}")
            return 1

    # Output
    if args.output_json:
        _print_json_preview(payloads)
    else:
        for payload in payloads:
            _print_rich_preview(payload)

    return 0


if __name__ == "__main__":
    sys.exit(main())
