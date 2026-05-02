from __future__ import annotations

import sys
from typing import Any

import click
import httpx


VERSION = "0.1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


@click.command()
@click.version_option(version=VERSION, prog_name="haha")
@click.option("--model", "-m", default=None, help="Model name to use for this session")
@click.option("--resume", "-r", "resume_session_id", default=None, help="Resume a previous session by ID")
@click.option("--cwd", "-C", default=None, help="Working directory for the session")
@click.option("--host", "-h", default=DEFAULT_HOST, help="FastAPI server host")
@click.option("--port", "-p", default=DEFAULT_PORT, help="FastAPI server port")
@click.option("--prompt", "-P", default=None, help="Send a prompt non-interactively (single turn)")
@click.argument("prompt_args", nargs=-1, required=False)
def main(
    model: str | None,
    resume_session_id: str | None,
    cwd: str | None,
    host: str,
    port: int,
    prompt: str | None,
    prompt_args: tuple[str, ...],
) -> None:
    base_url = f"http://{host}:{port}"
    api_chat_url = f"{base_url}/api/v1/chat"
    api_stop_url = f"{base_url}/api/v1/stop/{{session_id}}"
    api_health_url = f"{base_url}/api/v1/health"

    user_prompt = prompt
    if not user_prompt and prompt_args:
        user_prompt = " ".join(prompt_args)

    if not user_prompt:
        user_prompt = _read_stdin()

    if not user_prompt:
        click.echo("No prompt provided. Provide a prompt via --prompt, arguments, or stdin.", err=True)
        sys.exit(1)

    _run_streaming_chat(
        api_chat_url=api_chat_url,
        api_health_url=api_health_url,
        prompt=user_prompt,
        model=model,
        session_id=resume_session_id,
        cwd=cwd,
    )


def _read_stdin() -> str | None:
    if sys.stdin.isatty():
        return None
    try:
        data = sys.stdin.read()
        if data and data.strip():
            return data.strip()
    except Exception:
        pass
    return None


def _run_streaming_chat(
    api_chat_url: str,
    api_health_url: str,
    prompt: str,
    model: str | None = None,
    session_id: str | None = None,
    cwd: str | None = None,
) -> None:
    payload: dict[str, Any] = {"prompt": prompt, "permission_mode": "default"}
    if model:
        payload["model"] = model
    if session_id:
        payload["session_id"] = session_id
        payload["resume"] = True

    with httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
        try:
            health = client.get(api_health_url)
        except httpx.ConnectError:
            click.echo(
                f"Error: Could not connect to FastAPI server at {api_health_url}. "
                f"Start the server with 'uv run uvicorn server.main:app --port 8000' first.",
                err=True,
            )
            sys.exit(1)

        session_id_actual = session_id

        with client.stream("POST", api_chat_url, json=payload) as response:
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                click.echo(f"Rate limited. Try again in {retry_after} seconds.", err=True)
                sys.exit(1)
            if response.status_code == 503:
                click.echo("Server is shutting down. Try again later.", err=True)
                sys.exit(1)
            if response.status_code != 200:
                click.echo(f"Server error: HTTP {response.status_code}", err=True)
                try:
                    error_data = response.json()
                    click.echo(f"  {error_data}", err=True)
                except Exception:
                    click.echo(f"  {response.text}", err=True)
                sys.exit(1)

            if not session_id_actual:
                session_id_actual = response.headers.get("X-Session-Id", "")
                if session_id_actual:
                    click.echo(f"Session: {session_id_actual}", err=True)

            click.echo("--- Response ---")

            buffer = ""
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue

                line = raw_line.strip()
                if not line:
                    continue

                if line.startswith(":"):
                    continue

                if line.startswith("event: "):
                    buffer = line
                    continue

                if line.startswith("data: "):
                    data_str = line[6:]
                    buffer = ""
                    try:
                        import json
                        data = json.loads(data_str)
                        _render_event(data)
                    except json.JSONDecodeError:
                        click.echo(data_str)

    click.echo("", err=True)
    if session_id_actual:
        click.echo(f"Session ID: {session_id_actual}", err=True)


def _render_event(event: dict[str, Any]) -> None:
    event_type = event.get("type", "")

    if event_type == "text_delta":
        text = event.get("text", "")
        if text:
            click.echo(text, nl=False)
            sys.stdout.flush()

    elif event_type == "system_init":
        model_name = event.get("model", "unknown")
        tools = event.get("tools", [])
        click.echo(f"[system] Model: {model_name}, Tools: {len(tools)}", err=True)

    elif event_type == "tool_use":
        tool_name = event.get("data", {}).get("name", event.get("name", "unknown"))
        click.echo(f"\n[tool: {tool_name}]", err=True)

    elif event_type == "tool_result":
        click.echo(f"\n[tool result]", err=True)

    elif event_type == "error":
        error_msg = event.get("data", {}).get("message", event.get("message", "unknown error"))
        click.echo(f"\n[error] {error_msg}", err=True)

    elif event_type == "result":
        subtype = event.get("subtype", "")
        stop_reason = event.get("stop_reason", "")
        usage = event.get("usage", {})
        if stop_reason:
            click.echo(f"\n[result: {stop_reason}]", err=True)
        if usage:
            click.echo(f"[usage: in={usage.get('input_tokens', 0)} out={usage.get('output_tokens', 0)}]", err=True)

    elif event_type == "message":
        pass

    else:
        pass


if __name__ == "__main__":
    main()
