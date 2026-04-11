import customtkinter as ctk
import threading
from typing import Optional
from bettercode.context import SessionLocal, Workspace, Message, init_db, manage_workspace_context
from bettercode.auth import get_api_key, get_proxy_token, set_api_key, login
try:
    from bettercode.router import RouterDaemon, get_available_models, generate_response
except ImportError:
    RouterDaemon = None  # type: ignore[assignment,misc]
    get_available_models = None  # type: ignore[assignment]
    generate_response = None  # type: ignore[assignment]
try:
    from bettercode.agents import DelegationManager
except ImportError:
    DelegationManager = None  # type: ignore[assignment,misc]

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class AuthModal(ctk.CTkToplevel):
    def __init__(self, master, callbacks=None):
        super().__init__(master)
        self.title("Authenticate Provider")
        self.geometry("400x300")
        self.callbacks = callbacks
        self.focus()
        self.lift()
        self.grab_set()
        
        self.tabview = ctk.CTkTabview(self, width=380, height=280)
        self.tabview.pack(padx=10, pady=10)
        
        self.tabview.add("Anthropic")
        self.tabview.add("OpenAI")
        self.tabview.add("Subscription")
        
        # Anthropic
        ctk.CTkLabel(self.tabview.tab("Anthropic"), text="Claude 3.5 Sonnet API Key:").pack(pady=10)
        self.ant_key = ctk.CTkEntry(self.tabview.tab("Anthropic"), width=300, show="*")
        self.ant_key.pack(pady=10)
        ctk.CTkButton(self.tabview.tab("Anthropic"), text="Save", command=self.save_anthropic).pack(pady=10)
        
        # OpenAI
        ctk.CTkLabel(self.tabview.tab("OpenAI"), text="OpenAI API Key:").pack(pady=10)
        self.oai_key = ctk.CTkEntry(self.tabview.tab("OpenAI"), width=300, show="*")
        self.oai_key.pack(pady=10)
        ctk.CTkButton(self.tabview.tab("OpenAI"), text="Save", command=self.save_openai).pack(pady=10)
        
        # Sub
        ctk.CTkLabel(self.tabview.tab("Subscription"), text="Username:").pack(pady=5)
        self.sub_user = ctk.CTkEntry(self.tabview.tab("Subscription"), width=300)
        self.sub_user.pack(pady=5)
        ctk.CTkLabel(self.tabview.tab("Subscription"), text="Password:").pack(pady=5)
        self.sub_pass = ctk.CTkEntry(self.tabview.tab("Subscription"), width=300, show="*")
        self.sub_pass.pack(pady=5)
        ctk.CTkButton(self.tabview.tab("Subscription"), text="Login", command=self.save_sub).pack(pady=10)
        
    def save_anthropic(self):
        set_api_key("anthropic", self.ant_key.get())
        if self.callbacks: self.callbacks()
        self.destroy()
        
    def save_openai(self):
        set_api_key("openai", self.oai_key.get())
        if self.callbacks: self.callbacks()
        self.destroy()
        
    def save_sub(self):
        try:
            login(self.sub_user.get(), self.sub_pass.get())
            if self.callbacks: self.callbacks()
            self.destroy()
        except:
            pass

class BetterCodeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        init_db()
        
        self.title("BetterCode | Native Desktop")
        self.geometry("1100x700")
        
        # Layout: 1x2 grid (Sidebar, Chat Area)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        self.current_workspace_id: Optional[int] = None
        
        self.setup_sidebar()
        self.setup_chat_area()
        self.update_auth_status()
        self.load_workspaces()
        
    def setup_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(2, weight=1)
        
        self.logo = ctk.CTkLabel(self.sidebar, text="BetterCode", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        self.ws_label = ctk.CTkLabel(self.sidebar, text="Workspaces:")
        self.ws_label.grid(row=1, column=0, padx=20, pady=5, sticky="w")
        
        self.ws_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent")
        self.ws_scroll.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        
        self.add_ws_btn = ctk.CTkButton(self.sidebar, text="+ New Workspace", command=self.create_workspace)
        self.add_ws_btn.grid(row=3, column=0, padx=20, pady=10)
        
        self.auth_label = ctk.CTkLabel(self.sidebar, text="Auth Status: Unknown", cursor="hand2")
        self.auth_label.grid(row=4, column=0, padx=20, pady=20)
        self.auth_label.bind("<Button-1>", lambda e: self.open_auth())
        
    def setup_chat_area(self):
        self.chat_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.chat_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.chat_frame.grid_rowconfigure(0, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)
        
        # Chat log display
        self.chat_log = ctk.CTkTextbox(self.chat_frame, wrap="word", state="disabled")
        self.chat_log.grid(row=0, column=0, sticky="nsew", pady=(0, 20))
        self.chat_log.insert("end", "Welcome to BetterCode. Please select a workspace.")
        
        # Input area
        self.input_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        
        self.chat_input = ctk.CTkEntry(self.input_frame, placeholder_text="Ask a coding question...")
        self.chat_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.chat_input.bind("<Return>", self.handle_send)
        
        self.send_btn = ctk.CTkButton(self.input_frame, text="Send", width=80, command=self.handle_send)
        self.send_btn.grid(row=0, column=1)
        
    def append_chat(self, role: str, text: str):
        self.chat_log.configure(state="normal")
        if role == "user":
            self.chat_log.insert("end", f"\\nYou:\\n{text}\\n\\n")
        else:
            self.chat_log.insert("end", f"BetterCode:\\n{text}\\n\\n")
        self.chat_log.see("end")
        self.chat_log.configure(state="disabled")

    def create_workspace(self):
        dialog = ctk.CTkInputDialog(text="Type absolute path for new workspace:", title="New Workspace")
        path = dialog.get_input()
        if path:
            name = path.split("/")[-1] or path
            with SessionLocal() as db:
                ws = Workspace(name=name, path=path)
                db.add(ws)
                db.commit()
            self.load_workspaces()
            
    def load_workspaces(self):
        for child in self.ws_scroll.winfo_children():
            child.destroy()
            
        with SessionLocal() as db:
            for ws in db.query(Workspace).all():
                btn = ctk.CTkButton(self.ws_scroll, text=ws.name, fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"), anchor="w", command=lambda w_id=ws.id: self.select_workspace(w_id))
                btn.pack(fill="x", pady=2)
                
    def select_workspace(self, ws_id):
        self.current_workspace_id = ws_id
        self.chat_log.configure(state="normal")
        self.chat_log.delete("0.0", "end")
        self.chat_log.configure(state="disabled")
        
        with SessionLocal() as db:
            messages = db.query(Message).filter_by(workspace_id=ws_id).order_by(Message.created_at.asc()).all()
            for m in messages:
                self.append_chat(m.role, m.content)

    def update_auth_status(self):
        has_auth = bool(get_api_key("anthropic") or get_api_key("openai") or get_proxy_token())
        if has_auth:
            self.auth_label.configure(text="🔒 Authenticated", text_color="green")
        else:
            self.auth_label.configure(text="⚠️ Manage Auth", text_color="orange")
            
    def open_auth(self):
        AuthModal(self, callbacks=self.update_auth_status)
        
    def handle_send(self, event=None):
        text = self.chat_input.get().strip()
        if not text: return
        
        if not self.current_workspace_id:
            self.append_chat("system", "Please select a workspace first.")
            return
            
        if not (get_api_key("anthropic") or get_api_key("openai") or get_proxy_token()):
            self.open_auth()
            return
            
        self.chat_input.delete(0, "end")
        self.append_chat("user", text)
        
        # Disable input while processing
        self.chat_input.configure(state="disabled")
        self.send_btn.configure(state="disabled")
        
        # Save to DB
        with SessionLocal() as db:
            db.add(Message(workspace_id=self.current_workspace_id, role="user", content=text))
            db.commit()
            
            # Start streaming worker thread
            threading.Thread(target=self.process_chat, args=(self.current_workspace_id, text), daemon=True).start()
            
    def process_chat(self, ws_id, text):
        try:
            with SessionLocal() as db:
                ws = db.query(Workspace).filter_by(id=ws_id).first()
                manage_workspace_context(db, ws)
                
                history = db.query(Message).filter_by(workspace_id=ws_id).order_by(Message.created_at.desc()).limit(10).all()
                history.reverse()
                messages = [{"role": m.role, "content": m.content} for m in history]
                
                daemon = RouterDaemon()
                triage = daemon.triage_prompt(text, get_available_models())
                model = triage.get("recommended_model", "local")
                complexity = triage.get("complexity", 1)
                
                self.chat_log.configure(state="normal")
                self.chat_log.insert("end", f"BetterCode [{model} | complexity {complexity}]:\\n")
                
                full_reply = ""
                
                if complexity >= 8:
                    mgr = DelegationManager()
                    plan = mgr.plan_subtasks(text)
                    for step in plan:
                        self.chat_log.insert("end", f"\\n[Agent {step.get('agent')}] executing: {step.get('task_desc')}\\n")
                        agent = mgr.agents.get(step.get("agent"))
                        if agent:
                            stream = agent.execute(step.get("task_desc"), messages, stream=True)
                            agent_output = ""
                            for chunk in stream:
                                content = chunk.choices[0].delta.content or ""
                                agent_output += content
                                full_reply += content
                                self.chat_log.insert("end", content)
                                self.chat_log.see("end")
                            messages.append({"role": "assistant", "content": agent_output})
                else:
                    stream = generate_response(model, messages, stream=True)
                    for chunk in stream:
                        content = chunk.choices[0].delta.content or ""
                        full_reply += content
                        self.chat_log.insert("end", content)
                        self.chat_log.see("end")
                        
                self.chat_log.insert("end", "\\n\\n")
                self.chat_log.configure(state="disabled")
                
                # Save assistant response
                db.add(Message(workspace_id=ws_id, role="assistant", content=full_reply))
                db.commit()
                
        except Exception as e:
            self.chat_log.configure(state="normal")
            self.chat_log.insert("end", f"\\nError: {e}\\n\\n")
            self.chat_log.configure(state="disabled")
        finally:
            self.chat_input.configure(state="normal")
            self.send_btn.configure(state="normal")
