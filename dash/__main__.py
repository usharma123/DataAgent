"""CLI entry point: python -m vault

Interactive CLI for Vault data agent.
"""

from rich.console import Console
from rich.markdown import Markdown

from dash.native.contracts import AskRequest
from dash.native.runtime import get_native_orchestrator
from dash.personal.contracts import PersonalAskRequest
from dash.personal.runtime import get_personal_orchestrator

console = Console()


def main() -> None:
    console.print("\n[bold cyan]Vault[/bold cyan] — self-learning data agent\n")
    console.print("Commands: [dim]/sql[/dim] (data query) | [dim]/ask[/dim] (personal) | [dim]/quit[/dim]\n")

    mode = "personal"
    while True:
        try:
            prompt = console.input(f"[bold]{'sql' if mode == 'sql' else 'ask'}>[/bold] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not prompt:
            continue
        if prompt in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye.[/dim]")
            break
        if prompt == "/sql":
            mode = "sql"
            console.print("[dim]Switched to SQL mode.[/dim]")
            continue
        if prompt == "/ask":
            mode = "personal"
            console.print("[dim]Switched to personal mode.[/dim]")
            continue

        if mode == "sql":
            orchestrator = get_native_orchestrator()
            result = orchestrator.run_ask(AskRequest(question=prompt))
            if result.status == "success" and result.answer:
                console.print(Markdown(result.answer))
                if result.sql:
                    console.print(f"\n[dim]SQL: {result.sql}[/dim]")
            else:
                console.print(f"[red]Error: {result.error}[/red]")
        else:
            orchestrator = get_personal_orchestrator()
            result = orchestrator.run_ask(PersonalAskRequest(question=prompt))
            if result.status == "success" and result.answer:
                console.print(Markdown(result.answer))
                if result.citations:
                    console.print("\n[dim]Sources:[/dim]")
                    for c in result.citations[:3]:
                        label = c.title or c.source
                        console.print(f"  [dim]- {label}[/dim]")
            else:
                console.print(f"[red]Error: {result.error}[/red]")

        console.print()


if __name__ == "__main__":
    main()
