import asyncio
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from src.agent.core import Agent
from src.memory.database import init_db
from src.voice.stt import listen
from src.voice.tts import speak

console = Console()

async def main():
    init_db()
    agent = Agent(session_id="athul-main")
    voice_mode = False

    console.print(Panel.fit(
        "[bold red]DOOM — Personal AI Assistant[/bold red]\n"
        "[dim]Commands: 'voice' = toggle voice mode | 'quit' = exit | 'reset' = clear history[/dim]",
        border_style="red"
    ))

    while True:
        try:
            if voice_mode:
                console.print("\n[bold cyan]🎤 Listening...[/bold cyan]")
                user_input = listen()
                if not user_input:
                    console.print("[dim]Didn't catch that, try again.[/dim]")
                    continue
                console.print(f"\n[bold cyan]You (voice):[/bold cyan] {user_input}")
            else:
                user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")

            if user_input.lower() == "quit":
                console.print("[dim]Goodbye![/dim]")
                break

            if user_input.lower() == "reset":
                agent.reset()
                console.print("[dim]Session cleared.[/dim]")
                continue

            if user_input.lower() == "voice":
                voice_mode = not voice_mode
                status = "ON 🎤" if voice_mode else "OFF ⌨️"
                console.print(f"[bold yellow]Voice mode: {status}[/bold yellow]")
                continue

            if not user_input.strip():
                continue

            console.print("\n[bold red]DOOM[/bold red] thinking...", end="\r")
            response = await agent.chat(user_input)
            console.print(f"\n[bold red]DOOM[/bold red] {response}")

            if voice_mode:
                speak(response)

        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye![/dim]")
            break

if __name__ == "__main__":
    asyncio.run(main())