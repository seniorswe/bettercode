import os
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from rich.console import Console
from bettercode.context import SessionLocal, Workspace, Message, init_db, manage_workspace_context
from bettercode.auth import login, set_api_key
from bettercode.router import RouterDaemon, get_available_models, generate_response

console = Console()
style = Style.from_dict({
    'prompt': 'ansicyan bold',
})

class CLIApp:
    def __init__(self):
        init_db()
        self.db = SessionLocal()
        self.session = PromptSession()
        self.current_workspace = None

    def bootstrap(self):
        cwd = os.getcwd()
        workspace_name = os.path.basename(cwd)
        
        ws = self.db.query(Workspace).filter_by(path=cwd).first()
        if not ws:
            ws = Workspace(name=workspace_name, path=cwd)
            self.db.add(ws)
            self.db.commit()
            console.print(f"[green]Initialized new workspace:[/green] {workspace_name}")
        
        self.current_workspace = ws
        console.print(f"[cyan]Active Workspace:[/cyan] {ws.name}")

    def run(self):
        self.bootstrap()
        console.print("\\n[bold]Type '/help' for commands, or just chat.[/bold]\\n")
        
        while True:
            try:
                user_input = self.session.prompt('bettercode> ', style=style).strip()
                if not user_input:
                    continue
                    
                if user_input.startswith('/'):
                    self.handle_command(user_input)
                else:
                    self.handle_chat(user_input)
                    
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
                
    def handle_command(self, command_text: str):
        parts = command_text.split()
        cmd = parts[0]

        if cmd in ['/quit', '/exit']:
            raise EOFError()
        if cmd == '/help':
            console.print("[bold]Available commands:[/bold]")
            console.print("  /help      - Show this help")
            console.print("  /config    - Store an OpenAI or Anthropic API key")
            console.print("  /login     - Store a BetterCode subscription token")
            console.print("  /workspace - Show the active workspace")
            console.print("  /quit      - Exit application")
            return
        if cmd == '/workspace':
            console.print(f"[cyan]Active Workspace:[/cyan] {self.current_workspace.name}")
            console.print(self.current_workspace.path)
            return
        if cmd == '/config':
            console.print("[bold]Configure BYOK (Bring Your Own Key)[/bold]")
            provider = self.session.prompt('Provider (openai/anthropic): ').strip().lower()
            if provider not in ['openai', 'anthropic']:
                console.print("[red]Unknown provider.[/red]")
                return

            api_key = self.session.prompt('API Key: ', is_password=True).strip()
            try:
                set_api_key(provider, api_key)
                console.print(f"[green]Successfully stored BYOK for {provider}![/green]")
            except Exception as exc:
                console.print(f"[red]Error saving key:[/red] {exc}")
            return
        if cmd == '/login':
            console.print("[bold]Login to BetterCode Subscription[/bold]")
            username = self.session.prompt('Username: ').strip()
            password = self.session.prompt('Password: ', is_password=True).strip()
            if login(username, password):
                console.print("[green]Successfully logged into BetterCode Subscription![/green]")
                console.print("[dim]Using centralized proxy for routing...[/dim]")
            else:
                console.print("[red]Login failed.[/red]")
            return

        console.print(f"[red]Unknown command:[/red] {cmd}")

    def handle_chat(self, text: str):
        user_msg = Message(workspace_id=self.current_workspace.id, role="user", content=text)
        self.db.add(user_msg)
        self.db.commit()

        if manage_workspace_context(self.db, self.current_workspace):
            console.print("[dim italic]Conversation context compressed by the local router to save tokens.[/dim italic]\\n")

        console.print("[dim]Analyzing request complexity and routing...[/dim]")
        daemon = RouterDaemon()
        available = get_available_models()
        triage_info = daemon.triage_prompt(text, available)
        
        model = triage_info.get("recommended_model", "local")
        reasoning = triage_info.get("reasoning", "No specific reasoning provided.")
        console.print(f"[bold cyan]Routed to [yellow]{model}[/yellow][/bold cyan] - [dim]{reasoning}[/dim]\\n")
        
        history = (
            self.db.query(Message)
            .filter_by(workspace_id=self.current_workspace.id)
            .order_by(Message.created_at.desc())
            .limit(10)
            .all()
        )
        history.reverse()
        messages = [{"role": m.role, "content": m.content} for m in history]
        
        complexity = triage_info.get("complexity", 1)
        full_response = ""
        
        if complexity >= 8:
            console.print(f"[bold yellow]High Complexity Detected ({complexity}/10) — routing to single best model.[/bold yellow]\\n")
        if True:
            console.print(f"[bold cyan]Routed to [yellow]{model}[/yellow][/bold cyan] - [dim]{reasoning}[/dim]\\n")
            console.print(f"[bold green]Assistant ({model}):[/bold green] ", end="")
            
            try:
                response_stream = generate_response(model, messages, stream=True)
                for chunk in response_stream:
                    content = chunk.choices[0].delta.content or ""
                    console.print(content, end="")
                    full_response += content
                console.print("\\n")
            except Exception as e:
                console.print(f"\\n[bold red]Error calling model {model}:[/bold red] {e}\\n")
                return
            
        if full_response:
            assistant_msg = Message(workspace_id=self.current_workspace.id, role="assistant", content=full_response)
            self.db.add(assistant_msg)
            self.db.commit()

    def close(self):
        self.db.close()

def run_app():
    app = CLIApp()
    try:
        app.run()
    finally:
        app.close()
