import textwrap
from typing import List, Optional
import warnings

import typer
from langchain.callbacks.base import CallbackManager
from langchain.schema import AgentAction
from rich import print

from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt

from qabot.caching import configure_caching
from qabot.config import Settings
from qabot.duckdb_manual_data_loader import import_into_duckdb_from_files, create_duckdb
from qabot.agents.agent import create_agent_executor
from qabot.duckdb_query import run_sql_catch_error
from qabot.progress_callback import QACallback

warnings.filterwarnings("ignore")

INITIAL_NON_INTERACTIVE_PROMPT = "🚀 How can I help you explore your database?"
INITIAL_INTERACTIVE_PROMPT = "[bold green] 🚀 How can I help you explore your database?"
FOLLOW_UP_PROMPT = "[bold green] 🚀 any further questions?"
PROMPT = "[bold green] 🚀 Query"

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    pretty_exceptions_enable=True
)


def format_intermediate_steps(intermediate_steps):
    if isinstance(intermediate_steps, list):
        return "\n".join(intermediate_steps)
    else:
        return str(intermediate_steps)


def format_agent_action(agent_action: AgentAction, observation) -> str:
    """
    Sometimes observation is a string, sometimes it is a dict. This function handles both cases.


    """
    result = ''
    internal_result = str(observation).strip()
    logs = ''

    if isinstance(observation, dict):
        if 'input' in observation:
            # should be the same as agent_action.tool_input
            pass
        if 'output' in observation:
            internal_result = observation['output']
        #if 'intermediate_steps' in observation:
        #     observation = format_intermediate_steps(observation['intermediate_steps'])

    if len(agent_action) > 3:
        logs = '\n'.join([textwrap.indent(str(o).strip(), ' '*6) for o in agent_action])

    return f"""
[red]{agent_action.tool.strip()}[/red]
  [green]{agent_action.tool_input.strip()}[/green]

  [blue]{internal_result}[/blue]
  
    [cyan]{str(logs).strip()}[/cyan]

[bold red]{result}[/bold red]
"""


@app.command()
def main(
        query: str = typer.Option("Describe the tables", '-q', '--query', prompt=INITIAL_NON_INTERACTIVE_PROMPT),
        file: Optional[List[str]] = typer.Option(None, "-f", "--file", help="File or url containing data to query"),
        #database_uri: Optional[str] = typer.Option(None, "-d", "--database", help="Database URI (e.g. sqlite:///mydb.db)"),
        table: Optional[List[str]] = typer.Option(None, "--table", "-t", help="Limit queries to these tables (can be specified multiple times)"),
        disable_cache: bool = typer.Option(False, "--disable-cache", help="Disable caching of LLM queries"),
        verbose: bool = typer.Option(False, "-v", "--verbose", help='Essentially debug output'),
):
    """
    Query a database using a simple english query.

    Example:
        qabot -q "What is the average age of the people in the table?"
    """

    settings = Settings()
    executed_sql = ''
    # If files are given load data into local DuckDB
    database_engine = create_duckdb()

    if len(file) > 0:
        if isinstance(file, str):
            file = [file]
        print("[red]🦆[/red] [bold]Loading data from files...[/bold]")
        database_engine, executed_sql = import_into_duckdb_from_files(database_engine, file)
        executed_sql = '\n'.join(executed_sql)
    else:
        print("[red]🦆[/red]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[green][progress.description]{task.description}"),
        transient=False,
    ) as progress:

        callback_manager = CallbackManager(handlers=[QACallback(progress=progress)])

        if not disable_cache:
            t = progress.add_task(description="Setting up cache...", total=None)
            configure_caching(settings.QABOT_CACHE_DATABASE_URI)
            progress.remove_task(t)

        t2 = progress.add_task(description="Creating LLM agent using langchain...", total=None)

        agent = create_agent_executor(
            #database_uri=database_uri or settings.QABOT_DATABASE_URI,
            database_engine=database_engine,
            tables=table,
            return_intermediate_steps=True,
            callback_manager=callback_manager,
            verbose=False,
        )

        progress.remove_task(t2)
        chat_history = [f"""
        Startup SQL Queries:
        ```
        {executed_sql}
        ```
        """]

        while True:

            t = progress.add_task(description="Processing query...", total=None)
            print("[bold red]Query: [/][green]" + query)

            inputs = {
                "input": chat_history[0] + query,
                "table_names": run_sql_catch_error(database_engine, "show tables")
                #'chat_history': '\n\n'.join(chat_history)
            }

            result = agent(inputs)

            progress.remove_task(t)

            # Show intermediate steps
            if verbose:
                progress.console.print("[bold red]Intermediate Steps: [/]")
                for i, (agent_action, action_input) in enumerate(result['intermediate_steps'], 1):
                    print(f"  [bold red]Step {i}[/]")
                    print(textwrap.indent(format_agent_action(agent_action, action_input), "    "))

                print()

            # Stop the progress before outputting result and prompting for input
            progress.stop()
            print()

            print("[bold red]Result:[/]\n[bold blue]" + result['output'] + "\n")
            chat_history.append(result['output'])

            if not Confirm.ask(FOLLOW_UP_PROMPT, default=True):
                break

            print()
            query = Prompt.ask(PROMPT)

            if query == "exit" and Confirm.ask("Are you sure you want to Quit?"):
                break

            progress.start()


def run():
    app()


if __name__ == '__main__':
    run()