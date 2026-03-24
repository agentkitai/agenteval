"""The 'generate' command."""

from __future__ import annotations

import os
import sys
from typing import Optional

import click

from agenteval.loader import LoadError, load_suite


def register(cli: click.Group, helpers: dict) -> None:
    """Register the generate command on the CLI group."""

    @cli.command("generate")
    @click.option("--suite", required=True, type=click.Path(exists=True), help="Path to source YAML suite.")
    @click.option("--output", "-o", required=True, type=click.Path(), help="Output YAML path.")
    @click.option("--strategies", default=None, help="Comma-separated strategy names (default: all).")
    @click.option("--count", default=None, type=int, help="Max mutations per strategy per case.")
    @click.option("--api-key", default=None, help="OpenAI API key for LLM strategy.")
    @click.option("--model", default="gpt-4o-mini", show_default=True, help="LLM model for generation.")
    @click.option("--dry-run", is_flag=True, help="Show LLM prompt without calling API.")
    def generate_cmd(suite: str, output: str, strategies: Optional[str], count: Optional[int],
                     api_key: Optional[str], model: str, dry_run: bool) -> None:
        """Generate mutated test cases from an existing suite."""
        from agenteval.generators import generate

        try:
            eval_suite = load_suite(suite)
        except LoadError as e:
            click.echo(f"Error loading suite: {e}", err=True)
            sys.exit(1)

        strategy_list = [s.strip() for s in strategies.split(",")] if strategies else None

        # Handle LLM strategy
        llm_cases: list = []
        has_llm = strategy_list and "llm" in strategy_list
        if has_llm:
            resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
            if dry_run:
                from agenteval.generators.llm_gen import LLMGenerator
                gen = LLMGenerator(api_key="dry-run", model=model)
                prompt = gen.build_prompt(eval_suite.cases, count=count or 3)
                click.echo(prompt)
                return
            if not resolved_key:
                click.echo("Warning: No API key for LLM strategy (use --api-key or OPENAI_API_KEY). Skipping LLM.", err=True)
            else:
                from agenteval.generators.llm_gen import LLMGenerator
                gen = LLMGenerator(api_key=resolved_key, model=model)
                llm_cases = gen.generate_adversarial(eval_suite.cases, count=count or 3)
            # Remove 'llm' from mutation strategies
            strategy_list = [s for s in strategy_list if s != "llm"]

        # Run deterministic mutation strategies (if any remain)
        if strategy_list:
            try:
                result = generate(eval_suite, strategies=strategy_list, count=count)
            except ValueError as e:
                click.echo(f"Error: {e}", err=True)
                sys.exit(1)
        else:
            if not has_llm:
                try:
                    result = generate(eval_suite, strategies=strategy_list, count=count)
                except ValueError as e:
                    click.echo(f"Error: {e}", err=True)
                    sys.exit(1)
            else:
                # Only LLM was requested
                result = eval_suite

        # Append LLM-generated cases
        if llm_cases:
            result = type(result)(
                name=result.name, agent=result.agent,
                cases=list(result.cases) + llm_cases,
                defaults=dict(result.defaults),
            )

        # Serialize to YAML
        data = {
            "name": result.name,
            "agent": result.agent,
            "defaults": result.defaults,
            "cases": [
                {
                    "name": c.name,
                    "input": c.input,
                    "expected": c.expected,
                    "grader": c.grader,
                    **({"grader_config": c.grader_config} if c.grader_config else {}),
                    **({"tags": c.tags} if c.tags else {}),
                }
                for c in result.cases
            ],
        }

        import yaml as _yaml
        with open(output, "w") as f:
            _yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

        click.echo(f"Generated {len(result.cases)} cases ({len(result.cases) - len(eval_suite.cases)} new) \u2192 {output}")
