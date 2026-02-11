"""CLI entry point: python -m vault

Interactive CLI for Vault data agent — unified auto-routing.
"""

from rich.console import Console
from rich.markdown import Markdown

from dash.contracts import VaultAskRequest
from dash.runtime import get_vault_orchestrator

console = Console()


def main() -> None:
    console.print("\n[bold cyan]Vault[/bold cyan] — self-learning data agent\n")
    console.print(
        "Auto-routes questions to SQL or personal data.\n"
        "Override: [dim]/sql <query>[/dim] | [dim]/ask <query>[/dim] | [dim]/quit[/dim]\n"
    )

    orchestrator = get_vault_orchestrator()

    while True:
        try:
            prompt = console.input("[bold]vault>[/bold] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not prompt:
            continue
        if prompt in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        # Force-mode overrides
        force_mode: str | None = None
        if prompt.startswith("/sql "):
            force_mode = "sql"
            prompt = prompt[5:].strip()
        elif prompt.startswith("/ask "):
            force_mode = "personal"
            prompt = prompt[5:].strip()

        if not prompt:
            continue

        request = VaultAskRequest(question=prompt)
        result = orchestrator.run_ask(request, force_mode=force_mode)

        console.print(f"[dim]mode: {result.mode}[/dim]")

        if result.status == "success" and result.answer:
            console.print(Markdown(result.answer))
            if result.sql:
                console.print(f"\n[dim]SQL: {result.sql}[/dim]")
            if result.citations:
                console.print("\n[dim]Sources:[/dim]")
                for c in result.citations[:3]:
                    label = c.title or c.source
                    console.print(f"  [dim]- {label}[/dim]")
            if result.memory_used:
                console.print(f"\n[dim]Memory applied: {len(result.memory_used)} item(s)[/dim]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")

        console.print()


if __name__ == "__main__":
    main()
