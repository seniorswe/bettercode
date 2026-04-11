const state = {
  view: "chat-view",
  settingsTab: "settings-appearance",
  workspaces: [],
  currentWorkspaceId: null,
  currentTabId: null,
  auth: null,
  appInfo: null,
  messages: [],
  messagesLoading: false,
  messagePaging: null,
  git: null,
  selectedGitPaths: [],
  selectedReviewPaths: [],
  review: {
    searchQuery: "",
    depth: "standard",
    crossModel: "none"
  },
  attachments: [],
  slashCommands: {
    open: false,
    items: [],
    activeIndex: 0,
    query: "",
  },
  selectedModel: "smart",
  selectedAgentMode: "",
  modelPickerOpen: false,
  modePickerOpen: false,
  busyWorkspaces: new Set(),
  menuWorkspaceId: null,
  generatedFilesMenuWorkspaceId: null,
  generatedFilesCache: {},
  authProvider: null,
  accountProvider: null,
  renameWorkspaceId: null,
  pendingProjectPath: null,
  pendingProjectName: null,
  pendingProjectParentPath: null,
  theme: localStorage.getItem("bettercode-theme") || "dark",
  fontSize: localStorage.getItem("bettercode-font-size") || "medium",
  runtimeJobPollers: {},
  liveChats: new Map(),
  runConfig: null,
  runConfigStatus: "idle", // "idle" | "detecting" | "ready"
  runSettings: {},
  chatStatusPoller: null,
  reviewRun: {
    running: false,
    phase: "idle",
    primaryModel: "",
    secondaryModel: "none",
    activityLines: [],
    findings: [],
    summaryPrimary: "",
    summarySecondary: "",
    primaryModelLabel: "",
    secondaryModelLabel: "",
    dismissedIds: [],
    error: null,
    savedId: null,
  },
  reviewWorkspaceId: null,
  reviewTab: "new",
  reviewFileTab: "changed", // "changed" | "recent" | "all"
  reviewSearch: "",
  reviewAllFiles: [],
  reviewAllFilesLoading: false,
  savedReviews: [],
  reviewViewingSaved: null, // saved review object being viewed in Results tab
  fullReviewModal: false, // whether the full codebase review confirmation modal is open
  telemetry: {
    loading: false,
    loaded: false,
    error: "",
    events: [],
  },
  onboarding: {
    open: false,
    step: 0,
    language: null,
  },
  localPreprocessDraftModelId: "",
};

const LIGHT_THEMES = new Set(["light", "dawn", "sage"]);
const DARK_LOGO_PATH = "/assets/app-icon.svg";
const LIGHT_LOGO_PATH = "/assets/app-icon-light.svg";

const SLASH_COMMANDS = [
  {
    command: "/memory",
    description: "Review this chat and save useful details into memory.",
    keyword: "memory",
  },
];

const FALLBACK_HUMAN_LANGUAGES = [
  { code: "en", label: "English", native_label: "English", locale: "en-US" },
  { code: "fr", label: "French", native_label: "Français", locale: "fr-FR" },
  { code: "de", label: "German", native_label: "Deutsch", locale: "de-DE" },
  { code: "hi", label: "Hindi", native_label: "हिन्दी", locale: "hi-IN" },
  { code: "pl", label: "Polish", native_label: "Polski", locale: "pl-PL" },
  { code: "zh", label: "Chinese", native_label: "简体中文", locale: "zh-CN" },
  { code: "ja", label: "Japanese", native_label: "日本語", locale: "ja-JP" },
  { code: "ko", label: "Korean", native_label: "한국어", locale: "ko-KR" },
];

const UI_STRINGS = {
  en: {
    "nav.projects": "Projects",
    "nav.codeReview": "Code Review",
    "nav.git": "Git",
    "topbar.tabHistory": "Tab History",
    "composer.model": "Model",
    "composer.mode": "Mode",
    "composer.mode.plan": "Planning",
    "composer.mode.autoEdit": "Auto Accept Edits",
    "composer.mode.fullAgentic": "Full Agentic",
    "composer.attach": "Attach",
    "composer.placeholder": "Write an instruction…",
    "composer.hint": "Validate changes with the code reviewer and a manual review.",
    "composer.stop": "Stop",
    "composer.send": "Send",
    "review.title": "Code Review",
    "review.run": "Run Review",
    "settings.label": "Settings",
    "settings.title": "Configuration",
    "settings.tab.models": "CLI Models",
    "settings.tab.appearance": "Appearance",
    "settings.tab.performance": "Performance",
    "settings.tab.autoModel": "Model Select",
    "appearance.title": "Appearance",
    "appearance.copy": "Theme and sizing controls for the desktop shell.",
    "language.title": "Language",
    "language.copy": "Choose the human language BetterCode uses in the app and in model responses.",
    "language.label": "Human Language",
    "language.help": "BetterCode will keep code and filenames unchanged, but UI text and AI responses will switch to this language.",
    "theme.title": "Theme",
    "theme.copy": "Interface appearance.",
    "font.title": "Font Size",
    "font.copy": "Adjust the interface font size.",
    "font.scale": "Scale",
    "font.extra-small": "Extra Small",
    "font.small": "Small",
    "font.medium": "Medium",
    "font.large": "Large",
    "welcome.eyebrow": "Hello",
    "welcome.title": "Select your human language",
    "welcome.label": "Language",
    "welcome.continue": "Continue",
    "modelPicker.smart": "Auto Model Select",
    "modelPicker.codex": "OpenAI Codex",
    "modelPicker.cursor": "Cursor",
    "modelPicker.claude": "Claude",
    "modelPicker.gemini": "Gemini",
    "modelPicker.none": "No verified models available",
    "app.updateAvailable": "Update available",
    "toast.settingsUpdated": "Settings updated",
    "sidebar.updateVersion": "Update v{version}",
    "localModel.auto": "Auto",
    "localModel.installed": "Installed",
    "localModel.available": "Available to install",
    "localModel.pick": "Pick a local model or leave it on Auto.",
    "runtime.installing": "Installing...",
    "runtime.login": "Login in progress...",
    "runtime.notInstalled": "Not installed",
    "startup.failed": "Startup failed",
    "onboarding.kicker": "Welcome",
    "onboarding.brandCopy": "Local-first coding workspace",
    "onboarding.step1.title": "Pick your language",
    "onboarding.step1.copy": "BetterCode will use this language in the app and in AI replies.",
    "onboarding.step1.note": "Code, commands, and filenames stay unchanged.",
    "onboarding.step2.title": "Smart when it should be",
    "onboarding.step2.copy": "Auto Model Select routes each task to the best runtime and keeps local fast paths for simple work.",
    "onboarding.step2.feature1": "Routes review, debugging, and implementation work to the right model.",
    "onboarding.step2.feature2": "Uses local models when a request is self-contained and safe.",
    "onboarding.step2.feature3": "Keeps planning lightweight when speed matters.",
    "onboarding.step3.title": "Built for real project work",
    "onboarding.step3.copy": "Review code, run projects, and keep generated outputs organized without leaving the app.",
    "onboarding.step3.feature1": "Code Review page with quick, standard, and deep passes.",
    "onboarding.step3.feature2": "Project run controls with live output and clean stopping.",
    "onboarding.step3.feature3": "Generated files stay attached to the project but outside the repo.",
    "onboarding.step4.title": "Pick your local model",
    "onboarding.step4.copy": "Choose a local model for lightweight questions and fast routing, or skip this and come back later.",
    "onboarding.step4.feature1": "Install a small local model with Ollama for easy self-contained prompts.",
    "onboarding.step4.feature2": "Switch the active local model without changing your cloud runtimes.",
    "onboarding.step4.feature3": "Leave local routing off if you only want CLI and API-backed models.",
    "onboarding.step5.title": "Connect your coding models",
    "onboarding.step5.copy": "Install the coding runtimes you use and sign in so they appear in the model picker.",
    "onboarding.step5.feature1": "Install Codex, Cursor, Claude, and Gemini CLIs from inside BetterCode.",
    "onboarding.step5.feature2": "Use browser login when a runtime supports it, or save an API key instead.",
    "onboarding.step5.feature3": "Claude works with either terminal login or a saved Anthropic API key.",
    "onboarding.back": "Back",
    "onboarding.next": "Next",
    "onboarding.start": "Start coding",
  },
  fr: {
    "nav.projects": "Projets", "nav.codeReview": "Revue de code", "nav.git": "Git", "topbar.tabHistory": "Historique des onglets",
    "composer.model": "Modèle", "composer.attach": "Joindre", "composer.placeholder": "Écrivez une instruction…", "composer.hint": "Validez les changements avec la revue de code et une vérification manuelle.", "composer.stop": "Arrêter", "composer.send": "Envoyer",
    "review.title": "Revue de code", "review.run": "Lancer la revue", "settings.label": "Réglages", "settings.title": "Configuration",
    "settings.tab.models": "Modèles CLI", "settings.tab.appearance": "Apparence", "settings.tab.performance": "Performance", "settings.tab.autoModel": "Sélection du modèle",
    "appearance.title": "Apparence", "appearance.copy": "Thèmes et taille de l’interface.", "language.title": "Langue", "language.copy": "Choisissez la langue humaine utilisée par BetterCode dans l’app et dans les réponses des modèles.", "language.label": "Langue humaine", "language.help": "BetterCode garde le code et les noms de fichiers inchangés, mais l’interface et les réponses IA passent dans cette langue.",
    "theme.title": "Thème", "theme.copy": "Apparence de l’interface.", "font.title": "Taille de police", "font.copy": "Ajustez la taille du texte de l’interface.", "font.scale": "Échelle", "font.extra-small": "Très petite", "font.small": "Petite", "font.medium": "Moyenne", "font.large": "Grande",
    "welcome.eyebrow": "Bonjour", "welcome.title": "Sélectionnez votre langue", "welcome.label": "Langue", "welcome.continue": "Continuer",
    "modelPicker.smart": "Sélection auto", "modelPicker.codex": "OpenAI Codex", "modelPicker.claude": "Claude", "modelPicker.gemini": "Gemini", "modelPicker.none": "Aucun modèle vérifié disponible",
    "toast.settingsUpdated": "Réglages mis à jour", "sidebar.updateVersion": "Mise à jour v{version}", "localModel.auto": "Auto", "localModel.installed": "Installé", "localModel.available": "Disponible à installer", "localModel.pick": "Choisissez un modèle local ou laissez Auto.", "runtime.installing": "Installation…", "runtime.login": "Connexion en cours…", "runtime.notInstalled": "Non installé", "startup.failed": "Échec du démarrage",
    "onboarding.kicker": "Bienvenue", "onboarding.brandCopy": "Espace de travail local pour coder", "onboarding.step1.title": "Choisissez votre langue", "onboarding.step1.copy": "BetterCode utilisera cette langue dans l’app et dans les réponses IA.", "onboarding.step1.note": "Le code, les commandes et les noms de fichiers ne changent pas.", "onboarding.step2.title": "Intelligent quand il le faut", "onboarding.step2.copy": "La sélection automatique route chaque tâche vers le bon runtime et garde la voie locale pour les demandes simples.", "onboarding.step2.feature1": "Choisit le bon modèle pour la revue, le débogage et l’implémentation.", "onboarding.step2.feature2": "Utilise des modèles locaux quand la demande est autonome et sûre.", "onboarding.step2.feature3": "Évite la planification lourde quand elle ne ferait que ralentir la réponse.", "onboarding.step3.title": "Pensé pour de vrais projets", "onboarding.step3.copy": "Revoyez le code, lancez des projets et gardez les sorties générées organisées sans quitter l’app.", "onboarding.step3.feature1": "Page de revue avec modes rapide, standard et approfondi.", "onboarding.step3.feature2": "Contrôles d’exécution avec sortie en direct et arrêt propre.", "onboarding.step3.feature3": "Les fichiers générés restent liés au projet sans entrer dans le dépôt.", "onboarding.back": "Retour", "onboarding.next": "Suivant", "onboarding.start": "Commencer à coder",
  },
  de: {
    "nav.projects": "Projekte", "nav.codeReview": "Code-Review", "nav.git": "Git", "topbar.tabHistory": "Tab-Verlauf",
    "composer.model": "Modell", "composer.attach": "Anhängen", "composer.placeholder": "Schreibe eine Anweisung…", "composer.hint": "Änderungen mit Code-Review und manueller Prüfung validieren.", "composer.stop": "Stopp", "composer.send": "Senden",
    "review.title": "Code-Review", "review.run": "Review starten", "settings.label": "Einstellungen", "settings.title": "Konfiguration",
    "settings.tab.models": "CLI-Modelle", "settings.tab.appearance": "Darstellung", "settings.tab.performance": "Leistung", "settings.tab.autoModel": "Modellauswahl",
    "appearance.title": "Darstellung", "appearance.copy": "Themen und Größensteuerung für die Desktop-Oberfläche.", "language.title": "Sprache", "language.copy": "Wähle die Sprache, die BetterCode in der App und in Modellantworten verwendet.", "language.label": "Menschliche Sprache", "language.help": "BetterCode lässt Code und Dateinamen unverändert, aber UI-Text und KI-Antworten wechseln in diese Sprache.",
    "theme.title": "Thema", "theme.copy": "Aussehen der Oberfläche.", "font.title": "Schriftgröße", "font.copy": "Passe die Schriftgröße der Oberfläche an.", "font.scale": "Skalierung", "font.extra-small": "Sehr klein", "font.small": "Klein", "font.medium": "Mittel", "font.large": "Groß",
    "welcome.eyebrow": "Hallo", "welcome.title": "Wähle deine Sprache", "welcome.label": "Sprache", "welcome.continue": "Weiter",
    "modelPicker.smart": "Automatische Auswahl", "modelPicker.codex": "OpenAI Codex", "modelPicker.claude": "Claude", "modelPicker.gemini": "Gemini", "modelPicker.none": "Keine verifizierten Modelle verfügbar",
    "toast.settingsUpdated": "Einstellungen aktualisiert", "sidebar.updateVersion": "Update v{version}", "localModel.auto": "Auto", "localModel.installed": "Installiert", "localModel.available": "Zur Installation verfügbar", "localModel.pick": "Wähle ein lokales Modell oder lasse Auto aktiviert.", "runtime.installing": "Wird installiert…", "runtime.login": "Anmeldung läuft…", "runtime.notInstalled": "Nicht installiert", "startup.failed": "Start fehlgeschlagen",
    "onboarding.kicker": "Willkommen", "onboarding.brandCopy": "Lokaler Coding-Arbeitsbereich", "onboarding.step1.title": "Wähle deine Sprache", "onboarding.step1.copy": "BetterCode nutzt diese Sprache in der App und in KI-Antworten.", "onboarding.step1.note": "Code, Befehle und Dateinamen bleiben unverändert.", "onboarding.step2.title": "Klug, wenn es nötig ist", "onboarding.step2.copy": "Die automatische Modellauswahl leitet jede Aufgabe an die passende Runtime und nutzt lokale Schnellpfade für einfache Arbeit.", "onboarding.step2.feature1": "Wählt das richtige Modell für Review, Debugging und Umsetzung.", "onboarding.step2.feature2": "Nutzt lokale Modelle, wenn eine Anfrage in sich geschlossen und sicher ist.", "onboarding.step2.feature3": "Überspringt schwere Planung, wenn sie nur verzögern würde.", "onboarding.step3.title": "Für echte Projektarbeit gebaut", "onboarding.step3.copy": "Prüfe Code, starte Projekte und halte generierte Ausgaben organisiert, ohne die App zu verlassen.", "onboarding.step3.feature1": "Code-Review-Seite mit schnell, standard und tief.", "onboarding.step3.feature2": "Projektlauf mit Live-Ausgabe und sauberem Stoppen.", "onboarding.step3.feature3": "Generierte Dateien bleiben am Projekt, aber außerhalb des Repos.", "onboarding.back": "Zurück", "onboarding.next": "Weiter", "onboarding.start": "Jetzt coden",
  },
  hi: {
    "nav.projects": "प्रोजेक्ट", "nav.codeReview": "कोड रिव्यू", "nav.git": "Git", "topbar.tabHistory": "टैब इतिहास",
    "composer.model": "मॉडल", "composer.attach": "अटैच", "composer.placeholder": "निर्देश लिखें…", "composer.hint": "बदलावों को कोड रिव्यू और मैनुअल रिव्यू से सत्यापित करें।", "composer.stop": "रोकें", "composer.send": "भेजें",
    "review.title": "कोड रिव्यू", "review.run": "रिव्यू चलाएँ", "settings.label": "सेटिंग्स", "settings.title": "कॉन्फ़िगरेशन",
    "settings.tab.models": "CLI मॉडल", "settings.tab.appearance": "रूप", "settings.tab.performance": "परफ़ॉर्मेंस", "settings.tab.autoModel": "मॉडल चयन",
    "appearance.title": "रूप", "appearance.copy": "डेस्कटॉप शेल के लिए थीम और साइज़ नियंत्रण।", "language.title": "भाषा", "language.copy": "ऐसी मानवीय भाषा चुनें जिसे BetterCode ऐप और मॉडल उत्तरों में इस्तेमाल करे।", "language.label": "मानवीय भाषा", "language.help": "BetterCode कोड और फ़ाइल नाम नहीं बदलेगा, लेकिन UI टेक्स्ट और AI जवाब इस भाषा में बदल जाएँगे।",
    "theme.title": "थीम", "theme.copy": "इंटरफ़ेस का रूप।", "font.title": "फ़ॉन्ट आकार", "font.copy": "इंटरफ़ेस फ़ॉन्ट आकार बदलें।", "font.scale": "स्केल", "font.extra-small": "बहुत छोटा", "font.small": "छोटा", "font.medium": "मध्यम", "font.large": "बड़ा",
    "welcome.eyebrow": "नमस्ते", "welcome.title": "अपनी भाषा चुनें", "welcome.label": "भाषा", "welcome.continue": "जारी रखें",
    "modelPicker.smart": "ऑटो मॉडल चयन", "modelPicker.codex": "OpenAI Codex", "modelPicker.claude": "Claude", "modelPicker.gemini": "Gemini", "modelPicker.none": "कोई सत्यापित मॉडल उपलब्ध नहीं",
    "toast.settingsUpdated": "सेटिंग्स अपडेट हुईं", "sidebar.updateVersion": "अपडेट v{version}", "localModel.auto": "ऑटो", "localModel.installed": "इंस्टॉल्ड", "localModel.available": "इंस्टॉल के लिए उपलब्ध", "localModel.pick": "लोकल मॉडल चुनें या Auto रहने दें।", "runtime.installing": "इंस्टॉल हो रहा है…", "runtime.login": "लॉगिन जारी है…", "runtime.notInstalled": "इंस्टॉल नहीं", "startup.failed": "स्टार्टअप विफल हुआ",
    "onboarding.kicker": "स्वागत है", "onboarding.brandCopy": "लोकल-फ़र्स्ट कोडिंग वर्कस्पेस", "onboarding.step1.title": "अपनी भाषा चुनें", "onboarding.step1.copy": "BetterCode यही भाषा ऐप और AI जवाबों में इस्तेमाल करेगा।", "onboarding.step1.note": "कोड, कमांड और फ़ाइल नाम वैसे ही रहेंगे।", "onboarding.step2.title": "जहाँ ज़रूरी हो वहाँ स्मार्ट", "onboarding.step2.copy": "Auto Model Select हर काम को सही runtime तक भेजता है और आसान काम के लिए लोकल fast path रखता है।", "onboarding.step2.feature1": "रिव्यू, डिबगिंग और इम्प्लीमेंटेशन के लिए सही मॉडल चुनता है।", "onboarding.step2.feature2": "जब अनुरोध self-contained और safe हो तो लोकल मॉडल इस्तेमाल करता है।", "onboarding.step2.feature3": "जब भारी planning सिर्फ़ देरी बढ़ाए, तब उसे छोड़ देता है।", "onboarding.step3.title": "असल प्रोजेक्ट काम के लिए बनाया गया", "onboarding.step3.copy": "कोड रिव्यू करें, प्रोजेक्ट चलाएँ, और generated outputs को बिना ऐप छोड़े व्यवस्थित रखें।", "onboarding.step3.feature1": "Quick, standard और deep मोड वाला Code Review पेज।", "onboarding.step3.feature2": "Live output और clean stop के साथ project run controls।", "onboarding.step3.feature3": "Generated files प्रोजेक्ट से जुड़े रहते हैं लेकिन repo से बाहर।", "onboarding.back": "वापस", "onboarding.next": "आगे", "onboarding.start": "कोडिंग शुरू करें",
  },
  pl: {
    "nav.projects": "Projekty", "nav.codeReview": "Przegląd kodu", "nav.git": "Git", "topbar.tabHistory": "Historia kart",
    "composer.model": "Model", "composer.attach": "Dołącz", "composer.placeholder": "Napisz instrukcję…", "composer.hint": "Zweryfikuj zmiany przez przegląd kodu i ręczną kontrolę.", "composer.stop": "Zatrzymaj", "composer.send": "Wyślij",
    "review.title": "Przegląd kodu", "review.run": "Uruchom przegląd", "settings.label": "Ustawienia", "settings.title": "Konfiguracja",
    "settings.tab.models": "Modele CLI", "settings.tab.appearance": "Wygląd", "settings.tab.performance": "Wydajność", "settings.tab.autoModel": "Wybór modelu",
    "appearance.title": "Wygląd", "appearance.copy": "Motywy i rozmiar interfejsu aplikacji.", "language.title": "Język", "language.copy": "Wybierz język używany przez BetterCode w aplikacji i odpowiedziach modeli.", "language.label": "Język użytkownika", "language.help": "BetterCode zachowa kod i nazwy plików bez zmian, ale tekst UI i odpowiedzi AI przełączy na ten język.",
    "theme.title": "Motyw", "theme.copy": "Wygląd interfejsu.", "font.title": "Rozmiar czcionki", "font.copy": "Dostosuj rozmiar czcionki interfejsu.", "font.scale": "Skala", "font.extra-small": "Bardzo mały", "font.small": "Mały", "font.medium": "Średni", "font.large": "Duży",
    "welcome.eyebrow": "Cześć", "welcome.title": "Wybierz swój język", "welcome.label": "Język", "welcome.continue": "Dalej",
    "modelPicker.smart": "Automatyczny wybór", "modelPicker.codex": "OpenAI Codex", "modelPicker.claude": "Claude", "modelPicker.gemini": "Gemini", "modelPicker.none": "Brak zweryfikowanych modeli",
    "toast.settingsUpdated": "Ustawienia zapisane", "sidebar.updateVersion": "Aktualizacja v{version}", "localModel.auto": "Auto", "localModel.installed": "Zainstalowany", "localModel.available": "Dostępny do instalacji", "localModel.pick": "Wybierz model lokalny lub zostaw Auto.", "runtime.installing": "Instalowanie…", "runtime.login": "Logowanie w toku…", "runtime.notInstalled": "Nie zainstalowano", "startup.failed": "Uruchamianie nie powiodło się",
    "onboarding.kicker": "Witamy", "onboarding.brandCopy": "Lokalny obszar pracy do kodowania", "onboarding.step1.title": "Wybierz swój język", "onboarding.step1.copy": "BetterCode będzie używać tego języka w aplikacji i odpowiedziach AI.", "onboarding.step1.note": "Kod, polecenia i nazwy plików pozostaną bez zmian.", "onboarding.step2.title": "Sprytne wtedy, gdy trzeba", "onboarding.step2.copy": "Automatyczny wybór modelu kieruje każde zadanie do właściwego runtime i zachowuje lokalną szybką ścieżkę dla prostych zadań.", "onboarding.step2.feature1": "Dobiera właściwy model do przeglądu, debugowania i implementacji.", "onboarding.step2.feature2": "Używa modeli lokalnych, gdy prośba jest samowystarczalna i bezpieczna.", "onboarding.step2.feature3": "Pomija ciężkie planowanie, gdy tylko spowolniłoby odpowiedź.", "onboarding.step3.title": "Stworzone do prawdziwej pracy projektowej", "onboarding.step3.copy": "Przeglądaj kod, uruchamiaj projekty i utrzymuj wygenerowane wyniki w porządku bez opuszczania aplikacji.", "onboarding.step3.feature1": "Strona przeglądu kodu z trybami szybkim, standardowym i głębokim.", "onboarding.step3.feature2": "Uruchamianie projektu z żywym wyjściem i czystym zatrzymaniem.", "onboarding.step3.feature3": "Wygenerowane pliki są powiązane z projektem, ale poza repozytorium.", "onboarding.back": "Wstecz", "onboarding.next": "Dalej", "onboarding.start": "Zacznij kodować",
  },
  zh: {
    "nav.projects": "项目", "nav.codeReview": "代码审查", "nav.git": "Git", "topbar.tabHistory": "标签历史",
    "composer.model": "模型", "composer.attach": "附加", "composer.placeholder": "输入指令…", "composer.hint": "结合代码审查和人工检查来验证改动。", "composer.stop": "停止", "composer.send": "发送",
    "review.title": "代码审查", "review.run": "运行审查", "settings.label": "设置", "settings.title": "配置",
    "settings.tab.models": "CLI 模型", "settings.tab.appearance": "外观", "settings.tab.performance": "性能", "settings.tab.autoModel": "模型选择",
    "appearance.title": "外观", "appearance.copy": "桌面界面的主题和尺寸控制。", "language.title": "语言", "language.copy": "选择 BetterCode 在应用界面和模型回复中使用的语言。", "language.label": "人类语言", "language.help": "BetterCode 会保持代码和文件名不变，但界面文字和 AI 回复会切换到此语言。",
    "theme.title": "主题", "theme.copy": "界面外观。", "font.title": "字体大小", "font.copy": "调整界面字体大小。", "font.scale": "缩放", "font.extra-small": "特小", "font.small": "小", "font.medium": "中", "font.large": "大",
    "welcome.eyebrow": "你好", "welcome.title": "选择你的语言", "welcome.label": "语言", "welcome.continue": "继续",
    "modelPicker.smart": "自动模型选择", "modelPicker.codex": "OpenAI Codex", "modelPicker.claude": "Claude", "modelPicker.gemini": "Gemini", "modelPicker.none": "没有可用的已验证模型",
    "toast.settingsUpdated": "设置已更新", "sidebar.updateVersion": "更新 v{version}", "localModel.auto": "自动", "localModel.installed": "已安装", "localModel.available": "可安装", "localModel.pick": "选择本地模型，或保持自动。", "runtime.installing": "正在安装…", "runtime.login": "正在登录…", "runtime.notInstalled": "未安装", "startup.failed": "启动失败",
    "onboarding.kicker": "欢迎", "onboarding.brandCopy": "本地优先的编码工作区", "onboarding.step1.title": "选择你的语言", "onboarding.step1.copy": "BetterCode 会在应用界面和 AI 回复中使用这门语言。", "onboarding.step1.note": "代码、命令和文件名保持不变。", "onboarding.step2.title": "该聪明时才聪明", "onboarding.step2.copy": "自动模型选择会把每个任务路由到合适的运行时，并为简单任务保留本地快速路径。", "onboarding.step2.feature1": "为审查、调试和实现选择合适的模型。", "onboarding.step2.feature2": "当请求是自包含且安全时，使用本地模型。", "onboarding.step2.feature3": "当重度规划只会拖慢速度时，会直接跳过。", "onboarding.step3.title": "为真实项目工作而设计", "onboarding.step3.copy": "无需离开应用，就能审查代码、运行项目，并整理生成的输出。", "onboarding.step3.feature1": "代码审查页面支持快速、标准和深度模式。", "onboarding.step3.feature2": "项目运行支持实时输出和干净停止。", "onboarding.step3.feature3": "生成文件会绑定到项目，但不会进入仓库。", "onboarding.back": "返回", "onboarding.next": "下一步", "onboarding.start": "开始编码",
  },
  ja: {
    "nav.projects": "プロジェクト", "nav.codeReview": "コードレビュー", "nav.git": "Git", "topbar.tabHistory": "タブ履歴",
    "composer.model": "モデル", "composer.attach": "添付", "composer.placeholder": "指示を書いてください…", "composer.hint": "変更はコードレビューと手動確認で検証します。", "composer.stop": "停止", "composer.send": "送信",
    "review.title": "コードレビュー", "review.run": "レビュー実行", "settings.label": "設定", "settings.title": "構成",
    "settings.tab.models": "CLI モデル", "settings.tab.appearance": "表示", "settings.tab.performance": "性能", "settings.tab.autoModel": "モデル選択",
    "appearance.title": "表示", "appearance.copy": "デスクトップシェルのテーマとサイズ設定。", "language.title": "言語", "language.copy": "BetterCode がアプリとモデル応答で使う言語を選択します。", "language.label": "自然言語", "language.help": "コードやファイル名はそのまま保持し、UI テキストと AI 応答だけをこの言語に切り替えます。",
    "theme.title": "テーマ", "theme.copy": "インターフェースの見た目。", "font.title": "フォントサイズ", "font.copy": "インターフェースの文字サイズを調整します。", "font.scale": "倍率", "font.extra-small": "極小", "font.small": "小", "font.medium": "中", "font.large": "大",
    "welcome.eyebrow": "こんにちは", "welcome.title": "言語を選択してください", "welcome.label": "言語", "welcome.continue": "続ける",
    "modelPicker.smart": "自動モデル選択", "modelPicker.codex": "OpenAI Codex", "modelPicker.claude": "Claude", "modelPicker.gemini": "Gemini", "modelPicker.none": "確認済みモデルがありません",
    "toast.settingsUpdated": "設定を更新しました", "sidebar.updateVersion": "更新 v{version}", "localModel.auto": "自動", "localModel.installed": "インストール済み", "localModel.available": "インストール可能", "localModel.pick": "ローカルモデルを選ぶか、自動のままにしてください。", "runtime.installing": "インストール中…", "runtime.login": "ログイン中…", "runtime.notInstalled": "未インストール", "startup.failed": "起動に失敗しました",
    "onboarding.kicker": "ようこそ", "onboarding.brandCopy": "ローカルファーストのコーディング環境", "onboarding.step1.title": "言語を選んでください", "onboarding.step1.copy": "BetterCode はこの言語をアプリと AI 応答で使います。", "onboarding.step1.note": "コード、コマンド、ファイル名はそのままです。", "onboarding.step2.title": "必要なときだけ賢く", "onboarding.step2.copy": "自動モデル選択は各タスクを適切な実行系に振り分け、簡単な作業にはローカル高速経路を使います。", "onboarding.step2.feature1": "レビュー、デバッグ、実装に合うモデルを選びます。", "onboarding.step2.feature2": "要求が自己完結して安全ならローカルモデルを使います。", "onboarding.step2.feature3": "重い計画が遅くするだけならスキップします。", "onboarding.step3.title": "実際のプロジェクト作業向け", "onboarding.step3.copy": "アプリを離れずにコードレビュー、プロジェクト実行、生成物の整理ができます。", "onboarding.step3.feature1": "クイック、標準、ディープのコードレビューページ。", "onboarding.step3.feature2": "ライブ出力と安全な停止を備えたプロジェクト実行。", "onboarding.step3.feature3": "生成ファイルはプロジェクトに紐づきつつ、リポジトリ外に保たれます。", "onboarding.back": "戻る", "onboarding.next": "次へ", "onboarding.start": "始める",
  },
  ko: {
    "nav.projects": "프로젝트", "nav.codeReview": "코드 리뷰", "nav.git": "Git", "topbar.tabHistory": "탭 기록",
    "composer.model": "모델", "composer.attach": "첨부", "composer.placeholder": "지시를 입력하세요…", "composer.hint": "코드 리뷰와 수동 검토로 변경 사항을 확인하세요.", "composer.stop": "중지", "composer.send": "보내기",
    "review.title": "코드 리뷰", "review.run": "리뷰 실행", "settings.label": "설정", "settings.title": "구성",
    "settings.tab.models": "CLI 모델", "settings.tab.appearance": "모양", "settings.tab.performance": "성능", "settings.tab.autoModel": "모델 선택",
    "appearance.title": "모양", "appearance.copy": "데스크톱 셸의 테마와 크기 설정입니다.", "language.title": "언어", "language.copy": "BetterCode가 앱과 모델 응답에서 사용할 언어를 선택합니다.", "language.label": "사람 언어", "language.help": "BetterCode는 코드와 파일 이름은 그대로 두고, UI 텍스트와 AI 응답만 이 언어로 바꿉니다.",
    "theme.title": "테마", "theme.copy": "인터페이스 모양입니다.", "font.title": "글꼴 크기", "font.copy": "인터페이스 글꼴 크기를 조정합니다.", "font.scale": "배율", "font.extra-small": "매우 작게", "font.small": "작게", "font.medium": "보통", "font.large": "크게",
    "welcome.eyebrow": "안녕하세요", "welcome.title": "언어를 선택하세요", "welcome.label": "언어", "welcome.continue": "계속",
    "modelPicker.smart": "자동 모델 선택", "modelPicker.codex": "OpenAI Codex", "modelPicker.claude": "Claude", "modelPicker.gemini": "Gemini", "modelPicker.none": "검증된 모델이 없습니다",
    "toast.settingsUpdated": "설정이 업데이트되었습니다", "sidebar.updateVersion": "업데이트 v{version}", "localModel.auto": "자동", "localModel.installed": "설치됨", "localModel.available": "설치 가능", "localModel.pick": "로컬 모델을 선택하거나 자동으로 두세요.", "runtime.installing": "설치 중…", "runtime.login": "로그인 진행 중…", "runtime.notInstalled": "설치되지 않음", "startup.failed": "시작 실패",
    "onboarding.kicker": "환영합니다", "onboarding.brandCopy": "로컬 우선 코딩 워크스페이스", "onboarding.step1.title": "언어를 선택하세요", "onboarding.step1.copy": "BetterCode는 앱과 AI 응답에서 이 언어를 사용합니다.", "onboarding.step1.note": "코드, 명령어, 파일 이름은 그대로 유지됩니다.", "onboarding.step2.title": "필요할 때만 똑똑하게", "onboarding.step2.copy": "자동 모델 선택은 각 작업을 맞는 런타임으로 보내고, 간단한 작업에는 로컬 빠른 경로를 유지합니다.", "onboarding.step2.feature1": "리뷰, 디버깅, 구현에 맞는 모델을 고릅니다.", "onboarding.step2.feature2": "요청이 독립적이고 안전할 때 로컬 모델을 사용합니다.", "onboarding.step2.feature3": "무거운 계획이 속도만 늦출 때는 건너뜁니다.", "onboarding.step3.title": "실제 프로젝트 작업을 위해 제작", "onboarding.step3.copy": "앱을 떠나지 않고 코드 리뷰, 프로젝트 실행, 생성 파일 정리를 할 수 있습니다.", "onboarding.step3.feature1": "빠름, 표준, 깊음 모드의 코드 리뷰 페이지.", "onboarding.step3.feature2": "실시간 출력과 깔끔한 중지를 갖춘 프로젝트 실행.", "onboarding.step3.feature3": "생성 파일은 프로젝트에 연결되지만 저장소 밖에 유지됩니다.", "onboarding.back": "뒤로", "onboarding.next": "다음", "onboarding.start": "코딩 시작",
  },
};

const RUNTIME_TEXT_TRANSLATIONS = {
  de: {
    exact: {
      "CLI History": "CLI-Verlauf",
      "Full CLI History": "Vollständiger CLI-Verlauf",
      "History": "Verlauf",
      "Status Timeline": "Statusverlauf",
      "Squashed Diff": "Zusammengefasster Diff",
      "Show Diff": "Diff anzeigen",
      "Hide Diff": "Diff ausblenden",
      "Showing a trimmed diff preview.": "Es wird eine gekürzte Diff-Vorschau angezeigt.",
      "Latest Turn": "Letzte Anfrage",
      "No review history yet.": "Noch kein Review-Verlauf.",
      "Now": "Jetzt",
      "files": "Dateien",
      "Waiting for CLI activity…": "Warte auf CLI-Aktivität…",
      "Showing recent output only.": "Es wird nur die letzte Ausgabe angezeigt.",
      "Processing": "Verarbeitung",
      "Preparing request…": "Anfrage wird vorbereitet…",
      "Selecting model…": "Modell wird ausgewählt…",
      "Local LLM is breaking down the tasks and choosing the best model(s).": "Das lokale LLM analysiert die Aufgaben und wählt die besten Modelle aus.",
      "BetterCode needs a reply to continue.": "BetterCode braucht eine Antwort, um fortzufahren.",
      "No output for {seconds}s. Process may be stalled.": "Seit {seconds}s keine Ausgabe. Der Prozess könnte hängen.",
      "Plan": "Planen",
      "Inspect": "Prüfen",
      "Edit": "Bearbeiten",
      "Validate": "Validieren",
      "Finalize": "Abschließen",
      "Pending": "Ausstehend",
      "Queued": "Eingeplant",
      "Queued.": "Eingeplant.",
      "Blocked": "Blockiert",
      "Running": "Läuft",
      "Done": "Fertig",
      "Error": "Fehler",
      "Waiting": "Wartet",
      "Stopped": "Gestoppt",
      "parallel": "parallel",
      "sequential": "nacheinander",
      "async": "asynchron",
      "active": "aktiv",
      "Heuristic Router": "Heuristischer Router",
      "Local Router": "Lokaler Router",
      "Direct": "Direkt",
      "Local Fast Path": "Lokaler Schnellpfad",
      "general": "Allgemein",
      "implementation": "Implementierung",
      "small edit": "Kleine Änderung",
      "debugging": "Debugging",
      "review": "Review",
      "architecture": "Architektur",
      "Model selected directly.": "Modell direkt ausgewählt.",
      "Selected directly in the model picker.": "Direkt im Modellwähler ausgewählt.",
      "Auto Model Select routed this turn.": "Auto Model Select hat diese Anfrage zugeordnet.",
      "Task looks very small and self-contained, so Auto Model Select picked a cheaper fast-path model.": "Die Aufgabe wirkt sehr klein und in sich geschlossen, daher hat Auto Model Select ein günstigeres Schnellpfad-Modell gewählt.",
      "Task looks like standard coding work, so Auto Model Select picked a balanced model instead of the cheapest or deepest tier.": "Die Aufgabe wirkt wie normale Entwicklungsarbeit, daher hat Auto Model Select ein ausgewogenes Modell statt der günstigsten oder tiefsten Stufe gewählt.",
      "Task looks non-trivial, so Auto Model Select picked a higher-capability model.": "Die Aufgabe wirkt nicht trivial, daher hat Auto Model Select ein leistungsstärkeres Modell gewählt.",
      "Gathering requirements": "Anforderungen erfassen",
      "Pre-processing": "Vorverarbeitung",
      "Task breakdown": "Aufgaben aufteilen",
      "Execute tasks": "Aufgaben ausführen",
      "Validate completion": "Abschluss prüfen",
      "Plan approach": "Vorgehen planen",
      "Implement changes": "Änderungen umsetzen",
      "Planner": "Planung",
      "Execution": "Ausführung",
      "Completion": "Abschluss",
      "Human language rule:": "Sprachregel:",
      "Execution guidance:": "Ausführungsregeln:",
      "Generated file rule:": "Regel für generierte Dateien:",
      "Execution brief:": "Ausführungsüberblick:",
      "Ambiguity handling:": "Umgang mit Unklarheiten:",
      "Relevant recent conversation:": "Relevante letzte Unterhaltung:",
      "Attached file context:": "Angehängter Dateikontext:",
      "Workspace context summary:": "Zusammenfassung des Arbeitsbereich-Kontexts:",
      "Codex-specific guidance:": "Codex-spezifische Hinweise:",
      "Gemini-specific guidance:": "Gemini-spezifische Hinweise:",
      "Use this summary as durable project context. Prefer it over stale older chat details when they conflict.": "Nutze diese Zusammenfassung als dauerhaften Projektkontext. Bevorzuge sie gegenüber veralteten älteren Chat-Details, wenn sie im Konflikt stehen.",
      "- Use the minimum necessary tokens.": "- Verwende nur die minimal nötigen Tokens.",
      "- Read only the files needed for the task.": "- Lies nur die Dateien, die für die Aufgabe nötig sind.",
      "- Avoid repeating the provided context back verbatim.": "- Wiederhole den bereitgestellten Kontext nicht wörtlich.",
      "- Keep plans and explanations brief unless deeper detail is required.": "- Halte Pläne und Erklärungen kurz, außer mehr Tiefe ist wirklich nötig.",
      "- Prefer targeted edits and concise outputs.": "- Bevorzuge gezielte Änderungen und knappe Ausgaben.",
      "- Do not mention missing tests or unrun tests unless it is directly relevant.": "- Erwähne fehlende oder nicht ausgeführte Tests nur, wenn es direkt relevant ist.",
      "- If tests would be valuable, recommend adding them briefly instead of repeating that they were not run.": "- Wenn Tests hilfreich wären, empfehle sie kurz, statt wiederholt zu erwähnen, dass sie nicht gelaufen sind.",
      "- Do not try to write brand-new files directly to the final generated-files directory because the runtime sandbox may block that path.": "- Versuche nicht, komplett neue Dateien direkt in das endgültige generated-files-Verzeichnis zu schreiben, weil die Runtime-Sandbox diesen Pfad blockieren kann.",
      "- Examples of generated outputs: exports, reports, PDFs, CSVs, standalone HTML deliverables, and similar artifacts.": "- Beispiele für generierte Ausgaben: Exporte, Berichte, PDFs, CSVs, eigenständige HTML-Ergebnisse und ähnliche Artefakte.",
      "- If the task is to create or scaffold real project files that belong in the repo, create them normally in the workspace instead.": "- Wenn echte Projektdateien erstellt werden sollen, die ins Repo gehören, lege sie normal im Arbeitsbereich an.",
      "- Modify existing project files in place when needed.": "- Ändere bestehende Projektdateien bei Bedarf direkt an Ort und Stelle.",
      "- If you mention a generated file in your response, use its final absolute path.": "- Wenn du eine generierte Datei in deiner Antwort erwähnst, nutze ihren endgültigen absoluten Pfad.",
      "- Prefer patch-based edits (apply_patch) over full file rewrites.": "- Bevorzuge patch-basierte Änderungen (apply_patch) statt kompletter Dateineuschreibungen.",
      "- Use file search tools before assuming paths or file contents.": "- Nutze Dateisuche, bevor du Pfade oder Inhalte annimmst.",
      "- Do not echo file contents back in your final reply.": "- Gib Dateiinhalte in deiner finalen Antwort nicht einfach wieder.",
      "- Keep the closing summary to one concise paragraph.": "- Halte die abschließende Zusammenfassung auf einen knappen Absatz beschränkt.",
      "Direct answer unless code changes are clearly needed": "Direkte Antwort, sofern Codeänderungen nicht klar nötig sind",
      "Analysis-first response": "Analyse zuerst",
      "Targeted repo changes": "Gezielte Repo-Änderungen",
      "Answer directly and stay focused on the requested outcome.": "Antworte direkt und bleibe auf das gewünschte Ergebnis fokussiert.",
      "Call out concrete risks, regressions, and missing coverage.": "Nenne konkrete Risiken, Regressionen und fehlende Abdeckung.",
      "Return a clear design with practical tradeoffs and next steps.": "Liefere ein klares Design mit praktischen Abwägungen und nächsten Schritten.",
      "Identify the root cause and fix the actual failure path.": "Finde die Ursache und behebe den tatsächlichen Fehlerpfad.",
      "Use the attachment content directly and keep the answer grounded in it.": "Nutze den Inhalt der Anhänge direkt und halte die Antwort daran orientiert.",
      "The request is terse; inspect only the most relevant context before expanding scope.": "Die Anfrage ist knapp; prüfe nur den relevantesten Kontext, bevor du den Umfang erweiterst.",
      "The request may be underspecified; rely on the nearest relevant context, then proceed conservatively.": "Die Anfrage könnte zu ungenau sein; nutze zuerst den nächstliegenden relevanten Kontext und gehe dann vorsichtig vor.",
    },
  },
};

function runtimeTranslationDictionary() {
  return RUNTIME_TEXT_TRANSLATIONS[currentHumanLanguage()] || {};
}

function translateRuntimeExact(text, vars = {}) {
  const dict = runtimeTranslationDictionary().exact || {};
  const template = dict[text] || text;
  return template.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? ""));
}

function localizeRuntimeLine(rawText) {
  const source = String(rawText ?? "");
  const trimmed = source.trim();
  if (!trimmed) {
    return source;
  }

  if (currentHumanLanguage() !== "de") {
    return source;
  }

  const exact = translateRuntimeExact(trimmed);
  if (exact !== trimmed) {
    return source.replace(trimmed, exact);
  }

  const replacements = [
    [/^(\d+)\/(\d+) done$/, (_, done, total) => `${done}/${total} erledigt`],
    [/^\+(\d+) more$/, (_, count) => `+${count} mehr`],
    [/^(.+)\s\/\sLow$/, (_, label) => `${label} / Niedrig`],
    [/^(.+)\s\/\sMedium$/, (_, label) => `${label} / Mittel`],
    [/^(.+)\s\/\sHigh$/, (_, label) => `${label} / Hoch`],
    [/^No output for (\d+)s\. Process may be stalled\.$/, (_, seconds) => `Seit ${seconds}s keine Ausgabe. Der Prozess könnte hängen.`],
    [/^Blocked by: (.+)$/, (_, deps) => `Blockiert durch: ${deps}`],
    [/^Started turn\.$/, () => "Anfrage gestartet."],
    [/^Finished turn\.(.*)$/, (_, suffix) => `Anfrage abgeschlossen.${suffix || ""}`],
    [/^Started session(?: (.+))?\.$/, (_, threadId) => threadId ? `Sitzung ${threadId} gestartet.` : "Sitzung gestartet."],
    [/^Error: (.+)$/, (_, value) => `Fehler: ${value}`],
    [/^Running command: (.+)$/, (_, value) => `Befehl läuft: ${value}`],
    [/^Completed command: (.+) \(exit (\d+)\)$/, (_, value, code) => `Befehl abgeschlossen: ${value} (Exit ${code})`],
    [/^Completed command: (.+)$/, (_, value) => `Befehl abgeschlossen: ${value}`],
    [/^Searching: (.+)$/, (_, value) => `Suche: ${value}`],
    [/^Completed: (.+)$/, (_, value) => `Abgeschlossen: ${value}`],
    [/^Reading file: (.+)$/, (_, value) => `Lese Datei: ${value}`],
    [/^Read file: (.+)$/, (_, value) => `Datei gelesen: ${value}`],
    [/^Updating file: (.+)$/, (_, value) => `Aktualisiere Datei: ${value}`],
    [/^Updated file: (.+)$/, (_, value) => `Datei aktualisiert: ${value}`],
    [/^Using tool: (.+)$/, (_, value) => `Verwende Tool: ${value}`],
    [/^Tool result(?: \((.+)\))?\.$/, (_, status) => status ? `Tool-Ergebnis (${status}).` : "Tool-Ergebnis."],
    [/^Completed response\.$/, () => "Antwort abgeschlossen."],
    [/^Goal:\s*(.+)$/, (_, value) => `Ziel: ${value}`],
    [/^Task type:\s*(.+)$/, (_, value) => `Aufgabentyp: ${localizeRuntimeLine(value)}`],
    [/^Execution mode:\s*(.+)$/, (_, value) => `Ausführungsmodus: ${localizeRuntimeLine(value)}`],
    [/^Success criteria:\s*(.+)$/, (_, value) => `Erfolgskriterien: ${localizeRuntimeLine(value)}`],
    [/^Focus files:\s*(.+)$/, (_, value) => `Fokusdateien: ${value === "None" ? "Keine" : value}`],
    [/^Attachments:\s*(.+)$/, (_, value) => `Anhänge: ${value === "None" ? "Keine" : value}`],
    [/^File:\s*(.+)$/, (_, value) => `Datei: ${value}`],
    [/^Generated file staging directory:\s*(.+)$/, (_, value) => `Staging-Verzeichnis für generierte Dateien: ${value}`],
    [/^Generated files directory:\s*(.+)$/, (_, value) => `Verzeichnis für generierte Dateien: ${value}`],
    [/^- Write all user-facing prose in (.+) \((.+)\)\.$/, (_, label, nativeLabel) => `- Schreibe alle benutzerseitigen Texte in ${label} (${nativeLabel}).`],
    [/^- If you ask a question, ask it in (.+)\.$/, (_, label) => `- Wenn du eine Frage stellst, stelle sie auf ${label}.`],
    [/^- For generated outputs that should live outside the repo, create them in this staging directory inside the workspace: (.+)$/, (_, value) => `- Für generierte Ausgaben, die außerhalb des Repos liegen sollen, erstelle sie in diesem Staging-Verzeichnis im Arbeitsbereich: ${value}`],
    [/^- BetterCode will move those staged generated files after the turn into the final generated-files directory: (.+)$/, (_, value) => `- BetterCode verschiebt diese gestagten generierten Dateien nach der Anfrage in das endgültige generated-files-Verzeichnis: ${value}`],
    [/^- Make the needed changes with minimal scope, starting from (.+)\.$/, (_, value) => `- Nimm die nötigen Änderungen mit minimalem Umfang vor, beginnend bei ${value}.`],
    [/^\[Omitted — total attachment budget \((.+)\) reached\]$/, (_, value) => `[Ausgelassen — gesamtes Anhangsbudget (${value}) erreicht]`],
  ];

  for (const [pattern, replacer] of replacements) {
    if (pattern.test(trimmed)) {
      return source.replace(trimmed, trimmed.replace(pattern, replacer));
    }
  }

  return source;
}

function localizeRuntimeBlock(rawText) {
  return String(rawText ?? "")
    .split("\n")
    .map((line) => localizeRuntimeLine(line))
    .join("\n");
}

// In-flight guards — prevent duplicate concurrent requests on the same action
const _inflight = { gitRefresh: false, runDetect: false };

// Per-render AbortControllers — abort old dynamic listeners before each re-render
const _renderControllers = {};

// Focus trap registry — each open dialog stores its cleanup fn here
const _trapFocusCleanup = {};

// RAF throttle for high-frequency live chat renders (terminal_chunk, task_state)
let _liveChatRafPending = false;
let _liveChatRafWorkspace = null;
let _liveChatRenderTimer = null;
let _liveChatLastRenderAt = 0;
const LIVE_RENDER_MIN_INTERVAL_MS = 48;
const LIVE_RENDER_RAW_MIN_INTERVAL_MS = 96;
const LIVE_TERMINAL_MAX_CHARS = 60000;
const LIVE_TERMINAL_MAX_LINES = 800;
const LIVE_TERMINAL_RAW_MAX_CHARS = 24000;
const LIVE_TERMINAL_RAW_MAX_LINES = 320;
const LIVE_TERMINAL_MAX_COLUMNS = 240;

// ---------------------------------------------------------------------------
// xterm.js live terminal registry
// Each workspace gets one persistent Terminal instance while a live chat runs.
// The element is re-parented into the placeholder after every innerHTML update.
// ---------------------------------------------------------------------------
const _xtermInstances = new Map(); // workspaceId -> { terminal, fitAddon, el }

const XTERM_THEME = {
  background:    "#1e1e1e",
  foreground:    "#e2e8f0",
  cursor:        "#38bdf8",
  cursorAccent:  "#1e1e1e",
  selectionBackground: "rgba(56,189,248,0.25)",
  black:         "#1a1c1e",
  red:           "#f87171",
  green:         "#4ade80",
  yellow:        "#facc15",
  blue:          "#60a5fa",
  magenta:       "#c084fc",
  cyan:          "#38bdf8",
  white:         "#e2e8f0",
  brightBlack:   "#4b5563",
  brightRed:     "#fca5a5",
  brightGreen:   "#86efac",
  brightYellow:  "#fde047",
  brightBlue:    "#93c5fd",
  brightMagenta: "#d8b4fe",
  brightCyan:    "#7dd3fc",
  brightWhite:   "#f8fafc",
};

function _xtermAvailable() {
  return typeof window !== "undefined" && window.Terminal && window.FitAddon;
}

function _getOrCreateXterm(workspaceId) {
  if (_xtermInstances.has(workspaceId)) {
    return _xtermInstances.get(workspaceId);
  }
  if (!_xtermAvailable()) {
    return null;
  }
  const terminal = new window.Terminal({
    theme: XTERM_THEME,
    fontFamily: "ui-monospace, 'Cascadia Code', 'Fira Code', 'JetBrains Mono', Menlo, Monaco, Consolas, monospace",
    fontSize: 13,
    lineHeight: 1.5,
    cursorBlink: true,
    cursorStyle: "bar",
    scrollback: 5000,
    convertEol: true,
    allowProposedApi: true,
  });
  const fitAddon = new window.FitAddon.FitAddon();
  terminal.loadAddon(fitAddon);

  const el = document.createElement("div");
  el.className = "xterm-live-wrap";
  terminal.open(el);

  // Attempt initial fit — will be re-fitted after mounting
  try { fitAddon.fit(); } catch (_) {}

  const instance = { terminal, fitAddon, el };
  _xtermInstances.set(workspaceId, instance);
  return instance;
}

function _disposeXterm(workspaceId) {
  const instance = _xtermInstances.get(workspaceId);
  if (!instance) {
    return;
  }
  try { instance.terminal.dispose(); } catch (_) {}
  _xtermInstances.delete(workspaceId);
}

function _mountXtermToPlaceholder(progressNode, workspaceId, embedded = true) {
  if (!workspaceId || !progressNode) {
    return;
  }
  const placeholder = progressNode.querySelector(`[data-xterm-ws="${workspaceId}"]`);
  if (!placeholder) {
    return;
  }
  const instance = _getOrCreateXterm(workspaceId);
  if (!instance) {
    return;
  }
  const { el, fitAddon } = instance;
  if (embedded) {
    el.classList.add("embedded");
  } else {
    el.classList.remove("embedded");
  }
  if (placeholder !== el.parentElement) {
    placeholder.appendChild(el);
  }
  try { fitAddon.fit(); } catch (_) {}
}
const MESSAGE_CHANGE_SUMMARY_MAX_FILES = 8;
const MESSAGE_CHANGE_MAX_DIFF_CHARS = 160000;
const MESSAGE_CHANGE_MAX_DIFF_LINES = 2400;
const INITIAL_WORKSPACE_MESSAGE_PAGE_SIZE = 40;
const MESSAGE_RENDER_PROGRESSIVE_THRESHOLD = 24;
const MESSAGE_RENDER_BATCH_SIZE = 12;
const TAB_CHAT_CACHE_MAX_TABS = 5;
const TAB_CHAT_CACHE_MAX_MESSAGES = INITIAL_WORKSPACE_MESSAGE_PAGE_SIZE;
const TAB_CHAT_CACHE_MAX_LOG_LINES = 80;
const TAB_CHAT_CACHE_MAX_TERMINAL_CHARS = 24000;
const TAB_CHAT_CACHE_MAX_CHANGE_FILES = 8;
const TAB_CHAT_CACHE_MAX_DIFF_PREVIEW_CHARS = 4000;
let _messageRenderVersion = 0;

function scheduleLiveChatRender(workspace, { immediate = false } = {}) {
  _liveChatRafWorkspace = workspace;
  if (_liveChatRenderTimer) {
    clearTimeout(_liveChatRenderTimer);
    _liveChatRenderTimer = null;
  }
  if (_liveChatRafPending && !immediate) {
    return;
  }
  const queueFrame = () => {
    _liveChatRafPending = true;
    requestAnimationFrame(() => {
      _liveChatRafPending = false;
      _liveChatLastRenderAt = Date.now();
      renderLiveChatState(currentWorkspace());
    });
  };
  if (immediate) {
    queueFrame();
    return;
  }
  const elapsed = Date.now() - _liveChatLastRenderAt;
  const liveChat = activeLiveChatForWorkspace(workspace);
  const renderInterval = (
    liveChat?.terminalMode === "raw"
      ? LIVE_RENDER_RAW_MIN_INTERVAL_MS
      : LIVE_RENDER_MIN_INTERVAL_MS
  );
  const delay = Math.max(0, renderInterval - elapsed);
  if (delay > 0) {
    _liveChatRenderTimer = window.setTimeout(() => {
      _liveChatRenderTimer = null;
      queueFrame();
    }, delay);
    return;
  }
  queueFrame();
}

// RAF throttle for run-terminal auto-scroll
let _runScrollPending = false;
function scheduleRunScroll() {
  if (!_runScrollPending) {
    _runScrollPending = true;
    requestAnimationFrame(() => {
      _runScrollPending = false;
      const terminal = document.getElementById("run-terminal");
      if (terminal) terminal.scrollTop = terminal.scrollHeight;
    });
  }
}

function generatedFilesBadgeCount(workspace) {
  if (!workspace?.has_generated_files) {
    return 0;
  }
  const total = Number(workspace.generated_files_count || 0);
  const seen = Number(workspace.generated_files_seen_count || 0);
  return Math.max(0, total - seen);
}

function optimisticallyMarkGeneratedFilesSeen(workspaceId) {
  if (!workspaceId) {
    return;
  }
  state.workspaces = (state.workspaces || []).map((workspace) => {
    if (workspace.id !== workspaceId) {
      return workspace;
    }
    const total = Number(workspace.generated_files_count || 0);
    const seen = Number(workspace.generated_files_seen_count || 0);
    return {
      ...workspace,
      generated_files_seen_count: Math.max(seen, total),
    };
  });
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = typeof payload === "string" ? payload : payload.detail || "Request failed.";
    throw new Error(detail);
  }

  return payload;
}

let _toastIdSeq = 0;

function showToast(message, { persist = false, copyText = null } = {}) {
  const id = ++_toastIdSeq;
  const container = document.getElementById("toast-container");
  if (!container) return id;

  const el = document.createElement("div");
  el.className = "toast toast-enter";
  el.dataset.toastId = id;
  el.setAttribute("role", "status");

  const msgSpan = document.createElement("span");
  msgSpan.className = "toast-msg";
  msgSpan.textContent = message;
  el.appendChild(msgSpan);

  if (copyText) {
    const copyBtn = document.createElement("button");
    copyBtn.className = "toast-copy-btn";
    copyBtn.textContent = "Copy";
    copyBtn.dataset.toastCopy = copyText;
    el.appendChild(copyBtn);
  }

  const dismissBtn = document.createElement("button");
  dismissBtn.className = "toast-dismiss-btn";
  dismissBtn.setAttribute("aria-label", "Dismiss");
  dismissBtn.textContent = "×";
  dismissBtn.dataset.toastId = id;
  el.appendChild(dismissBtn);

  container.appendChild(el);
  requestAnimationFrame(() => el.classList.replace("toast-enter", "toast-visible"));

  if (!persist) {
    setTimeout(() => dismissToast(id), 4000);
  }
  return id;
}

function dismissToast(id) {
  const el = document.querySelector(`.toast[data-toast-id="${id}"]`);
  if (!el) return;
  el.classList.replace("toast-visible", "toast-exit");
  el.addEventListener("animationend", () => el.remove(), { once: true });
  // fallback if animationend never fires (e.g. reduced-motion)
  setTimeout(() => el.remove(), 300);
}

function availableHumanLanguages() {
  return Array.isArray(state.appInfo?.languages?.supported) && state.appInfo.languages.supported.length
    ? state.appInfo.languages.supported
    : FALLBACK_HUMAN_LANGUAGES;
}

function currentHumanLanguage() {
  return state.appInfo?.settings?.human_language
    || state.appInfo?.languages?.current
    || FALLBACK_HUMAN_LANGUAGES[0].code;
}

function t(key, vars = {}, languageOverride = null) {
  const language = languageOverride || currentHumanLanguage();
  const dictionary = UI_STRINGS[language] || UI_STRINGS.en;
  let text = dictionary[key] || UI_STRINGS.en[key] || key;
  return text.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? ""));
}

function renderHumanLanguageOptions(select, value) {
  if (!select) {
    return;
  }
  select.innerHTML = availableHumanLanguages().map((language) => (
    `<option value="${escapeHtml(language.code)}">${escapeHtml(language.native_label)} · ${escapeHtml(language.label)}</option>`
  )).join("");
  select.value = value || currentHumanLanguage();
}

function applyLocalizedUi() {
  const language = currentHumanLanguage();
  document.documentElement.lang = language;

  const setText = (id, key, vars = {}) => {
    const node = document.getElementById(id);
    if (node) {
      node.textContent = t(key, vars);
    }
  };

  setText("projects-section-title", "nav.projects");
  setText("review-section-title", "nav.codeReview");
  setText("git-section-title", "nav.git");
  setText("tab-history-button", "topbar.tabHistory");
  setText("composer-model-label", "composer.model");
  setText("composer-mode-label", "composer.mode");
  setText("attach-button", "composer.attach");
  setText("composer-hint", "composer.hint");
  setText("chat-stop-button", "composer.stop");
  setText("send-button", "composer.send");
  setText("review-topbar-label", "review.title");
  setText("review-open-chat-button", "review.run");
  setText("settings-topbar-label", "settings.label");
  setText("settings-topbar-title", "settings.title");
  setText("settings-tab-models", "settings.tab.models");
  setText("settings-tab-appearance", "settings.tab.appearance");
  setText("settings-tab-performance", "settings.tab.performance");
  setText("appearance-panel-title", "appearance.title");
  setText("appearance-panel-copy", "appearance.copy");
  setText("language-settings-title", "language.title");
  setText("language-settings-copy", "language.copy");
  setText("settings-human-language-label", "language.label");
  setText("settings-human-language-help", "language.help");
  setText("theme-settings-title", "theme.title");
  setText("theme-settings-copy", "theme.copy");
  setText("font-size-settings-title", "font.title");
  setText("font-size-settings-copy", "font.copy");
  setText("font-size-scale-label", "font.scale");
  setText("onboarding-brand-copy", "onboarding.brandCopy");

  const chatInput = document.getElementById("chat-input");
  if (chatInput) {
    chatInput.placeholder = t("composer.placeholder");
  }

  renderHumanLanguageOptions(document.getElementById("settings-human-language"), language);
  renderOnboarding();
}

function onboardingLanguage() {
  return state.onboarding.language || currentHumanLanguage();
}

function onboardingLocalModelState() {
  const availableLocalModels = localPreprocessModelsBySize(state.appInfo?.selector?.available_local_models);
  const selectedLocalModel = state.appInfo?.settings?.local_preprocess_model || "";
  const validModelIds = new Set(availableLocalModels.map((model) => model.id));
  const draftModelId = validModelIds.has(state.localPreprocessDraftModelId) ? state.localPreprocessDraftModelId : "";
  const selectedModelId = draftModelId || (validModelIds.has(selectedLocalModel) ? selectedLocalModel : (availableLocalModels[0]?.id || ""));
  return {
    availableLocalModels,
    selectedModelId,
    selectedCandidate: availableLocalModels.find((model) => model.id === selectedModelId) || null,
    activeCandidate: availableLocalModels.find((model) => model.id === selectedLocalModel) || null,
    selectorInstalled: Boolean(state.appInfo?.selector?.installed),
  };
}

function onboardingRuntimeCardsMarkup() {
  const runtimeDefinitions = [
    {
      id: "codex",
      title: "Codex CLI",
      copy: "Uses your local codex install, login session, and model access.",
      provider: "openai",
    },
    {
      id: "cursor",
      title: "Cursor CLI",
      copy: "Uses your local cursor-agent install with browser login or a saved Cursor API key.",
      provider: "cursor",
    },
    {
      id: "claude",
      title: "Claude CLI",
      copy: "Uses your local claude install with terminal login or a saved Anthropic API key.",
      provider: "anthropic",
    },
    {
      id: "gemini",
      title: "Gemini CLI",
      copy: "Uses your local Gemini CLI and its Google-authenticated session when available.",
      provider: "google",
    },
  ];

  return `
    <div class="onboarding-runtime-grid">
      ${runtimeDefinitions.map((definition) => {
        const runtime = state.appInfo?.runtimes?.[definition.id] || {};
        const job = runtime?.job;
        const jobRunning = job?.status === "running";
        const available = Boolean(runtime?.available);
        const configured = Boolean(runtime?.configured);
        const statusText = jobRunning
          ? (job?.action === "install" ? t("runtime.installing") : t("runtime.login"))
          : (available ? (runtime?.version || t("localModel.installed")) : t("runtime.notInstalled"));
        const accessText = jobRunning ? (job?.message || "Working...") : (runtime?.access_label || "Not configured");
        const buttons = [];

        if (!available) {
          buttons.push(`
            <button
              type="button"
              class="secondary-button"
              data-onboarding-runtime-action="install"
              data-runtime="${escapeHtml(definition.id)}"
              ${jobRunning ? "disabled" : ""}
            >${escapeHtml(jobRunning && job?.action === "install" ? "Installing..." : "Install Latest")}</button>
          `);
        } else if (configured) {
          buttons.push(`
            <button
              type="button"
              class="secondary-button"
              data-onboarding-runtime-action="logout"
              data-runtime="${escapeHtml(definition.id)}"
              ${jobRunning ? "disabled" : ""}
            >Logout</button>
          `);
        } else {
          buttons.push(`
            <button
              type="button"
              class="secondary-button"
              data-onboarding-runtime-action="login"
              data-runtime="${escapeHtml(definition.id)}"
              ${jobRunning ? "disabled" : ""}
            >${escapeHtml(jobRunning && job?.action === "login" ? "Logging In..." : "Login")}</button>
          `);
          buttons.push(`
            <button
              type="button"
              class="secondary-button"
              data-onboarding-runtime-action="key"
              data-provider="${escapeHtml(runtime?.provider || definition.provider)}"
              ${jobRunning ? "disabled" : ""}
            >Add Key</button>
          `);
        }

        return `
          <article class="onboarding-runtime-card">
            <div class="onboarding-runtime-card-head">
              <div>
                <div class="onboarding-runtime-card-title">${escapeHtml(definition.title)}</div>
                <div class="onboarding-runtime-card-copy">${escapeHtml(definition.copy)}</div>
              </div>
              <div class="runtime-status ${available ? "available" : "missing"}">${escapeHtml(statusText)}</div>
            </div>
            <div class="runtime-access ${configured ? "configured" : "missing"}">${escapeHtml(accessText)}</div>
            <div class="inline-actions onboarding-runtime-actions">
              ${buttons.join("")}
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

async function handleOnboardingLocalModelAction(button) {
  const { selectedCandidate, activeCandidate, selectorInstalled } = onboardingLocalModelState();
  if (!selectorInstalled) {
    await openExternalUrl("https://ollama.com/download");
    return;
  }
  if (!selectedCandidate) {
    showToast("Pick a local model first.");
    return;
  }
  if (selectedCandidate.installed) {
    if (activeCandidate?.id === selectedCandidate.id) {
      showToast("That local model is already active.");
      return;
    }
    setButtonPending(button, true, "Switching...");
    try {
      await updateAppSettings({ local_preprocess_model: selectedCandidate.id }, { showSuccessToast: false });
      state.localPreprocessDraftModelId = selectedCandidate.id;
      showToast("Local model updated.");
    } catch (error) {
      showToast(error.message);
      setButtonPending(button, false);
    }
    return;
  }
  openLocalModelInstallDialog(selectedCandidate.id);
}

async function handleOnboardingRuntimeAction(button) {
  const action = button.dataset.onboardingRuntimeAction || "";
  const runtime = button.dataset.runtime || "";
  const provider = button.dataset.provider || "";

  if (action === "key") {
    openAuthDialog(provider);
    return;
  }
  if (!runtime) {
    return;
  }
  if (action === "install") {
    setButtonPending(button, true, "Starting...");
    try {
      await installRuntime(runtime);
    } catch (error) {
      showToast(error.message);
      setButtonPending(button, false);
    }
    return;
  }
  if (action === "login") {
    setButtonPending(button, true, "Starting...");
    try {
      await loginRuntime(runtime);
      openAccountDialog(runtime);
    } catch (error) {
      showToast(error.message);
      setButtonPending(button, false);
    }
    return;
  }
  if (action === "logout") {
    setButtonPending(button, true, "Logging Out...");
    try {
      await logoutRuntime(runtime);
      await loadVerifiedModels();
    } catch (error) {
      showToast(error.message);
      setButtonPending(button, false);
    }
  }
}

function renderOnboarding() {
  const overlay = document.getElementById("onboarding-overlay");
  const body = document.getElementById("onboarding-body");
  const visual = document.getElementById("onboarding-visual");
  const stepper = document.getElementById("onboarding-stepper");
  const title = document.getElementById("onboarding-title");
  const copy = document.getElementById("onboarding-copy");
  const kicker = document.getElementById("onboarding-kicker");
  const progress = document.getElementById("onboarding-progress");
  const nextButton = document.getElementById("onboarding-next");
  const backButton = document.getElementById("onboarding-back");
  if (!overlay || !body || !visual || !stepper || !title || !copy || !kicker || !progress || !nextButton || !backButton) {
    return;
  }

  overlay.classList.toggle("hidden", !state.onboarding.open);
  overlay.setAttribute("aria-hidden", state.onboarding.open ? "false" : "true");
  document.body.classList.toggle("onboarding-open", state.onboarding.open);
  if (!state.onboarding.open) {
    return;
  }

  const total = 5;
  const step = Math.max(0, Math.min(total - 1, Number(state.onboarding.step) || 0));
  const language = onboardingLanguage();
  document.documentElement.lang = language;
  title.textContent = t(`onboarding.step${step + 1}.title`, {}, language);
  copy.textContent = t(`onboarding.step${step + 1}.copy`, {}, language);
  kicker.textContent = t("onboarding.kicker", {}, language);
  progress.textContent = `${step + 1} / ${total}`;
  backButton.classList.toggle("hidden", step === 0);
  backButton.textContent = t("onboarding.back", {}, language);
  nextButton.textContent = step === total - 1
    ? t("onboarding.start", {}, language)
    : t("onboarding.next", {}, language);
  const brandCopy = document.getElementById("onboarding-brand-copy");
  if (brandCopy) {
    brandCopy.textContent = t("onboarding.brandCopy", {}, language);
  }

  stepper.innerHTML = Array.from({ length: total }, (_, index) => (
    `<span class="onboarding-step-dot ${index === step ? "active" : ""}"></span>`
  )).join("");

  if (step === 0) {
    body.innerHTML = `
      <div class="onboarding-note">${escapeHtml(t("onboarding.step1.note", {}, language))}</div>
    `;
    visual.innerHTML = `
      <div class="onboarding-language-cloud">
        ${availableHumanLanguages().map((entry) => `<button class="onboarding-chip ${entry.code === language ? "active" : ""}" data-code="${escapeHtml(entry.code)}">${escapeHtml(entry.native_label)}</button>`).join("")}
      </div>
    `;
  } else if (step === 1) {
    body.innerHTML = `
      <div class="onboarding-feature-list">
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step2.feature1", {}, language))}</div>
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step2.feature2", {}, language))}</div>
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step2.feature3", {}, language))}</div>
      </div>
    `;
    visual.innerHTML = `
      <div class="onboarding-processing-card">
        <div class="onboarding-processing-line active"></div>
        <div class="onboarding-processing-line active short"></div>
        <div class="onboarding-processing-line"></div>
        <div class="onboarding-processing-stack">
          <span class="onboarding-processing-pill active"></span>
          <span class="onboarding-processing-pill active"></span>
          <span class="onboarding-processing-pill"></span>
        </div>
      </div>
    `;
  } else if (step === 2) {
    body.innerHTML = `
      <div class="onboarding-feature-list">
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step3.feature1", {}, language))}</div>
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step3.feature2", {}, language))}</div>
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step3.feature3", {}, language))}</div>
      </div>
    `;
    visual.innerHTML = `
      <div class="onboarding-feature-grid">
        <div class="onboarding-feature-card">${escapeHtml(t("nav.codeReview", {}, language))}</div>
        <div class="onboarding-feature-card">${escapeHtml(t("nav.projects", {}, language))}</div>
        <div class="onboarding-feature-card">${escapeHtml(t("nav.git", {}, language))}</div>
      </div>
    `;
  } else if (step === 3) {
    const {
      availableLocalModels,
      selectedModelId,
      selectedCandidate,
      activeCandidate,
      selectorInstalled,
    } = onboardingLocalModelState();
    let actionLabel = "Select a Model";
    let actionDisabled = false;
    if (!selectorInstalled) {
      actionLabel = "Download Ollama";
    } else if (!selectedCandidate) {
      actionDisabled = true;
    } else if (selectedCandidate.installed && activeCandidate?.id === selectedCandidate.id) {
      actionLabel = "Active Model";
      actionDisabled = true;
    } else if (selectedCandidate.installed) {
      actionLabel = "Use This Model";
    } else {
      actionLabel = "Install with Ollama";
    }

    body.innerHTML = `
      <div class="onboarding-feature-list">
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step4.feature1", {}, language))}</div>
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step4.feature2", {}, language))}</div>
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step4.feature3", {}, language))}</div>
      </div>
    `;
    visual.innerHTML = `
      <div class="onboarding-setup-stack">
        ${availableLocalModels.length ? `
          <div class="onboarding-setup-grid">
            ${availableLocalModels.map((model) => `
              <button
                type="button"
                class="onboarding-setup-card ${model.id === selectedModelId ? "active" : ""}"
                data-onboarding-local-model-id="${escapeHtml(model.id)}"
              >
                <div class="onboarding-setup-card-head">
                  <div class="onboarding-setup-card-title">${escapeHtml(model.label || model.id)}</div>
                  <div class="onboarding-setup-card-meta">${escapeHtml(localPreprocessSizeLabel(model))}</div>
                </div>
                <div class="onboarding-setup-card-copy">${escapeHtml(model.installed ? "Installed locally" : "Available to install")}</div>
              </button>
            `).join("")}
          </div>
        ` : `
          <div class="onboarding-empty-card">
            <div class="onboarding-empty-title">${escapeHtml(selectorInstalled ? "No local models available yet" : "Local setup uses Ollama")}</div>
            <div class="onboarding-empty-copy">${escapeHtml(selectorInstalled
              ? "Finish onboarding now and come back in Settings > Performance if you want to install a local model later."
              : "Install Ollama first, then BetterCode can download and switch local models for simple on-device tasks."
            )}</div>
          </div>
        `}
        ${localPreprocessStatusMarkup(selectedCandidate, activeCandidate)}
        <button
          type="button"
          class="primary-button"
          data-onboarding-local-model-action="primary"
          ${actionDisabled ? "disabled" : ""}
        >${escapeHtml(actionLabel)}</button>
      </div>
    `;
  } else {
    body.innerHTML = `
      <div class="onboarding-feature-list">
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step5.feature1", {}, language))}</div>
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step5.feature2", {}, language))}</div>
        <div class="onboarding-feature-item">${escapeHtml(t("onboarding.step5.feature3", {}, language))}</div>
      </div>
    `;
    visual.innerHTML = onboardingRuntimeCardsMarkup();
  }
}

function openOnboarding() {
  state.onboarding.open = true;
  state.onboarding.step = 0;
  state.onboarding.language = currentHumanLanguage();
  renderOnboarding();
}

function closeOnboarding() {
  state.onboarding.open = false;
  renderOnboarding();
}

function maybeOpenOnboarding() {
  if (state.appInfo?.languages?.needs_setup) {
    openOnboarding();
  }
}

function ensureDesktopBridge() {
  if (state.desktopBridgePromise) {
    return state.desktopBridgePromise;
  }

  state.desktopBridgePromise = new Promise((resolve) => {
    if (!window.qt?.webChannelTransport || typeof window.QWebChannel !== "function") {
      resolve(null);
      return;
    }

    try {
      new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
        resolve(channel?.objects?.bettercodeDesktopBridge || null);
      });
    } catch {
      resolve(null);
    }
  });

  return state.desktopBridgePromise;
}

async function initWindowChrome() {
  const bridge = await ensureDesktopBridge();
  if (!bridge || typeof bridge.getPlatform !== "function") return;

  let platform;
  try {
    platform = await bridge.getPlatform();
  } catch {
    return;
  }

  document.body.classList.add(`platform-${platform}`);

  const controls = document.getElementById("window-controls");
  const controlsHost = document.getElementById("sidebar-window-row");
  if (controls) {
    if ((platform === "macos" || platform === "linux") && controlsHost && controls.parentElement !== controlsHost) {
      controlsHost.appendChild(controls);
    } else if (platform === "windows" && controls.parentElement !== document.body) {
      document.body.appendChild(controls);
    }
  }

  // Wire up custom window controls
  {
    document.getElementById("wc-minimize")?.addEventListener("click", () => {
      bridge.minimizeWindow?.();
    });
    document.getElementById("wc-maximize")?.addEventListener("click", () => {
      bridge.maximizeRestoreWindow?.();
    });
    document.getElementById("wc-close")?.addEventListener("click", () => {
      requestWindowClose();
    });

    // Update maximize icon when window state changes
    const updateMaxIcon = async () => {
      const isMax = await bridge.isWindowMaximized?.();
      const btn = document.getElementById("wc-maximize");
      if (!btn) return;
      // Two overlapping squares when maximized, single square when normal
      btn.innerHTML = isMax
        ? `<svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true"><rect x="2" y="0" width="8" height="8" stroke="currentColor"/><rect x="0" y="2" width="8" height="8" stroke="currentColor" fill="var(--bg)"/></svg>`
        : `<svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true"><rect x="0.5" y="0.5" width="9" height="9" stroke="currentColor"/></svg>`;
    };
    window.addEventListener("resize", updateMaxIcon);
    if (platform !== "macos") {
      updateMaxIcon();
    }
  }

  const dragRegions = document.querySelectorAll("[data-window-drag-region]");
  if (dragRegions.length) {
    const endDrag = () => bridge.endWindowDrag?.();
    document.addEventListener("mouseup", endDrag);
    window.addEventListener("blur", endDrag);
    dragRegions.forEach((dragRegion) => {
      dragRegion.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        if (e.target.closest("button, input, textarea, select, a, .window-controls, [role=\"button\"], [data-settings-target], .workspace-tabs, .workspace-tab, .settings-tabs, .settings-tab")) return;
        e.preventDefault();
        bridge.startWindowDrag?.();
      });
    });
  }
}

async function requestWindowClose() {
  const bridge = await ensureDesktopBridge();
  if (bridge && typeof bridge.closeWindow === "function") {
    try {
      await bridge.closeWindow();
      return true;
    } catch {
      // Fall through to browser behavior.
    }
  }
  try {
    window.close();
    return true;
  } catch {
    return false;
  }
}

async function openExternalUrl(url) {
  const target = String(url || "").trim();
  if (!target) {
    return false;
  }
  const bridge = await ensureDesktopBridge();
  if (bridge && typeof bridge.openExternalUrl === "function") {
    try {
      return Boolean(await bridge.openExternalUrl(target));
    } catch (_) {
      // Fall through to browser behavior.
    }
  }
  window.open(target, "_blank", "noopener,noreferrer");
  return true;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function setButtonPending(button, pending, loadingText = "") {
  if (!button) {
    return;
  }

  if (pending) {
    if (!button.dataset.originalHtml) {
      button.dataset.originalHtml = button.innerHTML;
    }
    button.classList.add("button-pending");
    button.disabled = true;
    if (loadingText) {
      button.textContent = loadingText;
    }
    return;
  }

  if (button.dataset.originalHtml) {
    button.innerHTML = button.dataset.originalHtml;
    delete button.dataset.originalHtml;
  }
  button.classList.remove("button-pending");
  button.disabled = false;
}

function formatTimestamp(value) {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return new Intl.DateTimeFormat([], {
    hour: "numeric",
    minute: "2-digit"
  }).format(date);
}

function formatDateTime(value) {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return new Intl.DateTimeFormat([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(date);
}

function formatFileSize(value) {
  const size = Number(value);
  if (!Number.isFinite(size) || size <= 0) {
    return "0 B";
  }
  if (size < 1024) {
    return `${Math.round(size)} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(size >= 10 * 1024 ? 0 : 1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(size >= 10 * 1024 * 1024 ? 0 : 1)} MB`;
}

function applyThemeLogos(theme) {
  const logoPath = LIGHT_THEMES.has(theme) ? DARK_LOGO_PATH : LIGHT_LOGO_PATH;
  document.querySelectorAll("[data-theme-logo]").forEach((node) => {
    if (node.getAttribute("src") !== logoPath) {
      node.setAttribute("src", logoPath);
    }
  });
}

function applyTheme(theme) {
  const allowed = new Set(["dark", "midnight", "light", "dawn", "sage"]);
  state.theme = allowed.has(theme) ? theme : "dark";
  document.body.dataset.theme = state.theme;
  localStorage.setItem("bettercode-theme", state.theme);
  applyThemeLogos(state.theme);
  document.querySelectorAll(".theme-option").forEach((button) => {
    button.classList.toggle("active", button.dataset.themeOption === state.theme);
  });
}

function applyFontSize(fontSize) {
  const allowed = new Set(["extra-small", "small", "medium", "large"]);
  const scaleMap = {
    "extra-small": "0.82",
    "small": "0.92",
    "medium": "1",
    "large": "1.24",
  };
  state.fontSize = allowed.has(fontSize) ? fontSize : "medium";
  document.documentElement.style.setProperty("--font-scale", scaleMap[state.fontSize] || "1");
  document.documentElement.dataset.fontSize = state.fontSize;
  if (document.body) {
    document.body.dataset.fontSize = state.fontSize;
  }
  localStorage.setItem("bettercode-font-size", state.fontSize);
  renderFontSizeControl();
}

function renderFontSizeControl() {
  const slider = document.getElementById("font-size-slider");
  const current = document.getElementById("font-size-current");
  if (!slider || !current) {
    return;
  }

  const labels = {
    "extra-small": { value: "0", pct: "0%",      label: t("font.extra-small") },
    "small":       { value: "1", pct: "33.33%",  label: t("font.small") },
    "medium":      { value: "2", pct: "66.67%",  label: t("font.medium") },
    "large":       { value: "3", pct: "100%",    label: t("font.large") }
  };
  const active = labels[state.fontSize] || labels.medium;
  slider.value = active.value;
  slider.style.setProperty("--slider-fill", active.pct);
  current.textContent = active.label;

  document.querySelectorAll(".font-size-scale span").forEach((span) => {
    span.classList.toggle("active", span.dataset.size === state.fontSize);
  });
}

function localPreprocessOptionLabel(model) {
  const parts = [model?.label || model?.id || "Unknown model"];
  if (
    Number.isFinite(Number(model?.size_gb))
    && Number(model.size_gb) > 0
    && !/\bGB\)/.test(String(model?.label || ""))
  ) {
    parts.push(`${Number(model.size_gb).toFixed(1)} GB`);
  }
  parts.push(model?.installed ? t("localModel.installed") : t("localModel.available"));
  return parts.join(" • ");
}

function localPreprocessModelsBySize(models) {
  return [...(Array.isArray(models) ? models : [])].sort((left, right) => {
    const leftSize = Number.isFinite(Number(left?.size_gb)) ? Number(left.size_gb) : Number.POSITIVE_INFINITY;
    const rightSize = Number.isFinite(Number(right?.size_gb)) ? Number(right.size_gb) : Number.POSITIVE_INFINITY;
    if (leftSize !== rightSize) {
      return leftSize - rightSize;
    }
    if (Boolean(left?.installed) !== Boolean(right?.installed)) {
      return Number(Boolean(right?.installed)) - Number(Boolean(left?.installed));
    }
    return String(left?.label || left?.id || "").localeCompare(String(right?.label || right?.id || ""));
  });
}

function localPreprocessSizeLabel(model) {
  if (Number.isFinite(Number(model?.size_gb)) && Number(model.size_gb) > 0) {
    return `${Number(model.size_gb).toFixed(1)} GB`;
  }
  return "Unknown size";
}

function localPreprocessStatusMarkup(candidate, activeCandidate) {
  if (!candidate) {
    return `
      <div class="local-model-status-card">
        <div class="local-model-status-head">
          <div class="local-model-status-title">Local routing is off</div>
          <div class="local-model-status-pills">
            <span class="local-model-pill muted">Off</span>
          </div>
        </div>
        <div class="local-model-status-copy">Pick a local model to route lightweight requests on-device.</div>
      </div>
    `;
  }

  const isActive = activeCandidate?.id === candidate.id;
  const statusPills = [
    `<span class="local-model-pill size">${escapeHtml(localPreprocessSizeLabel(candidate))}</span>`,
    `<span class="local-model-pill ${candidate.installed ? "installed" : "available"}">${escapeHtml(candidate.installed ? t("localModel.installed") : t("localModel.available"))}</span>`,
    isActive
      ? `<span class="local-model-pill active">Active</span>`
      : `<span class="local-model-pill muted">${escapeHtml(candidate.installed ? "Ready to use" : "Needs install")}</span>`,
  ].filter(Boolean).join("");

  const currentModelLine = !isActive && activeCandidate
    ? `<div class="local-model-status-current">Current active model: ${escapeHtml(activeCandidate.label || activeCandidate.id)}</div>`
    : "";

  return `
    <div class="local-model-status-card">
      <div class="local-model-status-head">
        <div class="local-model-status-title">${escapeHtml(candidate.label || candidate.id)}</div>
        <div class="local-model-status-pills">${statusPills}</div>
      </div>
      <div class="local-model-status-copy">${escapeHtml(candidate.description || "Local model candidate.")}</div>
      ${currentModelLine}
    </div>
  `;
}

function renderLocalModelInstallDialogContent(candidate, options = {}) {
  if (!candidate) {
    return "";
  }
  const justInstalled = options.justInstalled === true;
  const activeCandidate = options.activeCandidate || null;
  const baseDescription = justInstalled
    ? "Installed locally. You can switch to it now."
    : (candidate.description || "Local model candidate.");
  return localPreprocessStatusMarkup({ ...candidate, description: baseDescription }, activeCandidate);
}

function renderAppSettings() {
  const budgetSelect = document.getElementById("settings-auto-model-budget");
  const preferenceSelect = document.getElementById("settings-auto-model-preference");
  const performanceProfileSelect = document.getElementById("settings-performance-profile");
  const taskBreakdownToggle = document.getElementById("settings-enable-task-breakdown");
  const followUpToggle = document.getElementById("settings-enable-follow-up-suggestions");
  const localPreprocessModelSelect = document.getElementById("settings-local-preprocess-model");
  const installLocalPreprocessButton = document.getElementById("settings-install-local-preprocess-model");
  const localPreprocessStatus = document.getElementById("settings-local-preprocess-model-status");
  const humanLanguageSelect = document.getElementById("settings-human-language");
  if (!budgetSelect || !preferenceSelect || !performanceProfileSelect || !taskBreakdownToggle || !followUpToggle || !localPreprocessModelSelect || !installLocalPreprocessButton || !localPreprocessStatus || !humanLanguageSelect) {
    return;
  }
  applyLocalizedUi();
  budgetSelect.value = state.appInfo?.settings?.max_cost_tier || "";
  preferenceSelect.value = state.appInfo?.settings?.auto_model_preference || "balanced";
  performanceProfileSelect.value = state.appInfo?.settings?.performance_profile || "balanced";
  taskBreakdownToggle.checked = state.appInfo?.settings?.enable_task_breakdown !== false;
  followUpToggle.checked = state.appInfo?.settings?.enable_follow_up_suggestions !== false;
  const availableLocalModels = localPreprocessModelsBySize(state.appInfo?.selector?.available_local_models);
  const selectedLocalModel = state.appInfo?.settings?.local_preprocess_model || "";
  const validModelIds = new Set(availableLocalModels.map((model) => model.id));
  if (state.localPreprocessDraftModelId && !validModelIds.has(state.localPreprocessDraftModelId)) {
    state.localPreprocessDraftModelId = "";
  }
  const resolvedLocalModelSelection = state.localPreprocessDraftModelId && validModelIds.has(state.localPreprocessDraftModelId)
    ? state.localPreprocessDraftModelId
    : (validModelIds.has(selectedLocalModel) ? selectedLocalModel : "");
  renderHumanLanguageOptions(humanLanguageSelect, state.appInfo?.settings?.human_language || currentHumanLanguage());
  localPreprocessModelSelect.innerHTML = [
    `<option value="">Off</option>`,
    ...availableLocalModels.map((model) => `<option value="${escapeHtml(model.id)}">${escapeHtml(localPreprocessOptionLabel(model))}</option>`),
  ].join("");
  localPreprocessModelSelect.value = resolvedLocalModelSelection;
  const selectedCandidate = availableLocalModels.find((model) => model.id === localPreprocessModelSelect.value) || null;
  const activeCandidate = availableLocalModels.find((model) => model.id === selectedLocalModel) || null;
  if (!selectedCandidate) {
    installLocalPreprocessButton.textContent = "Select a Model";
    installLocalPreprocessButton.disabled = true;
  } else if (selectedCandidate.installed && selectedCandidate.id === selectedLocalModel) {
    installLocalPreprocessButton.textContent = "Active Model";
    installLocalPreprocessButton.disabled = true;
  } else if (selectedCandidate.installed) {
    installLocalPreprocessButton.textContent = "Use Selected";
    installLocalPreprocessButton.disabled = false;
  } else {
    installLocalPreprocessButton.textContent = "Install Selected";
    installLocalPreprocessButton.disabled = false;
  }
  localPreprocessStatus.innerHTML = localPreprocessStatusMarkup(selectedCandidate, activeCandidate);
  renderFontSizeControl();
  renderDiagnosticsPanel();
}

function currentWorkspace() {
  return state.workspaces.find((workspace) => workspace.id === state.currentWorkspaceId) || null;
}

function workspaceTabStorageKey(workspaceId) {
  return `bettercode-workspace-tab-${workspaceId}`;
}

function workspaceDraftStorageKey(workspaceId, tabId) {
  return `bettercode-draft-${workspaceId}-${tabId || "default"}`;
}

function workspaceTabChatCacheStorageKey(workspaceId) {
  return `bettercode-tab-chat-cache-${workspaceId}`;
}

function readWorkspaceTabChatCache(workspaceId) {
  if (!workspaceId) {
    return { order: [], tabs: {} };
  }
  try {
    const raw = localStorage.getItem(workspaceTabChatCacheStorageKey(workspaceId));
    if (!raw) {
      return { order: [], tabs: {} };
    }
    const parsed = JSON.parse(raw);
    const tabs = parsed && typeof parsed.tabs === "object" && parsed.tabs ? parsed.tabs : {};
    const seen = new Set();
    const order = [];
    for (const value of Array.isArray(parsed?.order) ? parsed.order : []) {
      const tabKey = String(value || "").trim();
      if (!tabKey || seen.has(tabKey) || !tabs[tabKey]) {
        continue;
      }
      seen.add(tabKey);
      order.push(tabKey);
    }
    for (const tabKey of Object.keys(tabs)) {
      if (!seen.has(tabKey)) {
        seen.add(tabKey);
        order.push(tabKey);
      }
    }
    return { order: order.slice(0, TAB_CHAT_CACHE_MAX_TABS), tabs };
  } catch {
    return { order: [], tabs: {} };
  }
}

function writeWorkspaceTabChatCache(workspaceId, cache) {
  if (!workspaceId) {
    return;
  }
  const key = workspaceTabChatCacheStorageKey(workspaceId);
  let order = Array.isArray(cache?.order) ? cache.order.map((value) => String(value || "").trim()).filter(Boolean) : [];
  let tabs = cache && typeof cache.tabs === "object" && cache.tabs ? { ...cache.tabs } : {};
  order = order.filter((tabKey, index) => tabKey && order.indexOf(tabKey) === index);
  while (order.length > TAB_CHAT_CACHE_MAX_TABS) {
    const removed = order.pop();
    if (removed) {
      delete tabs[removed];
    }
  }
  order = order.filter((tabKey) => tabs[tabKey]);
  if (!order.length) {
    localStorage.removeItem(key);
    return;
  }
  while (true) {
    try {
      localStorage.setItem(key, JSON.stringify({ order, tabs }));
      return;
    } catch {
      const removed = order.pop();
      if (!removed) {
        localStorage.removeItem(key);
        return;
      }
      delete tabs[removed];
      if (!order.length) {
        localStorage.removeItem(key);
        return;
      }
    }
  }
}

function sanitizeCachedLogLines(lines) {
  if (!Array.isArray(lines)) {
    return [];
  }
  return lines
    .map((line) => String(line || ""))
    .filter((line) => line.trim())
    .slice(-TAB_CHAT_CACHE_MAX_LOG_LINES);
}

function sanitizeCachedTerminalLog(terminalLog) {
  const text = String(terminalLog || "");
  if (!text) {
    return "";
  }
  if (text.length <= TAB_CHAT_CACHE_MAX_TERMINAL_CHARS) {
    return text;
  }
  return text.slice(-TAB_CHAT_CACHE_MAX_TERMINAL_CHARS);
}

function sanitizeCachedChangeLog(changeLog) {
  if (!Array.isArray(changeLog)) {
    return [];
  }
  return changeLog.slice(0, TAB_CHAT_CACHE_MAX_CHANGE_FILES).map((entry) => {
    const diffText = String(entry?.diff || "");
    const trimmedDiff = diffText.length <= TAB_CHAT_CACHE_MAX_DIFF_PREVIEW_CHARS ? diffText : "";
    const note = String(entry?.note || "").trim()
      || (diffText && !trimmedDiff ? "Cached preview trimmed. Full diff reloads when the tab refreshes." : "");
    return {
      path: String(entry?.path || "").trim(),
      status: String(entry?.status || "modified").trim(),
      diff: trimmedDiff,
      note,
    };
  }).filter((entry) => entry.path || entry.diff || entry.note);
}

function sanitizeCachedMessage(message) {
  if (!message || typeof message !== "object") {
    return null;
  }
  const normalized = {
    id: Number.isFinite(Number(message.id)) ? Number(message.id) : null,
    role: String(message.role || "").trim() || "assistant",
    content: String(message.content || ""),
    created_at: message.created_at || null,
    activity_log: sanitizeCachedLogLines(message.activity_log || message.activityLog || []),
    history_log: sanitizeCachedLogLines(message.history_log || message.historyLog || []),
    terminal_log: sanitizeCachedTerminalLog(message.terminal_log || message.terminalLog || ""),
    change_log: sanitizeCachedChangeLog(message.change_log || message.changeLog || []),
    recommendations: Array.isArray(message.recommendations)
      ? message.recommendations.map((value) => String(value || "")).filter(Boolean).slice(0, 6)
      : [],
    routing_meta: message.routing_meta && typeof message.routing_meta === "object" ? message.routing_meta : {},
  };
  if (!normalized.role || (!normalized.content && !normalized.created_at && normalized.id === null)) {
    return null;
  }
  return normalized;
}

function sanitizeCachedPaging(paging, { truncated = false } = {}) {
  if (!paging || typeof paging !== "object" || truncated) {
    return null;
  }
  return {
    limit: Number.isFinite(Number(paging.limit)) ? Number(paging.limit) : INITIAL_WORKSPACE_MESSAGE_PAGE_SIZE,
    before_id: Number.isFinite(Number(paging.before_id)) ? Number(paging.before_id) : null,
    next_before_id: Number.isFinite(Number(paging.next_before_id)) ? Number(paging.next_before_id) : null,
    has_more: Boolean(paging.has_more),
  };
}

function cacheWorkspaceTabMessages(workspaceId, tabId, messages, paging = null) {
  if (!workspaceId || !tabId) {
    return;
  }
  const allMessages = Array.isArray(messages) ? messages : [];
  const truncated = allMessages.length > TAB_CHAT_CACHE_MAX_MESSAGES;
  const cachedMessages = (truncated ? allMessages.slice(-TAB_CHAT_CACHE_MAX_MESSAGES) : allMessages)
    .map((message) => sanitizeCachedMessage(message))
    .filter(Boolean);
  const tabKey = String(tabId);
  const cache = readWorkspaceTabChatCache(workspaceId);
  const order = [tabKey, ...cache.order.filter((value) => value !== tabKey)];
  const tabs = {
    ...cache.tabs,
    [tabKey]: {
      messages: cachedMessages,
      paging: sanitizeCachedPaging(paging, { truncated }),
      cached_at: new Date().toISOString(),
    },
  };
  while (order.length > TAB_CHAT_CACHE_MAX_TABS) {
    const removed = order.pop();
    if (removed) {
      delete tabs[removed];
    }
  }
  writeWorkspaceTabChatCache(workspaceId, { order, tabs });
}

function getCachedWorkspaceTabMessages(workspaceId, tabId) {
  if (!workspaceId || !tabId) {
    return null;
  }
  const cache = readWorkspaceTabChatCache(workspaceId);
  const snapshot = cache.tabs[String(tabId)];
  if (!snapshot) {
    return null;
  }
  const messages = (Array.isArray(snapshot.messages) ? snapshot.messages : [])
    .map((message) => sanitizeCachedMessage(message))
    .filter(Boolean);
  return {
    messages,
    paging: sanitizeCachedPaging(snapshot.paging),
  };
}

function removeWorkspaceTabMessagesCache(workspaceId, tabId) {
  if (!workspaceId || !tabId) {
    return;
  }
  const cache = readWorkspaceTabChatCache(workspaceId);
  const tabKey = String(tabId);
  if (!cache.tabs[tabKey]) {
    return;
  }
  delete cache.tabs[tabKey];
  cache.order = cache.order.filter((value) => value !== tabKey);
  writeWorkspaceTabChatCache(workspaceId, cache);
}

function clearWorkspaceTabMessagesCache(workspaceId) {
  if (!workspaceId) {
    return;
  }
  localStorage.removeItem(workspaceTabChatCacheStorageKey(workspaceId));
}

function resolveWorkspaceTab(workspace, preferredTabId = null) {
  const tabs = Array.isArray(workspace?.tabs) ? workspace.tabs : [];
  if (!tabs.length) {
    return null;
  }
  if (preferredTabId && tabs.some((tab) => tab.id === preferredTabId)) {
    return tabs.find((tab) => tab.id === preferredTabId) || null;
  }
  const savedTabId = Number(localStorage.getItem(workspaceTabStorageKey(workspace.id))) || null;
  if (savedTabId && tabs.some((tab) => tab.id === savedTabId)) {
    return tabs.find((tab) => tab.id === savedTabId) || null;
  }
  if (state.currentWorkspaceId === workspace.id && state.currentTabId && tabs.some((tab) => tab.id === state.currentTabId)) {
    return tabs.find((tab) => tab.id === state.currentTabId) || null;
  }
  return tabs[0] || null;
}

function setCurrentTabId(tabId) {
  state.currentTabId = tabId || null;
  if (state.currentWorkspaceId) {
    const key = workspaceTabStorageKey(state.currentWorkspaceId);
    if (state.currentTabId) {
      localStorage.setItem(key, String(state.currentTabId));
    } else {
      localStorage.removeItem(key);
    }
  }
}

function currentTab(workspace = currentWorkspace()) {
  return resolveWorkspaceTab(workspace, state.currentTabId);
}

function chatTabQuery(tabId = state.currentTabId) {
  if (!tabId) {
    return "";
  }
  return `tab_id=${encodeURIComponent(String(tabId))}`;
}

function reviewWorkspace() {
  const id = state.reviewWorkspaceId || state.currentWorkspaceId;
  return state.workspaces.find((w) => w.id === id) || null;
}

function applyRecommendedPrompt(promptText) {
  const input = document.getElementById("chat-input");
  if (!input) {
    return;
  }
  input.value = promptText || "";
  input.focus();
}

async function sendRecommendedPrompt(promptText) {
  const text = String(promptText || "").trim();
  if (!text || !state.currentWorkspaceId) {
    return;
  }
  if (isCurrentWorkspaceBusy()) {
    showToast("Wait for the current turn to finish first.");
    return;
  }
  if (!state.selectedModel) {
    showToast("No verified model is available yet.");
    return;
  }

  applyRecommendedPrompt(text);
  setComposerDraft("", []);
  await submitChatTurn(text, [], false);
}

// Returns true when the assistant reply ends with a question directed at the user.
function detectTrailingQuestion(content) {
  const text = String(content || "").trim();
  if (!text) return false;
  // Walk backwards past whitespace/punctuation to find the last real character
  const lastSentenceMatch = text.match(/[^.!?\s][^.!?]*\?[\s"']*$/);
  return Boolean(lastSentenceMatch);
}

function extractTrailingQuestion(content) {
  const text = String(content || "").trim();
  if (!detectTrailingQuestion(text)) {
    return "";
  }

  const questionIndex = text.lastIndexOf("?");
  if (questionIndex === -1) {
    return "";
  }

  const boundary = Math.max(
    text.lastIndexOf("\n", questionIndex),
    text.lastIndexOf(". ", questionIndex),
    text.lastIndexOf("! ", questionIndex),
    text.lastIndexOf("? ", questionIndex),
  );
  const start = boundary === -1 ? 0 : boundary + 1;
  return text.slice(start, questionIndex + 1).trim().replace(/^["']+|["']+$/g, "");
}

function detectBinaryTrailingQuestion(content) {
  const question = extractTrailingQuestion(content);
  if (!question) {
    return false;
  }
  return /^(do|did|does|can|could|would|should|will|is|are|was|were|have|has|had|want|need)\b/i.test(question);
}

function setGitCollapsed(collapsed) {
  const section = document.querySelector(".git-section");
  const button = document.getElementById("git-collapse-button");
  if (!section) {
    return;
  }
  section.classList.toggle("collapsed", Boolean(collapsed));
  if (button) {
    button.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
}

function modelOption(modelId) {
  return state.appInfo?.models?.find((model) => model.id === modelId) || null;
}

function activateView(viewId) {
  state.view = viewId;
  document.querySelectorAll(".view").forEach((node) => {
    node.classList.toggle("active", node.id === viewId);
  });
  const settingsBtn = document.getElementById("global-settings-button");
  if (settingsBtn) {
    settingsBtn.classList.toggle("active", viewId === "settings-view");
  }
  const reviewBtn = document.getElementById("review-open-button");
  if (reviewBtn) {
    reviewBtn.classList.toggle("active", viewId === "review-view");
  }
  if (viewId === "review-view") {
    renderReviewView();
  }
}

function activateSettingsTab(tabId) {
  state.settingsTab = tabId;
  document.querySelectorAll(".settings-tab").forEach((node) => {
    const isActive = node.dataset.settingsTarget === tabId;
    node.classList.toggle("active", isActive);
    node.setAttribute("aria-selected", isActive ? "true" : "false");
    node.tabIndex = isActive ? 0 : -1;
  });
  document.querySelectorAll(".settings-panel").forEach((node) => {
    const isActive = node.id === tabId;
    node.classList.toggle("active", isActive);
    node.setAttribute("aria-hidden", isActive ? "false" : "true");
  });
}

function telemetryEventLabel(name) {
  return String(name || "event")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function telemetryEventMeta(event) {
  const parts = [];
  if (event?.workspace_id) {
    parts.push(`Project ${event.workspace_id}`);
  }
  if (event?.runtime) {
    parts.push(String(event.runtime));
  }
  if (event?.duration_ms) {
    parts.push(`${event.duration_ms} ms`);
  }
  if (event?.status && !event?.duration_ms) {
    parts.push(String(event.status));
  }
  return parts.join(" • ");
}

function renderDiagnosticsPanel() {
  const panel = document.getElementById("settings-diagnostics-panel");
  const retryButton = document.getElementById("settings-retry-last-turn");
  const openTelemetryButton = document.getElementById("settings-open-telemetry");
  if (!panel) {
    return;
  }

  const workspace = currentWorkspace();
  const telemetryInfo = state.appInfo?.telemetry || {};
  const selectorInfo = state.appInfo?.selector || {};
  const events = Array.isArray(state.telemetry.events) ? state.telemetry.events.slice(-8).reverse() : [];

  if (retryButton) {
    retryButton.disabled = isCurrentWorkspaceBusy() || !workspace;
  }
  if (openTelemetryButton) {
    openTelemetryButton.disabled = !telemetryInfo?.path;
  }

  const selectorStatus = selectorInfo?.mode === "off"
    ? "Disabled"
    : selectorInfo?.running
      ? `Ready${selectorInfo?.selected_model ? ` · ${selectorInfo.selected_model}` : ""}`
      : "Unavailable";
  const selectorModeLabel = selectorInfo?.mode ? String(selectorInfo.mode).replace(/^./, (char) => char.toUpperCase()) : "Off";

  const statusText = state.telemetry.loading
    ? "Loading recent telemetry…"
    : state.telemetry.error
      ? escapeHtml(state.telemetry.error)
      : events.length
        ? ""
        : "No recent telemetry yet.";

  panel.innerHTML = `
    <div class="settings-diagnostics-meta">
      <div class="settings-diagnostics-item">
        <span class="settings-diagnostics-label">Current Project</span>
        <span class="settings-diagnostics-value">${workspace ? escapeHtml(workspace.name) : "No project selected"}</span>
      </div>
      <div class="settings-diagnostics-item">
        <span class="settings-diagnostics-label">Telemetry Log</span>
        <span class="settings-diagnostics-value mono-copy">${telemetryInfo?.path ? escapeHtml(telemetryInfo.path) : "Unavailable"}</span>
      </div>
      <div class="settings-diagnostics-item">
        <span class="settings-diagnostics-label">Last Updated</span>
        <span class="settings-diagnostics-value">${telemetryInfo?.modified_at ? escapeHtml(formatDateTime(telemetryInfo.modified_at)) : "Not written yet"}</span>
      </div>
      <div class="settings-diagnostics-item">
        <span class="settings-diagnostics-label">Auto Select</span>
        <span class="settings-diagnostics-value">${escapeHtml(selectorStatus)}</span>
        <span class="settings-diagnostics-hint">${escapeHtml(selectorModeLabel === "Off" ? "Local model off" : `${selectorModeLabel} local model`)}</span>
      </div>
    </div>
    <div class="settings-diagnostics-feed">
      <div class="settings-diagnostics-feed-head">
        <div class="settings-diagnostics-label">Recent Events</div>
        ${telemetryInfo?.size ? `<div class="settings-diagnostics-size">${escapeHtml(formatFileSize(telemetryInfo.size))}</div>` : ""}
      </div>
      ${statusText ? `<div class="settings-diagnostics-empty">${statusText}</div>` : `
        <div class="settings-diagnostics-events">
          ${events.map((event) => `
            <div class="settings-diagnostics-event">
              <div class="settings-diagnostics-event-head">
                <span class="settings-diagnostics-event-name">${escapeHtml(telemetryEventLabel(event.event))}</span>
                <span class="settings-diagnostics-event-time">${escapeHtml(formatDateTime(event.ts))}</span>
              </div>
              ${telemetryEventMeta(event) ? `<div class="settings-diagnostics-event-meta">${escapeHtml(telemetryEventMeta(event))}</div>` : ""}
            </div>
          `).join("")}
        </div>
      `}
    </div>
  `;
}

async function openTelemetryLog() {
  const button = document.getElementById("settings-open-telemetry");
  setButtonPending(button, true, "Opening...");
  try {
    const payload = await request("/api/app/telemetry/open", { method: "POST" });
    showToast(payload?.opened ? "Telemetry log opened." : "Could not open telemetry log.");
  } catch (error) {
    showToast(error.message || "Could not open telemetry log.");
  } finally {
    setButtonPending(button, false);
  }
}

async function loadTelemetry(force = false) {
  if (state.telemetry.loading) {
    return;
  }
  if (state.telemetry.loaded && !force) {
    return;
  }
  state.telemetry.loading = true;
  state.telemetry.error = "";
  renderDiagnosticsPanel();
  try {
    const payload = await request("/api/app/telemetry?limit=24");
    state.telemetry.events = Array.isArray(payload?.events) ? payload.events : [];
    if (payload?.telemetry) {
      state.appInfo = {
        ...(state.appInfo || {}),
        telemetry: payload.telemetry,
      };
    }
    state.telemetry.loaded = true;
  } catch (error) {
    state.telemetry.error = error.message || "Could not load telemetry.";
  } finally {
    state.telemetry.loading = false;
    renderDiagnosticsPanel();
  }
}

function ensureDiagnosticsLoaded() {
  if (!state.telemetry.loaded && !state.telemetry.loading) {
    loadTelemetry().catch(() => {});
    return;
  }
  renderDiagnosticsPanel();
}

function renderAppInfo() {
  if (!state.appInfo) {
    return;
  }

  applyLocalizedUi();
  applyFontSize(state.appInfo?.settings?.font_size || state.fontSize);

  const versionNode = document.getElementById("app-version");
  if (versionNode) {
    versionNode.textContent = `v${state.appInfo.version}`;
  }
  const updateInfo = state.appInfo?.update || null;
  const updateButtons = document.querySelectorAll("[data-app-update-button]");
  for (const updateButton of updateButtons) {
    const label = updateButton.querySelector("[data-app-update-label]");
    const hasInstallableUpdate = Boolean(
      updateInfo?.update_available
      && updateInfo.download_url
      && updateInfo.sha256
    );
    const labelText = t("app.updateAvailable");
    if (label) {
      label.textContent = labelText;
    }
    const versionSuffix = hasInstallableUpdate && updateInfo.latest_version ? ` ${updateInfo.latest_version}` : "";
    updateButton.setAttribute("aria-label", `${labelText}${versionSuffix}`);
    updateButton.title = `${labelText}${versionSuffix}`;
    updateButton.classList.toggle("hidden", !hasInstallableUpdate);
  }

  if (!state.appInfo.models.length) {
    state.selectedModel = "";
    state.selectedAgentMode = "";
    state.modelPickerOpen = false;
    state.modePickerOpen = false;
  } else {
    const currentModelIsAvailable = state.appInfo.models.some((model) => model.id === state.selectedModel);
    state.selectedModel = currentModelIsAvailable ? state.selectedModel : state.appInfo.models[0].id;
    syncSelectedAgentMode();
  }
  renderModelPicker();

  for (const runtimeName of ["codex", "cursor", "claude", "gemini"]) {
    const runtime = state.appInfo.runtimes?.[runtimeName];
    const job = runtime?.job;
    const statusNode = document.getElementById(`${runtimeName}-runtime-status`);
    const accessNode = document.getElementById(`${runtimeName}-runtime-access`);
    const loginButton = document.querySelector(`.runtime-login-button[data-runtime="${runtimeName}"]`);
    const logoutButton = document.querySelector(`.runtime-logout-button[data-runtime="${runtimeName}"]`);
    const keyButton = document.querySelector(`.auth-open-button[data-provider="${runtime?.provider || ""}"]`);
    const installButton = document.querySelector(`.runtime-install-button[data-runtime="${runtimeName}"]`);
    const jobRunning = job?.status === "running";

    if (statusNode) {
      if (jobRunning) {
        statusNode.textContent = job.action === "install" ? t("runtime.installing") : t("runtime.login");
      } else {
        statusNode.textContent = runtime?.available ? (runtime.version || t("localModel.installed")) : t("runtime.notInstalled");
      }
      statusNode.className = `runtime-status ${runtime?.available ? "available" : "missing"}`;
    }

    if (accessNode) {
      accessNode.textContent = jobRunning ? (job.message || "Working...") : (runtime?.access_label || "Not configured");
      accessNode.className = `runtime-access ${runtime?.configured ? "configured" : "missing"}`;
    }

    if (loginButton) {
      loginButton.disabled = jobRunning;
      loginButton.textContent = jobRunning && job?.action === "login" ? "Logging In..." : "Login";
      loginButton.classList.toggle("button-pending", jobRunning && job?.action === "login");
      loginButton.classList.toggle("hidden", !runtime?.available || Boolean(runtime?.configured));
    }

    if (keyButton) {
      keyButton.disabled = jobRunning;
      keyButton.classList.toggle("hidden", !runtime?.available || Boolean(runtime?.configured));
    }

    if (logoutButton) {
      logoutButton.disabled = jobRunning;
      logoutButton.classList.remove("button-pending");
      logoutButton.classList.toggle("hidden", !runtime?.available || !runtime?.configured);
    }

    if (installButton) {
      installButton.disabled = jobRunning;
      if (jobRunning && job?.action === "install") {
        installButton.textContent = "Installing...";
      } else {
        installButton.textContent = runtime?.available ? "Update Latest" : "Install Latest";
      }
      installButton.classList.toggle("button-pending", jobRunning && job?.action === "install");
    }
  }

  renderAppSettings();
  maybeOpenOnboarding();
}

async function updateAppSettings(updates, options = {}) {
  const showSuccessToast = options.showSuccessToast !== false;
  const budgetSelect = document.getElementById("settings-auto-model-budget");
  const preferenceSelect = document.getElementById("settings-auto-model-preference");
  const performanceProfileSelect = document.getElementById("settings-performance-profile");
  const taskBreakdownToggle = document.getElementById("settings-enable-task-breakdown");
  const followUpToggle = document.getElementById("settings-enable-follow-up-suggestions");
  const localPreprocessModelSelect = document.getElementById("settings-local-preprocess-model");
  const installLocalPreprocessButton = document.getElementById("settings-install-local-preprocess-model");
  const humanLanguageSelect = document.getElementById("settings-human-language");
  if (!budgetSelect || !preferenceSelect || !performanceProfileSelect || !taskBreakdownToggle || !followUpToggle || !localPreprocessModelSelect || !installLocalPreprocessButton || !humanLanguageSelect) {
    return;
  }
  const previousBudget = budgetSelect.value;
  const previousPreference = preferenceSelect.value;
  const previousPerformanceProfile = performanceProfileSelect.value;
  const previousTaskBreakdown = taskBreakdownToggle.checked;
  const previousFollowUp = followUpToggle.checked;
  const previousLocalPreprocessModel = localPreprocessModelSelect.value;
  const previousLocalPreprocessDraft = state.localPreprocessDraftModelId;
  const previousFontSize = state.appInfo?.settings?.font_size || state.fontSize;
  const previousHumanLanguage = humanLanguageSelect.value;
  budgetSelect.disabled = true;
  preferenceSelect.disabled = true;
  performanceProfileSelect.disabled = true;
  taskBreakdownToggle.disabled = true;
  followUpToggle.disabled = true;
  localPreprocessModelSelect.disabled = true;
  installLocalPreprocessButton.disabled = true;
  humanLanguageSelect.disabled = true;
  try {
    const requestBody = {};
    for (const [key, value] of Object.entries(updates || {})) {
      requestBody[key] = value;
    }
    const payload = await request("/api/app/settings", {
      method: "POST",
      body: JSON.stringify(requestBody)
    });
    state.appInfo = {
      ...(state.appInfo || {}),
      settings: payload.settings,
      languages: {
        ...((state.appInfo || {}).languages || {}),
        current: payload.settings?.human_language || currentHumanLanguage(),
        needs_setup: Object.prototype.hasOwnProperty.call(updates, "human_language") ? false : Boolean(state.appInfo?.languages?.needs_setup),
      },
    };
    applyFontSize(payload.settings?.font_size || state.fontSize);
    if (
      Object.prototype.hasOwnProperty.call(updates, "local_preprocess_mode")
      || Object.prototype.hasOwnProperty.call(updates, "local_preprocess_model")
      || Object.prototype.hasOwnProperty.call(updates, "performance_profile")
    ) {
      await loadAppInfo();
    }
    if (Object.prototype.hasOwnProperty.call(updates, "local_preprocess_model")) {
      state.localPreprocessDraftModelId = payload.settings?.local_preprocess_model || "";
    }
    renderAppInfo();
    if (Object.prototype.hasOwnProperty.call(updates, "human_language")) {
      for (const liveChat of state.liveChats.values()) {
        if (liveChat && typeof liveChat === "object") {
          liveChat.renderCache = {};
        }
      }
      renderMessages(state.messages, currentWorkspace(), state.messagePaging);
      renderLiveChatState(currentWorkspace());
      renderDiagnosticsPanel();
    }
    if (showSuccessToast) {
      showToast(t("toast.settingsUpdated"));
    }
  } catch (error) {
    budgetSelect.value = previousBudget;
    preferenceSelect.value = previousPreference;
    performanceProfileSelect.value = previousPerformanceProfile;
    taskBreakdownToggle.checked = previousTaskBreakdown;
    followUpToggle.checked = previousFollowUp;
    localPreprocessModelSelect.value = previousLocalPreprocessModel;
    state.localPreprocessDraftModelId = previousLocalPreprocessDraft;
    humanLanguageSelect.value = previousHumanLanguage;
    applyFontSize(previousFontSize);
    showToast(error.message);
  } finally {
    budgetSelect.disabled = false;
    preferenceSelect.disabled = false;
    performanceProfileSelect.disabled = false;
    taskBreakdownToggle.disabled = false;
    followUpToggle.disabled = false;
    localPreprocessModelSelect.disabled = false;
    humanLanguageSelect.disabled = false;
    renderAppSettings();
  }
}

function modelPickerGroups(models) {
  const grouped = new Map();
  const labels = {
    smart: t("modelPicker.smart"),
    codex: t("modelPicker.codex"),
    cursor: t("modelPicker.cursor"),
    claude: t("modelPicker.claude"),
    gemini: t("modelPicker.gemini")
  };

  for (const model of models) {
    const key = model.id === "smart" ? "smart" : model.id.split("/", 1)[0];
    if (!grouped.has(key)) {
      grouped.set(key, []);
    }
    grouped.get(key).push(model);
  }

  return Array.from(grouped.entries()).map(([key, items]) => ({
    label: labels[key] || key,
    items
  }));
}

const AGENT_MODE_META = {
  plan: { labelKey: "composer.mode.plan" },
  auto_edit: { labelKey: "composer.mode.autoEdit" },
  full_agentic: { labelKey: "composer.mode.fullAgentic" },
};

function supportedAgentModes(modelId = state.selectedModel) {
  const modes = modelOption(modelId)?.agent_modes;
  if (!Array.isArray(modes)) {
    return [];
  }
  return modes.filter((mode, index) => AGENT_MODE_META[mode] && modes.indexOf(mode) === index);
}

function defaultAgentMode(modelId = state.selectedModel) {
  const supported = supportedAgentModes(modelId);
  if (!supported.length) {
    return "";
  }
  const configured = String(modelOption(modelId)?.default_agent_mode || "");
  return supported.includes(configured) ? configured : supported[0];
}

function syncSelectedAgentMode() {
  const supported = supportedAgentModes();
  if (!supported.length) {
    state.selectedAgentMode = "";
    return;
  }
  if (supported.includes(state.selectedAgentMode)) {
    return;
  }
  state.selectedAgentMode = defaultAgentMode();
}

function currentAgentMode() {
  syncSelectedAgentMode();
  return state.selectedAgentMode || defaultAgentMode();
}

function closeModePicker() {
  state.modePickerOpen = false;
  const button = document.getElementById("mode-picker-button");
  const menu = document.getElementById("mode-picker-menu");
  button?.setAttribute("aria-expanded", "false");
  menu?.classList.add("hidden");
}

function toggleModePicker(forceOpen = !state.modePickerOpen) {
  const button = document.getElementById("mode-picker-button");
  const menu = document.getElementById("mode-picker-menu");
  if (!button || !menu || button.disabled) {
    return;
  }
  if (forceOpen) {
    closeModelPicker(); // close the model picker when mode picker opens
  }
  state.modePickerOpen = forceOpen;
  button.setAttribute("aria-expanded", state.modePickerOpen ? "true" : "false");
  menu.classList.toggle("hidden", !state.modePickerOpen);
}

function renderAgentModePicker() {
  const container = document.getElementById("agent-mode-cap");
  const button = document.getElementById("mode-picker-button");
  const labelEl = document.getElementById("mode-picker-label");
  const menu = document.getElementById("mode-picker-menu");
  const fieldLabel = document.getElementById("composer-mode-label");
  if (!container || !button || !menu) {
    return;
  }

  const supported = supportedAgentModes();
  if (fieldLabel) {
    fieldLabel.textContent = t("composer.mode");
  }
  if (!supported.length) {
    state.selectedAgentMode = "";
    container.classList.add("hidden");
    menu.innerHTML = "";
    button.disabled = true;
    return;
  }

  syncSelectedAgentMode();
  const active = supported.includes(state.selectedAgentMode) ? state.selectedAgentMode : defaultAgentMode();
  const busy = isCurrentWorkspaceBusy() || !state.selectedModel;

  // Update button label
  if (labelEl) {
    labelEl.textContent = t(AGENT_MODE_META[active]?.labelKey || active);
  }
  button.disabled = busy;

  // Rebuild menu options
  menu.innerHTML = supported.map((mode) => `
    <button type="button" class="model-picker-option${mode === active ? " active" : ""}"
            role="option" aria-selected="${mode === active ? "true" : "false"}"
            data-mode-id="${escapeHtml(mode)}">
      ${escapeHtml(t(AGENT_MODE_META[mode]?.labelKey || mode))}
    </button>
  `).join("");

  container.classList.toggle("hidden", supported.length <= 1);
}

function closeModelPicker() {
  state.modelPickerOpen = false;
  const button = document.getElementById("model-picker-button");
  const menu = document.getElementById("model-picker-menu");
  button?.setAttribute("aria-expanded", "false");
  menu?.classList.add("hidden");
}

function toggleModelPicker(forceOpen = !state.modelPickerOpen) {
  const button = document.getElementById("model-picker-button");
  const menu = document.getElementById("model-picker-menu");
  if (!button || !menu || button.disabled) {
    return;
  }
  if (forceOpen) {
    closeModePicker(); // close mode picker when model picker opens
  }
  state.modelPickerOpen = forceOpen;
  button.setAttribute("aria-expanded", state.modelPickerOpen ? "true" : "false");
  menu.classList.toggle("hidden", !state.modelPickerOpen);
}

function renderModelPicker() {
  const button = document.getElementById("model-picker-button");
  const label = document.getElementById("model-picker-label");
  const menu = document.getElementById("model-picker-menu");
  if (!button || !label || !menu) {
    return;
  }

  const models = state.appInfo?.models || [];
  if (!models.length) {
    button.disabled = true;
    label.textContent = t("modelPicker.none");
    menu.innerHTML = `<div class="model-picker-empty">${escapeHtml(t("modelPicker.none"))}.</div>`;
    state.selectedAgentMode = "";
    renderAgentModePicker();
    closeModelPicker();
    return;
  }

  syncSelectedAgentMode();
  const selectedModel = models.find((model) => model.id === state.selectedModel) || models[0];
  label.textContent = selectedModel.label;
  button.disabled = false;

  menu.innerHTML = modelPickerGroups(models).map((group) => `
    <div class="model-picker-section">
      <div class="model-picker-section-label">${group.label}</div>
      ${group.items.map((model) => `
        <button
          type="button"
          class="model-picker-option ${model.id === state.selectedModel ? "active" : ""}"
          data-model-id="${model.id}"
          role="option"
          aria-selected="${model.id === state.selectedModel ? "true" : "false"}"
        >${model.label}</button>
      `).join("")}
    </div>
  `).join("");

  renderAgentModePicker();
  toggleModelPicker(state.modelPickerOpen);
}

function selectModel(modelId) {
  if (!state.appInfo?.models?.some((model) => model.id === modelId)) {
    return;
  }

  state.selectedModel = modelId;
  syncSelectedAgentMode();
  renderModelPicker();
}

async function installRuntime(runtime) {
  const payload = await request(`/api/runtimes/${runtime}/install`, { method: "POST" });
  state.appInfo = {
    ...state.appInfo,
    models: payload.models,
    runtimes: payload.runtimes,
  };
  renderAppInfo();
  if (payload.job) {
    pollRuntimeJob(payload.job.id);
  }
}

async function loginRuntime(runtime) {
  const payload = await request(`/api/runtimes/${runtime}/login`, { method: "POST" });
  state.appInfo = {
    ...state.appInfo,
    models: payload.models,
    runtimes: payload.runtimes,
  };
  renderAppInfo();
  if (payload.job) {
    pollRuntimeJob(payload.job.id);
  }
}

async function logoutRuntime(runtime) {
  const payload = await request(`/api/runtimes/${runtime}/logout`, { method: "POST" });
  state.appInfo = {
    ...state.appInfo,
    models: payload.models,
    runtimes: payload.runtimes,
  };
  renderAppInfo();
  showToast(payload.output || `${runtime} logged out.`);
}

function pollRuntimeJob(jobId) {
  if (!jobId || state.runtimeJobPollers[jobId]) {
    return;
  }

  const tick = async () => {
    try {
      const payload = await request(`/api/runtime-jobs/${jobId}`);
      state.appInfo = {
        ...state.appInfo,
        models: payload.models,
        runtimes: payload.runtimes,
      };
      renderAppInfo();

      if (payload.job?.status === "running") {
        state.runtimeJobPollers[jobId] = window.setTimeout(tick, 1500);
        return;
      }

      delete state.runtimeJobPollers[jobId];
      if (payload.job?.status === "completed") {
        showToast(payload.job.message || `${payload.job.runtime} ready.`);
      } else if (payload.job?.status === "failed") {
        showToast(payload.job.message || `${payload.job.runtime} failed.`);
      }
    } catch (error) {
      delete state.runtimeJobPollers[jobId];
      showToast(error.message);
    }
  };

  state.runtimeJobPollers[jobId] = window.setTimeout(tick, 150);
}

function renderAttachmentList() {
  const container = document.getElementById("attachment-list");
  if (!container) {
    return;
  }

  if (!state.attachments.length) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = state.attachments.map((attachment, index) => `
    <div class="attachment-chip">
      <span class="attachment-name">${attachment.name}</span>
      <button type="button" class="attachment-remove" data-attachment-index="${index}" aria-label="Remove ${attachment.name}">×</button>
    </div>
  `).join("");
}

function currentSlashCommandToken(input) {
  if (!input) return "";
  const caret = Number.isFinite(input.selectionStart) ? input.selectionStart : input.value.length;
  const lineBeforeCaret = input.value.slice(0, caret).split("\n").pop() || "";
  const trimmed = lineBeforeCaret.trim();
  if (!trimmed.startsWith("/") || /\s/.test(trimmed)) {
    return "";
  }
  return trimmed;
}

function matchingSlashCommands(token) {
  if (!token) return [];
  const query = token.slice(1).toLowerCase();
  return SLASH_COMMANDS.filter((item) => {
    if (!query) return true;
    return item.command.slice(1).toLowerCase().startsWith(query) || item.keyword.includes(query);
  });
}

function closeSlashCommandMenu() {
  state.slashCommands.open = false;
  state.slashCommands.items = [];
  state.slashCommands.activeIndex = 0;
  state.slashCommands.query = "";
  renderSlashCommandMenu();
}

function renderSlashCommandMenu() {
  const container = document.getElementById("slash-command-menu");
  if (!container) return;
  const { open, items, activeIndex } = state.slashCommands;
  if (!open || !items.length) {
    container.classList.add("hidden");
    container.innerHTML = "";
    return;
  }

  container.classList.remove("hidden");
  container.innerHTML = items.map((item, index) => `
    <button
      type="button"
      class="slash-command-item${index === activeIndex ? " active" : ""}"
      data-command-index="${index}"
      role="option"
      aria-selected="${index === activeIndex ? "true" : "false"}"
    >
      <span class="slash-command-main">
        <span class="slash-command-name">${escapeHtml(item.command)}</span>
        <span class="slash-command-description">${escapeHtml(item.description)}</span>
      </span>
      <span class="slash-command-badge">Command</span>
    </button>
  `).join("");

  container.querySelectorAll("[data-command-index]").forEach((node) => {
    node.addEventListener("mousedown", (event) => event.preventDefault());
    node.addEventListener("click", () => applySlashCommand(Number(node.dataset.commandIndex)));
  });
}

function updateSlashCommandMenu() {
  const input = document.getElementById("chat-input");
  const token = currentSlashCommandToken(input);
  const items = matchingSlashCommands(token);
  state.slashCommands.query = token;
  state.slashCommands.items = items;
  state.slashCommands.open = Boolean(token && items.length && !isCurrentWorkspaceBusy());
  if (state.slashCommands.activeIndex >= items.length) {
    state.slashCommands.activeIndex = 0;
  }
  renderSlashCommandMenu();
}

function applySlashCommand(index = state.slashCommands.activeIndex) {
  const input = document.getElementById("chat-input");
  const item = state.slashCommands.items[index];
  if (!input || !item) return;
  const caret = Number.isFinite(input.selectionStart) ? input.selectionStart : input.value.length;
  const beforeCaret = input.value.slice(0, caret);
  const afterCaret = input.value.slice(caret);
  const line = beforeCaret.split("\n").pop() || "";
  const lineStart = beforeCaret.length - line.length;
  const replacementStart = lineStart + line.indexOf("/");
  const nextValue = `${input.value.slice(0, replacementStart)}${item.command}${afterCaret}`;
  input.value = nextValue;
  input.focus();
  const nextCaret = replacementStart + item.command.length;
  input.setSelectionRange(nextCaret, nextCaret);
  setComposerDraft(input.value, state.attachments);
  closeSlashCommandMenu();
}

function previewChatPayload(text, attachments = []) {
  return [text, attachments.length ? `Attached files: ${attachments.map((attachment) => attachment.name).join(", ")}` : ""]
    .filter(Boolean)
    .join("\n\n");
}


function isCurrentWorkspaceBusy() {
  return state.busyWorkspaces.has(state.currentWorkspaceId);
}

function currentLiveChat() {
  return state.liveChats.get(state.currentWorkspaceId) ?? null;
}

function renderComposerState() {
  const button = document.getElementById("send-button");
  const stopButton = document.getElementById("chat-stop-button");
  const input = document.getElementById("chat-input");
  const hint = document.getElementById("composer-hint");
  const composer = document.getElementById("chat-form");
  const attachButton = document.getElementById("attach-button");
  const modelButton = document.getElementById("model-picker-button");
  const modeButton = document.getElementById("mode-picker-button");
  if (!button) {
    return;
  }

  if (isCurrentWorkspaceBusy()) {
    closeSlashCommandMenu();
    button.textContent = "Working…";
    button.disabled = true;
    stopButton?.classList.remove("hidden");
    if (stopButton) {
      const lc = currentLiveChat();
      stopButton.disabled = Boolean(lc?.stopRequested);
      stopButton.textContent = lc?.stopRequested ? "Stopping…" : "Stop";
    }
    if (input) {
      input.placeholder = "Write an instruction…";
      input.disabled = true;
    }
    composer?.classList.add("busy");
    composer?.setAttribute("aria-busy", "true");
    if (attachButton) attachButton.disabled = true;
    if (modelButton) modelButton.disabled = true;
    if (modeButton) modeButton.disabled = true;
  } else {
    button.textContent = "Send";
    button.disabled = false;
    stopButton?.classList.add("hidden");
    if (stopButton) {
      stopButton.disabled = false;
      stopButton.textContent = "Stop";
    }
    if (input) {
      input.placeholder = "Write an instruction…";
      input.disabled = false;
    }
    composer?.classList.remove("busy");
    composer?.setAttribute("aria-busy", "false");
    if (attachButton) attachButton.disabled = false;
    if (modelButton) modelButton.disabled = false;
    if (modeButton) modeButton.disabled = !state.selectedModel || !supportedAgentModes().length;
  }
}

function stopChatStatusPolling() {
  if (state.chatStatusPoller) {
    clearInterval(state.chatStatusPoller);
    state.chatStatusPoller = null;
  }
}

function ensureLiveChatStatusLine(message, lc = currentLiveChat()) {
  if (!lc || !message) {
    return;
  }
  const lines = lc.activityLines || [];
  if (lines[lines.length - 1] !== message) {
    lines.push(message);
  }
}

async function pollChatStatus() {
  const lc = currentLiveChat();
  const workspaceId = lc?.workspaceId;
  const tabId = lc?.tabId;
  if (!workspaceId || state.busyWorkspaces.size === 0) {
    stopChatStatusPolling();
    return;
  }
  try {
    const payload = await request(`/api/workspaces/${workspaceId}/chat/status${tabId ? `?tab_id=${tabId}` : ""}`);
    const chat = payload?.chat || {};
    if (!lc) {
      return;
    }
    lc.inputPrompt = chat.input_waiting ? (lc.inputPrompt || localizeRuntimeLine("BetterCode needs a reply to continue.")) : lc.inputPrompt;
    if (chat.stalled && !lc.stallNotified) {
      lc.stallNotified = true;
      ensureLiveChatStatusLine(localizeRuntimeLine(`No output for ${Math.round(chat.idle_seconds || 0)}s. Process may be stalled.`));
      scheduleLiveChatRender(currentWorkspace(), { immediate: true });
    } else if (!chat.stalled) {
      lc.stallNotified = false;
    }
  } catch (_) {
    // Ignore polling failures while the stream is still active.
  }
}

function startChatStatusPolling() {
  stopChatStatusPolling();
  state.chatStatusPoller = setInterval(() => {
    pollChatStatus().catch(() => {});
  }, 4000);
}

async function stopChatTurn() {
  const lc = currentLiveChat();
  const workspaceId = lc?.workspaceId || state.currentWorkspaceId;
  const tabId = lc?.tabId || state.currentTabId;
  if (!workspaceId || !isCurrentWorkspaceBusy()) {
    return;
  }
  if (lc?.stopRequested) {
    return;
  }
  if (lc) {
    lc.stopRequested = true;
    ensureLiveChatStatusLine("Stopping turn…", lc);
  }
  renderComposerState();
  renderLiveChatState(currentWorkspace());
  try {
    await request(`/api/workspaces/${workspaceId}/chat/stop${tabId ? `?tab_id=${tabId}` : ""}`, { method: "POST" });
  } catch (error) {
    if (lc) {
      lc.stopRequested = false;
    }
    renderComposerState();
    renderLiveChatState(currentWorkspace());
    showToast(error.message);
  }
}

async function sendCliInput(text) {
  if (!state.currentWorkspaceId || !state.currentTabId || !text) {
    return;
  }
  try {
    await request(`/api/workspaces/${state.currentWorkspaceId}/chat/input?tab_id=${state.currentTabId}`, {
      method: "POST",
      body: JSON.stringify({ text })
    });
  } catch (error) {
    showToast(error.message);
  }
}

function setComposerDraft(text, attachments = []) {
  const input = document.getElementById("chat-input");
  if (input) {
    input.value = text || "";
  }
  state.attachments = attachments.map((attachment) => ({ ...attachment }));
  renderAttachmentList();
  persistComposerDraftText(text || "");
  updateSlashCommandMenu();
}

function persistComposerDraftText(text) {
  if (state.currentWorkspaceId && state.currentTabId) {
    const key = workspaceDraftStorageKey(state.currentWorkspaceId, state.currentTabId);
    if (text) {
      localStorage.setItem(key, text);
    } else {
      localStorage.removeItem(key);
    }
  }
}


function restoreComposerDraft(text, attachments, force = false) {
  const input = document.getElementById("chat-input");
  const hasDraft = Boolean(input?.value.trim()) || state.attachments.length > 0;
  if (!force && hasDraft) {
    return;
  }
  setComposerDraft(text, attachments);
}

function isCurrentWorkspaceId(workspaceId) {
  return Boolean(workspaceId) && state.currentWorkspaceId === workspaceId;
}

function getGitFiles() {
  if (!state.git) {
    return [];
  }

  const files = new Map();

  for (const entry of [...state.git.staged, ...state.git.changed]) {
    const existing = files.get(entry.path) || {
      path: entry.path,
      index_status: ".",
      worktree_status: "."
    };

    if (entry.index_status && entry.index_status !== ".") {
      existing.index_status = entry.index_status;
    }
    if (entry.worktree_status && entry.worktree_status !== ".") {
      existing.worktree_status = entry.worktree_status;
    }

    files.set(entry.path, existing);
  }

  return Array.from(files.values()).sort((left, right) => left.path.localeCompare(right.path));
}

function syncGitSelection() {
  const availablePaths = new Set(getGitFiles().map((entry) => entry.path));
  state.selectedGitPaths = state.selectedGitPaths.filter((path) => availablePaths.has(path));
}

function setGitState(git, output = "") {
  state.git = git;
  if (!state.git) {
    state.selectedGitPaths = [];
    renderGitPanel();
    if (state.view === "review-view") renderReviewView();
    return;
  }

  state.git.output = output;
  syncGitSelection();
  renderGitPanel();
  if (state.view === "review-view") renderReviewView();
}

function toggleGitPathSelection(path, selected) {
  if (selected) {
    if (!state.selectedGitPaths.includes(path)) {
      state.selectedGitPaths = [...state.selectedGitPaths, path];
    }
  } else {
    state.selectedGitPaths = state.selectedGitPaths.filter((item) => item !== path);
  }

  renderGitPanel();
}

function closeWorkspaceMenu() {
  const menu = document.getElementById("workspace-menu");
  menu.classList.add("hidden");
  menu.innerHTML = "";
  state.menuWorkspaceId = null;
}

function closeGeneratedFilesMenu() {
  const menu = document.getElementById("generated-files-menu");
  menu.classList.add("hidden");
  menu.innerHTML = "";
  state.generatedFilesMenuWorkspaceId = null;
}

function closeProjectAddMenu() {
  const menu = document.getElementById("project-add-menu");
  menu.classList.add("hidden");
}

function closeGitMenu() {
  const menu = document.getElementById("git-menu");
  menu.classList.add("hidden");
}

function openWorkspaceMenu(workspaceId, anchor) {
  const workspace = state.workspaces.find((item) => item.id === workspaceId);
  state.menuWorkspaceId = workspaceId;
  const menu = document.getElementById("workspace-menu");
  menu.innerHTML = `
    <button type="button" data-action="rename">Rename</button>
    <button type="button" data-action="reset-session"${workspace?.has_session ? "" : " disabled"}>Reset Session</button>
    <button type="button" data-action="delete">Remove</button>
  `;
  const rect = anchor.getBoundingClientRect();
  menu.style.top = `${rect.bottom + 6}px`;
  menu.style.left = `${Math.max(16, rect.right - 140)}px`;
  menu.classList.remove("hidden");
}

function openGitMenu(anchor) {
  const menu = document.getElementById("git-menu");
  const rect = anchor.getBoundingClientRect();
  menu.style.top = `${rect.bottom + 6}px`;
  menu.style.left = `${Math.max(16, rect.right - 148)}px`;
  menu.classList.remove("hidden");
}

function openProjectAddMenu(anchor) {
  const menu = document.getElementById("project-add-menu");
  const rect = anchor.getBoundingClientRect();
  menu.style.top = `${rect.bottom + 6}px`;
  menu.style.left = `${Math.max(16, rect.right - 168)}px`;
  menu.classList.remove("hidden");
}

function renderGeneratedFilesMenuContent(workspaceId) {
  const payload = state.generatedFilesCache[workspaceId];
  if (!payload || payload.loading) {
    return `<div class="generated-files-menu-empty" style="padding:var(--space-4)"><div class="skeleton-block"><div class="skeleton-line"></div><div class="skeleton-line" style="width:75%"></div><div class="skeleton-line" style="width:55%"></div></div></div>`;
  }
  if (payload.error) {
    return `<div class="generated-files-menu-empty">${escapeHtml(payload.error)}</div>`;
  }

  const files = Array.isArray(payload.generated_files) ? payload.generated_files : [];
  if (!files.length) {
    return `<div class="generated-files-menu-empty">No generated files yet.</div>`;
  }

  const workspace = state.workspaces.find((item) => item.id === workspaceId);
  // Return template with empty list container; caller populates via createVirtualList
  return `
    <div class="generated-files-menu-header">
      <div class="generated-files-menu-title">${escapeHtml(workspace?.name || "Project files")}</div>
      <div class="generated-files-menu-count">${files.length}</div>
    </div>
    <div class="generated-files-menu-root">${escapeHtml(payload.generated_root || "")}</div>
    <div class="generated-files-menu-list" id="generated-files-vlist"></div>
  `;
}

function renderGeneratedFileItem(file) {
  return `
    <button type="button" class="generated-file-item" data-generated-file-open="${escapeHtml(file.path)}">
      <div class="generated-file-name">${escapeHtml(file.path)}</div>
      <div class="generated-file-meta">${escapeHtml(formatFileSize(file.size))} · ${escapeHtml(formatDateTime(file.modified_at) || "Now")}</div>
    </button>
  `;
}

async function openGeneratedFile(workspaceId, relativePath) {
  if (!workspaceId || !relativePath) {
    return;
  }
  await request(`/api/workspaces/${workspaceId}/generated-files/open`, {
    method: "POST",
    body: JSON.stringify({ path: relativePath }),
  });
}

async function openGeneratedFilesMenu(workspaceId, anchor) {
  closeWorkspaceMenu();
  state.generatedFilesMenuWorkspaceId = workspaceId;
  optimisticallyMarkGeneratedFilesSeen(workspaceId);
  renderWorkspaceRail();

  request(`/api/workspaces/${workspaceId}/generated-files/seen`, { method: "POST" })
    .then((payload) => {
      if (payload?.workspace) {
        state.workspaces = state.workspaces.map((workspace) => workspace.id === workspaceId ? payload.workspace : workspace);
        renderWorkspaceRail();
      }
    })
    .catch(() => {});
  const menu = document.getElementById("generated-files-menu");
  const rect = anchor.getBoundingClientRect();
  menu.style.top = `${rect.bottom + 6}px`;
  menu.style.left = `${Math.max(16, rect.right - 320)}px`;
  function setMenuContent() {
    menu.innerHTML = renderGeneratedFilesMenuContent(workspaceId);
    const vlist = menu.querySelector("#generated-files-vlist");
    const files = state.generatedFilesCache[workspaceId]?.generated_files;
    if (vlist && Array.isArray(files) && files.length) {
      createVirtualList(vlist, files, renderGeneratedFileItem);
    }
  }

  setMenuContent();
  menu.classList.remove("hidden");

  if (state.generatedFilesCache[workspaceId]?.generated_files || state.generatedFilesCache[workspaceId]?.error) {
    return;
  }

  state.generatedFilesCache[workspaceId] = { loading: true };
  setMenuContent();

  try {
    const payload = await request(`/api/workspaces/${workspaceId}/generated-files`);
    state.generatedFilesCache[workspaceId] = payload;
    state.workspaces = state.workspaces.map((workspace) => workspace.id === workspaceId ? payload.workspace : workspace);
    renderWorkspaceRail();
  } catch (error) {
    state.generatedFilesCache[workspaceId] = { error: error.message };
  }

  if (state.generatedFilesMenuWorkspaceId === workspaceId) {
    setMenuContent();
  }
}

function renderWorkspaceRail() {
  const rail = document.getElementById("workspace-rail");
  rail.innerHTML = "";

  for (const workspace of state.workspaces) {
    const row = document.createElement("div");
    row.className = `workspace-row ${workspace.id === state.currentWorkspaceId ? "active" : ""}`;

    const main = document.createElement("button");
    main.type = "button";
    main.className = "workspace-main";
    const sessionRuntime = workspace.session_runtime ? workspace.session_runtime.toUpperCase() : "";
    const sessionState = workspace.has_session ? (workspace.session_state || "cold") : "cold";
    const indicatorClass = workspace.has_session
      ? sessionState
      : (workspace.has_context ? "context" : "empty");
    const indicatorTitle = workspace.has_session
      ? `${sessionRuntime} session ${sessionState}`
      : (workspace.has_context
        ? `${workspace.last_runtime ? `${String(workspace.last_runtime).toUpperCase()} ` : ""}context available. BetterCode will include prior project context and recent conversation on the next turn.`
        : "No active session or saved context");
    main.innerHTML = `
      <div class="workspace-main-row">
        <div class="workspace-name">${workspace.name}</div>
        <span class="workspace-session-indicator ${indicatorClass}" title="${escapeHtml(indicatorTitle)}"></span>
      </div>
    `;
    main.addEventListener("click", async () => {
      await selectWorkspace(workspace.id);
      activateView("chat-view");
    });

    const actions = document.createElement("div");
    actions.className = "workspace-actions";

    if (workspace.has_generated_files) {
      const newGeneratedCount = generatedFilesBadgeCount(workspace);
      const generatedButton = document.createElement("button");
      generatedButton.type = "button";
      generatedButton.className = "icon-button workspace-generated-button";
      generatedButton.innerHTML = `
        <span class="workspace-generated-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" role="img" focusable="false">
            <path d="M3.5 7.5V5.75C3.5 4.78 4.28 4 5.25 4h5.05c.45 0 .88.18 1.2.5l1.5 1.5h5.75C19.72 6 20.5 6.78 20.5 7.75v10.5c0 .97-.78 1.75-1.75 1.75H5.25c-.97 0-1.75-.78-1.75-1.75V7.5z" />
          </svg>
        </span>
        ${newGeneratedCount ? `<span class="workspace-generated-count">${escapeHtml(newGeneratedCount > 99 ? "99+" : String(newGeneratedCount))}</span>` : ""}
      `;
      generatedButton.setAttribute("aria-label", `Show generated files for ${workspace.name}`);
      generatedButton.addEventListener("click", (event) => {
        event.stopPropagation();
        if (state.generatedFilesMenuWorkspaceId === workspace.id) {
          closeGeneratedFilesMenu();
          return;
        }
        openGeneratedFilesMenu(workspace.id, generatedButton);
      });
      actions.appendChild(generatedButton);
    }

    const gear = document.createElement("button");
    gear.type = "button";
    gear.className = "icon-button";
    gear.textContent = "⚙";
    gear.setAttribute("aria-label", `Project actions for ${workspace.name}`);
    gear.addEventListener("click", (event) => {
      event.stopPropagation();
      closeGeneratedFilesMenu();
      if (state.menuWorkspaceId === workspace.id) {
        closeWorkspaceMenu();
        return;
      }
      openWorkspaceMenu(workspace.id, gear);
    });

    row.appendChild(main);
    actions.appendChild(gear);
    row.appendChild(actions);
    rail.appendChild(row);
  }
}

function renderGitPanel() {
  const panel = document.getElementById("git-panel");
  const workspace = currentWorkspace();

  if (!workspace) {
    panel.innerHTML = `<div class="git-card"><div class="panel-copy">Select a project to view repository status.</div></div>`;
    return;
  }

  if (!state.git) {
    panel.innerHTML = `<div class="git-card"><div class="skeleton-block"><div class="skeleton-line" style="width:55%"></div><div class="skeleton-line" style="width:80%"></div><div class="skeleton-line" style="width:40%"></div></div></div>`;
    return;
  }

  if (!state.git.is_repo) {
    panel.innerHTML = `<div class="git-card"><div class="panel-copy">Not a Git repository.</div><button type="button" class="secondary-button" data-git-action="init">Initialize Repository</button></div>`;
    return;
  }

  const files = getGitFiles();
  const selectedCount = state.selectedGitPaths.length;
  const fileRows = files.map((entry) => {
    const status = `${entry.index_status ?? "."}${entry.worktree_status ?? "."}`;
    return `
      <label class="git-file-row ${state.selectedGitPaths.includes(entry.path) ? "selected" : ""}">
        <input type="checkbox" class="git-file-toggle" data-git-path="${entry.path}" ${state.selectedGitPaths.includes(entry.path) ? "checked" : ""}>
        <span class="git-file-details">
          <span class="git-file-path">${entry.path}</span>
          <span class="git-file-status">${status}</span>
        </span>
      </label>
    `;
  }).join("");

  panel.innerHTML = `
    <div class="git-card git-summary">
      <div class="git-summary-header">
        <div class="git-branch">${state.git.branch || "detached HEAD"}</div>
        <div class="git-file-count">${files.length} files</div>
      </div>
      <div class="git-stats">
        <span>${files.length} changed</span>
        <span>${state.git.staged.length} staged</span>
        <span>${state.git.ahead} ahead</span>
        <span>${state.git.behind} behind</span>
      </div>
    </div>
    <div class="git-card git-commit">
      <input id="git-commit-message" class="git-commit-input" placeholder="Commit message">
      <button type="button" class="primary-button" id="git-commit-button">Commit & Push</button>
    </div>
    <div class="git-card git-files">
      <div class="git-files-header">
        <div class="section-title">Files Changed</div>
        <div class="git-file-count">${selectedCount ? `${selectedCount} selected` : "Select files"}</div>
      </div>
      <div class="git-selection-actions">
        <button type="button" class="secondary-button" data-git-action="stage" ${selectedCount ? "" : "disabled"}>Stage Selected</button>
        <button type="button" class="secondary-button" data-git-action="unstage" ${selectedCount ? "" : "disabled"}>Unstage Selected</button>
      </div>
      <div class="git-files-list">${fileRows || '<div class="panel-copy">Working tree clean.</div>'}</div>
    </div>
    ${state.git.output ? `<div class="git-card git-output">${state.git.output}</div>` : ""}
  `;
}


function reviewAvailablePaths() {
  const changedFiles = state.reviewData?.changed_files || [];
  const recentFiles = state.reviewData?.recent_files || [];
  const allFiles = state.reviewAllFiles || [];
  const seen = new Set();
  const result = [];
  for (const entry of [...changedFiles, ...recentFiles, ...allFiles]) {
    if (!seen.has(entry.path)) {
      seen.add(entry.path);
      result.push(entry);
    }
  }
  return result;
}

function syncReviewSelection() {
  const available = new Set(reviewAvailablePaths().map((e) => e.path));
  state.selectedReviewPaths = (state.selectedReviewPaths || []).filter((p) => available.has(p));
}

function getReviewFilesForTab() {
  const tab = state.reviewFileTab || "changed";
  const search = (state.reviewSearch || "").toLowerCase().trim();
  let files;
  if (tab === "all") {
    files = state.reviewAllFiles || [];
  } else if (tab === "recent") {
    files = state.reviewData?.recent_files || [];
  } else {
    files = state.reviewData?.changed_files || [];
  }
  if (search) {
    files = files.filter((f) => f.path.toLowerCase().includes(search));
  }
  return files;
}

async function loadAllReviewFiles() {
  const workspace = reviewWorkspace();
  if (!workspace || state.reviewAllFilesLoading) return;
  state.reviewAllFilesLoading = true;
  renderReviewView();
  try {
    const data = await request(`/api/workspaces/${workspace.id}/review/all-files`);
    const raw = data.files || [];
    state.reviewAllFiles = raw.map((f) => (typeof f === "string" ? { path: f } : f));
  } catch (err) {
    showToast("Could not load all files: " + err.message);
  } finally {
    state.reviewAllFilesLoading = false;
    renderReviewView();
  }
}

function reviewPromptText(paths) {
  if (!paths || !paths.length) return "";
  return `Review the following files for bugs, security issues, performance problems, and code quality:\n${paths.map((p) => `- ${p}`).join("\n")}`;
}

function setReviewSelection(paths) {
  const available = new Set(reviewAvailablePaths().map((entry) => entry.path));
  state.selectedReviewPaths = Array.from(new Set(paths)).filter((path) => available.has(path));
  renderReviewPanel();
  renderReviewView();
}

function toggleReviewPathSelection(path, selected) {
  if (selected) {
    setReviewSelection([...state.selectedReviewPaths, path]);
    return;
  }
  setReviewSelection(state.selectedReviewPaths.filter((item) => item !== path));
}

function humanizeTaskType(taskType) {
  return taskType ? localizeRuntimeLine(String(taskType).replace(/_/g, " ")) : "";
}

function routingTaskBreakdown(routingMeta = {}) {
  if (!routingMeta || typeof routingMeta !== "object") {
    return {};
  }
  const breakdown = routingMeta.task_breakdown;
  return breakdown && typeof breakdown === "object" ? breakdown : {};
}

function routingBadgeLabels(routingMeta = {}) {
  if (!routingMeta || !Object.keys(routingMeta).length) {
    return [];
  }

  const breakdown = routingTaskBreakdown(routingMeta);
  const labels = [
    localizeRuntimeLine(routingMeta.selector_label || ""),
    localizeRuntimeLine(routingMeta.model_label || routingMeta.model_id || ""),
    humanizeTaskType(routingMeta.task_type),
  ];
  if (Number.isFinite(Number(breakdown.model_count)) && Number(breakdown.model_count) > 1) {
    labels.push(localizeRuntimeLine(`${Number(breakdown.model_count)} models`));
  }
  if (Number.isFinite(Number(breakdown.task_count)) && Number(breakdown.task_count) > 0) {
    labels.push(localizeRuntimeLine(`${Number(breakdown.task_count)} tasks`));
  }
  return labels.filter(Boolean);
}

function summarizeReviewText(content, maxLength = 180) {
  const clean = String(content || "").replace(/\s+/g, " ").trim();
  if (!clean) {
    return "";
  }
  if (clean.length <= maxLength) {
    return clean;
  }
  return `${clean.slice(0, maxLength - 1).trimEnd()}…`;
}

function summarizeNotificationText(content, maxLength = 140) {
  const clean = String(content || "").replace(/\s+/g, " ").trim();
  if (!clean) {
    return "";
  }
  if (clean.length <= maxLength) {
    return clean;
  }
  return `${clean.slice(0, maxLength - 1).trimEnd()}…`;
}

function latestAssistantMessage() {
  return [...state.messages].reverse().find((message) => message.role === "assistant") || null;
}

async function notifyDesktopTurnComplete(workspaceId, modelLabel) {
  const bridge = await ensureDesktopBridge();
  if (!bridge?.notifyTurnComplete) {
    return;
  }

  const workspace = state.workspaces.find((item) => item.id === workspaceId) || currentWorkspace();
  const assistantMessage = latestAssistantMessage();
  const title = workspace?.name ? `BetterCode • ${workspace.name}` : "BetterCode";
  const message = summarizeNotificationText(assistantMessage?.content || "")
    || `${modelLabel || "Assistant"} finished responding.`;

  bridge.notifyTurnComplete(title, message);
}

function renderLatestTurnSummary(message, options = {}) {
  const emptyText = localizeRuntimeLine(options.emptyText || "No review history yet.");
  if (!message) {
    return `<div class="review-empty-note">${escapeHtml(emptyText)}</div>`;
  }

  const routingMeta = message.routing_meta || {};
  const badges = routingBadgeLabels(routingMeta);
  const changeLog = Array.isArray(message.change_log) ? message.change_log : [];
  const visibleChanges = changeLog.slice(0, options.maxFiles || 5);
  const remainingChanges = Math.max(0, changeLog.length - visibleChanges.length);
  const summary = summarizeReviewText(message.content, options.maxSummaryLength || 220);

  return `
    <div class="review-card-header">
      <div>
        <div class="review-kicker">${escapeHtml(localizeRuntimeLine("Latest Turn"))}</div>
        <div class="review-updated">${escapeHtml(formatDateTime(message.created_at) || localizeRuntimeLine("Now"))}</div>
      </div>
      ${changeLog.length ? `<div class="git-file-count">${changeLog.length} ${escapeHtml(localizeRuntimeLine("files"))}</div>` : ""}
    </div>
    ${badges.length ? `
      <div class="review-badges">
        ${badges.map((badge) => `<span class="message-routing-badge">${escapeHtml(badge)}</span>`).join("")}
      </div>
    ` : ""}
    ${routingMeta.reason ? `<div class="review-reason">${escapeHtml(localizeRuntimeLine(routingMeta.reason))}</div>` : ""}
    ${summary ? `<div class="review-summary">${escapeHtml(summary)}</div>` : ""}
    ${visibleChanges.length ? `
      <div class="review-file-list">
        ${visibleChanges.map((change) => `<span class="message-change-file ${change.status || "modified"}">${escapeHtml(change.path || "Unknown file")}</span>`).join("")}
      </div>
    ` : ""}
    ${remainingChanges ? `<div class="review-more">${escapeHtml(localizeRuntimeLine(`+${remainingChanges} more`))}</div>` : ""}
  `;
}

function renderReviewPanel() {
  const panel = document.getElementById("review-panel");
  if (!panel) return;
  panel.innerHTML = "";
}

/**
 * Render items into a container in pages, appending more as the user scrolls.
 * Uses IntersectionObserver on a sentinel element — O(1) per item rendered.
 */
function createVirtualList(container, items, renderItem, pageSize = 60) {
  container.innerHTML = "";
  let rendered = 0;

  function renderBatch() {
    const batch = items.slice(rendered, rendered + pageSize);
    const fragment = document.createDocumentFragment();
    batch.forEach((item) => {
      const wrapper = document.createElement("div");
      wrapper.innerHTML = renderItem(item);
      while (wrapper.firstChild) fragment.appendChild(wrapper.firstChild);
    });
    rendered += batch.length;

    if (rendered < items.length) {
      const sentinel = document.createElement("div");
      sentinel.className = "vlist-sentinel";
      fragment.appendChild(sentinel);
      container.appendChild(fragment);
      const obs = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) {
          obs.disconnect();
          sentinel.remove();
          renderBatch();
        }
      }, { root: container.closest(".review-files-card, .generated-files-menu-list") || null, threshold: 0 });
      obs.observe(sentinel);
    } else {
      container.appendChild(fragment);
    }
  }

  renderBatch();
}

function renderReviewFileRow(entry) {
  return `
    <label class="review-file-row">
      <input type="checkbox" class="review-file-toggle" data-review-path="${escapeHtml(entry.path)}" ${state.selectedReviewPaths.includes(entry.path) ? "checked" : ""}>
      <span class="review-file-body">
        <span class="review-file-path">${escapeHtml(entry.path)}</span>
        <span class="review-file-meta-row">
          ${entry.status ? `<span class="message-change-file ${entry.status || "modified"}">${escapeHtml(entry.status)}</span>` : ""}
          ${entry.source_label ? `<span class="message-routing-badge">${escapeHtml(entry.source_label)}</span>` : ""}
          ${entry.git_status ? `<span class="message-routing-badge">${escapeHtml(entry.git_status)}</span>` : ""}
          ${entry.modified_at ? `<span class="review-file-meta">${escapeHtml(formatDateTime(entry.modified_at))}</span>` : ""}
        </span>
      </span>
    </label>
  `;
}

function renderReviewFileRows(entries, emptyText) {
  if (!Array.isArray(entries) || !entries.length) {
    return `<div class="review-empty-note">${escapeHtml(emptyText)}</div>`;
  }
  return entries.map(renderReviewFileRow).join("");
}

function renderReviewView() {
  const body = document.getElementById("review-view-body");
  const pickerBar = document.getElementById("review-project-picker-bar");
  const actionButton = document.getElementById("review-open-chat-button");
  if (!body || !pickerBar || !actionButton) return;

  const workspace = reviewWorkspace();
  const rr = state.reviewRun;
  const selectedCount = (state.selectedReviewPaths || []).length;
  const isRunning = rr.running;

  actionButton.disabled = isRunning || selectedCount === 0 || !workspace;
  actionButton.textContent = isRunning ? "Reviewing\u2026" : "Run Review";

  // Render project picker into the topbar slot.
  // The picker lives in <header> (outside #review-view-body), so its change events never
  // bubble to the review-view-body listener — attach a dedicated handler each render.
  const effectiveReviewId = state.reviewWorkspaceId || state.currentWorkspaceId;
  pickerBar.innerHTML = `
    <select class="review-topbar-project-select">
      <option value="" ${!effectiveReviewId ? "selected" : ""}>— pick a project —</option>
      ${state.workspaces.map((w) => `<option value="${w.id}" ${effectiveReviewId === w.id ? "selected" : ""}>${escapeHtml(w.name)}</option>`).join("")}
    </select>
  `;
  _renderControllers.reviewPicker?.abort();
  _renderControllers.reviewPicker = new AbortController();
  pickerBar.querySelector("select").addEventListener("change", (e) => {
    const newId = e.target.value ? Number(e.target.value) : null;
    if (newId !== state.reviewWorkspaceId) {
      state.reviewWorkspaceId = newId;
      state.reviewData = null;
      state.reviewError = "";
      state.selectedReviewPaths = [];
      state.reviewSearch = "";
      state.reviewFileTab = "changed";
      state.reviewAllFiles = [];
      state.reviewAllFilesLoading = false;
      renderReviewView();
      if (newId) loadReviewData(true, true).catch((err) => showToast(err.message));
    }
  }, { signal: _renderControllers.reviewPicker.signal });

  const historyCount = state.savedReviews.length;
  const hasResults = rr.phase !== "idle" || !!state.reviewViewingSaved;
  const tabBar = `
    <div class="review-tab-bar">
      <button type="button" class="review-tab ${state.reviewTab === "new" ? "active" : ""}" data-review-tab="new">New Review</button>
      ${hasResults ? `<button type="button" class="review-tab ${state.reviewTab === "results" ? "active" : ""}" data-review-tab="results">
        ${isRunning ? `<span class="review-tab-spinner"></span> ` : ""}Results${(() => {
          const count = state.reviewViewingSaved
            ? (state.reviewViewingSaved.findings || []).length
            : (!isRunning && rr.findings?.length ? (rr.findings || []).filter(f => !rr.dismissedIds.includes(f._id)).length : 0);
          return count ? ` <span class="review-tab-count">${count}</span>` : "";
        })()}
      </button>` : ""}
      <button type="button" class="review-tab ${state.reviewTab === "history" ? "active" : ""}" data-review-tab="history">
        History${historyCount ? ` <span class="review-tab-count">${historyCount}</span>` : ""}
      </button>
    </div>`;

  if (state.reviewTab === "history") {
    body.innerHTML = tabBar + renderReviewHistoryTab(workspace);
    return;
  }

  if (state.reviewTab === "results") {
    body.innerHTML = tabBar + renderReviewResultsTab(rr, workspace);
    const logEl = document.getElementById("review-progress-log");
    if (logEl) logEl.scrollTop = logEl.scrollHeight;
    return;
  }

  if (!workspace) {
    body.innerHTML = tabBar + `
      <div class="review-layout">
        <article class="review-page-card">
          <div class="review-empty-note">Select a project above to load files for review.</div>
        </article>
      </div>
    `;
    return;
  }

  if (state.reviewLoading) {
    body.innerHTML = tabBar + `<div class="review-layout"><article class="review-page-card"><div class="skeleton-block"><div class="skeleton-line"></div><div class="skeleton-line" style="width:70%"></div><div class="skeleton-line" style="width:85%"></div><div class="skeleton-line" style="width:60%"></div></div></article></div>`;
    return;
  }

  if (state.reviewError) {
    body.innerHTML = tabBar + `
      <div class="review-layout">
        <article class="review-page-card">
          <div class="review-error-banner">Failed to load files: ${escapeHtml(state.reviewError)}</div>
          <div class="review-selection-actions" style="margin-top:10px">
            <button type="button" class="secondary-button" data-review-action="refresh">Try Again</button>
          </div>
        </article>
      </div>
    `;
    return;
  }

  const changedFiles = state.reviewData?.changed_files || [];
  const recentFiles = state.reviewData?.recent_files || [];
  const models = state.appInfo?.models || [];
  const realModels = models.filter((m) => m.id !== "smart");

  // Auto-initialize primaryModel to the first real model if unset or previously "smart"
  if ((!rr.primaryModel || rr.primaryModel === "smart") && realModels.length) {
    state.reviewRun.primaryModel = realModels[0].id;
  }

  const modelOptions = realModels
    .map((m) => `<option value="${escapeHtml(m.id)}" ${rr.primaryModel === m.id ? "selected" : ""}>${escapeHtml(m.label)}</option>`)
    .join("");
  const secondaryModelOptions = realModels
    .map((m) => `<option value="${escapeHtml(m.id)}" ${rr.secondaryModel === m.id ? "selected" : ""}>${escapeHtml(m.label)}</option>`)
    .join("");

  const fileTab = state.reviewFileTab || "changed";
  const reviewSearch = state.reviewSearch || "";
  const filesForTab = getReviewFilesForTab();
  const allCount = state.reviewAllFiles.length;

  const fileSectionBody = (() => {
    if (fileTab === "all" && state.reviewAllFilesLoading) {
      return `<div class="review-loading-note"><span class="review-progress-spinner"></span> Loading files…</div>`;
    }
    if (fileTab === "all" && !allCount) {
      return `<div class="review-empty-note">Click <strong>Load</strong> to browse all workspace files.</div>`;
    }
    if (!filesForTab.length && reviewSearch) {
      return `<div class="review-empty-note">No files match "<strong>${escapeHtml(reviewSearch)}</strong>"</div>`;
    }
    if (!filesForTab.length) {
      return `<div class="review-empty-note">No ${fileTab} files found. <button type="button" class="inline-text-btn" data-review-action="refresh">Refresh</button></div>`;
    }
    return `<div class="review-file-list" id="review-vlist-files"></div>`;
  })();

  body.innerHTML = tabBar + `
    <div class="review-layout">
      <div class="review-top-row">

        <article class="review-page-card review-files-card">
          <div class="review-files-toolbar">
            <span class="review-file-section-title">
              Files${selectedCount ? ` <span class="review-files-badge">${selectedCount} selected</span>` : ""}
            </span>
            <div class="review-files-toolbar-right">
              ${selectedCount ? `<button type="button" class="secondary-button btn-xs" data-review-action="clear-selection">Clear</button>` : ""}
              <button type="button" class="icon-button" data-review-action="refresh" title="Refresh">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              </button>
            </div>
          </div>

          <input
            type="search"
            class="review-file-search"
            placeholder="Filter files…"
            value="${escapeHtml(reviewSearch)}"
            data-review-search
            autocomplete="off"
            spellcheck="false"
          >

          <div class="review-file-tabs">
            <button type="button" class="review-file-tab ${fileTab === "changed" ? "active" : ""}" data-review-filetab="changed">
              Changed${changedFiles.length ? ` <span class="review-file-tab-count">${changedFiles.length}</span>` : ""}
            </button>
            <button type="button" class="review-file-tab ${fileTab === "recent" ? "active" : ""}" data-review-filetab="recent">
              Recent${recentFiles.length ? ` <span class="review-file-tab-count">${recentFiles.length}</span>` : ""}
            </button>
            <button type="button" class="review-file-tab ${fileTab === "all" ? "active" : ""}" data-review-filetab="all" ${state.reviewAllFilesLoading ? "disabled" : ""}>
              All Files${allCount ? ` <span class="review-file-tab-count">${allCount}</span>` : ""}
            </button>
          </div>

          <div class="review-files-list-wrap">${fileSectionBody}</div>

          ${filesForTab.length > 1 ? `
            <div class="review-files-footer">
              <button type="button" class="secondary-button btn-xs" data-review-action="select-view">Select all (${filesForTab.length})</button>
            </div>
          ` : ""}
        </article>

        <article class="review-page-card review-config-card">
          <div class="review-config-section">
            <div class="review-config-group">
              <label class="review-config-label">Depth</label>
              <div class="review-depth-switcher">
                <button type="button" class="review-depth-btn ${(state.review.depth || "standard") === "quick" ? "active" : ""}" data-review-depth="quick">Quick</button>
                <button type="button" class="review-depth-btn ${(state.review.depth || "standard") === "standard" ? "active" : ""}" data-review-depth="standard">Standard</button>
                <button type="button" class="review-depth-btn ${(state.review.depth || "standard") === "deep" ? "active" : ""}" data-review-depth="deep">Deep</button>
              </div>
            </div>
            <div class="review-config-group">
              <label class="review-config-label">Reviewer</label>
              <select class="review-model-select" data-review-model="primary">
                ${modelOptions}
              </select>
            </div>
            <div class="review-config-group">
              <label class="review-config-label">Second Reviewer <span class="review-config-optional">optional</span></label>
              <select class="review-model-select" data-review-model="secondary">
                <option value="none" ${rr.secondaryModel === "none" ? "selected" : ""}>None</option>
                ${secondaryModelOptions}
              </select>
            </div>
            <div class="review-run-row">
              <button type="button" class="primary-button review-run-btn" data-review-action="run" ${isRunning || !selectedCount ? "disabled" : ""}>
                ${isRunning ? "Reviewing\u2026" : selectedCount ? `Review ${selectedCount} file${selectedCount !== 1 ? "s" : ""}` : "Run Review"}
              </button>
              ${!selectedCount ? `<div class="review-run-hint">Select files to begin.</div>` : ""}
            </div>
            <div class="review-full-row">
              <button type="button" class="secondary-button review-full-btn" data-review-action="full-codebase" ${isRunning ? "disabled" : ""}>
                Review Full Codebase
              </button>
            </div>
          </div>
        </article>

      </div>
    </div>
  `;

  // Populate file list using virtual rendering
  const fileList = body.querySelector("#review-vlist-files");
  if (fileList && filesForTab.length) createVirtualList(fileList, filesForTab, renderReviewFileRow);

  // Restore search input focus if user was typing
  const searchEl = body.querySelector("[data-review-search]");
  if (searchEl && reviewSearch) {
    searchEl.setSelectionRange(searchEl.value.length, searchEl.value.length);
  }

  // Keep sidebar badge in sync regardless of which view is active
  const tabBtn = document.getElementById("review-open-button");
  if (tabBtn) tabBtn.classList.toggle("running", rr.running && state.view !== "review-view");
}

async function loadReviewData(force = false, showErrorToast = false) {
  const workspace = reviewWorkspace();
  if (!workspace) {
    state.reviewData = null;
    state.reviewLoading = false;
    state.reviewError = "";
    state.selectedReviewPaths = [];
    renderReviewPanel();
    renderReviewView();
    return null;
  }

  if (state.reviewLoading && !force) {
    return state.reviewData;
  }
  // Only use cached data if it's for the same workspace
  if (state.reviewData && state.reviewData.workspace?.id === workspace.id && !force) {
    renderReviewPanel();
    renderReviewView();
    return state.reviewData;
  }

  const workspaceId = workspace.id;
  state.reviewLoading = true;
  state.reviewError = "";
  state.reviewData = null;
  state.selectedReviewPaths = [];
  renderReviewPanel();
  renderReviewView();

  try {
    const payload = await request(`/api/workspaces/${workspaceId}/review`);
    // Discard if workspace changed while loading
    if ((state.reviewWorkspaceId || state.currentWorkspaceId) !== workspaceId) {
      return null;
    }
    state.reviewData = payload;
    syncReviewSelection();
    return payload;
  } catch (error) {
    if ((state.reviewWorkspaceId || state.currentWorkspaceId) !== workspaceId) {
      return null;
    }
    state.reviewData = null;
    state.reviewError = error.message;
    if (showErrorToast) {
      showToast(error.message);
    }
    return null;
  } finally {
    if ((state.reviewWorkspaceId || state.currentWorkspaceId) === workspaceId) {
      state.reviewLoading = false;
      renderReviewPanel();
      renderReviewView();
    }
  }
}

async function openReviewView() {
  // If a review is running or has results, show the Results tab
  const rr = state.reviewRun;
  if (rr.phase !== "idle" && state.reviewTab !== "history") {
    state.reviewTab = "results";
  }
  activateView("review-view");
  window.setTimeout(() => {
    loadReviewData(false, true).catch((error) => showToast(error.message));
    const ws = reviewWorkspace();
    if (ws) {
      loadReviewHistory(ws.id);
    }
  }, 0);
}

function parseReviewResult(content) {
  const text = String(content || "").trim();
  const jsonMatch = text.match(/\{[\s\S]*\}/);
  if (!jsonMatch) return { summary: text.slice(0, 300), findings: [] };
  try {
    const parsed = JSON.parse(jsonMatch[0]);
    return {
      summary: String(parsed.summary || ""),
      findings: Array.isArray(parsed.findings) ? parsed.findings : [],
    };
  } catch {
    return { summary: text.slice(0, 300), findings: [] };
  }
}

function dismissFinding(id) {
  if (!state.reviewRun.dismissedIds.includes(id)) {
    state.reviewRun.dismissedIds = [...state.reviewRun.dismissedIds, id];
    renderReviewView();
  }
}

function implementFinding(id) {
  const finding = state.reviewRun.findings.find((f) => f._id === id);
  if (!finding) return;
  const instruction = finding.fix_instruction || finding.description || finding.title || "";
  const fileHint = finding.file ? ` (${finding.file}${finding.line_hint ? `:${finding.line_hint}` : ""})` : "";
  setComposerDraft(`${instruction}${fileHint}`, []);
  activateView("chat-view");
  document.getElementById("chat-input")?.focus();
}

async function openFullReviewModal() {
  const workspace = reviewWorkspace();
  if (!workspace) {
    showToast("Select a project to review.");
    return;
  }
  const modal = document.getElementById("full-review-modal");
  const countEl = document.getElementById("full-review-file-count");
  if (!modal) return;

  // Fetch all files count first so we can show it in the warning
  let allFiles = null;
  try {
    const data = await request(`/api/workspaces/${workspace.id}/review/all-files`);
    allFiles = data.files || [];
    if (countEl) countEl.textContent = `${allFiles.length} file${allFiles.length !== 1 ? "s" : ""}`;
  } catch (_) {
    if (countEl) countEl.textContent = "all files";
  }

  modal.classList.remove("hidden");
  modal.dataset.files = JSON.stringify(allFiles || []);
  document.getElementById("full-review-confirm")?.focus();
}

function closeFullReviewModal() {
  const modal = document.getElementById("full-review-modal");
  if (modal) {
    modal.classList.add("hidden");
    modal.dataset.files = "";
  }
}

async function runFullCodebaseReview() {
  const modal = document.getElementById("full-review-modal");
  const allFiles = JSON.parse(modal?.dataset.files || "[]");
  closeFullReviewModal();

  const workspace = reviewWorkspace();
  if (!workspace) {
    showToast("Select a project to review.");
    return;
  }
  if (!allFiles.length) {
    showToast("No files found to review.");
    return;
  }

  state.selectedReviewPaths = allFiles;
  await runCodeReview();
}

async function runCodeReview() {
  if (!(state.selectedReviewPaths || []).length) {
    showToast("Select at least one file to review.");
    return;
  }
  const workspace = reviewWorkspace();
  if (!workspace) {
    showToast("Select a project to review.");
    return;
  }

  state.reviewRun = {
    ...state.reviewRun,
    running: true,
    phase: "primary",
    activityLines: ["Starting review\u2026"],
    findings: [],
    summaryPrimary: "",
    summarySecondary: "",
    primaryModelLabel: "",
    secondaryModelLabel: "",
    error: null,
  };
  state.reviewViewingSaved = null;
  state.reviewTab = "results";
  // Pin the workspace so navigating away and back still shows this review
  state.reviewWorkspaceId = workspace.id;
  activateView("review-view");
  renderReviewView();

  try {
    const response = await fetch(`/api/workspaces/${workspace.id}/review/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        files: state.selectedReviewPaths,
        depth: state.review.depth || "standard",
        primary_model: state.reviewRun.primaryModel,
        secondary_model: state.reviewRun.secondaryModel || "none",
      }),
    });

    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json") ? await response.json() : await response.text();
      throw new Error(typeof payload === "string" ? payload : (payload.detail || "Review failed."));
    }

    await readStreamResponse(response, async (event) => {
      if (event.type === "status") {
        if (event.message) state.reviewRun.activityLines.push(event.message);
        if (event.role === "secondary") state.reviewRun.phase = "secondary";
        if (event.model_label) {
          if (event.role === "primary") state.reviewRun.primaryModelLabel = event.model_label;
          else if (event.role === "secondary") state.reviewRun.secondaryModelLabel = event.model_label;
        }
        renderReviewView();
        const logEl = document.getElementById("review-progress-log");
        if (logEl) logEl.scrollTop = logEl.scrollHeight;
        return;
      }
      if (event.type === "result") {
        const parsed = parseReviewResult(event.content || "");
        const source = event.role === "secondary" ? "secondary" : "primary";
        if (source === "primary") {
          state.reviewRun.summaryPrimary = parsed.summary;
          state.reviewRun.primaryModelLabel = event.model_label || state.reviewRun.primaryModelLabel;
        } else {
          state.reviewRun.summarySecondary = parsed.summary;
          state.reviewRun.secondaryModelLabel = event.model_label || state.reviewRun.secondaryModelLabel;
        }
        const newFindings = parsed.findings.map((f, i) => ({
          ...f,
          _source: source,
          _id: `${source[0]}-${f.id || i}-${Date.now()}`,
        }));
        state.reviewRun.findings = [...state.reviewRun.findings, ...newFindings];
        renderReviewView();
        return;
      }
      if (event.type === "error") {
        state.reviewRun.error = event.message || "Review failed.";
        state.reviewRun.running = false;
        state.reviewRun.phase = "error";
        renderReviewView();
        return;
      }
      if (event.type === "final") {
        state.reviewRun.running = false;
        state.reviewRun.phase = "done";
        state.reviewRun.savedId = event.review_id || null;
        renderReviewView();
        const ws = reviewWorkspace();
        if (ws) loadReviewHistory(ws.id);
      }
    });
  } catch (error) {
    state.reviewRun.error = error.message;
    state.reviewRun.running = false;
    state.reviewRun.phase = "error";
    renderReviewView();
  }
}

async function loadReviewHistory(workspaceId) {
  try {
    const resp = await fetch(`/api/workspaces/${workspaceId}/reviews`);
    if (!resp.ok) return;
    const data = await resp.json();
    const activeReviewWorkspaceId = state.reviewWorkspaceId || state.currentWorkspaceId;
    if (activeReviewWorkspaceId !== workspaceId) {
      return;
    }
    state.savedReviews = data.reviews || [];
    if (state.view === "review-view") renderReviewView();
  } catch (_) {}
}

function buildReviewReport(rr, workspaceName) {
  const date = new Date().toLocaleString();
  const severityColors = { critical: "#ef4444", high: "#f97316", medium: "#eab308", low: "#22c55e", info: "#60a5fa" };
  const findings = (rr.findings || []).filter(f => !rr.dismissedIds.includes(f._id));
  const findingRows = findings.map(f => `
    <div class="finding">
      <div class="finding-header">
        <span class="badge" style="background:${severityColors[f.severity] || "#888"}">${(f.severity || "info").toUpperCase()}</span>
        <span class="category">${escapeHtml(f.category || "")}</span>
        <strong>${escapeHtml(f.title || "")}</strong>
        ${f._source === "secondary" ? `<span class="secondary-badge">2nd reviewer</span>` : ""}
      </div>
      <p>${escapeHtml(f.description || "")}</p>
      ${f.file ? `<div class="file-ref">${escapeHtml(f.file)}${f.line_hint ? `:${f.line_hint}` : ""}</div>` : ""}
      ${f.fix_instruction ? `<div class="fix"><strong>Fix:</strong> ${escapeHtml(f.fix_instruction)}</div>` : ""}
    </div>`).join("");
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Code Review Report — ${escapeHtml(workspaceName || "Project")}</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:860px;margin:40px auto;padding:0 24px;color:#1a1a2e;line-height:1.6}
  h1{font-size:22px;margin-bottom:4px}
  .meta{color:#666;font-size:13px;margin-bottom:32px}
  .section{margin-bottom:32px}
  h2{font-size:16px;text-transform:uppercase;letter-spacing:.08em;color:#666;border-bottom:1px solid #e5e7eb;padding-bottom:6px;margin-bottom:16px}
  .summary{background:#f8f9fc;border-radius:8px;padding:16px;font-size:14px}
  .finding{border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px}
  .finding-header{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
  .badge{color:#fff;font-size:11px;font-weight:700;padding:2px 7px;border-radius:4px}
  .category{font-size:11px;background:#f0f0f5;padding:2px 7px;border-radius:4px;color:#555}
  .secondary-badge{font-size:11px;background:#e0e7ff;color:#4f46e5;padding:2px 7px;border-radius:4px}
  .file-ref{font-family:monospace;font-size:12px;color:#666;margin-top:6px}
  .fix{font-size:13px;margin-top:8px;padding:8px;background:#f0fdf4;border-radius:4px;color:#166534}
  p{margin:0 0 4px;font-size:14px}
  .files-list{font-family:monospace;font-size:13px;color:#555}
</style>
</head>
<body>
<h1>Code Review Report</h1>
<div class="meta">
  ${escapeHtml(workspaceName || "Project")} &nbsp;·&nbsp; ${date}<br>
  Primary: ${escapeHtml(rr.primaryModelLabel || rr.primaryModel || "—")}
  ${rr.secondaryModelLabel ? ` &nbsp;·&nbsp; Secondary: ${escapeHtml(rr.secondaryModelLabel)}` : ""}
  &nbsp;·&nbsp; Depth: ${escapeHtml(rr.depth || "standard")}
  &nbsp;·&nbsp; ${findings.length} finding${findings.length !== 1 ? "s" : ""}
</div>
${rr.summaryPrimary ? `<div class="section"><h2>Summary</h2><div class="summary">${escapeHtml(rr.summaryPrimary)}</div></div>` : ""}
${rr.summarySecondary ? `<div class="section"><h2>Secondary Reviewer Summary</h2><div class="summary">${escapeHtml(rr.summarySecondary)}</div></div>` : ""}
${findings.length ? `<div class="section"><h2>Findings (${findings.length})</h2>${findingRows}</div>` : `<div class="section"><p>No findings.</p></div>`}
</body>
</html>`;
  const filename = `code-review-${(workspaceName || "report").replace(/[^a-z0-9]/gi, "-").toLowerCase()}-${Date.now()}.html`;
  return { html, filename };
}

async function generateReviewReport(rr, workspaceName) {
  const { html, filename } = buildReviewReport(rr, workspaceName);
  const bridge = await ensureDesktopBridge();
  if (bridge?.saveReviewReport) {
    try {
      const savedPath = await bridge.saveReviewReport(filename, html);
      if (savedPath) {
        showToast("Review report saved.");
      }
      return;
    } catch {
      showToast("Could not save review report.");
      return;
    }
  }
  const blob = new Blob([html], { type: "text/html" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderReviewFindingCards(findings, dismissedIds, allowDismiss = true) {
  const visible = findings.filter(f => !(dismissedIds || []).includes(f._id));
  if (!visible.length) return "";
  return `<div class="review-findings-list">
    ${visible.map((finding) => `
      <div class="review-finding-card" data-finding-id="${escapeHtml(finding._id)}">
        <div class="review-finding-header">
          <span class="review-severity-badge severity-${escapeHtml(finding.severity || "info")}">${escapeHtml((finding.severity || "info").toUpperCase())}</span>
          <span class="review-category-badge">${escapeHtml(finding.category || "")}</span>
          <span class="review-finding-title">${escapeHtml(finding.title || "")}</span>
          ${finding._source === "secondary" ? `<span class="review-source-badge">2nd</span>` : ""}
        </div>
        <div class="review-finding-desc">${escapeHtml(finding.description || "")}</div>
        ${finding.file ? `<div class="review-finding-meta">${escapeHtml(finding.file)}${finding.line_hint ? `:${escapeHtml(String(finding.line_hint))}` : ""}</div>` : ""}
        ${finding.fix_instruction ? `<div class="review-finding-fix">${escapeHtml(finding.fix_instruction)}</div>` : ""}
        <div class="review-finding-actions">
          <button type="button" class="primary-button review-finding-btn" data-review-action="implement-finding" data-finding-id="${escapeHtml(finding._id)}">Implement Fix</button>
          ${allowDismiss ? `<button type="button" class="secondary-button review-finding-btn" data-review-action="dismiss-finding" data-finding-id="${escapeHtml(finding._id)}">Dismiss</button>` : ""}
        </div>
      </div>
    `).join("")}
  </div>`;
}

function renderReviewResultsTab(rr, workspace) {
  // May be showing a saved review from history instead of live run
  const saved = state.reviewViewingSaved;
  const isLive = !saved;
  const isRunning = isLive && rr.running;
  const phase = isLive ? rr.phase : "done";
  const error = isLive ? rr.error : null;
  const summaryPrimary = isLive ? rr.summaryPrimary : (saved?.summary_primary || "");
  const summarySecondary = isLive ? rr.summarySecondary : (saved?.summary_secondary || "");
  const primaryLabel = isLive ? rr.primaryModelLabel : (saved?.primary_model_label || "");
  const secondaryLabel = isLive ? rr.secondaryModelLabel : (saved?.secondary_model_label || "");
  const activityLines = isLive ? (rr.activityLines || []) : [];
  const allFindings = isLive
    ? (rr.findings || [])
    : (saved?.findings || []).map((f, i) => ({ ...f, _id: `sv-${saved.id}-${i}`, _source: f._source || "primary" }));
  const dismissedIds = isLive ? (rr.dismissedIds || []) : [];
  const visibleFindings = allFindings.filter(f => !dismissedIds.includes(f._id));

  const phaseLabel = rr.phase === "secondary"
    ? `Secondary review${secondaryLabel ? ` · ${escapeHtml(secondaryLabel)}` : "…"}`
    : `Primary review${primaryLabel ? ` · ${escapeHtml(primaryLabel)}` : "…"}`;

  const savedMeta = saved ? `
    <div class="review-saved-meta">
      ${escapeHtml(new Date(saved.created_at).toLocaleString())}
      ${primaryLabel ? ` · ${escapeHtml(primaryLabel)}` : ""}
      ${secondaryLabel ? ` + ${escapeHtml(secondaryLabel)}` : ""}
      · ${escapeHtml(saved.depth || "standard")}
      · ${saved.files?.length || 0} file${(saved.files?.length || 0) !== 1 ? "s" : ""}
    </div>` : "";

  return `<div class="review-layout review-results-layout">
    <article class="review-page-card review-results-card">
      ${savedMeta}
      ${isRunning ? `
        <div class="review-progress-header">
          <div class="review-progress-label">
            <span class="review-progress-spinner"></span>
            ${phaseLabel}
          </div>
          ${activityLines.length ? `
            <div class="review-progress-log" id="review-progress-log">
              ${activityLines.map(line => `<div class="review-progress-line">${escapeHtml(line)}</div>`).join("")}
            </div>
          ` : ""}
        </div>
      ` : activityLines.length ? `
        <details class="review-activity-details">
          <summary class="review-activity-summary">Activity Log (${activityLines.length} steps)</summary>
          <div class="review-progress-log">
            ${activityLines.map(line => `<div class="review-progress-line">${escapeHtml(line)}</div>`).join("")}
          </div>
        </details>
      ` : ""}

      ${error ? `<div class="review-error-banner">${escapeHtml(error)}</div>` : ""}

      ${summaryPrimary || summarySecondary ? `
        <div class="review-summaries">
          ${summaryPrimary ? `
            <div class="review-summary-block">
              <div class="review-summary-source">${escapeHtml(primaryLabel || "Primary")} · Summary</div>
              <div class="review-summary-text">${escapeHtml(summaryPrimary)}</div>
            </div>
          ` : ""}
          ${summarySecondary ? `
            <div class="review-summary-block">
              <div class="review-summary-source">${escapeHtml(secondaryLabel || "Secondary")} · Summary</div>
              <div class="review-summary-text">${escapeHtml(summarySecondary)}</div>
            </div>
          ` : ""}
        </div>
      ` : ""}

      ${visibleFindings.length
        ? `<div class="review-findings-header">${visibleFindings.length} finding${visibleFindings.length !== 1 ? "s" : ""}</div>` + renderReviewFindingCards(allFindings, dismissedIds, isLive)
        : phase === "done" && !error
          ? `<div class="review-empty-note">${allFindings.length ? "All findings dismissed." : "✓ No findings — code looks good!"}</div>`
          : ""}

      ${phase === "done" && !error ? `
        <div class="review-download-row">
          <button type="button" class="secondary-button" data-review-action="${saved ? "download-saved-current" : "download-report"}">Download Report</button>
          ${saved ? `<button type="button" class="secondary-button" data-review-action="close-saved-view">← Back to History</button>` : ""}
        </div>
      ` : ""}
    </article>
  </div>`;
}

function renderReviewHistoryTab(workspace) {
  const reviews = state.savedReviews;
  if (!reviews.length) {
    return `<div class="review-layout"><article class="review-page-card"><div class="review-empty-note">No saved reviews yet. Run a review to save it here.</div></article></div>`;
  }
  const severityOrder = ["critical", "high", "medium", "low", "info"];
  const rows = reviews.map(r => {
    const findings = r.findings || [];
    const countsBySeverity = severityOrder.filter(s => findings.some(f => f.severity === s));
    const badges = countsBySeverity.map(s => {
      const n = findings.filter(f => f.severity === s).length;
      return `<span class="review-history-severity-badge severity-${s}">${n} ${s}</span>`;
    }).join("");
    const dateStr = r.created_at ? new Date(r.created_at).toLocaleString() : "";
    const modelStr = [r.primary_model_label, r.secondary_model_label].filter(Boolean).join(" + ");
    return `
      <div class="review-history-row" data-review-history-id="${r.id}">
        <div class="review-history-meta">
          <div class="review-history-date">${escapeHtml(dateStr)}</div>
          <div class="review-history-detail">${escapeHtml(modelStr)}${r.depth ? ` · ${r.depth}` : ""} · ${r.files.length} file${r.files.length !== 1 ? "s" : ""}</div>
        </div>
        <div class="review-history-badges">${badges || `<span class="review-history-clean">No findings</span>`}</div>
        <div class="review-history-actions">
          <button type="button" class="primary-button" data-review-action="view-saved" data-review-id="${r.id}">View</button>
          <button type="button" class="secondary-button" data-review-action="download-saved" data-review-id="${r.id}">Download</button>
        </div>
      </div>`;
  }).join("");
  return `<div class="review-layout"><article class="review-page-card review-history-card"><div class="review-history-list">${rows}</div></article></div>`;
}

function diffLineClass(line) {
  if (line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++")) {
    return "diff-line meta";
  }
  if (line.startsWith("+")) {
    return "diff-line added";
  }
  if (line.startsWith("-")) {
    return "diff-line removed";
  }
  return "diff-line";
}

function buildChangeDiff(change = {}) {
  const path = change.path || "unknown";
  const status = change.status || "modified";
  const diffText = String(change.diff || "").trim();
  if (diffText) {
    return diffText;
  }
  const note = change.note || "Diff preview unavailable for this file.";
  return `# ${path} (${status})\n# ${note}`;
}

function buildChangeDiffPreview(change = null) {
  let text = buildChangeDiff(change || {});
  if (!text) {
    return { text: "", trimmed: false };
  }

  let trimmed = false;
  if (text.length > MESSAGE_CHANGE_MAX_DIFF_CHARS) {
    text = text.slice(0, MESSAGE_CHANGE_MAX_DIFF_CHARS);
    const lastNewline = text.lastIndexOf("\n");
    if (lastNewline > 0) {
      text = text.slice(0, lastNewline);
    }
    trimmed = true;
  }

  const lines = text.split("\n");
  if (lines.length > MESSAGE_CHANGE_MAX_DIFF_LINES) {
    text = lines.slice(0, MESSAGE_CHANGE_MAX_DIFF_LINES).join("\n");
    trimmed = true;
  }

  return { text, trimmed };
}

function describeChangePath(path = "") {
  const full = String(path || "Unknown file");
  const normalized = full.replace(/\\/g, "/");
  const slashIndex = normalized.lastIndexOf("/");
  if (slashIndex < 0) {
    return { full, name: normalized || "Unknown file", directory: "" };
  }
  return {
    full,
    name: normalized.slice(slashIndex + 1) || normalized,
    directory: normalized.slice(0, slashIndex),
  };
}

function buildMessageArtifactEntries(changeLog = []) {
  const entries = [];
  if (Array.isArray(changeLog)) {
    for (const [index, change] of changeLog.entries()) {
      const pathInfo = describeChangePath(change?.path);
      entries.push({
        key: `file:${index}`,
        kind: "file",
        label: pathInfo.name,
        meta: pathInfo.directory,
        status: change?.status || "modified",
        change,
      });
    }
  }
  return entries;
}

function setActiveChangeTab(section, activeIndex = 0) {
  if (!section) {
    return;
  }
  section.dataset.activeChangeIndex = String(activeIndex);
  section.querySelectorAll("[data-change-tab-index]").forEach((tab) => {
    const isActive = Number(tab.dataset.changeTabIndex || -1) === activeIndex;
    tab.classList.toggle("active", isActive);
    tab.setAttribute("aria-selected", isActive ? "true" : "false");
    tab.tabIndex = isActive ? 0 : -1;
  });
}

function populateChangeDiffContent(container, change = {}, { headerClass = "message-change-current" } = {}) {
  if (!container) {
    return;
  }
  const pathInfo = describeChangePath(change.path);
  const { text, trimmed } = buildChangeDiffPreview(change);
  container.innerHTML = "";

  if (headerClass) {
    const current = document.createElement("div");
    current.className = headerClass;
    current.innerHTML = `
      <div class="message-change-current-main">
        <div class="message-change-current-name" title="${escapeHtml(pathInfo.full)}">${escapeHtml(pathInfo.name)}</div>
        ${pathInfo.directory ? `<div class="message-change-current-dir" title="${escapeHtml(pathInfo.full)}">${escapeHtml(pathInfo.directory)}</div>` : ""}
      </div>
      <span class="message-change-status ${escapeHtml(change.status || "modified")}">${escapeHtml(change.status || "modified")}</span>
    `;
    container.appendChild(current);
  }

  if (trimmed) {
    const note = document.createElement("div");
    note.className = "message-change-more";
    note.textContent = localizeRuntimeLine("Showing a trimmed diff preview.");
    container.appendChild(note);
  }

  for (const lineText of text.split("\n")) {
    const line = document.createElement("div");
    line.className = diffLineClass(lineText);
    line.textContent = lineText || " ";
    container.appendChild(line);
  }
}

function appendChangeDiff(section, changeLog = [], activeIndex = 0) {
  const diff = section?.querySelector(".message-diff");
  if (!diff || !Array.isArray(changeLog) || !changeLog.length) {
    return;
  }

  const nextIndex = Math.max(0, Math.min(changeLog.length - 1, Number(activeIndex) || 0));
  const change = changeLog[nextIndex] || {};
  setActiveChangeTab(section, nextIndex);
  populateChangeDiffContent(diff, change, { headerClass: "message-change-current" });
}

function appendChangeDetails(container, changeLog = []) {
  if (!container || !Array.isArray(changeLog) || !changeLog.length) {
    return;
  }

  const section = document.createElement("section");
  section.className = "message-change-section";
  section._changeLog = changeLog;
  section.dataset.activeChangeIndex = "0";
  section.innerHTML = `
    <div class="message-change-head">
      <div class="message-change-heading">
        <div class="message-detail-title">${escapeHtml(localizeRuntimeLine("Diffs"))}</div>
        <div class="message-change-meta">${escapeHtml(localizeRuntimeLine(`${changeLog.length} ${changeLog.length === 1 ? "file" : "files"}`))}</div>
      </div>
      <button type="button" class="message-toggle message-change-toggle" aria-expanded="false" aria-label="Show diffs">
        <span class="message-toggle-label">${escapeHtml(localizeRuntimeLine("Show Diff"))}</span>
        <span class="message-toggle-caret">▾</span>
      </button>
    </div>
  `;

  const tabs = document.createElement("div");
  tabs.className = "message-change-tabs";
  tabs.setAttribute("role", "tablist");
  for (const [index, change] of changeLog.entries()) {
    const pathInfo = describeChangePath(change.path);
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = `message-change-tab ${change.status || "modified"}${index === 0 ? " active" : ""}`;
    tab.dataset.changeTabIndex = String(index);
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", index === 0 ? "true" : "false");
    tab.tabIndex = index === 0 ? 0 : -1;
    tab.title = pathInfo.full;
    tab.innerHTML = `
      <span class="message-change-tab-main">
        <span class="message-change-tab-file">${escapeHtml(pathInfo.name)}</span>
        ${pathInfo.directory ? `<span class="message-change-tab-dir">${escapeHtml(pathInfo.directory)}</span>` : ""}
      </span>
    `;
    tabs.appendChild(tab);
  }
  section.appendChild(tabs);

  const diff = document.createElement("div");
  diff.className = "message-diff squashed hidden";
  section.appendChild(diff);
  container.appendChild(section);
}

function setActiveArtifactTab(section, activeKey = "") {
  if (!section) {
    return;
  }
  section.dataset.activeArtifactKey = String(activeKey || "");
  section.querySelectorAll("[data-artifact-key]").forEach((tab) => {
    const isActive = String(tab.dataset.artifactKey || "") === String(activeKey || "");
    tab.classList.toggle("active", isActive);
    tab.setAttribute("aria-selected", isActive ? "true" : "false");
    tab.tabIndex = isActive ? 0 : -1;
  });
}

function appendMessageArtifactPanel(section, artifacts = [], activeKey = "") {
  const panel = section?.querySelector(".message-artifact-panel");
  if (!panel || !Array.isArray(artifacts) || !artifacts.length) {
    return;
  }

  const artifact = artifacts.find((entry) => entry.key === activeKey) || artifacts[0];
  if (!artifact) {
    return;
  }

  panel.innerHTML = "";
  setActiveArtifactTab(section, artifact.key);

  if (artifact.kind === "cli") {
    const terminal = document.createElement("div");
    terminal.className = "message-live-terminal message-artifact-terminal";
    terminal.dataset.terminalMode = "stored";
    terminal.innerHTML = renderStoredTerminalHtml(artifact.terminalLog || "");
    panel.appendChild(terminal);
    terminal.scrollTop = terminal.scrollHeight;
    return;
  }

  const diff = document.createElement("div");
  diff.className = "message-diff message-artifact-diff";
  populateChangeDiffContent(diff, artifact.change || {}, { headerClass: "message-artifact-file-head" });
  panel.appendChild(diff);
}

function appendMessageArtifacts(container, changeLog = []) {
  if (!container) {
    return;
  }

  const artifacts = buildMessageArtifactEntries(changeLog);
  if (!artifacts.length) {
    return;
  }

  const section = document.createElement("section");
  section.className = "message-artifact-section";
  section._artifacts = artifacts;
  section.dataset.activeArtifactKey = artifacts[0].key;

  const tabs = document.createElement("div");
  tabs.className = "message-artifact-tabs";
  tabs.setAttribute("role", "tablist");
  for (const [index, artifact] of artifacts.entries()) {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = `message-artifact-tab ${artifact.kind === "file" ? artifact.status || "modified" : "cli"}${index === 0 ? " active" : ""}`;
    tab.dataset.artifactKey = artifact.key;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", index === 0 ? "true" : "false");
    tab.tabIndex = index === 0 ? 0 : -1;
    tab.title = artifact.kind === "file"
      ? [artifact.label, artifact.meta].filter(Boolean).join(" - ")
      : artifact.label;
    tab.innerHTML = `
      <span class="message-artifact-tab-main">
        <span class="message-artifact-tab-label">${escapeHtml(artifact.label || "Item")}</span>
        ${artifact.meta ? `<span class="message-artifact-tab-meta">${escapeHtml(artifact.meta)}</span>` : ""}
      </span>
    `;
    tabs.appendChild(tab);
  }
  section.appendChild(tabs);

  const panel = document.createElement("div");
  panel.className = "message-artifact-panel";
  section.appendChild(panel);
  container.appendChild(section);
  appendMessageArtifactPanel(section, artifacts, artifacts[0].key);
}

function appendDetailSection(details, title, entries, mono = false) {
  if (!details || !Array.isArray(entries) || !entries.length) {
    return;
  }

  const section = document.createElement("section");
  section.className = `message-detail-section ${mono ? "console" : ""}`.trim();
  section.innerHTML = `<div class="message-detail-title">${escapeHtml(localizeRuntimeLine(title))}</div>`;
  const list = document.createElement("div");
  list.className = `message-activity ${mono ? "console" : ""}`.trim();

  for (const entry of entries) {
    const line = document.createElement("div");
    line.className = `message-activity-line ${mono ? "console" : ""}`.trim();
    line.textContent = localizeRuntimeBlock(entry);
    list.appendChild(line);
  }

  section.appendChild(list);
  details.appendChild(section);
}

function renderTranscriptFeed(entries, emptyText = "Waiting for activity…") {
  if (!Array.isArray(entries) || !entries.length) {
    return `<div class="message-transcript-entry event">${escapeHtml(localizeRuntimeLine(emptyText))}</div>`;
  }

  return entries.map((entry) => `
    <div class="message-transcript-entry ${escapeHtml(entry.kind || "event")}">${escapeHtml(localizeRuntimeBlock(entry.text || ""))}</div>
  `).join("");
}

const ANSI_BASIC_COLORS = {
  30: "var(--ansi-black)",
  31: "var(--ansi-red)",
  32: "var(--ansi-green)",
  33: "var(--ansi-yellow)",
  34: "var(--ansi-blue)",
  35: "var(--ansi-magenta)",
  36: "var(--ansi-cyan)",
  37: "var(--ansi-white)",
  90: "var(--ansi-bright-black)",
  91: "var(--ansi-bright-red)",
  92: "var(--ansi-bright-green)",
  93: "var(--ansi-bright-yellow)",
  94: "var(--ansi-bright-blue)",
  95: "var(--ansi-bright-magenta)",
  96: "var(--ansi-bright-cyan)",
  97: "var(--ansi-bright-white)",
};

function defaultTerminalStyle() {
  return {
    fg: "",
    bg: "",
    bold: false,
    dim: false,
    italic: false,
    underline: false,
    inverse: false,
  };
}

function cloneTerminalStyle(style) {
  return { ...style };
}

function ansi256Color(code) {
  const n = Number(code);
  if (!Number.isFinite(n)) {
    return "";
  }
  if (n < 16) {
    const map = [
      "var(--ansi-black)", "var(--ansi-red)", "var(--ansi-green)", "var(--ansi-yellow)",
      "var(--ansi-blue)", "var(--ansi-magenta)", "var(--ansi-cyan)", "var(--ansi-white)",
      "var(--ansi-bright-black)", "var(--ansi-bright-red)", "var(--ansi-bright-green)", "var(--ansi-bright-yellow)",
      "var(--ansi-bright-blue)", "var(--ansi-bright-magenta)", "var(--ansi-bright-cyan)", "var(--ansi-bright-white)",
    ];
    return map[n] || "";
  }
  if (n >= 16 && n <= 231) {
    const idx = n - 16;
    const levels = [0, 95, 135, 175, 215, 255];
    const r = levels[Math.floor(idx / 36) % 6];
    const g = levels[Math.floor(idx / 6) % 6];
    const b = levels[idx % 6];
    return `rgb(${r}, ${g}, ${b})`;
  }
  if (n >= 232 && n <= 255) {
    const level = 8 + (n - 232) * 10;
    return `rgb(${level}, ${level}, ${level})`;
  }
  return "";
}

function applyAnsiSgr(style, params = []) {
  const next = cloneTerminalStyle(style);
  const values = params.length ? params : [0];
  for (let i = 0; i < values.length; i += 1) {
    const code = Number(values[i] || 0);
    if (code === 0) {
      Object.assign(next, defaultTerminalStyle());
      continue;
    }
    if (code === 1) {
      next.bold = true;
      continue;
    }
    if (code === 2) {
      next.dim = true;
      continue;
    }
    if (code === 3) {
      next.italic = true;
      continue;
    }
    if (code === 4) {
      next.underline = true;
      continue;
    }
    if (code === 22) {
      next.bold = false;
      next.dim = false;
      continue;
    }
    if (code === 23) {
      next.italic = false;
      continue;
    }
    if (code === 24) {
      next.underline = false;
      continue;
    }
    if (code === 39) {
      next.fg = "";
      continue;
    }
    if (code === 49) {
      next.bg = "";
      continue;
    }
    if (ANSI_BASIC_COLORS[code] && code >= 30 && code <= 97) {
      if (code >= 40) {
        next.bg = ANSI_BASIC_COLORS[code - 10] || "";
      } else {
        next.fg = ANSI_BASIC_COLORS[code];
      }
      continue;
    }
    if (code >= 40 && code <= 47) {
      next.bg = ANSI_BASIC_COLORS[code - 10] || "";
      continue;
    }
    if (code >= 100 && code <= 107) {
      next.bg = ANSI_BASIC_COLORS[code - 10] || "";
      continue;
    }
    if ((code === 38 || code === 48) && values[i + 1] === "5" && values[i + 2] !== undefined) {
      const color = ansi256Color(values[i + 2]);
      if (code === 38) {
        next.fg = color;
      } else {
        next.bg = color;
      }
      i += 2;
    }
  }
  return next;
}

function ensureTerminalLine(lines, row) {
  while (lines.length <= row) {
    lines.push([]);
  }
  return lines[row];
}

function writeTerminalChar(lines, row, col, char, style) {
  const line = ensureTerminalLine(lines, row);
  while (line.length < col) {
    line.push({ char: " ", style: defaultTerminalStyle() });
  }
  line[col] = { char, style: cloneTerminalStyle(style) };
}

function eraseTerminalLine(line, fromCol = 0) {
  if (!Array.isArray(line)) {
    return;
  }
  line.length = Math.max(0, fromCol);
}

function terminalStyleCss(style) {
  const css = [];
  const fg = style.inverse ? style.bg : style.fg;
  const bg = style.inverse ? style.fg : style.bg;
  if (fg) css.push(`color:${fg}`);
  if (bg) css.push(`background:${bg}`);
  if (style.bold) css.push("font-weight:700");
  if (style.dim) css.push("opacity:0.75");
  if (style.italic) css.push("font-style:italic");
  if (style.underline) css.push("text-decoration:underline");
  return css.join(";");
}

function renderAnsiTerminalFeed(buffer, emptyText = "Waiting for raw CLI output…") {
  const source = String(buffer || "");
  if (!source.trim()) {
    return `<div class="message-live-terminal-row"><span class="message-live-terminal-empty">${escapeHtml(localizeRuntimeLine(emptyText))}</span></div>`;
  }

  const lines = [[]];
  let row = 0;
  let col = 0;
  let style = defaultTerminalStyle();

  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (char === "\u001b") {
      const next = source[i + 1];
      if (next === "[") {
        let j = i + 2;
        while (j < source.length && !/[A-Za-z]/.test(source[j])) {
          j += 1;
        }
        if (j >= source.length) {
          break;
        }
        const final = source[j];
        const rawParams = source.slice(i + 2, j);
        const params = rawParams.split(";").filter((part) => part.length);
        if (final === "m") {
          style = applyAnsiSgr(style, params);
        } else if (final === "K") {
          const line = ensureTerminalLine(lines, row);
          const mode = Number(params[0] || 0);
          if (mode === 2) {
            line.length = 0;
            col = 0;
          } else if (mode === 1) {
            for (let k = 0; k <= col && k < line.length; k += 1) {
              line[k] = { char: " ", style: defaultTerminalStyle() };
            }
          } else {
            eraseTerminalLine(line, col);
          }
        } else if (final === "J") {
          const mode = Number(params[0] || 0);
          if (mode === 2) {
            lines.length = 0;
            lines.push([]);
            row = 0;
            col = 0;
          }
        } else if (final === "G") {
          col = Math.max(0, Number(params[0] || 1) - 1);
        } else if (final === "H" || final === "f") {
          row = Math.max(0, Number(params[0] || 1) - 1);
          col = Math.max(0, Number(params[1] || 1) - 1);
          ensureTerminalLine(lines, row);
        } else if (final === "A") {
          row = Math.max(0, row - Math.max(1, Number(params[0] || 1)));
        } else if (final === "B") {
          row += Math.max(1, Number(params[0] || 1));
          ensureTerminalLine(lines, row);
        } else if (final === "C") {
          col += Math.max(1, Number(params[0] || 1));
        } else if (final === "D") {
          col = Math.max(0, col - Math.max(1, Number(params[0] || 1)));
        }
        i = j;
        continue;
      }
      if (next === "]") {
        let j = i + 2;
        while (j < source.length && source[j] !== "\u0007") {
          if (source[j] === "\u001b" && source[j + 1] === "\\") {
            j += 1;
            break;
          }
          j += 1;
        }
        i = j;
        continue;
      }
      continue;
    }

    if (char === "\r") {
      col = 0;
      continue;
    }
    if (char === "\n") {
      row += 1;
      col = 0;
      ensureTerminalLine(lines, row);
      continue;
    }
    if (char === "\b") {
      col = Math.max(0, col - 1);
      continue;
    }
    writeTerminalChar(lines, row, col, char, style);
    col += 1;
  }

  return lines.map((line) => {
    if (!line.length) {
      return `<div class="message-live-terminal-row"><span class="message-live-terminal-empty">&nbsp;</span></div>`;
    }
    const segments = [];
    let currentText = "";
    let currentCss = null;
    for (let i = 0; i < line.length; i += 1) {
      const cell = line[i] || { char: " ", style: defaultTerminalStyle() };
      const css = terminalStyleCss(cell.style);
      if (currentCss !== css) {
        if (currentText) {
          segments.push(`<span class="message-live-terminal-segment"${currentCss ? ` style="${currentCss}"` : ""}>${escapeHtml(currentText)}</span>`);
        }
        currentText = cell.char;
        currentCss = css;
      } else {
        currentText += cell.char;
      }
    }
    if (currentText) {
      segments.push(`<span class="message-live-terminal-segment"${currentCss ? ` style="${currentCss}"` : ""}>${escapeHtml(currentText)}</span>`);
    }
    return `<div class="message-live-terminal-row">${segments.join("")}</div>`;
  }).join("");
}

function resolveLiveTerminalRenderSource(buffer, { maxChars = LIVE_TERMINAL_MAX_CHARS, maxLines = LIVE_TERMINAL_MAX_LINES } = {}) {
  let source = String(buffer || "");
  if (!source) {
    return { source: "", trimmed: false };
  }

  let trimmed = false;
  if (source.length > maxChars) {
    source = source.slice(-maxChars);
    const firstNewline = source.indexOf("\n");
    if (firstNewline >= 0) {
      source = source.slice(firstNewline + 1);
    }
    trimmed = true;
  }

  const lines = source.split("\n");
  if (lines.length > maxLines) {
    source = lines.slice(-maxLines).join("\n");
    trimmed = true;
  }

  return { source, trimmed };
}

function renderTerminalBufferHtml(buffer, { trim = true, emptyText = "Waiting for raw CLI output…" } = {}) {
  const raw = String(buffer || "");
  const resolved = trim ? resolveLiveTerminalRenderSource(raw) : { source: raw, trimmed: false };
  const terminalRows = renderAnsiTerminalFeed(resolved.source, emptyText);
  if (!resolved.trimmed) {
    return terminalRows;
  }
  return `<div class="message-live-terminal-row"><span class="message-live-terminal-empty">${escapeHtml(localizeRuntimeLine("Showing recent output only."))}</span></div>${terminalRows}`;
}

function parseCliResultPayload(line) {
  const text = String(line || "").trim();
  if (!text.startsWith("{") || !text.endsWith("}")) {
    return null;
  }
  try {
    const payload = JSON.parse(text);
    if (!payload || typeof payload !== "object") {
      return null;
    }
    if (payload.type === "result") {
      return payload;
    }
    return Object.prototype.hasOwnProperty.call(payload, "result")
      && Object.prototype.hasOwnProperty.call(payload, "is_error")
      ? payload
      : null;
  } catch {
    return null;
  }
}

function sanitizeStoredTerminalLog(terminalLog = "") {
  const text = String(terminalLog || "");
  if (!text) {
    return "";
  }
  const lines = text.match(/[^\r\n]*(?:\r\n|\r|\n|$)/g) || [];
  let index = lines.length - 1;
  while (index >= 0 && !lines[index].trim()) {
    index -= 1;
  }
  if (index < 0 || !parseCliResultPayload(lines[index])) {
    return text;
  }
  lines.splice(index, 1);
  return lines.join("").replace(/[\r\n]+$/u, "");
}

function ensurePlainTerminalLine(lines, row) {
  while (lines.length <= row) {
    lines.push([]);
  }
  return lines[row];
}

function writePlainTerminalChar(lines, row, col, char) {
  if (col >= LIVE_TERMINAL_MAX_COLUMNS) {
    return;
  }
  const line = ensurePlainTerminalLine(lines, row);
  while (line.length < col) {
    line.push(" ");
  }
  line[col] = char;
}

function renderPlainTerminalText(buffer, emptyText = "Waiting for raw CLI output…") {
  const source = String(buffer || "");
  if (!source.trim()) {
    return { html: `<pre class="message-live-terminal-plain">${escapeHtml(localizeRuntimeLine(emptyText))}</pre>`, hasContent: false };
  }

  const lines = [[]];
  let row = 0;
  let col = 0;

  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (char === "\u001b") {
      const next = source[i + 1];
      if (next === "[") {
        let j = i + 2;
        while (j < source.length && !/[A-Za-z]/.test(source[j])) {
          j += 1;
        }
        if (j >= source.length) {
          break;
        }
        const final = source[j];
        const rawParams = source.slice(i + 2, j);
        const params = rawParams.split(";").filter((part) => part.length);
        if (final === "K") {
          const line = ensurePlainTerminalLine(lines, row);
          const mode = Number(params[0] || 0);
          if (mode === 2) {
            line.length = 0;
            col = 0;
          } else if (mode === 1) {
            for (let k = 0; k <= col && k < line.length; k += 1) {
              line[k] = " ";
            }
          } else {
            line.length = Math.max(0, col);
          }
        } else if (final === "J") {
          const mode = Number(params[0] || 0);
          if (mode === 2) {
            lines.length = 0;
            lines.push([]);
            row = 0;
            col = 0;
          }
        } else if (final === "G") {
          col = Math.max(0, Number(params[0] || 1) - 1);
        } else if (final === "H" || final === "f") {
          row = Math.max(0, Number(params[0] || 1) - 1);
          col = Math.max(0, Number(params[1] || 1) - 1);
          ensurePlainTerminalLine(lines, row);
        } else if (final === "A") {
          row = Math.max(0, row - Math.max(1, Number(params[0] || 1)));
        } else if (final === "B") {
          row += Math.max(1, Number(params[0] || 1));
          ensurePlainTerminalLine(lines, row);
        } else if (final === "C") {
          col += Math.max(1, Number(params[0] || 1));
        } else if (final === "D") {
          col = Math.max(0, col - Math.max(1, Number(params[0] || 1)));
        }
        i = j;
        continue;
      }
      if (next === "]") {
        let j = i + 2;
        while (j < source.length && source[j] !== "\u0007") {
          if (source[j] === "\u001b" && source[j + 1] === "\\") {
            j += 1;
            break;
          }
          j += 1;
        }
        i = j;
        continue;
      }
      continue;
    }

    if (char === "\r") {
      col = 0;
      continue;
    }
    if (char === "\n") {
      row += 1;
      col = 0;
      ensurePlainTerminalLine(lines, row);
      continue;
    }
    if (char === "\b") {
      col = Math.max(0, col - 1);
      continue;
    }
    writePlainTerminalChar(lines, row, col, char);
    col += 1;
  }

  const text = lines
    .map((line) => line.join("").replace(/\s+$/u, ""))
    .join("\n");

  return {
    html: `<pre class="message-live-terminal-plain">${escapeHtml(text || localizeRuntimeLine(emptyText))}</pre>`,
    hasContent: Boolean(text.trim()),
  };
}

function renderPlainTerminalBufferHtml(
  buffer,
  {
    trim = true,
    emptyText = "Waiting for raw CLI output…",
    maxChars = LIVE_TERMINAL_RAW_MAX_CHARS,
    maxLines = LIVE_TERMINAL_RAW_MAX_LINES,
  } = {},
) {
  const raw = String(buffer || "");
  const resolved = trim ? resolveLiveTerminalRenderSource(raw, { maxChars, maxLines }) : { source: raw, trimmed: false };
  const rendered = renderPlainTerminalText(resolved.source, emptyText);
  if (!resolved.trimmed) {
    return rendered.html;
  }
  return `<div class="message-live-terminal-row"><span class="message-live-terminal-empty">${escapeHtml(localizeRuntimeLine("Showing recent output only."))}</span></div>${rendered.html}`;
}

function renderLiveTerminalHtml(liveChat, activityLines = []) {
  if (!liveChat) {
    return renderTerminalBufferHtml("");
  }
  const transcriptLines = Array.isArray(liveChat.transcriptLines) ? liveChat.transcriptLines : [];
  const cache = liveChat.renderCache || (liveChat.renderCache = {});
  const language = currentHumanLanguage();
  const bufferKey = String(liveChat.terminalBuffer || "");
  const terminalMode = String(liveChat.terminalMode || "");
  const activityCount = activityLines.length;
  const lastActivity = activityLines[activityCount - 1] || "";
  if (
    cache.language === language
    && cache.terminalBuffer === bufferKey
    && cache.terminalMode === terminalMode
    && cache.transcriptCount === transcriptLines.length
    && cache.activityCount === activityCount
    && cache.lastActivity === lastActivity
    && typeof cache.terminalHtml === "string"
  ) {
    return cache.terminalHtml;
  }

  const terminalHtml = terminalMode === "raw"
    ? renderPlainTerminalBufferHtml(bufferKey)
    : renderTerminalBufferHtml(bufferKey);

  cache.language = language;
  cache.terminalBuffer = bufferKey;
  cache.terminalMode = terminalMode;
  cache.transcriptCount = transcriptLines.length;
  cache.activityCount = activityCount;
  cache.lastActivity = lastActivity;
  cache.terminalHtml = terminalHtml;
  cache.terminalRenderVersion = (cache.terminalRenderVersion || 0) + 1;
  return terminalHtml;
}

function renderStoredTerminalHtml(terminalLog = "") {
  return renderTerminalBufferHtml(sanitizeStoredTerminalLog(terminalLog), {
    trim: true,
    emptyText: "No terminal output captured.",
  });
}

function hasTerminalOutput(buffer = "") {
  return Boolean(String(buffer || "").trim());
}

function renderTerminalPanel({
  terminalHtml = "",
  title = "",
  meta = "",
  embedded = false,
  stored = false,
  mode = "",
} = {}) {
  const panelClass = `message-live-console${embedded ? " embedded" : ""}${stored ? " stored" : ""}`;
  const terminalClass = `message-live-terminal${embedded ? " embedded" : ""}`;
  const terminalMode = mode || (stored ? "stored" : "live");
  const showHead = Boolean(title || meta);
  return `
    <div class="${panelClass}">
      ${showHead ? `
        <div class="message-live-console-head">
          ${title ? `<div class="message-live-console-title">${escapeHtml(localizeRuntimeLine(title))}</div>` : ""}
          ${meta ? `<div class="message-live-console-meta">${escapeHtml(localizeRuntimeLine(meta))}</div>` : ""}
        </div>
      ` : ""}
      <div class="${terminalClass}" data-terminal-mode="${escapeHtml(terminalMode)}">${terminalHtml}</div>
    </div>
  `;
}

function liveChatRenderSignature(liveChat, activityLines = [], { includeTasks = true } = {}) {
  if (!liveChat) {
    return "";
  }
  const taskFingerprint = includeTasks
    ? normalizeLiveTasks(liveChat.tasks || [])
      .map((task) => [
        task.id,
        task.status,
        task.modelId,
        task.modelLabel,
        task.trackKey,
        task.execution,
        task.stage,
        task.parallelGroup,
        task.dependsOn.join(","),
      ].join(":"))
      .join("|")
    : "";
  // When xterm.js is handling the terminal (raw mode), exclude the buffer from
  // the render signature — xterm updates itself directly via terminal.write()
  // and does not need an HTML re-render on every incoming chunk.
  const useXterm = liveChat.terminalMode === "raw" && _xtermAvailable();
  const buf = useXterm ? "" : String(liveChat.terminalBuffer || "");
  return [
    useXterm ? "xterm" : String(liveChat.renderCache?.terminalRenderVersion || 0),
    currentHumanLanguage(),
    String(liveChat.selectedModelLabel || ""),
    String(liveChat.selectionReasoning || ""),
    String(liveChat.inputPrompt || ""),
    String(activityLines.length),
    String(activityLines[activityLines.length - 1] || ""),
    taskFingerprint,
    String(buf.length),
    buf.slice(-64),
  ].join("::");
}

function appendTranscriptSection(details, title, historyLog = []) {
  if (!details) {
    return;
  }

  const entries = buildTranscriptEntries(historyLog);
  if (!entries.length) {
    return;
  }

  const section = document.createElement("section");
  section.className = "message-detail-section console";
  section.innerHTML = `
    <div class="message-detail-title">${escapeHtml(localizeRuntimeLine(title))}</div>
    <div class="message-transcript-feed">${renderTranscriptFeed(entries)}</div>
  `;
  details.appendChild(section);
}

function appendMessageDetails(node, activityLog = [], historyLog = [], terminalLog = "") {
  const details = node.querySelector(".message-details");
  if (!details || details.dataset.loaded === "true") {
    return;
  }

  const statusLines = Array.isArray(activityLog) ? activityLog.filter(Boolean) : [];
  const transcriptLines = Array.isArray(historyLog) ? historyLog.filter(Boolean) : [];
  const hasTerminalLog = Boolean(String(terminalLog || "").trim());

  if (hasTerminalLog) {
    const section = document.createElement("section");
    section.className = "message-detail-section";
    section.innerHTML = `<div class="message-detail-title">${escapeHtml(localizeRuntimeLine("CLI Output"))}</div>`;
    section.insertAdjacentHTML("beforeend", renderTerminalPanel({
      terminalHtml: renderStoredTerminalHtml(terminalLog),
      stored: true,
    }));
    details.appendChild(section);
  }
  if (transcriptLines.length) {
    appendTranscriptSection(details, localizeRuntimeLine("Full CLI History"), transcriptLines);
  }
  if (statusLines.length) {
    appendDetailSection(details, localizeRuntimeLine("Status Timeline"), statusLines, false);
  }
  details.dataset.loaded = "true";
}

function renderRoutingMeta(routingMeta = {}) {
  if (!routingMeta || !Object.keys(routingMeta).length) {
    return "";
  }

  const badges = routingBadgeLabels(routingMeta);

  return `
    <div class="message-routing">
      <div class="message-routing-badges">
        ${badges.map((badge) => `<span class="message-routing-badge">${escapeHtml(localizeRuntimeLine(badge))}</span>`).join("")}
      </div>
      ${routingMeta.reason ? `<div class="message-routing-reason">${escapeHtml(localizeRuntimeLine(routingMeta.reason))}</div>` : ""}
      ${renderRoutingTaskBreakdown(routingMeta)}
    </div>
  `;
}

function renderRecommendations(recommendations = [], content = "") {
  const hasRecs = Array.isArray(recommendations) && recommendations.length > 0;
  const isQuestion = detectTrailingQuestion(content);
  const isBinaryQuestion = isQuestion && detectBinaryTrailingQuestion(content);

  // Question mode — surface smart reply buttons
  if (isQuestion) {
    if (!hasRecs && !isBinaryQuestion) {
      return "";
    }

    const replyBtns = hasRecs
      ? recommendations.map((r) => `<button type="button" class="message-quick-reply-btn" data-recommendation="${escapeHtml(r)}">${escapeHtml(r)}</button>`).join("")
      : `<button type="button" class="message-quick-reply-btn" data-recommendation="Yes">Yes</button>
         <button type="button" class="message-quick-reply-btn" data-recommendation="No">No</button>`;

    return `
      <div class="message-quick-replies">
        <div class="message-quick-replies-label">Suggested reply</div>
        <div class="message-quick-replies-list">
          ${replyBtns}
          <button type="button" class="message-quick-reply-btn message-quick-reply-other" data-recommendation-other="1">Other…</button>
        </div>
      </div>
    `;
  }

  // Standard next-action recommendation
  if (!hasRecs) return "";
  return `
    <div class="message-recommendations">
      <div class="message-recommendations-label">Suggested next step</div>
      <div class="message-recommendations-list">
        ${recommendations.map((r) => `<button type="button" class="message-recommendation-button" data-recommendation="${escapeHtml(r)}">${escapeHtml(r)}</button>`).join("")}
      </div>
    </div>
  `;
}

function createMessageNode(role, content, createdAt = null, activityLog = [], historyLog = [], changeLog = [], recommendations = [], routingMeta = {}, terminalLog = "") {
  const node = document.createElement("article");
  node.className = `message ${role}`;
  const label = role === "user" ? "You" : role === "assistant" ? "BetterCode" : "System";
  const timestamp = formatTimestamp(createdAt) || localizeRuntimeLine("Now");
  const hasActivityLog = Array.isArray(activityLog) && activityLog.length > 0;
  const hasHistoryLog = Array.isArray(historyLog) && historyLog.length > 0;
  const hasTerminalLog = Boolean(String(terminalLog || "").trim());
  const hasChangeLog = Array.isArray(changeLog) && changeLog.length > 0;
  const hasArtifacts = hasChangeLog;
  const hasDetails = hasActivityLog || hasHistoryLog || hasTerminalLog;
  const detailToggleLabel = localizeRuntimeLine(
    hasTerminalLog ? "CLI Output" : (hasHistoryLog ? "CLI History" : "History")
  );
  node.innerHTML = `
    ${role === "assistant" ? "" : `
      <div class="message-head">
        <span class="message-role">${label}</span>
      </div>
    `}
    <div class="message-main">
      <div class="message-toolbar">
        <span class="message-time">${timestamp}</span>
        ${hasDetails ? `<button type="button" class="message-toggle" aria-expanded="false" aria-label="Show response trace"><span class="message-toggle-label">${detailToggleLabel}</span><span class="message-toggle-caret">▾</span></button>` : ""}
      </div>
      ${role === "assistant" ? renderRoutingMeta(routingMeta) : ""}
      <div class="message-body"></div>
      ${hasArtifacts ? '<div class="message-artifact-shell"></div>' : ""}
      ${role === "assistant" ? renderRecommendations(recommendations, content) : ""}
      ${hasDetails ? '<div class="message-details hidden"></div>' : ""}
    </div>
  `;
  node.querySelector(".message-body").textContent = content;
  if (hasArtifacts) {
    appendMessageArtifacts(node.querySelector(".message-artifact-shell"), changeLog);
  }
  if (hasDetails) {
    node._detailActivityLog = activityLog;
    node._detailHistoryLog = historyLog;
    node._detailTerminalLog = terminalLog;
  }
  return node;
}

function activeLiveChatForWorkspace(workspace) {
  if (!workspace || !state.liveChats.has(workspace.id) || state.view !== "chat-view") {
    return null;
  }
  if (workspace.id !== state.currentWorkspaceId) {
    return null;
  }
  const tab = resolveWorkspaceTab(workspace, state.currentTabId);
  if (!tab) {
    return null;
  }
  const lc = state.liveChats.get(workspace.id);
  return lc && lc.workspaceId === workspace.id && lc.tabId === tab.id ? lc : null;
}

function liveChatPreviewText(liveChat) {
  if (!liveChat) {
    return localizeRuntimeLine("Waiting for CLI activity…");
  }

  const transcriptEntries = buildTranscriptEntries(liveChat.transcriptLines || []);
  const transcriptLines = transcriptEntries
    .filter((entry) => entry.kind !== "response")
    .map((entry) => String(entry.text || "").trim())
    .filter(Boolean);
  if (transcriptLines.length) {
    return localizeRuntimeBlock(transcriptLines.slice(-16).join("\n"));
  }

  const activityLines = Array.isArray(liveChat.activityLines) ? liveChat.activityLines.filter(Boolean) : [];
  if (activityLines.length) {
    return localizeRuntimeBlock(activityLines.slice(-12).join("\n"));
  }

  return localizeRuntimeLine("Waiting for CLI activity…");
}

function recentLiveActivityLines(activityLines = [], limit = 5) {
  const lines = [];
  for (const rawLine of Array.isArray(activityLines) ? activityLines : []) {
    const line = String(rawLine || "").trim();
    if (!line) {
      continue;
    }
    if (lines[lines.length - 1] === line) {
      continue;
    }
    lines.push(line);
  }
  return lines.slice(-limit);
}

function terminalLineCount(liveChat) {
  const source = String(liveChat?.terminalBuffer || "");
  if (!source.trim()) {
    return 0;
  }
  return source.split("\n").filter((line) => line.trim()).length;
}

function normalizeLiveTasks(tasks) {
  if (!Array.isArray(tasks)) {
    return [];
  }
  return tasks
    .filter((task) => task && (task.title || task.id))
    .map((task) => ({
      id: String(task.id || "").trim(),
      title: String(task.title || task.id || "").trim(),
      status: String(task.status || "pending").trim(),
      modelLabel: String(task.model_label || task.modelLabel || "").trim(),
      progress: Number.isFinite(task.progress) ? Number(task.progress) : null,
      waitingOn: Array.isArray(task.waiting_on) ? task.waiting_on.map((v) => String(v)) : [],
      dependsOn: Array.isArray(task.depends_on) ? task.depends_on.map((v) => String(v)) : [],
      execution: String(task.execution || "").trim(),
      stage: String(task.stage || "").trim(),
      detail: String(task.detail || "").trim(),
      selectionReason: String(task.selection_reason || task.selectionReason || "").trim(),
      modelId: String(task.model_id || task.modelId || "").trim(),
      trackKey: String(task.track_key || task.trackKey || "").trim(),
      trackLabel: String(task.track_label || task.trackLabel || "").trim(),
      trackKind: String(task.track_kind || task.trackKind || "").trim(),
      parallelGroup: String(task.parallel_group || task.parallelGroup || "").trim(),
      kind: String(task.kind || "").trim(),
    }));
}

function liveTaskPhaseIndex(stage) {
  const normalized = ["inspect", "edit", "validate"].includes(stage) ? stage : "inspect";
  const index = LIVE_PHASES.findIndex((phase) => phase.key === normalized);
  return index >= 0 ? index : 1;
}

function formatLiveTaskStage(stage) {
  if (stage === "inspect") {
    return localizeRuntimeLine("Inspect");
  }
  if (stage === "edit") {
    return localizeRuntimeLine("Edit");
  }
  if (stage === "validate") {
    return localizeRuntimeLine("Validate");
  }
  return "";
}

function formatLiveTaskStatus(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "queued") {
    return localizeRuntimeLine("Queued");
  }
  if (normalized === "pending") {
    return localizeRuntimeLine("Pending");
  }
  if (normalized === "blocked") {
    return localizeRuntimeLine("Blocked");
  }
  if (normalized === "running") {
    return localizeRuntimeLine("Running");
  }
  if (normalized === "done") {
    return localizeRuntimeLine("Done");
  }
  if (normalized === "error") {
    return localizeRuntimeLine("Error");
  }
  if (normalized === "waiting") {
    return localizeRuntimeLine("Waiting");
  }
  if (normalized === "stopped") {
    return localizeRuntimeLine("Stopped");
  }
  return normalized ? localizeRuntimeLine(normalized.charAt(0).toUpperCase() + normalized.slice(1)) : "";
}

function taskDisplayOrder(task, byId) {
  const systemOrder = {
    preprocess: 0,
    route: 1,
    breakdown: 2,
    execute: 100,
    validate_completion: 101,
  };
  const direct = systemOrder[task.id];
  if (Number.isFinite(direct)) {
    return direct;
  }
  const dependencyDepth = (() => {
    const seen = new Set();
    function visit(taskId) {
      if (!taskId || seen.has(taskId)) {
        return 0;
      }
      seen.add(taskId);
      const current = byId.get(taskId);
      if (!current) {
        return 0;
      }
      const deps = Array.isArray(current.dependsOn) ? current.dependsOn : [];
      if (!deps.length) {
        return 0;
      }
      return 1 + Math.max(...deps.map((depId) => visit(depId)));
    }
    return visit(task.id);
  })();
  return 10 + dependencyDepth;
}

function resolveLiveTaskRows(tasks, activityLines = []) {
  const items = normalizeLiveTasks(tasks);
  if (!items.length) {
    return [];
  }

  const byId = new Map(items.map((task) => [task.id, task]));
  const phaseKey = inferLivePhase(Array.isArray(activityLines) ? activityLines.filter(Boolean) : []).current?.key || "plan";
  const currentPhaseIndex = Math.max(0, LIVE_PHASES.findIndex((phase) => phase.key === phaseKey));
  const resolvedStatus = new Map();
  const resolving = new Set();

  function dependencyNames(task) {
    return task.dependsOn
      .map((taskId) => byId.get(taskId)?.title || taskId)
      .filter(Boolean);
  }

  function computeStatus(task) {
    if (!task?.id) {
      return "planned";
    }
    if (resolvedStatus.has(task.id)) {
      return resolvedStatus.get(task.id);
    }
    if (resolving.has(task.id)) {
      return task.status || "planned";
    }
    resolving.add(task.id);

    const rawStatus = String(task.status || "planned").toLowerCase();
    if (classifyLiveTaskKind(task) === "system") {
      resolving.delete(task.id);
      resolvedStatus.set(task.id, rawStatus);
      return rawStatus;
    }
    let effective = rawStatus;
    if (rawStatus !== "done" && rawStatus !== "error" && rawStatus !== "running" && rawStatus !== "stopped") {
      const dependencyStates = task.dependsOn
        .map((taskId) => byId.get(taskId))
        .filter(Boolean)
        .map((entry) => computeStatus(entry));
      const blocked = dependencyStates.some((status) => status !== "done");
      const taskPhaseIndex = liveTaskPhaseIndex(task.stage);
      if (phaseKey === "finalize") {
        effective = blocked ? "blocked" : "done";
      } else if (blocked) {
        effective = currentPhaseIndex >= taskPhaseIndex ? "blocked" : "waiting";
      } else if (currentPhaseIndex > taskPhaseIndex) {
        effective = "done";
      } else if (currentPhaseIndex < taskPhaseIndex) {
        effective = task.execution === "async" ? "queued" : "planned";
      } else if (task.execution === "async") {
        effective = "running";
      } else {
        const eligibleSync = items.filter((candidate) => (
          candidate
          && candidate.id
          && candidate.execution !== "async"
          && liveTaskPhaseIndex(candidate.stage) === taskPhaseIndex
          && candidate.dependsOn.every((taskId) => computeStatus(byId.get(taskId)) === "done")
          && !["done", "error"].includes(String(candidate.status || "").toLowerCase())
        ));
        effective = eligibleSync[0]?.id === task.id ? "running" : "queued";
      }
    }

    resolving.delete(task.id);
    resolvedStatus.set(task.id, effective);
    return effective;
  }

  const resolved = items.map((task) => ({
    ...task,
    effectiveStatus: computeStatus(task),
    dependencyNames: dependencyNames(task),
    displayOrder: taskDisplayOrder(task, byId),
  }));

  return resolved.sort((left, right) => {
    const leftOrder = Number.isFinite(left.displayOrder) ? left.displayOrder : taskDisplayOrder(left, byId);
    const rightOrder = Number.isFinite(right.displayOrder) ? right.displayOrder : taskDisplayOrder(right, byId);
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return String(left.title || left.id || "").localeCompare(String(right.title || right.id || ""));
  });
}

function classifyLiveTaskKind(task) {
  const explicit = String(task.kind || "").trim().toLowerCase();
  if (explicit) {
    return explicit;
  }
  return String(task.id || "").startsWith("subtask:") ? "planned" : "system";
}

function renderLiveTaskRow(task) {
  const status = task.effectiveStatus || task.status || "pending";
  const statusClass = status.toLowerCase().replace(/[^a-z0-9_-]/g, "");
  const isSubtask = classifyLiveTaskKind(task) !== "system";
  const metaParts = [];
  const statusLabel = formatLiveTaskStatus(status);
  if (statusLabel) {
    metaParts.push(statusLabel);
  }
  if (isSubtask && task.modelLabel) {
    metaParts.push(localizeRuntimeLine(task.modelLabel));
  }
  if (isSubtask && task.stage) {
    metaParts.push(formatLiveTaskStage(task.stage));
  }
  if (isSubtask && task.execution) {
    metaParts.push(localizeRuntimeLine(task.execution === "async" ? "parallel" : "sequential"));
  }
  const dependencyLine = task.dependencyNames.length
    ? localizeRuntimeLine(`${status === "blocked" ? "Blocked by" : "Depends on"}: ${task.dependencyNames.join(", ")}`)
    : "";
  const queued = status === "queued" ? localizeRuntimeLine("Queued.") : "";
  const detail = task.detail || queued;
  const detailLines = [];
  if (detail) {
    detailLines.push(detail);
  }
  if (dependencyLine) {
    detailLines.push(dependencyLine);
  }
  const pct = task.progress === null ? null : Math.max(0, Math.min(1, task.progress));
  return `
    <div class="message-live-task ${statusClass}" data-kind="${escapeHtml(isSubtask ? "planned" : "system")}">
      <span class="message-live-task-dot" aria-hidden="true"></span>
      <div class="message-live-task-main">
        <div class="message-live-task-top">
          <div class="message-live-task-title">${escapeHtml(localizeRuntimeLine(task.title))}</div>
          ${metaParts.length ? `<div class="message-live-task-meta">${escapeHtml(metaParts.join(" · "))}</div>` : ""}
        </div>
        ${detailLines.map((line) => `<div class="message-live-task-detail">${escapeHtml(localizeRuntimeBlock(line))}</div>`).join("")}
        ${pct !== null ? `
          <div class="message-live-task-bar" role="progressbar" aria-valuenow="${Math.round(pct * 100)}" aria-valuemin="0" aria-valuemax="100">
            <div class="message-live-task-bar-fill" style="width:${pct * 100}%"></div>
          </div>
        ` : ""}
      </div>
    </div>
  `;
}

function renderRoutingTaskBreakdown(routingMeta = {}) {
  const breakdown = routingTaskBreakdown(routingMeta);
  const tasks = normalizeLiveTasks(breakdown.tasks || []);
  if (!tasks.length) {
    return "";
  }

  const byId = new Map(tasks.map((task) => [task.id, task]));

  return `
    <div class="message-routing-plan-list">
      ${tasks.map((task) => {
        const dependencyNames = task.dependsOn
          .map((taskId) => byId.get(taskId)?.title || taskId)
          .filter(Boolean);
        const taskMeta = [
          formatLiveTaskStatus(task.status || "planned"),
          task.modelLabel ? localizeRuntimeLine(task.modelLabel) : "",
          task.stage ? formatLiveTaskStage(task.stage) : "",
          task.execution ? localizeRuntimeLine(task.execution === "async" ? "parallel" : "sequential") : "",
        ].filter(Boolean);
        const statusClass = String(task.status || "planned").toLowerCase().replace(/[^a-z0-9_-]/g, "");
        return `
          <div class="message-routing-plan-task ${statusClass}">
            <span class="message-routing-plan-task-dot" aria-hidden="true"></span>
            <div class="message-routing-plan-task-body">
              <div class="message-routing-plan-task-top">
                <span class="message-routing-plan-task-title">${escapeHtml(localizeRuntimeLine(task.title))}</span>
                ${taskMeta.length ? `<span class="message-routing-plan-task-meta">${escapeHtml(taskMeta.join(" · "))}</span>` : ""}
              </div>
              ${task.detail ? `<div class="message-routing-plan-task-detail">${escapeHtml(localizeRuntimeBlock(task.detail))}</div>` : ""}
              ${dependencyNames.length ? `<div class="message-routing-plan-task-note">${escapeHtml(localizeRuntimeLine(`Depends on: ${dependencyNames.join(", ")}`))}</div>` : ""}
              ${task.selectionReason ? `<div class="message-routing-plan-task-note">${escapeHtml(localizeRuntimeBlock(task.selectionReason))}</div>` : ""}
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderLiveTaskRows(tasks) {
  return `
    <div class="message-live-task-list">
      ${tasks.map((task) => renderLiveTaskRow(task)).join("")}
    </div>
  `;
}

function groupResolvedLiveTasks(tasks) {
  const systemTasks = [];
  const trackMap = new Map();
  for (const task of tasks) {
    const kind = classifyLiveTaskKind(task);
    if (kind === "system") {
      systemTasks.push(task);
      continue;
    }
    const key = task.trackKey || task.modelId || task.trackLabel || `stage:${task.stage || "inspect"}`;
    if (!trackMap.has(key)) {
      trackMap.set(key, {
        key,
        label: task.trackLabel || task.modelLabel || `${formatLiveTaskStage(task.stage) || "Shared"} Track`,
        kind: task.trackKind || (task.modelId ? "model" : "stage"),
        tasks: [],
      });
    }
    trackMap.get(key).tasks.push(task);
  }

  const system = systemTasks.sort((left, right) => {
    const leftOrder = Number.isFinite(left.displayOrder) ? left.displayOrder : 0;
    const rightOrder = Number.isFinite(right.displayOrder) ? right.displayOrder : 0;
    return leftOrder - rightOrder;
  });

  const tracks = Array.from(trackMap.values())
    .map((track) => {
      const sortedTasks = track.tasks.sort((left, right) => {
        const leftOrder = Number.isFinite(left.displayOrder) ? left.displayOrder : 0;
        const rightOrder = Number.isFinite(right.displayOrder) ? right.displayOrder : 0;
        return leftOrder - rightOrder;
      });
      const doneCount = sortedTasks.filter((task) => task.effectiveStatus === "done").length;
      const asyncCount = sortedTasks.filter((task) => task.execution === "async").length;
      const activeCount = sortedTasks.filter((task) => task.effectiveStatus === "running").length;
      return {
        ...track,
        tasks: sortedTasks,
        doneCount,
        asyncCount,
        activeCount,
        displayOrder: Math.min(...sortedTasks.map((task) => Number.isFinite(task.displayOrder) ? task.displayOrder : 999)),
      };
    })
    .sort((left, right) => {
      if (left.displayOrder !== right.displayOrder) {
        return left.displayOrder - right.displayOrder;
      }
      return String(left.label || left.key || "").localeCompare(String(right.label || right.key || ""));
    });

  return { system, tracks };
}

function sortLiveTasksByDisplayOrder(tasks) {
  return [...tasks].sort((left, right) => {
    const leftOrder = Number.isFinite(left.displayOrder) ? left.displayOrder : 0;
    const rightOrder = Number.isFinite(right.displayOrder) ? right.displayOrder : 0;
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder;
    }
    return String(left.title || left.id || "").localeCompare(String(right.title || right.id || ""));
  });
}

function partitionResolvedLiveTasks(tasks) {
  const pipeline = [];
  const execution = [];
  const completion = [];
  const planned = [];

  for (const task of tasks) {
    if (classifyLiveTaskKind(task) !== "system") {
      planned.push(task);
      continue;
    }
    if (task.id === "execute") {
      execution.push(task);
      continue;
    }
    if (task.id === "validate_completion") {
      completion.push(task);
      continue;
    }
    pipeline.push(task);
  }

  return {
    pipeline: sortLiveTasksByDisplayOrder(pipeline),
    execution: sortLiveTasksByDisplayOrder(execution),
    completion: sortLiveTasksByDisplayOrder(completion),
    tracks: groupResolvedLiveTasks(planned).tracks,
  };
}

function renderLiveTrackCards(tracks) {
  if (!tracks.length) {
    return "";
  }
  return `
    <div class="message-live-track-grid">
      ${tracks.map((track) => {
        const summaryParts = [localizeRuntimeLine(`${track.doneCount}/${track.tasks.length} done`)];
        if (track.asyncCount) {
          summaryParts.push(`${track.asyncCount} ${localizeRuntimeLine("async")}`);
        }
        if (track.activeCount) {
          summaryParts.push(`${track.activeCount} ${localizeRuntimeLine("active")}`);
        }
        const cardTitle = localizeRuntimeLine(track.label);
        return `
          <section class="message-live-track-card" data-track-kind="${escapeHtml(track.kind || "model")}">
            <div class="message-live-track-head">
              <div class="message-live-track-title">${escapeHtml(cardTitle)}</div>
              <div class="message-live-track-meta">${escapeHtml(summaryParts.join(" · "))}</div>
            </div>
            ${renderLiveTaskRows(track.tasks)}
          </section>
        `;
      }).join("")}
    </div>
  `;
}

function renderLiveTaskList(tasks, { activityLines = [] } = {}) {
  const items = resolveLiveTaskRows(tasks, activityLines);
  if (!items.length) {
    return "";
  }

  const showDone = items.find((task) => task.id === "validate_completion")?.effectiveStatus === "done";

  return `
    <div class="message-live-tasks">
      <div class="message-live-task-list">
        ${items.map((task) => renderLiveTaskRow(task)).join("")}
        ${showDone ? `
          <div class="message-live-task done" data-kind="system">
            <span class="message-live-task-dot" aria-hidden="true"></span>
            <div class="message-live-task-main">
              <div class="message-live-task-top">
                <div class="message-live-task-title">${escapeHtml(localizeRuntimeLine("Done"))}</div>
              </div>
            </div>
          </div>
        ` : ""}
      </div>
    </div>
  `;
}

function renderCompactLiveTaskProgress(tasks, activityLines = []) {
  const items = resolveLiveTaskRows(tasks, activityLines);
  if (!items.length) {
    return "";
  }

  const doneCount = items.filter((task) => task.effectiveStatus === "done").length;
  const rows = items.map((task) => {
    const status = task.effectiveStatus || task.status || "pending";
    const statusClass = status.toLowerCase().replace(/[^a-z0-9_-]/g, "");
    const statusLabel = formatLiveTaskStatus(status);
    const isSubtask = classifyLiveTaskKind(task) !== "system";
    const taskTitle = localizeRuntimeLine(task.title);
    const label = isSubtask && task.modelLabel ? `${taskTitle} · ${task.modelLabel}` : taskTitle;
    return `
      <div class="composer-live-task-pill ${statusClass}">
        <span class="composer-live-task-dot ${statusClass}" aria-hidden="true"></span>
        <span class="composer-live-task-title">${escapeHtml(label)}</span>
        <span class="composer-live-task-status ${statusClass}">${escapeHtml(statusLabel)}</span>
      </div>
    `;
  }).join("");

  return `
    <div class="composer-live-tasks">
      <div class="composer-live-tasks-inline-head">
        <div class="composer-live-tasks-title">${escapeHtml(localizeRuntimeLine("Processing"))}</div>
        <div class="composer-live-tasks-summary">${escapeHtml(localizeRuntimeLine(`${doneCount}/${items.length} done`))}</div>
      </div>
      <div class="composer-live-task-inline-list">
        ${rows}
      </div>
    </div>
  `;
}

function isScrolledNearBottom(element, threshold = 56) {
  if (!element) {
    return true;
  }
  return (element.scrollHeight - element.scrollTop - element.clientHeight) <= threshold;
}

function clearNestedScrollActivation(scope) {
  if (!scope) {
    return;
  }
  scope.querySelectorAll(".message-live-terminal.scroll-active, .message-diff.scroll-active").forEach((node) => {
    node.classList.remove("scroll-active");
  });
}

function closestNestedScrollPanel(target) {
  return target?.closest?.(".message-live-terminal, .message-diff") || null;
}

function scrollLiveTerminalsToBottom(scope) {
  if (!scope) {
    return;
  }
  scope.querySelectorAll(".message-live-terminal").forEach((node) => {
    node.scrollTop = node.scrollHeight;
  });
}

function renderLiveCliCard(liveChat, { embedded = false, includePrompt = false, workspaceId = null } = {}) {
  if (!liveChat) {
    return "";
  }

  const activityLines = Array.isArray(liveChat.activityLines) ? liveChat.activityLines.filter(Boolean) : [];
  const phaseState = inferLivePhase(activityLines);
  const selectedModelLabel = localizeRuntimeLine(String(liveChat.selectedModelLabel || "").trim());
  const selectionReasoning = String(liveChat.selectionReasoning || "").trim();
  const prompt = includePrompt ? (liveChat.inputPrompt || "") : "";
  const isRaw = liveChat.terminalMode === "raw";

  // ------------------------------------------------------------------
  // Terminal panel: use xterm.js placeholder for raw/live mode so the
  // real terminal emulator is mounted after innerHTML is set.  Fall back
  // to the existing ANSI-renderer for synthetic/stored mode.
  // ------------------------------------------------------------------
  let terminalPanelHtml = "";
  if (isRaw && workspaceId !== null && _xtermAvailable()) {
    // xterm.js path: render a lightweight placeholder; the actual xterm
    // element is attached by _mountXtermToPlaceholder() after innerHTML.
    const panelClass = `message-live-console${embedded ? " embedded" : ""}`;
    terminalPanelHtml = `
      <div class="${panelClass}">
        <div class="message-live-console-head">
          <div class="message-live-console-title">Output</div>
          <div class="message-live-console-meta">live</div>
        </div>
        <div data-xterm-ws="${escapeHtml(String(workspaceId))}"></div>
      </div>
    `;
  } else if (hasTerminalOutput(liveChat.terminalBuffer)) {
    const terminalHtml = renderLiveTerminalHtml(liveChat, activityLines);
    terminalPanelHtml = renderTerminalPanel({
      terminalHtml,
      title: "Output",
      meta: isRaw ? "live" : "",
      embedded,
      mode: liveChat.terminalMode || "live",
    });
  }

  if (embedded) {
    if (!terminalPanelHtml) {
      return "";
    }
    return `
      <div class="message-live-stream">
        ${terminalPanelHtml}
      </div>
    `;
  }

  const phaseSeps = phaseState.phases.map((phase, i) =>
    `<span class="message-live-phase ${phase.state}" data-key="${escapeHtml(phase.key)}">${escapeHtml(localizeRuntimeLine(phase.label))}</span>` +
    (i < phaseState.phases.length - 1 ? '<span class="message-live-phase-sep" aria-hidden="true"></span>' : ""),
  ).join("");

  return `
    <div class="message-live-shell standalone">
      <div class="message-live-heading">
        <div class="message-live-label-row">
          <span class="message-live-dot running" aria-hidden="true"></span>
          ${selectedModelLabel ? `
            <span class="composer-live-model-shell">
              <span class="composer-live-model"${selectionReasoning ? ' tabindex="0"' : ""}>
                ${escapeHtml(selectedModelLabel)}
              </span>
              ${selectionReasoning ? `
                <span class="composer-live-model-tooltip" role="tooltip">
                  ${escapeHtml(localizeRuntimeBlock(selectionReasoning))}
                </span>
              ` : ""}
            </span>
          ` : ""}
        </div>
      </div>
      <div class="message-live-phase-row">${phaseSeps}</div>
      ${renderLiveTaskList(liveChat.tasks, { activityLines })}
      ${terminalPanelHtml}
      ${prompt ? renderLiveInputPrompt(prompt) : ""}
    </div>
  `;
}

function renderCompactLivePanel(liveChat) {
  if (!liveChat) {
    return "";
  }

  const activityLines = Array.isArray(liveChat.activityLines) ? liveChat.activityLines.filter(Boolean) : [];
  const selectedModelLabel = localizeRuntimeLine(String(liveChat.selectedModelLabel || "").trim());
  const selectionReasoning = String(liveChat.selectionReasoning || "").trim();
  const prompt = liveChat.inputPrompt || "";

  return `
    <div class="composer-live-head">
      <div class="composer-live-title-row">
        <span class="message-live-dot running" aria-hidden="true"></span>
        ${selectedModelLabel ? `
          <span class="composer-live-model-shell">
            <span class="composer-live-model"${selectionReasoning ? ' tabindex="0"' : ""}>
              ${escapeHtml(selectedModelLabel)}
            </span>
            ${selectionReasoning ? `
              <span class="composer-live-model-tooltip" role="tooltip">
                  ${escapeHtml(localizeRuntimeBlock(selectionReasoning))}
                </span>
              ` : ""}
            </span>
          ` : ""}
        ${selectionReasoning ? `<span class="composer-live-status">${escapeHtml(localizeRuntimeBlock(selectionReasoning))}</span>` : ""}
      </div>
    </div>
    ${renderCompactLiveTaskProgress(liveChat.tasks, activityLines)}
    ${prompt ? renderLiveInputPrompt(prompt) : ""}
  `;
}

// Returns an array of {label, value} quick-reply options if the prompt has a
// recognisable choice pattern, or null if a free-text field should be shown.
function parseInputPromptOptions(prompt) {
  const text = String(prompt || "").trim();

  // Yes / No  (Y/N), [Y/N], (yes/no)
  if (
    /\(\s*[Yy]\s*\/\s*[Nn]\s*\)/i.test(text) ||
    /\[\s*[Yy]\s*\/\s*[Nn]\s*\]/i.test(text) ||
    /\(\s*yes\s*\/\s*no\s*\)/i.test(text)
  ) {
    return [{ label: "Yes", value: "Yes" }, { label: "No", value: "No" }];
  }

  // Numbered list  "1. thing\n2. thing"
  const numbered = text
    .split("\n")
    .map((line) => line.match(/^\s*(\d+)[.)]\s+(.+)/))
    .filter(Boolean);
  if (numbered.length >= 2) {
    return numbered.map((m) => ({ label: m[2].trim(), value: m[1] }));
  }

  return null;
}

function renderLiveInputPrompt(prompt) {
  const options = parseInputPromptOptions(prompt);
  if (options) {
    const btnHtml = options
      .map((opt) => `<button type="button" class="message-live-quick-btn" data-quick-reply="${escapeHtml(opt.value)}">${escapeHtml(opt.label)}</button>`)
      .join("");
    return `
      <div class="message-live-input">
        <div class="message-live-input-label">${escapeHtml(prompt)}</div>
        <div class="message-live-quick-buttons">
          ${btnHtml}
          <button type="button" class="message-live-quick-btn message-live-other-btn">Other…</button>
        </div>
        <form class="message-live-input-form hidden">
          <input class="message-live-input-field" type="text" placeholder="Type your response…" autocomplete="off" />
          <button type="submit" class="message-live-input-send">Send</button>
        </form>
      </div>
    `;
  }
  return `
    <div class="message-live-input">
      <div class="message-live-input-label">${escapeHtml(prompt)}</div>
      <form class="message-live-input-form">
        <input class="message-live-input-field" type="text" placeholder="Type your response…" autocomplete="off" />
        <button type="submit" class="message-live-input-send">Send</button>
      </form>
    </div>
  `;
}

async function submitLiveChatInput(text) {
  if (!text) return;
  const lc = currentLiveChat();
  if (lc) {
    lc.inputPrompt = null;
    lc.activityLines.push(`You: ${text}`);
    lc.transcriptLines.push(`You: ${text}`);
  }
  try {
    await sendCliInput(text);
  } catch (error) {
    showToast(error.message);
  }
  renderLiveChatState(currentWorkspace());
}

function attachLiveInputHandlers(panel) {
  const promptKey = String(currentLiveChat()?.inputPrompt || "");
  if (panel.dataset.liveInputBound === promptKey) {
    return;
  }
  panel.dataset.liveInputBound = promptKey;

  // Quick-reply buttons
  panel.querySelectorAll(".message-live-quick-btn[data-quick-reply]").forEach((btn) => {
    btn.addEventListener("click", () => submitLiveChatInput(btn.dataset.quickReply));
  });

  // "Other…" reveals the free-text form
  const otherBtn = panel.querySelector(".message-live-other-btn");
  if (otherBtn) {
    otherBtn.addEventListener("click", () => {
      panel.querySelector(".message-live-quick-buttons")?.classList.add("hidden");
      const form = panel.querySelector(".message-live-input-form");
      if (form) {
        form.classList.remove("hidden");
        form.querySelector(".message-live-input-field")?.focus();
      }
    });
  }

  // Free-text form submit
  const form = panel.querySelector(".message-live-input-form");
  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const text = form.querySelector(".message-live-input-field")?.value.trim() || "";
      if (text) submitLiveChatInput(text);
    });
    if (!form.classList.contains("hidden")) {
      form.querySelector(".message-live-input-field")?.focus();
    }
  }
}

function renderLiveStatusPanel(workspace = currentWorkspace()) {
  const panel = document.getElementById("live-status-panel");
  if (!panel) {
    return;
  }

  const liveChat = activeLiveChatForWorkspace(workspace);
  if (!liveChat) {
    panel.innerHTML = "";
    panel.dataset.renderedHtml = "";
    panel.dataset.liveInputBound = "";
    panel.classList.add("hidden");
    return;
  }

  panel.classList.remove("hidden");
  const nextHtml = renderCompactLivePanel(liveChat);
  if (panel.dataset.renderedHtml !== nextHtml) {
    panel.innerHTML = nextHtml;
    panel.dataset.renderedHtml = nextHtml;
    panel.dataset.liveInputBound = "";
  }

  if (liveChat.inputPrompt) {
    attachLiveInputHandlers(panel);
  }
  scrollLiveTerminalsToBottom(panel);
}

function renderLiveChatState(workspace = currentWorkspace()) {
  const liveChat = activeLiveChatForWorkspace(workspace);
  if (!liveChat) {
    renderLiveStatusPanel(workspace);
    return null;
  }

  const container = document.getElementById("messages");
  if (!container) {
    return null;
  }
  const shouldFollow = isScrolledNearBottom(container);

  let pendingUser = container.querySelector('[data-pending-user="true"]');
  if (!pendingUser && liveChat.userPreview) {
    pendingUser = createMessageNode("user", liveChat.userPreview);
    pendingUser.dataset.pendingUser = "true";
    container.appendChild(pendingUser);
  } else if (pendingUser) {
    const body = pendingUser.querySelector(".message-body");
    if (body) {
      body.textContent = liveChat.userPreview || "";
    }
  }

  let progressNode = container.querySelector('[data-live-transcript="true"]');
  if (!progressNode) {
    progressNode = createMessageNode("assistant", " ");
    progressNode.dataset.liveTranscript = "true";
    progressNode.classList.add("message-live-transcript");
    container.appendChild(progressNode);
  }

  const wsId = workspace?.id ?? null;
  const body = progressNode.querySelector(".message-body");
  if (body) {
    const isRaw = liveChat.terminalMode === "raw";
    const nextHtml = renderLiveCliCard(liveChat, { embedded: true, includePrompt: false, workspaceId: wsId });
    const renderSignature = liveChatRenderSignature(
      liveChat,
      Array.isArray(liveChat.activityLines) ? liveChat.activityLines.filter(Boolean) : [],
      { includeTasks: false },
    );
    if (body.dataset.liveRenderSignature !== renderSignature) {
      body.innerHTML = nextHtml;
      body.dataset.liveRenderSignature = renderSignature;
      // After replacing innerHTML, re-mount the xterm terminal into its placeholder.
      // (xterm.js is only used for raw/live PTY mode.)
      if (isRaw && wsId !== null) {
        _mountXtermToPlaceholder(progressNode, wsId, true);
      }
    } else if (isRaw && wsId !== null) {
      // Signature unchanged — make sure xterm is still mounted (survives partial updates)
      _mountXtermToPlaceholder(progressNode, wsId, true);
    }
  }
  renderLiveStatusPanel(workspace);
  // Scroll xterm viewport to bottom for raw terminals
  if (liveChat.terminalMode === "raw" && wsId !== null) {
    const inst = _xtermInstances.get(wsId);
    if (inst) {
      try { inst.terminal.scrollToBottom(); } catch (_) {}
    }
  } else {
    scrollLiveTerminalsToBottom(progressNode);
  }
  if (shouldFollow) {
    container.scrollTop = container.scrollHeight;
  }
  return progressNode;
}

function createMessageNodesFragment(messages = []) {
  const fragment = document.createDocumentFragment();
  for (const message of messages) {
    fragment.appendChild(
      createMessageNode(
        message.role,
        message.content,
        message.created_at,
        message.activity_log || [],
        message.history_log || [],
        message.change_log || [],
        message.recommendations || [],
        message.routing_meta || {},
        message.terminal_log || "",
      )
    );
  }
  return fragment;
}

function syncLoadOlderMessagesButton(container, paging = null) {
  if (!container) {
    return null;
  }
  let button = container.querySelector("#load-older-messages");
  if (!paging?.has_more) {
    button?.remove();
    return null;
  }
  if (!button) {
    button = document.createElement("button");
    button.type = "button";
    button.id = "load-older-messages";
    button.className = "message-load-more";
    button.textContent = "Load older messages";
    container.insertBefore(button, container.firstChild);
    return button;
  }
  if (container.firstChild !== button) {
    container.insertBefore(button, container.firstChild);
  }
  return button;
}

function syncWorkspacePayload(workspacePayload) {
  if (!workspacePayload?.id) {
    return null;
  }
  const exists = state.workspaces.some((workspace) => workspace.id === workspacePayload.id);
  state.workspaces = exists
    ? state.workspaces.map((workspace) => workspace.id === workspacePayload.id ? workspacePayload : workspace)
    : [workspacePayload, ...state.workspaces];
  if (state.currentWorkspaceId === workspacePayload.id) {
    const resolvedTab = resolveWorkspaceTab(workspacePayload, state.currentTabId);
    setCurrentTabId(resolvedTab?.id || null);
  }
  return state.workspaces.find((workspace) => workspace.id === workspacePayload.id) || null;
}

function renderWorkspaceTabs(workspace = currentWorkspace()) {
  const container = document.getElementById("workspace-tabs");
  const historyButton = document.getElementById("tab-history-button");
  if (!container || !historyButton) {
    return;
  }
  if (!workspace) {
    container.innerHTML = "";
    historyButton.disabled = true;
    historyButton.textContent = "Tab History";
    return;
  }

  const activeTab = resolveWorkspaceTab(workspace, state.currentTabId);
  if (activeTab && state.currentTabId !== activeTab.id) {
    setCurrentTabId(activeTab.id);
  }
  const tabs = Array.isArray(workspace.tabs) ? workspace.tabs : [];
  container.innerHTML = [
    ...tabs.map((tab) => `
      <div class="workspace-tab ${tab.id === activeTab?.id ? "active" : ""}" data-workspace-tab-shell="${tab.id}">
        <button type="button" class="workspace-tab-select" data-workspace-tab="${tab.id}">
          <span class="workspace-tab-label">${escapeHtml(tab.title || "New Tab")}</span>
        </button>
        <button type="button" class="workspace-tab-close" data-workspace-tab-close="${tab.id}" aria-label="Close ${escapeHtml(tab.title || "New Tab")}">x</button>
      </div>
    `),
    '<button type="button" class="workspace-tab-add" data-workspace-tab-add="true" aria-label="Create tab">+</button>',
  ].join("");
  const historyCount = Array.isArray(workspace.tab_history) ? workspace.tab_history.length : 0;
  historyButton.disabled = !historyCount;
  historyButton.textContent = historyCount ? `Tab History (${historyCount})` : "Tab History";
}

function renderTabHistoryDialog(workspace = currentWorkspace()) {
  const container = document.getElementById("tab-history-list");
  if (!container) {
    return;
  }
  const history = Array.isArray(workspace?.tab_history) ? workspace.tab_history : [];
  if (!history.length) {
    container.innerHTML = '<div class="tab-history-empty">No archived tabs yet.</div>';
    return;
  }
  container.innerHTML = history.map((tab) => `
    <div class="tab-history-item" data-tab-history-id="${tab.id}">
      <div class="tab-history-item-meta">
        <div class="tab-history-item-title">${escapeHtml(tab.title || "New Tab")}</div>
        <div class="tab-history-item-time">Closed ${escapeHtml(formatDateTime(tab.archived_at) || "recently")}</div>
      </div>
      <button type="button" class="secondary-button" data-tab-history-restore="${tab.id}">Restore</button>
    </div>
  `).join("");
}

function openTabHistoryDialog() {
  const dialog = document.getElementById("tab-history-dialog");
  renderTabHistoryDialog(currentWorkspace());
  dialog.showModal();
  _trapFocusCleanup.tabHistory = trapFocus(dialog);
}

function closeTabHistoryDialog() {
  _trapFocusCleanup.tabHistory?.(); delete _trapFocusCleanup.tabHistory;
  document.getElementById("tab-history-dialog")?.close();
}

async function createWorkspaceTab() {
  if (!state.currentWorkspaceId) {
    return;
  }
  const payload = await request(`/api/workspaces/${state.currentWorkspaceId}/tabs`, { method: "POST" });
  const workspace = syncWorkspacePayload(payload.workspace);
  renderWorkspaceRail();
  renderWorkspaceTabs(workspace);
  await selectWorkspace(state.currentWorkspaceId, payload.tab?.id || null);
}

async function archiveWorkspaceTab(tabId) {
  const workspace = currentWorkspace();
  if (!workspace || !tabId) {
    return;
  }
  if (state.busyWorkspaces.has(workspace.id) && state.liveChats.get(workspace.id)?.tabId === tabId) {
    showToast("Stop the active turn before closing this tab.");
    return;
  }
  const payload = await request(`/api/workspaces/${workspace.id}/tabs/${tabId}`, { method: "DELETE" });
  removeWorkspaceTabMessagesCache(workspace.id, tabId);
  const updatedWorkspace = syncWorkspacePayload(payload.workspace);
  renderWorkspaceRail();
  renderWorkspaceTabs(updatedWorkspace);
  renderTabHistoryDialog(updatedWorkspace);
  await selectWorkspace(workspace.id, payload.next_tab_id || null);
}

async function restoreWorkspaceTab(tabId) {
  const workspace = currentWorkspace();
  if (!workspace || !tabId) {
    return;
  }
  const payload = await request(`/api/workspaces/${workspace.id}/tabs/${tabId}/restore`, { method: "POST" });
  const updatedWorkspace = syncWorkspacePayload(payload.workspace);
  renderWorkspaceRail();
  renderWorkspaceTabs(updatedWorkspace);
  renderTabHistoryDialog(updatedWorkspace);
  await selectWorkspace(workspace.id, payload.tab?.id || null);
}

function finishMessagesRender(container, workspace, liveChat, renderVersion) {
  if (renderVersion !== _messageRenderVersion) {
    return;
  }
  if (liveChat) {
    renderLiveChatState(workspace);
  } else {
    renderLiveStatusPanel(workspace);
  }
  scrollLiveTerminalsToBottom(container);
  renderReviewPanel();
  container.scrollTop = container.scrollHeight;
}

function renderMessageNodesProgressively(container, messages, workspace, liveChat, renderVersion, startIndex = 0) {
  if (renderVersion !== _messageRenderVersion) {
    return;
  }
  const batch = messages.slice(startIndex, startIndex + MESSAGE_RENDER_BATCH_SIZE);
  if (batch.length) {
    container.appendChild(createMessageNodesFragment(batch));
  }
  const nextIndex = startIndex + batch.length;
  if (nextIndex < messages.length) {
    requestAnimationFrame(() => {
      renderMessageNodesProgressively(container, messages, workspace, liveChat, renderVersion, nextIndex);
    });
    return;
  }
  finishMessagesRender(container, workspace, liveChat, renderVersion);
}

function renderMessages(messages, workspace, paging = null) {
  const title = document.getElementById("workspace-title");
  const container = document.getElementById("messages");
  const liveChat = activeLiveChatForWorkspace(workspace);
  const renderVersion = ++_messageRenderVersion;

  if (!workspace) {
    title.textContent = "No project selected";
    renderWorkspaceTabs(null);
    _renderControllers.messages?.abort();
    _renderControllers.messages = new AbortController();
    const { signal: msgSignal } = _renderControllers.messages;
    container.innerHTML = `
      <div class="empty-state">
        <h3>No project selected</h3>
        <p>Import an existing directory or create a new project to get started.</p>
        <div class="empty-state-actions">
          <button type="button" class="secondary-button" id="empty-import-btn">Import Project</button>
          <button type="button" class="secondary-button" id="empty-create-btn">New Project</button>
        </div>
      </div>
    `;
    document.getElementById("empty-import-btn")?.addEventListener("click", () => {
      chooseProjectFolder().catch((e) => showToast(e.message));
    }, { signal: msgSignal });
    document.getElementById("empty-create-btn")?.addEventListener("click", () => {
      chooseCreateProjectLocation().catch((e) => showToast(e.message));
    }, { signal: msgSignal });
    renderReviewPanel();
    return;
  }

  title.textContent = workspace.name;
  renderWorkspaceTabs(workspace);
  _renderControllers.messages?.abort();
  container.innerHTML = "";
  state.messagePaging = paging || null;

  if (state.messagesLoading && !messages.length && !liveChat) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="skeleton-block">
          <div class="skeleton-line" style="width:48%"></div>
          <div class="skeleton-line" style="width:82%"></div>
          <div class="skeleton-line" style="width:67%"></div>
        </div>
      </div>
    `;
    renderReviewPanel();
    return;
  }

  if (!messages.length && !liveChat) {
    _renderControllers.messages?.abort();
    _renderControllers.messages = new AbortController();
    const { signal: msgSignal } = _renderControllers.messages;
    container.innerHTML = `
      <div class="empty-state">
        <h3>Ready</h3>
        <p>Ask for implementation, review, debugging, planning, or refactoring work.</p>
        <div class="empty-state-suggestions">
          <button class="suggestion-chip" data-suggestion="Review this codebase and suggest improvements">Review codebase</button>
          <button class="suggestion-chip" data-suggestion="Add tests for the main module">Add tests</button>
          <button class="suggestion-chip" data-suggestion="Fix any linting or type errors">Fix lint errors</button>
          <button class="suggestion-chip" data-suggestion="Explain how this codebase is structured">Explain structure</button>
        </div>
      </div>
    `;
    container.querySelectorAll(".suggestion-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const input = document.getElementById("chat-input");
        if (input) {
          input.value = chip.dataset.suggestion;
          input.focus();
          // auto-resize if applicable
          input.dispatchEvent(new Event("input"));
        }
      }, { signal: msgSignal });
    });
    renderReviewPanel();
    return;
  }

  syncLoadOlderMessagesButton(container, paging);
  if (!liveChat && messages.length > MESSAGE_RENDER_PROGRESSIVE_THRESHOLD) {
    const initialBatch = messages.slice(0, MESSAGE_RENDER_BATCH_SIZE);
    container.appendChild(createMessageNodesFragment(initialBatch));
    if (initialBatch.length < messages.length) {
      requestAnimationFrame(() => {
        renderMessageNodesProgressively(container, messages, workspace, liveChat, renderVersion, initialBatch.length);
      });
      return;
    }
  } else {
    container.appendChild(createMessageNodesFragment(messages));
  }

  finishMessagesRender(container, workspace, liveChat, renderVersion);
}

async function loadAppInfo() {
  state.appInfo = await request("/api/app/info");
  renderAppInfo();
}

async function loadUpdateInfo(force = false) {
  const suffix = force ? "?force=true" : "";
  const payload = await request(`/api/app/update${suffix}`);
  state.appInfo = {
    ...(state.appInfo || {}),
    update: payload,
  };
  renderAppInfo();
  if (payload?.update_available && payload.latest_version) {
    const storageKey = "bettercode-last-update-toast-version";
    const seenVersion = localStorage.getItem(storageKey);
    if (seenVersion !== payload.latest_version) {
      localStorage.setItem(storageKey, payload.latest_version);
      showToast(t("sidebar.updateVersion", { version: payload.latest_version }));
    }
  }
}

async function installAvailableAppUpdate(button) {
  setButtonPending(button, true, "Installing...");
  try {
    const payload = await request("/api/app/update/install", { method: "POST" });
    if (payload?.message) {
      showToast(payload.message);
    }
  } finally {
    setButtonPending(button, false);
  }
}

async function loadVerifiedModels() {
  const payload = await request("/api/models/refresh", { method: "POST" });
  state.appInfo = {
    ...state.appInfo,
    models: payload.models
  };
  renderAppInfo();
}

function refreshVerifiedModelsInBackground(showErrorToast = false) {
  return loadVerifiedModels().catch((error) => {
    if (showErrorToast) {
      showToast(error.message);
    }
  });
}

async function loadAuth() {
  state.auth = await request("/api/auth/status");
}

async function loadGitStatus(workspaceId = state.currentWorkspaceId) {
  if (!workspaceId) {
    state.git = null;
    renderGitPanel();
    if (state.view === "review-view") renderReviewView();
    return;
  }

  const payload = await request(`/api/workspaces/${workspaceId}/git`);
  if (!isCurrentWorkspaceId(workspaceId)) {
    return;
  }
  setGitState(payload.git);
}

async function loadWorkspaces(preferredId = null) {
  const payload = await request("/api/workspaces");
  state.workspaces = payload.workspaces;
  closeGeneratedFilesMenu();

  if (preferredId !== null) {
    state.currentWorkspaceId = preferredId;
  } else if (state.currentWorkspaceId && !state.workspaces.some((workspace) => workspace.id === state.currentWorkspaceId)) {
    state.currentWorkspaceId = null;
  }

  if (!state.currentWorkspaceId && state.workspaces.length) {
    state.currentWorkspaceId = state.workspaces[0].id;
  }

  renderWorkspaceRail();
  renderGitPanel();
  if (state.view === "review-view") renderReviewView();

  if (state.currentWorkspaceId) {
    await selectWorkspace(state.currentWorkspaceId);
  } else {
    setCurrentTabId(null);
    state.reviewData = null;
    state.reviewLoading = false;
    state.reviewError = "";
    state.selectedReviewPaths = [];
    state.messages = [];
    state.messagesLoading = false;
    state.messagePaging = null;
    renderMessages([], null);
  }
}

async function selectWorkspace(workspaceId, preferredTabId = null) {
  const previousWorkspaceId = state.currentWorkspaceId;
  const previousTabId = state.currentTabId;
  const previousMessages = Array.isArray(state.messages) ? state.messages : [];
  const previousPaging = state.messagePaging;
  state.currentWorkspaceId = workspaceId;
  if (workspaceId) {
    localStorage.setItem("bettercode-workspace-id", String(workspaceId));
  }
  const initialWorkspace = currentWorkspace();
  const initialTab = resolveWorkspaceTab(initialWorkspace, preferredTabId);
  setCurrentTabId(initialTab?.id || null);
  delete state.generatedFilesCache[workspaceId];
  renderWorkspaceRail();
  renderWorkspaceTabs(currentWorkspace());
  state.git = null;
  state.reviewData = null;
  state.reviewLoading = false;
  state.reviewError = "";
  state.selectedReviewPaths = [];
  const initialCachedMessages = getCachedWorkspaceTabMessages(workspaceId, state.currentTabId);
  const preserveVisibleMessages = (
    previousWorkspaceId === workspaceId
    && previousTabId
    && previousTabId === state.currentTabId
    && previousMessages.length > 0
  );
  // Keep the visible transcript in place while the same tab refreshes in the background.
  state.messages = preserveVisibleMessages ? previousMessages : (initialCachedMessages?.messages || []);
  state.messagesLoading = true;
  state.messagePaging = preserveVisibleMessages
    ? (previousPaging || initialCachedMessages?.paging || null)
    : (initialCachedMessages?.paging || null);
  state.selectedGitPaths = [];
  state.runConfig = null;
  state.runConfigStatus = "detecting";
  renderRunButton();
  renderDiagnosticsPanel();
  closeGitMenu();
  closeGeneratedFilesMenu();
  setGitCollapsed(true);
  renderReviewPanel();
  renderGitPanel();
  renderMessages(state.messages, currentWorkspace(), state.messagePaging);
  if (state.view === "review-view") renderReviewView();

  try {
    const initialTabId = state.currentTabId;
    const activateQuery = state.currentTabId ? `?tab_id=${state.currentTabId}` : "";
    const activated = await request(`/api/workspaces/${workspaceId}/session/activate${activateQuery}`, { method: "POST" });
    if (!isCurrentWorkspaceId(workspaceId)) {
      return;
    }
    const activatedWorkspace = syncWorkspacePayload(activated.workspace);
    setCurrentTabId(activated.tab?.id || resolveWorkspaceTab(activatedWorkspace, preferredTabId)?.id || null);
    renderWorkspaceRail();
    renderWorkspaceTabs(currentWorkspace());
    if (state.currentTabId && state.currentTabId !== initialTabId) {
      const activatedCachedMessages = getCachedWorkspaceTabMessages(workspaceId, state.currentTabId);
      state.messages = activatedCachedMessages?.messages || [];
      state.messagePaging = activatedCachedMessages?.paging || null;
      renderMessages(state.messages, currentWorkspace(), state.messagePaging);
    }

    const params = new URLSearchParams({ limit: String(INITIAL_WORKSPACE_MESSAGE_PAGE_SIZE) });
    if (state.currentTabId) {
      params.set("tab_id", String(state.currentTabId));
    }
    const payload = await request(`/api/workspaces/${workspaceId}/messages?${params.toString()}`);
    if (!isCurrentWorkspaceId(workspaceId)) {
      return;
    }
    syncWorkspacePayload(payload.workspace);
    setCurrentTabId(payload.tab?.id || state.currentTabId);
    state.messages = payload.messages;
    state.messagesLoading = false;
    state.messagePaging = payload.paging || null;
    cacheWorkspaceTabMessages(workspaceId, state.currentTabId, state.messages, state.messagePaging);
    renderMessages(state.messages, currentWorkspace(), state.messagePaging);
    // Restore persisted composer draft for this workspace tab
    const savedDraft = localStorage.getItem(workspaceDraftStorageKey(workspaceId, state.currentTabId)) || "";
    restoreComposerDraft(savedDraft, [], true);
    activateView(state.view === "review-view" ? "review-view" : "chat-view");

    loadGitStatus(workspaceId).catch(() => {});
    if (state.view === "review-view") {
      loadReviewData(false, false).catch(() => {});
      loadReviewHistory(workspaceId).catch(() => {});
    }

    // Detect run config and load settings in background
    void (async () => {
      try {
        const [cfg] = await Promise.all([
          fetch(`/api/workspaces/${workspaceId}/run/config`),
          syncRunStatus(workspaceId),
          loadRunSettings(workspaceId),
        ]);
        if (!isCurrentWorkspaceId(workspaceId)) {
          return;
        }
        state.runConfig = cfg.ok ? await cfg.json() : { command: "", detected_from: "", env_required: [], settings_suggested: [] };
      } catch (_) {
        if (!isCurrentWorkspaceId(workspaceId)) {
          return;
        }
        state.runConfig = { command: "", detected_from: "", env_required: [], settings_suggested: [] };
        await syncRunStatus(workspaceId);
      }
      if (!isCurrentWorkspaceId(workspaceId)) {
        return;
      }
      state.runConfigStatus = "ready";
      renderRunButton();
    })();
  } catch (error) {
    state.reviewLoading = false;
    state.messagesLoading = false;
    renderReviewPanel();
    renderReviewView();
    renderDiagnosticsPanel();
    throw error;
  }
}

function renderRunButton() {
  const runBtn = document.getElementById("run-button");
  const runLabel = runBtn?.querySelector(".run-button-label");
  if (!runBtn) return;

  const isRunning = runIsActiveForWorkspace();

  if (isRunning) {
    if (runLabel) runLabel.textContent = "Stop";
    runBtn.disabled = false;
    runBtn.title = "";
    runBtn.dataset.mode = "stop";
    return;
  }

  runBtn.dataset.mode = "run";

  if (!state.currentWorkspaceId || state.runConfigStatus === "idle") {
    if (runLabel) runLabel.textContent = "Run";
    runBtn.disabled = true;
    runBtn.title = "No project open";
    return;
  }
  if (state.runConfigStatus === "detecting") {
    runBtn.disabled = true;
    runBtn.title = "";
    if (runLabel) runLabel.innerHTML = `<span class="btn-spinner"></span>Run`;
    return;
  }
  const command = state.runConfig?.command || "";
  if (!command) {
    runBtn.disabled = true;
    runBtn.title = "No run command detected for this project";
    if (runLabel) runLabel.textContent = "Run";
    return;
  }
  runBtn.disabled = false;
  runBtn.title = "";
  if (runLabel) runLabel.textContent = "Run";
}

async function loadOlderMessages() {
  if (!state.currentWorkspaceId || !state.currentTabId || !state.messagePaging?.has_more || !state.messagePaging?.next_before_id) {
    return;
  }

  const container = document.getElementById("messages");
  const previousHeight = container.scrollHeight;
  const params = new URLSearchParams({
    limit: String(state.messagePaging.limit || 100),
    before_id: String(state.messagePaging.next_before_id),
    tab_id: String(state.currentTabId),
  });
  const payload = await request(`/api/workspaces/${state.currentWorkspaceId}/messages?${params.toString()}`);
  const olderMessages = Array.isArray(payload.messages) ? payload.messages : [];
  state.messages = [...olderMessages, ...state.messages];
  state.messagePaging = payload.paging || null;
  cacheWorkspaceTabMessages(state.currentWorkspaceId, state.currentTabId, state.messages, state.messagePaging);
  const insertAfter = syncLoadOlderMessagesButton(container, state.messagePaging);
  const fragment = createMessageNodesFragment(olderMessages);
  if (insertAfter?.nextSibling) {
    container.insertBefore(fragment, insertAfter.nextSibling);
  } else if (insertAfter) {
    container.appendChild(fragment);
  } else {
    container.insertBefore(fragment, container.firstChild);
  }
  const nextHeight = container.scrollHeight;
  container.scrollTop = Math.max(0, nextHeight - previousHeight);
}

async function attachCurrentProject() {
  const payload = await request("/api/workspaces/current", { method: "POST" });
  await loadWorkspaces(payload.workspace.id);
  showToast("Current project attached.");
}

function openProjectTrustDialog(path, name) {
  state.pendingProjectPath = path;
  state.pendingProjectName = name;
  document.getElementById("project-trust-name").textContent = name;
  document.getElementById("project-trust-path").textContent = path;
  const dialog = document.getElementById("project-trust-dialog");
  dialog.showModal();
  _trapFocusCleanup.projectTrust = trapFocus(dialog);
}

function closeProjectTrustDialog() {
  _trapFocusCleanup.projectTrust?.(); delete _trapFocusCleanup.projectTrust;
  state.pendingProjectPath = null;
  state.pendingProjectName = null;
  document.getElementById("project-trust-dialog").close();
}

function openCreateProjectDialog(parentPath) {
  state.pendingProjectParentPath = parentPath;
  document.getElementById("create-project-parent-path").textContent = parentPath;
  const input = document.getElementById("create-project-input");
  input.value = "";
  const dialog = document.getElementById("create-project-dialog");
  dialog.showModal();
  _trapFocusCleanup.createProject = trapFocus(dialog);
}

function closeCreateProjectDialog() {
  _trapFocusCleanup.createProject?.(); delete _trapFocusCleanup.createProject;
  state.pendingProjectParentPath = null;
  document.getElementById("create-project-dialog").close();
}

async function chooseProjectFolder() {
  const payload = await request("/api/workspaces/pick", { method: "POST" });
  if (payload.cancelled) {
    return;
  }

  openProjectTrustDialog(payload.path, payload.name);
}

async function chooseCreateProjectLocation() {
  const payload = await request("/api/workspaces/pick", { method: "POST" });
  if (payload.cancelled) {
    return;
  }

  openCreateProjectDialog(payload.path);
}

async function confirmProjectTrust(event) {
  event.preventDefault();
  if (!state.pendingProjectPath) {
    return;
  }

  const payload = await request("/api/workspaces", {
    method: "POST",
    body: JSON.stringify({ path: state.pendingProjectPath })
  });

  closeProjectTrustDialog();
  await loadWorkspaces(payload.workspace.id);
  showToast("Project added.");
}

async function createProject(event) {
  event.preventDefault();
  if (!state.pendingProjectParentPath) {
    return;
  }

  const input = document.getElementById("create-project-input");
  const button = document.querySelector("#create-project-form .primary-button");
  const name = input.value.trim();
  if (!name) {
    showToast("Project name cannot be empty.");
    input.focus();
    return;
  }

  setButtonPending(button, true, "Creating...");
  try {
    const payload = await request("/api/workspaces/create-folder", {
      method: "POST",
      body: JSON.stringify({
        parent_path: state.pendingProjectParentPath,
        name,
      })
    });

    closeCreateProjectDialog();
    await loadWorkspaces(payload.workspace.id);
    showToast("Project created.");
  } finally {
    setButtonPending(button, false);
  }
}

async function addAttachments(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) {
    return;
  }

  const nextAttachments = [];
  let skippedCount = 0;

  for (const file of files) {
    if (file.size > 250000) {
      skippedCount += 1;
      continue;
    }

    const content = await file.text();
    if (content.includes("\u0000")) {
      skippedCount += 1;
      continue;
    }

    nextAttachments.push({ name: file.name, content });
  }

  if (!nextAttachments.length) {
    showToast("Only text files up to 250 KB can be attached right now.");
    return;
  }

  state.attachments = [...state.attachments, ...nextAttachments];
  renderAttachmentList();

  if (skippedCount) {
    showToast(`${nextAttachments.length} file(s) attached. ${skippedCount} skipped.`);
    return;
  }

  showToast(`${nextAttachments.length} file(s) attached.`);
}

function openRenameDialog(workspaceId) {
  const workspace = state.workspaces.find((item) => item.id === workspaceId);
  if (!workspace) {
    return;
  }

  state.renameWorkspaceId = workspaceId;
  const dialog = document.getElementById("rename-dialog");
  document.getElementById("rename-dialog-input").value = workspace.name;
  dialog.showModal();
  _trapFocusCleanup.rename = trapFocus(dialog);
}

function closeRenameDialog() {
  _trapFocusCleanup.rename?.(); delete _trapFocusCleanup.rename;
  state.renameWorkspaceId = null;
  document.getElementById("rename-dialog").close();
}

async function renameWorkspace(event) {
  event.preventDefault();
  if (!state.renameWorkspaceId) {
    return;
  }

  const name = document.getElementById("rename-dialog-input").value.trim();
  const payload = await request(`/api/workspaces/${state.renameWorkspaceId}`, {
    method: "PATCH",
    body: JSON.stringify({ name })
  });

  closeRenameDialog();
  await loadWorkspaces(payload.workspace.id);
  showToast("Project renamed.");
}

async function deleteWorkspace(workspaceId) {
  const workspace = state.workspaces.find((item) => item.id === workspaceId);
  if (!workspace) {
    return;
  }

  if (!window.confirm(`Remove project "${workspace.name}" from BetterCode?`)) {
    return;
  }

  await request(`/api/workspaces/${workspaceId}`, { method: "DELETE" });
  clearWorkspaceTabMessagesCache(workspaceId);
  closeWorkspaceMenu();
  await loadWorkspaces();
  showToast("Project removed.");
}

async function resetWorkspaceSession(workspaceId) {
  const workspace = state.workspaces.find((item) => item.id === workspaceId);
  const tab = resolveWorkspaceTab(workspace, workspaceId === state.currentWorkspaceId ? state.currentTabId : null);
  if (!workspace) {
    return;
  }

  if (!window.confirm(`Reset the saved session for "${workspace.name}"${tab ? ` / ${tab.title}` : ""}? BetterCode will keep the project and message history, but the CLI session will start fresh on the next turn.`)) {
    return;
  }

  const payload = await request(`/api/workspaces/${workspaceId}/session/reset${tab?.id ? `?tab_id=${tab.id}` : ""}`, { method: "POST" });
  syncWorkspacePayload(payload.workspace);
  closeWorkspaceMenu();
  renderWorkspaceRail();
  renderWorkspaceTabs(currentWorkspace());
  showToast("Project session reset.");
}

async function runGitAction(action, body = null) {
  const workspace = currentWorkspace();
  if (!workspace) {
    return;
  }

  const payload = await request(`/api/workspaces/${workspace.id}/git/${action}`, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined
  });

  closeGitMenu();
  setGitState(payload.git, payload.output || "");
}

async function commitGitChanges() {
  const input = document.getElementById("git-commit-message");
  const button = document.getElementById("git-commit-button");
  if (!input) {
    return;
  }

  const message = input.value.trim();
  if (!message) {
    showToast("Enter a commit message.");
    return;
  }

  const workspace = currentWorkspace();
  if (!workspace) {
    return;
  }

  setButtonPending(button, true, "Committing...");
  try {
    const commitPayload = await request(`/api/workspaces/${workspace.id}/git/commit`, {
      method: "POST",
      body: JSON.stringify({ message })
    });

    try {
      const pushPayload = await request(`/api/workspaces/${workspace.id}/git/push`, {
        method: "POST"
      });
      const output = [commitPayload.output, pushPayload.output].filter(Boolean).join("\n\n");
      setGitState(pushPayload.git, output);
    } catch (error) {
      const output = [commitPayload.output, error.message].filter(Boolean).join("\n\n");
      setGitState(commitPayload.git, output);
      throw new Error(`Commit succeeded, but push failed: ${error.message}`);
    }

    input.value = "";
  } finally {
    setButtonPending(button, false);
  }
}

function openAuthDialog(provider) {
  state.authProvider = provider;
  const providerTitles = {
    openai: "OpenAI",
    cursor: "Cursor",
    anthropic: "Anthropic",
    google: "Google"
  };
  const providerCopy = {
    openai: "Save an OpenAI API key locally for Codex-backed GPT access.",
    cursor: "Save a Cursor API key locally for Cursor CLI access.",
    anthropic: "Save an Anthropic API key locally for Claude access.",
    google: "Save a Google AI API key locally for Gemini access.",
  };
  document.getElementById("auth-dialog-title").textContent = `Add ${providerTitles[provider] || "Provider"} API Key`;
  document.getElementById("auth-dialog-copy").textContent = providerCopy[provider] || "Save a provider API key locally for BetterCode.";
  document.getElementById("auth-dialog-input").value = "";
  const authDialog = document.getElementById("auth-dialog");
  authDialog.showModal();
  _trapFocusCleanup.auth = trapFocus(authDialog);
}

function closeAuthDialog() {
  _trapFocusCleanup.auth?.(); delete _trapFocusCleanup.auth;
  state.authProvider = null;
  document.getElementById("auth-dialog").close();
}

function openAccountDialog(runtime) {
  state.accountProvider = runtime;
  const runtimeInfo = state.appInfo?.runtimes?.[runtime] || {};
  const labels = {
    codex: "Codex CLI",
    cursor: "Cursor CLI",
    claude: "Claude CLI",
    gemini: "Gemini CLI"
  };
  const commands = {
    codex: "codex login",
    cursor: "cursor-agent login",
    claude: "claude",
    gemini: "gemini"
  };
  document.getElementById("account-dialog-title").textContent = `Login to ${labels[runtime] || "Runtime"}`;
  document.getElementById("account-dialog-copy").textContent = runtimeInfo.login_hint || "Complete the runtime login flow, then refresh status here.";
  document.getElementById("account-dialog-command").textContent = commands[runtime] || runtime;
  const accountDialog = document.getElementById("account-dialog");
  accountDialog.showModal();
  _trapFocusCleanup.account = trapFocus(accountDialog);
}

function closeAccountDialog() {
  _trapFocusCleanup.account?.(); delete _trapFocusCleanup.account;
  state.accountProvider = null;
  document.getElementById("account-dialog").close();
}

async function saveProviderKey(event) {
  event.preventDefault();
  if (!state.authProvider) {
    return;
  }

  const apiKey = document.getElementById("auth-dialog-input").value.trim();
  if (!apiKey) {
    showToast("Enter an API key.");
    return;
  }

  const submitButton = event.submitter || event.target.querySelector('button[type="submit"]');
  setButtonPending(submitButton, true, "Saving...");
  try {
    state.auth = await request("/api/auth/api-key", {
      method: "POST",
      body: JSON.stringify({ provider: state.authProvider, api_key: apiKey })
    });

    await loadAppInfo();
    closeAuthDialog();
    refreshVerifiedModelsInBackground(true);
    const label = state.authProvider === "openai"
      ? "OpenAI"
      : state.authProvider === "cursor"
        ? "Cursor"
        : state.authProvider === "anthropic"
          ? "Anthropic"
          : "Google";
    showToast(`${label} API key saved.`);
  } finally {
    setButtonPending(submitButton, false);
  }
}

async function saveProviderAccount(event) {
  event.preventDefault();
  if (!state.accountProvider) {
    return;
  }

  closeAccountDialog();
  await loadAppInfo();
  refreshVerifiedModelsInBackground(true);
  showToast("Runtime status refreshed.");
}

function appendTemporaryMessage(role, content, activityLog = [], historyLog = [], changeLog = [], routingMeta = {}, retryPayload = null) {
  const container = document.getElementById("messages");
  const node = createMessageNode(role, content, null, activityLog, historyLog, changeLog, [], routingMeta);
  if (retryPayload) {
    const actions = document.createElement("div");
    actions.className = "message-retry-actions";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "message-retry-btn";
    btn.textContent = "Try again";
    btn.dataset.retryText = retryPayload.text || "";
    btn.dataset.retryAttachments = JSON.stringify(retryPayload.attachments || []);
    actions.appendChild(btn);
    node.appendChild(actions);
  }
  container.appendChild(node);
  container.scrollTop = container.scrollHeight;
  return node;
}

function updateTemporaryMessage(node, content) {
  if (!node) {
    return;
  }

  const body = node.querySelector(".message-body");
  if (body) {
    body.textContent = content;
  }

  const container = document.getElementById("messages");
  container.scrollTop = container.scrollHeight;
}

function formatCommand(command) {
  if (Array.isArray(command)) {
    return command.map((part) => String(part)).join(" ");
  }
  return String(command || "").trim();
}

function formatUsageSummary(usage = {}) {
  const parts = [];
  if (Number.isFinite(usage.input_tokens)) {
    parts.push(`input ${usage.input_tokens.toLocaleString()}`);
  }
  if (Number.isFinite(usage.cached_input_tokens)) {
    parts.push(`cached ${usage.cached_input_tokens.toLocaleString()}`);
  }
  if (Number.isFinite(usage.output_tokens)) {
    parts.push(`output ${usage.output_tokens.toLocaleString()}`);
  }
  return parts.length ? ` (${parts.join(", ")})` : "";
}

const LIVE_PHASES = [
  { key: "plan", label: "Plan", title: "Planning the work", note: "Understanding the request, selecting the model, and preparing the turn." },
  { key: "inspect", label: "Inspect", title: "Inspecting the project", note: "Reading files, searching the codebase, and gathering context." },
  { key: "edit", label: "Edit", title: "Making changes", note: "Updating files and applying the implementation." },
  { key: "validate", label: "Validate", title: "Checking the result", note: "Running commands, checks, or validation steps." },
  { key: "finalize", label: "Finalize", title: "Finalizing the response", note: "Wrapping up the turn and preparing the final answer." },
];

function classifyShellCommand(step) {
  const match = step.match(/^(?:running|completed)(?: shell)? command:\s*(.+)$/i);
  const command = (match?.[1] || "").toLowerCase();
  if (!command) {
    return "validate";
  }

  if (
    /(^|\s)(rg|grep|find|ls|cat|sed|head|tail|tree|pwd)(\s|$)/.test(command)
    || command.includes("git status")
    || command.includes("git show")
    || command.includes("git ls-files")
    || command.includes("git diff")
    || command.includes("git log")
    || command.includes("sed -n")
  ) {
    return "inspect";
  }

  if (
    command.includes("pytest")
    || command.includes("vitest")
    || command.includes("jest")
    || command.includes("playwright")
    || command.includes("npm test")
    || command.includes("pnpm test")
    || command.includes("yarn test")
    || command.includes("cargo test")
    || command.includes("go test")
    || command.includes("ruff")
    || command.includes("mypy")
    || command.includes("eslint")
    || command.includes("tsc")
  ) {
    return "validate";
  }

  if (
    command.includes("apply_patch")
    || command.includes("git add")
    || command.includes("git mv")
    || command.includes("git rm")
    || command.includes("tee ")
    || command.includes("sed -i")
    || command.includes("perl -pi")
    || command.includes("perl -0pi")
    || command.includes("write_text(")
    || command.includes("write_bytes(")
    || command.includes("fs.writefile")
    || command.includes("fs.promises.writefile")
    || command.includes("cat >")
    || command.includes("printf >")
    || command.includes("echo >")
    || /(^|\s)(mv|cp|mkdir|touch|chmod)(\s|$)/.test(command)
  ) {
    return "edit";
  }

  return "validate";
}

function classifyLiveStep(step) {
  const text = String(step || "").trim();
  const lower = text.toLowerCase();
  if (!lower) {
    return "";
  }

  if (
    lower.includes("is pre-processing the request")
    || lower.includes("auto model select chose")
    || lower.includes("pre-processed this request")
    || lower.includes("preparing request")
    || lower.includes("turn started")
    || lower.includes("starting codex")
    || lower.includes("starting cursor")
    || lower.includes("starting claude")
    || lower.includes("starting gemini")
    || lower.includes("session started")
  ) {
    return "plan";
  }

  if (
    lower.startsWith("searching:")
    || lower.startsWith("listing directory:")
    || lower.startsWith("reading file:")
    || lower.includes("searching codebase")
    || lower.includes("working with file")
    || lower.includes("reading file")
    || lower.includes("listing files")
    || lower.includes("using search")
    || lower.includes("using open")
    || lower.includes("using read")
    || lower.includes("using find")
  ) {
    return "inspect";
  }

  if (
    lower.startsWith("running shell command:")
    || lower.startsWith("completed shell command:")
    || lower.startsWith("running command:")
    || lower.startsWith("completed command:")
  ) {
    return classifyShellCommand(lower);
  }

  if (
    lower.startsWith("updating file:")
    || lower.startsWith("applying changes:")
    || lower.includes("updating file")
    || lower.includes("applying patch")
    || lower.includes("applying changes")
    || lower.includes("completed work on")
    || lower.includes("completed updating file")
    || lower.includes("using apply_patch")
    || lower.includes("using write")
    || lower.includes("using edit")
  ) {
    return "edit";
  }

  if (
    lower.includes("tool result")
    || lower.includes("running tests")
    || lower.includes("checking")
    || lower.includes("validating")
  ) {
    return "validate";
  }

  if (
    lower.includes("turn complete")
    || lower.includes("finalizing")
    || lower.includes("returned no output")
    || lower.includes("failed")
    || lower.includes("error")
  ) {
    return "finalize";
  }

  return "";
}

function translateTranscriptEvent(rawLine) {
  const line = String(rawLine || "").trim();
  if (!line) {
    return [];
  }

  let payload = null;
  try {
    payload = JSON.parse(line);
  } catch {
    return [{ kind: "event", text: line }];
  }

  const type = payload.type || "";
  if (type === "thread.started") {
    return [{ kind: "event", text: `Started session${payload.thread_id ? ` ${payload.thread_id}` : ""}.` }];
  }
  if (type === "turn.started") {
    return [{ kind: "event", text: "Started turn." }];
  }
  if (type === "turn.completed") {
    return [{ kind: "event", text: `Finished turn.${formatUsageSummary(payload.usage || {})}` }];
  }
  if (type === "error") {
    return [{ kind: "event", text: payload.message ? `Error: ${payload.message}` : "Error." }];
  }

  if (type === "item.started" || type === "item.completed") {
    const completed = type === "item.completed";
    const item = payload.item && typeof payload.item === "object" ? payload.item : {};
    const itemType = item.type || item.kind || "";
    const entries = [];

    if (itemType === "command_execution" || itemType === "command" || itemType === "shell_command") {
      const command = formatCommand(item.command);
      entries.push({
        kind: "command",
        text: `${completed ? "Completed" : "Running"} command${command ? `: ${command}` : "."}${completed && Number.isFinite(item.exit_code) ? ` (exit ${item.exit_code})` : ""}`,
      });
      const output = String(item.aggregated_output || "").trim();
      if (completed && output) {
        entries.push({ kind: "output", text: output });
      }
      return entries;
    }

    if (itemType === "search" || itemType === "grep_search") {
      return [{ kind: "event", text: `${completed ? "Completed" : "Searching"}${item.query ? `: ${item.query}` : "."}` }];
    }

    if (itemType === "read_file" || itemType === "open_file") {
      return [{ kind: "event", text: `${completed ? "Read" : "Reading"} file${item.path ? `: ${item.path}` : "."}` }];
    }

    if (itemType === "write_file" || itemType === "apply_patch" || itemType === "edit_file") {
      return [{ kind: "event", text: `${completed ? "Updated" : "Updating"} file${item.path ? `: ${item.path}` : "."}` }];
    }

    if (itemType === "plan") {
      return [{ kind: "event", text: `${completed ? "Updated" : "Updating"} plan.` }];
    }

    return [{ kind: "event", text: `${completed ? "Completed" : "Started"} ${itemType || "step"}.` }];
  }

  if (type === "system" && payload.subtype === "init") {
    return [{ kind: "event", text: `${payload.model || "Model"} session started.` }];
  }

  if (type === "tool_use") {
    return [{ kind: "event", text: `Using tool${payload.tool_name ? `: ${payload.tool_name}` : "."}` }];
  }

  if (type === "tool_result") {
    const status = payload.status ? ` (${payload.status})` : "";
    const output = String(payload.output || "").trim();
    if (output) {
      return [
        { kind: "event", text: `Tool result${status}.` },
        { kind: "output", text: output },
      ];
    }
    return [{ kind: "event", text: `Tool result${status}.` }];
  }

  if (type === "result" && typeof payload.result === "string" && payload.result.trim()) {
    return [{ kind: "event", text: payload.is_error ? `Error: ${payload.result.trim()}` : "Completed response." }];
  }

  if (type === "message" && payload.role === "assistant") {
    const content = String(payload.content || "").trim();
    return content ? [{ kind: "response", text: content }] : [];
  }

  return [{ kind: "event", text: line }];
}

function buildTranscriptEntries(historyLog = []) {
  const entries = [];
  for (const rawLine of Array.isArray(historyLog) ? historyLog : []) {
    entries.push(...translateTranscriptEvent(rawLine));
  }
  return entries;
}

function inferLivePhase(activityLines) {
  const classifiedSteps = activityLines
    .filter(Boolean)
    .map((step) => classifyLiveStep(step))
    .filter(Boolean);
  const currentKey = classifiedSteps[classifiedSteps.length - 1] || "plan";
  const seenIndices = classifiedSteps
    .map((stepKey) => LIVE_PHASES.findIndex((phase) => phase.key === stepKey))
    .filter((index) => index >= 0);
  const currentIndex = LIVE_PHASES.findIndex((phase) => phase.key === currentKey);
  const furthestIndex = seenIndices.length ? Math.max(...seenIndices) : Math.max(0, currentIndex);
  return {
    current: LIVE_PHASES[Math.max(0, currentIndex)],
    phases: LIVE_PHASES.map((phase, index) => ({
      ...phase,
      state: index < currentIndex || index < furthestIndex ? "done" : index === currentIndex ? "active" : "pending",
    })),
  };
}

async function readStreamResponse(response, onEvent) {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Streaming is not available in this environment.");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const rawLine of lines) {
      if (!rawLine.trim()) {
        continue;
      }

      await onEvent(JSON.parse(rawLine));
    }

    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    await onEvent(JSON.parse(buffer));
  }
}


async function executeChatStream({
  url,
  body = null,
  workspaceId,
  tabId,
  fromQueue = false,
  restoreText = "",
  restoreAttachments = [],
  restoreOnFailure = true,
  userPreview = "",
  selectedModelLabel = "",
  selectionReasoning = "",
  selectedModelId = "",
}) {
  const workspace = currentWorkspace();
  state.liveChats.set(workspaceId, {
    workspaceId,
    tabId,
    userPreview,
    activityLines: [localizeRuntimeLine("Preparing request…")],
    transcriptLines: [],
    terminalBuffer: "",
    terminalMode: "",
    tasks: [],
    inputPrompt: null,
    selectedModelId,
    selectedModelLabel,
    selectionReasoning,
    stopRequested: false,
    stallNotified: false,
  });
  const lc = state.liveChats.get(workspaceId);
  const notificationWorkspaceId = workspaceId;
  renderMessages(state.messages, workspace, state.messagePaging);
  const activityLines = lc.activityLines;
  const transcriptLines = lc.transcriptLines;
  let streamError = null;

  state.busyWorkspaces.add(workspaceId);
  renderComposerState();
  renderDiagnosticsPanel();
  renderLiveChatState(workspace);
  startChatStatusPolling();

  try {
    const response = await fetch(url, {
      method: "POST",
      ...(body ? {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      } : {})
    });

    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json") ? await response.json() : await response.text();
      const detail = typeof payload === "string" ? payload : payload.detail || "Request failed.";
      throw new Error(detail);
    }

    let workspaceLoaded = false;
    let streamCancelled = false;
    await readStreamResponse(response, async (streamEvent) => {
      if (streamEvent.type === "status") {
        if (lc) {
          if (streamEvent.selected_model) {
            lc.selectedModelId = streamEvent.selected_model;
          }
          if (streamEvent.selected_model_label) {
            lc.selectedModelLabel = streamEvent.selected_model_label;
          }
          if (streamEvent.selection_reasoning) {
            lc.selectionReasoning = streamEvent.selection_reasoning;
          }
        }
        const prevPhaseKey = inferLivePhase(activityLines).current?.key;
        if (streamEvent.message) {
          activityLines.push(streamEvent.message);
        }
        if (streamEvent.transcript) {
          transcriptLines.push(streamEvent.transcript);
        }
        if (streamEvent.terminal && lc && lc.terminalMode !== "raw") {
          if (lc.terminalMode !== "synthetic") {
            lc.terminalBuffer = "";
            lc.terminalMode = "synthetic";
          }
          lc.terminalBuffer += `${streamEvent.terminal}\n`;
        }
        if (streamEvent.tasks && lc) {
          lc.tasks = Array.isArray(streamEvent.tasks) ? streamEvent.tasks : [];
        }
        scheduleLiveChatRender(workspace, { immediate: prevPhaseKey !== inferLivePhase(activityLines).current?.key });
        if (streamEvent.message && inferLivePhase(activityLines).current?.key !== prevPhaseKey) {
          await new Promise(resolve => requestAnimationFrame(resolve));
        }
        return;
      }

      if (streamEvent.type === "task_state") {
        if (lc) {
          lc.tasks = Array.isArray(streamEvent.tasks) ? streamEvent.tasks : [];
        }
        scheduleLiveChatRender(workspace);
        return;
      }

      if (streamEvent.type === "terminal_chunk") {
        if (lc && streamEvent.text) {
          if (lc.terminalMode !== "raw") {
            if (lc.terminalMode === "synthetic") {
              lc.terminalBuffer = "";
            }
            lc.terminalMode = "raw";
          }
          // Keep the text buffer for stored/fallback rendering
          lc.terminalBuffer += streamEvent.text;
          // Write directly to xterm.js — handles all ANSI codes natively
          if (_xtermAvailable()) {
            const inst = _getOrCreateXterm(workspaceId);
            if (inst) {
              inst.terminal.write(streamEvent.text);
              // Ensure the terminal is mounted if we just got our first chunk
              const progressNode = document.querySelector('[data-live-transcript="true"]');
              if (progressNode) {
                _mountXtermToPlaceholder(progressNode, workspaceId, true);
                try { inst.terminal.scrollToBottom(); } catch (_) {}
              }
            }
          }
        }
        scheduleLiveChatRender(workspace);
        return;
      }

      if (streamEvent.type === "input_required") {
        if (lc) {
          lc.inputPrompt = streamEvent.prompt || localizeRuntimeLine("BetterCode needs a reply to continue.");
        }
        scheduleLiveChatRender(workspace, { immediate: true });
        return;
      }

      if (streamEvent.type === "error") {
        streamError = streamEvent.message || "Request failed.";
        activityLines.push(streamError);
        if (lc && lc.terminalMode !== "raw") {
          lc.terminalBuffer += `\nError: ${streamError}\n`;
        }
        scheduleLiveChatRender(workspace, { immediate: true });
        return;
      }

      if (streamEvent.type === "final") {
        const completedModelLabel = lc?.selectedModelLabel || selectedModelLabel;
        _disposeXterm(workspaceId);
        state.liveChats.delete(workspaceId);
        await selectWorkspace(workspaceId, tabId);
        workspaceLoaded = true;
        await notifyDesktopTurnComplete(notificationWorkspaceId, completedModelLabel);
        return;
      }

      if (streamEvent.type === "cancelled") {
        streamCancelled = true;
        _disposeXterm(workspaceId);
        if (lc) {
          ensureLiveChatStatusLine(streamEvent.message || "Turn stopped.", lc);
          scheduleLiveChatRender(workspace, { immediate: true });
        }
        return;
      }

      if (streamEvent.type === "patch") {
        await selectWorkspace(state.currentWorkspaceId, tabId);
        workspaceLoaded = true;
      }
    });

    if (streamError) {
      throw new Error(streamError);
    }

    if (streamCancelled) {
      if (restoreOnFailure) {
        restoreComposerDraft(restoreText, restoreAttachments, !fromQueue);
      }
      state.liveChats.delete(workspaceId);
      await selectWorkspace(workspaceId, tabId);
      showToast("Turn stopped.");
      return;
    }

    if (!workspaceLoaded) {
      state.liveChats.delete(workspaceId);
      await selectWorkspace(workspaceId, tabId);
    }
  } catch (error) {
    state.liveChats.delete(workspaceId);
    await selectWorkspace(workspaceId, tabId);
    const retryPayload = restoreOnFailure && restoreText ? { text: restoreText, attachments: restoreAttachments } : null;
    appendTemporaryMessage("assistant", error.message, activityLines, transcriptLines, [], {}, retryPayload);
  } finally {
    stopChatStatusPolling();
    state.busyWorkspaces.delete(workspaceId);
    renderComposerState();
    renderDiagnosticsPanel();
  }
}

async function submitChatTurn(text, attachments, fromQueue = false) {
  if (!state.currentTabId) {
    showToast("Create or select a tab first.");
    restoreComposerDraft(text, attachments, !fromQueue);
    return;
  }
  if (!state.selectedModel) {
    showToast("No verified model is available yet.");
    restoreComposerDraft(text, attachments, !fromQueue);
    return;
  }

  const selectedOption = modelOption(state.selectedModel);
  const usingAutoSelect = state.selectedModel === "smart";
  const selectedAgentMode = currentAgentMode();
  await executeChatStream({
    url: "/api/chat/stream",
    body: {
      workspace_id: state.currentWorkspaceId,
      tab_id: state.currentTabId,
      text,
      model: state.selectedModel,
      agent_mode: selectedAgentMode || null,
      attachments,
    },
    workspaceId: state.currentWorkspaceId,
    tabId: state.currentTabId,
    fromQueue,
    restoreText: text,
    restoreAttachments: attachments,
    restoreOnFailure: true,
    userPreview: previewChatPayload(text, attachments),
    selectedModelId: usingAutoSelect ? "" : state.selectedModel,
    selectedModelLabel: usingAutoSelect ? localizeRuntimeLine("Selecting model…") : (selectedOption?.label || state.selectedModel),
    selectionReasoning: usingAutoSelect
      ? localizeRuntimeLine("Local LLM is breaking down the tasks and choosing the best model(s).")
      : localizeRuntimeLine("Selected directly in the model picker."),
  });
}

async function retryLastTurn() {
  const workspace = currentWorkspace();
  const tab = currentTab(workspace);
  if (!workspace) {
    showToast("Select a project first.");
    return;
  }
  if (!tab) {
    showToast("Select a tab first.");
    return;
  }
  if (isCurrentWorkspaceBusy()) {
    showToast("Wait for the current turn to finish first.");
    return;
  }

  await executeChatStream({
    url: `/api/workspaces/${workspace.id}/chat/retry/stream?tab_id=${tab.id}`,
    workspaceId: workspace.id,
    tabId: tab.id,
    restoreOnFailure: false,
    userPreview: "Retrying last turn…",
    selectedModelLabel: "Retrying…",
    selectionReasoning: "Running the most recent saved request for this tab again.",
  });
}

async function restartSelectorRuntime() {
  const button = document.getElementById("settings-restart-selector");
  setButtonPending(button, true, "Restarting...");
  try {
    const payload = await request("/api/selector/restart", { method: "POST" });
    await loadAppInfo();
    showToast(payload?.message || "Auto Model Select restarted.");
  } catch (error) {
    showToast(error.message);
  } finally {
    setButtonPending(button, false);
    renderDiagnosticsPanel();
  }
}

async function installSelectedLocalPreprocessModel() {
  const button = document.getElementById("settings-install-local-preprocess-model");
  const modelSelect = document.getElementById("settings-local-preprocess-model");
  const modelId = state.localPreprocessDraftModelId || modelSelect?.value || "";
  if (!modelId) {
    showToast("Pick a local model first.");
    return;
  }
  const availableLocalModels = localPreprocessModelsBySize(state.appInfo?.selector?.available_local_models);
  const candidate = availableLocalModels.find((model) => model.id === modelId) || null;
  if (!candidate) {
    showToast("That local model is no longer available.");
    return;
  }
  if (candidate.installed) {
    if (state.appInfo?.settings?.local_preprocess_model === modelId) {
      showToast("That local model is already active.");
      return;
    }
    setButtonPending(button, true, "Switching...");
    try {
      await updateAppSettings({ local_preprocess_model: modelId }, { showSuccessToast: false });
      showToast("Local model updated.");
    } catch (error) {
      showToast(error.message);
    } finally {
      setButtonPending(button, false);
      renderAppSettings();
    }
    return;
  }
  try {
    openLocalModelInstallDialog(modelId);
  } catch (error) {
    showToast(error.message);
  }
}

function openLocalModelInstallDialog(modelId) {
  const dialog = document.getElementById("local-model-install-dialog");
  const title = document.getElementById("local-model-install-dialog-title");
  const copy = document.getElementById("local-model-install-dialog-copy");
  const installBtn = document.getElementById("local-model-install-dialog-install");
  const activateBtn = document.getElementById("local-model-install-dialog-activate");
  if (!dialog) return;

  const availableLocalModels = Array.isArray(state.appInfo?.selector?.available_local_models)
    ? state.appInfo.selector.available_local_models : [];
  const candidate = availableLocalModels.find((m) => m.id === modelId);
  const label = candidate?.label || modelId;
  const activeCandidate = availableLocalModels.find((m) => m.id === (state.appInfo?.settings?.local_preprocess_model || "")) || null;

  title.textContent = candidate?.installed ? `Use ${label}` : `Install ${label}`;
  copy.innerHTML = renderLocalModelInstallDialogContent(candidate, { activeCandidate });

  installBtn.classList.toggle("hidden", Boolean(candidate?.installed));
  activateBtn.classList.toggle("hidden", !candidate?.installed);
  installBtn.textContent = "Install with Ollama";
  activateBtn.textContent = candidate?.installed && activeCandidate?.id !== modelId ? "Use This Model" : "Active Model";
  activateBtn.disabled = Boolean(candidate?.installed && activeCandidate?.id === modelId);

  installBtn.dataset.modelId = modelId;
  activateBtn.dataset.modelId = modelId;

  dialog.showModal();
  _trapFocusCleanup.localModelInstall = trapFocus(dialog);
}

function closeLocalModelInstallDialog() {
  const dialog = document.getElementById("local-model-install-dialog");
  const installBtn = document.getElementById("local-model-install-dialog-install");
  const activateBtn = document.getElementById("local-model-install-dialog-activate");
  if (installBtn) {
    setButtonPending(installBtn, false);
    installBtn.disabled = false;
  }
  if (activateBtn) {
    setButtonPending(activateBtn, false);
    activateBtn.disabled = false;
  }
  dialog?.close();
  if (_trapFocusCleanup.localModelInstall) {
    _trapFocusCleanup.localModelInstall();
    delete _trapFocusCleanup.localModelInstall;
  }
}

async function installAndActivateLocalModel(modelId) {
  const title = document.getElementById("local-model-install-dialog-title");
  const installBtn = document.getElementById("local-model-install-dialog-install");
  const activateBtn = document.getElementById("local-model-install-dialog-activate");
  const copy = document.getElementById("local-model-install-dialog-copy");
  setButtonPending(installBtn, true, "Installing...");
  try {
    await request("/api/selector/models/install", {
      method: "POST",
      body: JSON.stringify({ model_id: modelId }),
    });
    await loadAppInfo();
    state.localPreprocessDraftModelId = modelId;
    renderAppSettings();
    // Model is now installed — swap to activate button
    const availableLocalModels = Array.isArray(state.appInfo?.selector?.available_local_models)
      ? state.appInfo.selector.available_local_models : [];
    const candidate = availableLocalModels.find((m) => m.id === modelId);
    const label = candidate?.label || modelId;
    const activeCandidate = availableLocalModels.find((m) => m.id === (state.appInfo?.settings?.local_preprocess_model || "")) || null;
    title.textContent = `${label} installed`;
    copy.innerHTML = renderLocalModelInstallDialogContent(candidate, { justInstalled: true, activeCandidate });
    installBtn.classList.add("hidden");
    activateBtn.classList.remove("hidden");
    activateBtn.textContent = "Use This Model";
    activateBtn.disabled = false;
    activateBtn.dataset.modelId = modelId;
  } catch (error) {
    showToast(error.message);
    setButtonPending(installBtn, false);
  }
}

async function activateLocalModel(modelId) {
  const activateBtn = document.getElementById("local-model-install-dialog-activate");
  setButtonPending(activateBtn, true, "Activating...");
  try {
    await updateAppSettings({ local_preprocess_model: modelId }, { showSuccessToast: false });
    state.localPreprocessDraftModelId = modelId;
    closeLocalModelInstallDialog();
    showToast("Local model activated.");
  } catch (error) {
    showToast(error.message);
    setButtonPending(activateBtn, false);
  }
}

async function sendChat(event) {
  event.preventDefault();
  if (!state.currentWorkspaceId) {
    return;
  }

  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  const attachments = state.attachments.map((attachment) => ({ ...attachment }));
  if (!text && !attachments.length) {
    return;
  }

  if (isCurrentWorkspaceBusy()) {
    showToast("Wait for the current turn to finish, or use the inline reply field if BetterCode asks for input.");
    return;
  }

  if (!state.selectedModel) {
    showToast("No verified model is available yet.");
    return;
  }

  setComposerDraft("", []);
  await submitChatTurn(text, attachments, false);
}

// ----------------------------------------------------------------
// RUN SETTINGS
// ----------------------------------------------------------------
let _runSettingsOpen = false;

async function loadRunSettings(workspaceId) {
  if (!workspaceId) { state.runSettings = {}; return; }
  try {
    const payload = await request(`/api/workspaces/${workspaceId}/run/settings`);
    if (!isCurrentWorkspaceId(workspaceId)) {
      return;
    }
    state.runSettings = payload.settings || {};
  } catch (_) {
    if (!isCurrentWorkspaceId(workspaceId)) {
      return;
    }
    state.runSettings = {};
  }
}

function openRunSettingsPanel() {
  _runSettingsOpen = true;
  renderRunSettingsPanel();
  const panel = document.getElementById("run-settings-panel");
  const anchor = document.getElementById("run-settings-button");
  if (!panel || !anchor) {
    return;
  }
  const rect = anchor.getBoundingClientRect();
  const viewportWidth = document.documentElement.clientWidth || window.innerWidth || 0;
  const viewportHeight = document.documentElement.clientHeight || window.innerHeight || 0;
  const edgeGap = 100;
  const panelWidth = Math.min(300, Math.max(220, viewportWidth - (edgeGap * 2)));
  const desiredTop = rect.bottom + 6;
  const maxTop = Math.max(edgeGap, viewportHeight - panel.offsetHeight - edgeGap);
  const rightGap = Math.max(edgeGap, viewportWidth - rect.right + 6);
  panel.style.width = `${panelWidth}px`;
  panel.style.top = `${Math.min(desiredTop, maxTop)}px`;
  panel.style.right = `${rightGap}px`;
  panel.classList.remove("hidden");
}

function closeRunSettingsPanel() {
  _runSettingsOpen = false;
  document.getElementById("run-settings-panel").classList.add("hidden");
}

function renderRunSettingsPanel() {
  const container = document.getElementById("run-settings-fields");
  const suggestions = state.runConfig?.settings_suggested || [];
  const savedEnv = (state.runSettings || {}).env || {};

  // Build a merged list: suggestions first, then any saved keys not in suggestions
  const suggestedNames = new Set(suggestions.map(s => s.name));
  const rows = suggestions.map(s => ({
    name: s.name,
    label: s.label || s.name,
    description: s.description || "",
    value: savedEnv[s.name] ?? s.default_value ?? "",
    suggested: true,
  }));
  for (const [key, val] of Object.entries(savedEnv)) {
    if (!suggestedNames.has(key)) {
      rows.push({ name: key, label: key, description: "", value: val, suggested: false });
    }
  }

  container.innerHTML = "";
  for (const row of rows) {
    container.appendChild(_buildRunSettingsRow(row.name, row.label, row.description, row.value));
  }
}

function _buildRunSettingsRow(name, label, description, value, removable = true) {
  const wrap = document.createElement("div");
  wrap.className = "run-settings-row";
  wrap.innerHTML = `
    <div class="run-settings-row-meta">
      <label class="run-settings-row-label">${escapeHtml(label)}</label>
      ${description ? `<span class="run-settings-row-desc">${escapeHtml(description)}</span>` : ""}
    </div>
    <div class="run-settings-row-inputs">
      <input class="run-settings-name-input${name ? " hidden" : ""}" type="text" placeholder="VARIABLE_NAME" value="${escapeHtml(name)}" data-role="name">
      <input class="run-settings-val-input" type="text" placeholder="value" value="${escapeHtml(value)}" data-role="value" data-var-name="${escapeHtml(name)}">
      ${removable ? `<button type="button" class="icon-button run-settings-remove" aria-label="Remove"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>` : ""}
    </div>
  `;
  wrap.querySelector(".run-settings-remove")?.addEventListener("click", (e) => { e.stopPropagation(); wrap.remove(); });
  return wrap;
}

function _addRunSettingsRow() {
  const container = document.getElementById("run-settings-fields");
  const row = _buildRunSettingsRow("", "", "", "", true);
  // For blank rows, show the name input
  row.querySelector(".run-settings-name-input").classList.remove("hidden");
  container.appendChild(row);
  row.querySelector(".run-settings-name-input").focus();
}

function _collectRunSettings() {
  const env = {};
  document.querySelectorAll("#run-settings-fields .run-settings-row").forEach(row => {
    const nameEl = row.querySelector("[data-role='name']");
    const valEl = row.querySelector("[data-role='value']");
    const name = (nameEl?.value || nameEl?.dataset.varName || "").trim();
    const val = valEl?.value ?? "";
    if (name) env[name] = val;
  });
  return env;
}

async function saveRunSettings() {
  const wsId = state.currentWorkspaceId;
  if (!wsId) return;
  const env = _collectRunSettings();
  try {
    const payload = await request(`/api/workspaces/${wsId}/run/settings`, {
      method: "PATCH",
      body: JSON.stringify({ env }),
    });
    state.runSettings = payload.settings || {};
    closeRunSettingsPanel();
    showToast("Run settings saved.");
  } catch (e) {
    showToast(e.message);
  }
}

// ----------------------------------------------------------------
// RUN PROJECT
// ----------------------------------------------------------------
const runState = {
  phase: "idle",
  status: null,   // null | "running" | "stopped" | "ok" | "failed"
  workspaceId: null,
  minimized: false,
  reader: null,
  completedPrereqs: new Set(),  // commands that finished with exit 0
  isPrereqRun: false,           // true while a prereq (not main) command is running
};

function runIsActiveForWorkspace(workspaceId = state.currentWorkspaceId) {
  return Boolean(
    workspaceId &&
    runState.workspaceId === workspaceId &&
    runState.status === "running" &&
    !runState.isPrereqRun
  );
}

async function syncRunStatus(workspaceId = state.currentWorkspaceId) {
  if (!workspaceId) {
    if (!runState.reader && runState.status === "running") {
      runState.status = null;
      runState.workspaceId = null;
    }
    renderRunButton();
    return;
  }

  try {
    const payload = await request(`/api/workspaces/${workspaceId}/run/status`);
    if (!isCurrentWorkspaceId(workspaceId)) {
      return;
    }
    if (payload.active) {
      runState.workspaceId = workspaceId;
      if (!runState.reader) {
        runState.status = "running";
      }
    } else if (runState.workspaceId === workspaceId && !runState.reader && runState.status === "running") {
      runState.status = null;
      runState.workspaceId = null;
    }
  } catch (_) {
    // Ignore status-sync failures and keep local state.
  }

  renderRunButton();
}

function openRunDialog() {
  const runDialog = document.getElementById("run-dialog");
  if (runState.phase === "output") {
    runState.minimized = false;
    runDialog.showModal();
    _trapFocusCleanup.run = trapFocus(runDialog);
    updateRunPill();
    return;
  }
  runState.minimized = false;
  runState.status = null;

  // If we already have a detected command, show ready (or start immediately if no prereqs)
  if (state.runConfig?.command) {
    renderRunReady(state.runConfig);
    runDialog.showModal();
    _trapFocusCleanup.run = trapFocus(runDialog);
    if (!state.runConfig.prereqs?.length) {
      startRun();
    } else {
      setRunPhase("ready");
    }
    return;
  }

  // Fall back to detect-then-show flow
  setRunPhase("detecting");
  runDialog.showModal();
  _trapFocusCleanup.run = trapFocus(runDialog);
  detectRunConfig();
}

function closeRunDialog() {
  _trapFocusCleanup.run?.(); delete _trapFocusCleanup.run;
  document.getElementById("run-dialog").close();
  runState.minimized = false;
  if (!runIsActiveForWorkspace()) {
    runState.status = null;
    runState.workspaceId = null;
  }
  runState.completedPrereqs.clear();
  runState.isPrereqRun = false;
  setRunPhase("idle");
  if (runState.reader) {
    try { runState.reader.cancel(); } catch (_) {}
    runState.reader = null;
  }
  updateRunPill();
  renderRunButton();
}

function minimizeRunDialog() {
  document.getElementById("run-dialog").close();
  runState.minimized = true;
  updateRunPill();
  renderRunButton();
}

function setRunPhase(phase) {
  runState.phase = phase;
  const titles = { detecting: "Analyzing Project", ready: "Run Project", output: "Running" };
  document.getElementById("run-dialog-title").textContent = titles[phase] || "Run Project";
  for (const p of ["detecting", "ready", "output"]) {
    const el = document.getElementById(`run-phase-${p}`);
    if (el) el.classList.toggle("hidden", p !== phase);
  }
  const minimizeBtn = document.getElementById("run-minimize-button");
  if (minimizeBtn) minimizeBtn.classList.toggle("hidden", phase !== "output");
}

function updateRunPill() {
  const pill = document.getElementById("run-pill");
  if (!pill) return;
  const { phase, status, minimized } = runState;
  const visible = phase === "output" && status !== null && (minimized || status !== "running");
  pill.classList.toggle("hidden", !visible);
  if (!visible) return;
  pill.dataset.status = status;
  const labelEl = document.getElementById("run-pill-label");
  if (labelEl) {
    labelEl.textContent = { running: "Running", stopped: "Stopped", ok: "Done", failed: "Failed" }[status] || "Running";
  }
  document.getElementById("run-pill-dismiss")?.classList.toggle("hidden", status === "running");
}

async function detectRunConfig() {
  if (_inflight.runDetect) return;
  _inflight.runDetect = true;
  const wsId = state.currentWorkspaceId;
  if (!wsId) {
    renderRunReady({ command: "", env_required: [], detected_from: "" });
    setRunPhase("ready");
    _inflight.runDetect = false;
    return;
  }
  try {
    const resp = await fetch(`/api/workspaces/${wsId}/run/config`);
    const data = resp.ok ? await resp.json() : {};
    renderRunReady(data);
  } catch (_) {
    renderRunReady({ command: "", env_required: [], detected_from: "" });
  } finally {
    _inflight.runDetect = false;
  }
  setRunPhase("ready");
}

function renderRunReady(config) {
  document.getElementById("run-command-input").value = config.command || "";
  const fromEl = document.getElementById("run-detected-from");
  fromEl.textContent = config.detected_from ? `Detected from ${config.detected_from}` : "";

  const envSection = document.getElementById("run-env-section");
  const envFields = document.getElementById("run-env-fields");
  envFields.innerHTML = "";
  const required = Array.isArray(config.env_required) ? config.env_required : [];
  if (required.length > 0) {
    envSection.classList.remove("hidden");
    for (const envVar of required) {
      const field = document.createElement("div");
      field.className = "run-env-field";
      field.innerHTML =
        `<span class="run-env-field-label">${envVar.name}</span>` +
        (envVar.description ? `<span class="run-env-field-desc">${envVar.description}</span>` : "") +
        `<input class="run-env-input" data-env-name="${envVar.name}" type="text" autocomplete="off" placeholder="Value">`;
      envFields.appendChild(field);
    }
  } else {
    envSection.classList.add("hidden");
  }

  // Prereqs
  const prereqs = Array.isArray(config.prereqs) ? config.prereqs : [];
  const prereqSection = document.getElementById("run-prereqs-section");
  const prereqList = document.getElementById("run-prereqs-list");
  prereqList.innerHTML = "";

  if (prereqs.length > 0) {
    prereqSection.classList.remove("hidden");
    for (const prereq of prereqs) {
      const done = runState.completedPrereqs.has(prereq.command);
      const item = document.createElement("div");
      item.className = `run-prereq-item${done ? " done" : ""}`;
      item.innerHTML =
        `<div class="run-prereq-info">` +
          `<span class="run-prereq-label">${prereq.label}</span>` +
          `<code class="run-prereq-cmd">${prereq.command}</code>` +
          (prereq.reason && !done ? `<span class="run-prereq-reason">${prereq.reason}</span>` : "") +
        `</div>` +
        (done
          ? `<span class="run-prereq-status-done">Done ✓</span>`
          : `<button class="run-prereq-run-btn" data-command="${prereq.command}">Run</button>`);
      prereqList.appendChild(item);
    }
    prereqList.querySelectorAll(".run-prereq-run-btn").forEach(btn => {
      btn.addEventListener("click", () => startRunSingle(btn.dataset.command));
    });
  } else {
    prereqSection.classList.add("hidden");
  }
}

function _collectRunEnv() {
  const env = {};
  document.querySelectorAll("#run-env-fields .run-env-input").forEach(input => {
    const name = input.dataset.envName;
    const value = input.value.trim();
    if (name && value) env[name] = value;
  });
  return env;
}

function _prepareRunOutput(title = "Running") {
  document.getElementById("run-terminal").textContent = "";
  const exitStatus = document.getElementById("run-exit-status");
  exitStatus.textContent = "";
  exitStatus.className = "run-exit-status hidden";
  document.getElementById("run-done-button").classList.add("hidden");
  document.getElementById("run-dialog-title").textContent = title;
  setRunPhase("output");
  runState.status = "running";
  updateRunPill();
  renderRunButton();
}

// Stream a single command; returns its exit code. Does NOT call finishRun.
async function _streamRunCommand(command, env) {
  const wsId = state.currentWorkspaceId;
  const resp = await fetch(`/api/workspaces/${wsId}/run/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, env }),
  });
  if (!resp.ok || !resp.body) {
    appendRunOutput(`Error: failed to start (${resp.status})\n`);
    return 1;
  }
  const reader = resp.body.getReader();
  runState.reader = reader;
  const decoder = new TextDecoder();
  let buffer = "";
  let exitCode = 1;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const evt = JSON.parse(line);
        if (evt.type === "started") appendRunOutput(`Process started (PID: ${evt.pid})\n`);
        else if (evt.type === "output") appendRunOutput(evt.text);
        else if (evt.type === "done") exitCode = evt.exit_code ?? 0;
        else if (evt.type === "error") { appendRunOutput(`Error: ${evt.message}\n`); exitCode = 1; }
      } catch (_) {}
    }
  }
  if (buffer.trim()) {
    try {
      const evt = JSON.parse(buffer);
      if (evt.type === "done") exitCode = evt.exit_code ?? 0;
      else if (evt.type === "error") { appendRunOutput(`Error: ${evt.message}\n`); exitCode = 1; }
    } catch (_) {}
  }
  runState.reader = null;
  return exitCode;
}

// Run a single command (main run, no prereqs)
async function startRun() {
  const wsId = state.currentWorkspaceId;
  if (!wsId) return;
  const command = document.getElementById("run-command-input").value.trim();
  if (!command) { showToast("Enter a command to run."); return; }
  const env = _collectRunEnv();
  runState.workspaceId = wsId;
  _prepareRunOutput();
  try {
    const exitCode = await _streamRunCommand(command, env);
    if (runState.status !== "stopped") finishRun(exitCode);
  } catch (e) {
    if (runState.status !== "stopped") { appendRunOutput(`Error: ${e.message}\n`); finishRun(1); }
  }
}

// Run a single prereq command; on completion, return to the ready phase
async function startRunSingle(command) {
  const wsId = state.currentWorkspaceId;
  if (!wsId) return;
  const env = _collectRunEnv();
  runState.workspaceId = wsId;
  runState.isPrereqRun = true;
  _prepareRunOutput("Setting Up");
  try {
    const exitCode = await _streamRunCommand(command, env);
    if (runState.status !== "stopped" && exitCode === 0) {
      runState.completedPrereqs.add(command);
    }
  } catch (e) {
    if (runState.status !== "stopped") appendRunOutput(`Error: ${e.message}\n`);
  } finally {
    runState.isPrereqRun = false;
    runState.status = null;
    runState.workspaceId = null;
    renderRunReady(state.runConfig || {});
    setRunPhase("ready");
    updateRunPill();
    renderRunButton();
  }
}


function appendRunOutput(text) {
  const terminal = document.getElementById("run-terminal");
  if (!terminal) return;
  terminal.appendChild(document.createTextNode(text));
  scheduleRunScroll();
}

function finishRun(exitCode) {
  runState.status = exitCode === 0 ? "ok" : "failed";
  runState.workspaceId = null;
  document.getElementById("run-done-button").classList.remove("hidden");
  document.getElementById("run-dialog-title").textContent = exitCode === 0 ? "Completed" : "Failed";
  const statusEl = document.getElementById("run-exit-status");
  statusEl.textContent = exitCode === 0 ? "Process exited successfully." : `Process exited with code ${exitCode}.`;
  statusEl.className = `run-exit-status ${exitCode === 0 ? "exit-ok" : "exit-err"}`;
  updateRunPill();
  renderRunButton();
}

async function stopRun() {
  const wsId = state.currentWorkspaceId;
  if (!wsId) return;
  runState.status = "stopped";
  runState.workspaceId = null;
  try { await fetch(`/api/workspaces/${wsId}/run/stop`, { method: "POST" }); } catch (_) {}
  if (runState.reader) {
    try { runState.reader.cancel(); } catch (_) {}
  }
  // If we were running a prereq, startRunSingle's finally block handles the UI reset
  if (runState.isPrereqRun) return;
  document.getElementById("run-done-button")?.classList.remove("hidden");
  document.getElementById("run-dialog-title").textContent = "Stopped";
  const statusEl = document.getElementById("run-exit-status");
  if (statusEl) {
    statusEl.textContent = "Process was stopped.";
    statusEl.className = "run-exit-status exit-stopped";
  }
  updateRunPill();
  renderRunButton();
}

/**
 * Trap Tab/Shift-Tab focus inside a dialog element.
 * Returns a cleanup function that removes the listener.
 */
function trapFocus(dialogEl) {
  const FOCUSABLE = [
    'button:not([disabled])',
    '[href]',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(', ');

  function getFocusable() {
    return Array.from(dialogEl.querySelectorAll(FOCUSABLE)).filter((el) => !el.closest('[hidden]'));
  }

  function handleKeydown(e) {
    if (e.key !== 'Tab') return;
    const focusable = getFocusable();
    if (!focusable.length) { e.preventDefault(); return; }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey) {
      if (document.activeElement === first || !dialogEl.contains(document.activeElement)) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last || !dialogEl.contains(document.activeElement)) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  dialogEl.addEventListener('keydown', handleKeydown);
  // Auto-focus first focusable element
  requestAnimationFrame(() => {
    const first = getFocusable()[0];
    if (first && document.activeElement !== first) first.focus();
  });
  return () => dialogEl.removeEventListener('keydown', handleKeydown);
}

function bindEvents() {
  applyTheme(state.theme);
  applyFontSize(state.fontSize);

  // Toast container: dismiss + copy
  document.getElementById("toast-container").addEventListener("click", (e) => {
    const dismissBtn = e.target.closest(".toast-dismiss-btn");
    if (dismissBtn) { dismissToast(Number(dismissBtn.dataset.toastId)); return; }
    const copyBtn = e.target.closest(".toast-copy-btn");
    if (copyBtn) {
      navigator.clipboard.writeText(copyBtn.dataset.toastCopy).catch(() => {});
      copyBtn.textContent = "Copied!";
      setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
    }
  });
  document.getElementById("global-settings-button").addEventListener("click", () => {
    activateView(state.view === "settings-view" ? "chat-view" : "settings-view");
  });
  document.querySelectorAll("[data-app-update-button]").forEach((button) => {
    button.addEventListener("click", (event) => {
      installAvailableAppUpdate(event.currentTarget).catch((error) => showToast(error.message));
    });
  });
  document.getElementById("settings-close-button").addEventListener("click", () => activateView("chat-view"));
  document.getElementById("settings-retry-last-turn")?.addEventListener("click", () => {
    retryLastTurn().catch((error) => showToast(error.message));
  });
  document.getElementById("settings-restart-selector")?.addEventListener("click", () => {
    restartSelectorRuntime().catch((error) => showToast(error.message));
  });
  document.getElementById("settings-install-local-preprocess-model")?.addEventListener("click", () => {
    installSelectedLocalPreprocessModel().catch((error) => showToast(error.message));
  });
  document.getElementById("local-model-install-dialog-close")?.addEventListener("click", closeLocalModelInstallDialog);
  document.getElementById("local-model-install-dialog-cancel")?.addEventListener("click", closeLocalModelInstallDialog);
  document.getElementById("local-model-install-dialog-install")?.addEventListener("click", (event) => {
    const modelId = event.currentTarget.dataset.modelId;
    if (modelId) installAndActivateLocalModel(modelId).catch((error) => showToast(error.message));
  });
  document.getElementById("local-model-install-dialog-activate")?.addEventListener("click", (event) => {
    const modelId = event.currentTarget.dataset.modelId;
    if (modelId) activateLocalModel(modelId).catch((error) => showToast(error.message));
  });
  document.getElementById("local-model-install-dialog")?.addEventListener("cancel", closeLocalModelInstallDialog);
  document.getElementById("onboarding-overlay")?.addEventListener("click", async (event) => {
    const chip = event.target.closest(".onboarding-chip[data-code]");
    if (chip) {
      state.onboarding.language = chip.dataset.code || currentHumanLanguage();
      renderOnboarding();
      return;
    }
    const localModelCard = event.target.closest("[data-onboarding-local-model-id]");
    if (localModelCard) {
      state.localPreprocessDraftModelId = localModelCard.dataset.onboardingLocalModelId || "";
      renderOnboarding();
      return;
    }
    const localModelAction = event.target.closest("[data-onboarding-local-model-action]");
    if (localModelAction) {
      try {
        await handleOnboardingLocalModelAction(localModelAction);
      } catch (error) {
        showToast(error.message);
      }
      return;
    }
    const runtimeAction = event.target.closest("[data-onboarding-runtime-action]");
    if (runtimeAction) {
      try {
        await handleOnboardingRuntimeAction(runtimeAction);
      } catch (error) {
        showToast(error.message);
      }
      return;
    }
  });
  document.getElementById("onboarding-back")?.addEventListener("click", () => {
    state.onboarding.step = Math.max(0, state.onboarding.step - 1);
    renderOnboarding();
  });
  document.getElementById("onboarding-close-button")?.addEventListener("click", () => {
    requestWindowClose();
  });
  document.getElementById("onboarding-next")?.addEventListener("click", async () => {
    if (state.onboarding.step === 0) {
      try {
        await updateAppSettings(
          { human_language: state.onboarding.language || currentHumanLanguage() },
          { showSuccessToast: false },
        );
        state.onboarding.step = 1;
        renderOnboarding();
      } catch (error) {
        showToast(error.message);
      }
      return;
    }
    if (state.onboarding.step >= 4) {
      closeOnboarding();
      return;
    }
    state.onboarding.step += 1;
    renderOnboarding();
  });
  document.getElementById("settings-open-telemetry")?.addEventListener("click", () => {
    openTelemetryLog().catch((error) => showToast(error.message));
  });
  document.getElementById("settings-refresh-telemetry")?.addEventListener("click", (event) => {
    const button = event.currentTarget;
    setButtonPending(button, true, "Refreshing...");
    loadTelemetry(true)
      .catch((error) => showToast(error.message))
      .finally(() => setButtonPending(button, false));
  });
  document.getElementById("project-add-button").addEventListener("click", (event) => {
    const menu = document.getElementById("project-add-menu");
    if (!menu.classList.contains("hidden")) {
      closeProjectAddMenu();
      return;
    }

    openProjectAddMenu(event.currentTarget);
  });
  document.getElementById("workspace-tabs").addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-workspace-tab-add]");
    if (addButton) {
      createWorkspaceTab().catch((error) => showToast(error.message));
      return;
    }
    const closeButton = event.target.closest("[data-workspace-tab-close]");
    if (closeButton) {
      archiveWorkspaceTab(Number(closeButton.dataset.workspaceTabClose)).catch((error) => showToast(error.message));
      return;
    }
    const tabButton = event.target.closest("[data-workspace-tab]");
    if (tabButton) {
      selectWorkspace(state.currentWorkspaceId, Number(tabButton.dataset.workspaceTab))
        .then(() => activateView("chat-view"))
        .catch((error) => showToast(error.message));
    }
  });
  document.getElementById("tab-history-button").addEventListener("click", () => {
    if (!currentWorkspace()?.tab_history?.length) {
      return;
    }
    openTabHistoryDialog();
  });
  document.getElementById("tab-history-close").addEventListener("click", closeTabHistoryDialog);
  document.getElementById("tab-history-cancel").addEventListener("click", closeTabHistoryDialog);
  document.getElementById("tab-history-list").addEventListener("click", (event) => {
    const restoreButton = event.target.closest("[data-tab-history-restore]");
    if (!restoreButton) {
      return;
    }
    restoreWorkspaceTab(Number(restoreButton.dataset.tabHistoryRestore))
      .then(() => closeTabHistoryDialog())
      .catch((error) => showToast(error.message));
  });
  document.getElementById("git-refresh-button").addEventListener("click", async () => {
    if (_inflight.gitRefresh) return;
    _inflight.gitRefresh = true;
    const button = document.getElementById("git-refresh-button");
    setButtonPending(button, true);
    try {
      await loadGitStatus();
    } catch (error) {
      showToast(error.message);
    } finally {
      setButtonPending(button, false);
      _inflight.gitRefresh = false;
    }
  });
  document.getElementById("git-menu-button").addEventListener("click", (event) => {
    const menu = document.getElementById("git-menu");
    if (!currentWorkspace() || !state.git || !state.git.is_repo) {
      return;
    }

    if (!menu.classList.contains("hidden")) {
      closeGitMenu();
      return;
    }

    openGitMenu(event.currentTarget);
  });
  document.querySelectorAll(".settings-tab").forEach((node) => {
    node.addEventListener("click", () => activateSettingsTab(node.dataset.settingsTarget));
    node.addEventListener("keydown", (event) => {
      const keys = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "Enter", " "];
      if (!keys.includes(event.key)) {
        return;
      }

      const tabs = Array.from(document.querySelectorAll(".settings-tab"));
      const currentIndex = tabs.indexOf(node);
      if (currentIndex === -1) {
        return;
      }

      let nextIndex = currentIndex;
      if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
        nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
      } else if (event.key === "ArrowDown" || event.key === "ArrowRight") {
        nextIndex = (currentIndex + 1) % tabs.length;
      } else if (event.key === "Home") {
        nextIndex = 0;
      } else if (event.key === "End") {
        nextIndex = tabs.length - 1;
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activateSettingsTab(node.dataset.settingsTarget);
        return;
      }

      event.preventDefault();
      const nextTab = tabs[nextIndex];
      nextTab.focus();
      activateSettingsTab(nextTab.dataset.settingsTarget);
    });
  });

  document.querySelectorAll(".theme-option").forEach((node) => {
    node.addEventListener("click", () => applyTheme(node.dataset.themeOption));
  });
  document.getElementById("theme-toggle-button")?.addEventListener("click", () => {
    applyTheme(LIGHT_THEMES.has(state.theme) ? "dark" : "light");
  });
  document.getElementById("font-size-slider").addEventListener("input", (event) => {
    const sizeMap = {
      "0": "extra-small",
      "1": "small",
      "2": "medium",
      "3": "large"
    };
    applyFontSize(sizeMap[event.target.value] || "medium");
  });
  document.getElementById("font-size-slider").addEventListener("change", () => {
    updateAppSettings({ font_size: state.fontSize }).catch((error) => showToast(error.message));
  });
  const humanLanguageSelect = document.getElementById("settings-human-language");
  if (humanLanguageSelect) {
    humanLanguageSelect.addEventListener("change", (event) => {
      updateAppSettings({ human_language: event.target.value }).catch((error) => showToast(error.message));
    });
  }
  const autoModelBudgetSelect = document.getElementById("settings-auto-model-budget");
  if (autoModelBudgetSelect) {
    autoModelBudgetSelect.addEventListener("change", (event) => {
      updateAppSettings({ max_cost_tier: event.target.value }).catch((error) => showToast(error.message));
    });
  }
  const autoModelPreferenceSelect = document.getElementById("settings-auto-model-preference");
  if (autoModelPreferenceSelect) {
    autoModelPreferenceSelect.addEventListener("change", (event) => {
      updateAppSettings({ auto_model_preference: event.target.value }).catch((error) => showToast(error.message));
    });
  }
  const performanceProfileSelect = document.getElementById("settings-performance-profile");
  if (performanceProfileSelect) {
    performanceProfileSelect.addEventListener("change", (event) => {
      updateAppSettings({ performance_profile: event.target.value }).catch((error) => showToast(error.message));
    });
  }
  const taskBreakdownToggle = document.getElementById("settings-enable-task-breakdown");
  if (taskBreakdownToggle) {
    taskBreakdownToggle.addEventListener("change", (event) => {
      updateAppSettings({ enable_task_breakdown: event.target.checked }).catch((error) => showToast(error.message));
    });
  }
  const followUpToggle = document.getElementById("settings-enable-follow-up-suggestions");
  if (followUpToggle) {
    followUpToggle.addEventListener("change", (event) => {
      updateAppSettings({ enable_follow_up_suggestions: event.target.checked }).catch((error) => showToast(error.message));
    });
  }
  const localPreprocessModelSelect = document.getElementById("settings-local-preprocess-model");
  if (localPreprocessModelSelect) {
    localPreprocessModelSelect.addEventListener("change", (event) => {
      const nextModel = event.target.value || null;
      if (!nextModel) {
        state.localPreprocessDraftModelId = "";
        updateAppSettings({ local_preprocess_model: null }).catch((error) => showToast(error.message));
        return;
      }
      state.localPreprocessDraftModelId = nextModel;
      renderAppSettings();
    });
  }
  document.getElementById("model-picker-button").addEventListener("click", () => {
    toggleModelPicker();
  });
  document.getElementById("model-picker-menu").addEventListener("click", (event) => {
    const option = event.target.closest("[data-model-id]");
    if (!option) {
      return;
    }

    selectModel(option.dataset.modelId);
    closeModelPicker();
  });
  // Mode picker — custom button+menu matching the model picker UX
  document.getElementById("mode-picker-button")?.addEventListener("click", () => {
    toggleModePicker();
  });
  document.getElementById("mode-picker-menu")?.addEventListener("click", (event) => {
    const option = event.target.closest("[data-mode-id]");
    if (!option) {
      return;
    }
    state.selectedAgentMode = option.dataset.modeId || defaultAgentMode();
    closeModePicker();
    renderAgentModePicker();
  });
  document.querySelectorAll(".runtime-install-button").forEach((node) => {
    node.addEventListener("click", async () => {
      setButtonPending(node, true, "Starting...");
      try {
        await installRuntime(node.dataset.runtime);
      } catch (error) {
        showToast(error.message);
        setButtonPending(node, false);
      }
    });
  });
  document.getElementById("attach-button").addEventListener("click", () => {
    document.getElementById("chat-attachment-input").click();
  });
  document.getElementById("chat-stop-button")?.addEventListener("click", () => {
    stopChatTurn().catch((error) => showToast(error.message));
  });
  document.getElementById("chat-attachment-input").addEventListener("change", async (event) => {
    try {
      await addAttachments(event.target.files);
    } catch (error) {
      showToast(error.message);
    } finally {
      event.target.value = "";
    }
  });

  document.querySelectorAll(".auth-open-button").forEach((node) => {
    node.addEventListener("click", () => openAuthDialog(node.dataset.provider));
  });

  document.querySelectorAll(".runtime-login-button").forEach((node) => {
    node.addEventListener("click", async () => {
      setButtonPending(node, true, "Starting...");
      try {
        await loginRuntime(node.dataset.runtime);
        openAccountDialog(node.dataset.runtime);
      } catch (error) {
        showToast(error.message);
        setButtonPending(node, false);
      }
    });
  });
  document.querySelectorAll(".runtime-logout-button").forEach((node) => {
    node.addEventListener("click", async () => {
      setButtonPending(node, true, "Logging Out...");
      try {
        await logoutRuntime(node.dataset.runtime);
        await loadVerifiedModels();
      } catch (error) {
        showToast(error.message);
        setButtonPending(node, false);
      }
    });
  });

  document.getElementById("chat-form").addEventListener("submit", async (event) => {
    try {
      await sendChat(event);
    } catch (error) {
      showToast(error.message);
    }
  });

  const authDialogForm = document.getElementById("auth-dialog-form");
  if (authDialogForm) {
    authDialogForm.addEventListener("submit", async (event) => {
      try {
        await saveProviderKey(event);
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  const accountDialogForm = document.getElementById("account-dialog-form");
  if (accountDialogForm) {
    accountDialogForm.addEventListener("submit", async (event) => {
      try {
        await saveProviderAccount(event);
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  document.getElementById("auth-dialog-close")?.addEventListener("click", closeAuthDialog);
  document.getElementById("auth-dialog-cancel")?.addEventListener("click", closeAuthDialog);
  document.getElementById("account-dialog-close")?.addEventListener("click", closeAccountDialog);
  document.getElementById("account-dialog-cancel")?.addEventListener("click", closeAccountDialog);
  document.getElementById("rename-dialog-form").addEventListener("submit", async (event) => {
    try {
      await renameWorkspace(event);
    } catch (error) {
      showToast(error.message);
    }
  });
  document.getElementById("project-trust-form").addEventListener("submit", async (event) => {
    try {
      await confirmProjectTrust(event);
    } catch (error) {
      showToast(error.message);
    }
  });
  document.getElementById("create-project-form").addEventListener("submit", async (event) => {
    try {
      await createProject(event);
    } catch (error) {
      showToast(error.message);
    }
  });
  document.getElementById("rename-dialog-close").addEventListener("click", closeRenameDialog);
  document.getElementById("rename-dialog-cancel").addEventListener("click", closeRenameDialog);
  document.getElementById("project-trust-close").addEventListener("click", closeProjectTrustDialog);
  document.getElementById("project-trust-cancel").addEventListener("click", closeProjectTrustDialog);
  document.getElementById("create-project-close").addEventListener("click", closeCreateProjectDialog);
  document.getElementById("create-project-cancel").addEventListener("click", closeCreateProjectDialog);
  document.getElementById("chat-input").addEventListener("input", (event) => {
    persistComposerDraftText(event.target.value || "");
    updateSlashCommandMenu();
  });

  document.getElementById("chat-input").addEventListener("keydown", async (event) => {
    // Escape cancels the current chat turn
    if (event.key === "Escape" && isCurrentWorkspaceBusy()) {
      event.preventDefault();
      stopChatTurn().catch((error) => showToast(error.message));
      return;
    }

    if (state.slashCommands.open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      const itemCount = state.slashCommands.items.length;
      state.slashCommands.activeIndex = (state.slashCommands.activeIndex + delta + itemCount) % itemCount;
      renderSlashCommandMenu();
      return;
    }

    if (state.slashCommands.open && (event.key === "Enter" || event.key === "Tab")) {
      event.preventDefault();
      applySlashCommand();
      return;
    }

    if (state.slashCommands.open && event.key === "Escape") {
      event.preventDefault();
      closeSlashCommandMenu();
      return;
    }

    // Shift+Enter inserts a newline — let browser handle it
    if (event.shiftKey && event.key === "Enter") return;

    // Cmd+Enter (Mac) or Ctrl+Enter (Win/Linux) sends regardless of settings
    // Plain Enter also sends (existing behaviour)
    const isSend = event.key === "Enter" && (event.metaKey || event.ctrlKey || (!event.shiftKey));
    if (!isSend) return;

    event.preventDefault();
    try {
      await sendChat(event);
    } catch (error) {
      showToast(error.message);
    }
  });

  document.addEventListener("click", (event) => {
    const workspaceMenu = document.getElementById("workspace-menu");
    const generatedFilesMenu = document.getElementById("generated-files-menu");
    const projectAddMenu = document.getElementById("project-add-menu");
    const gitMenu = document.getElementById("git-menu");

    if (!workspaceMenu.contains(event.target) && !event.target.closest(".workspace-row")) {
      closeWorkspaceMenu();
    }

    if (!generatedFilesMenu.contains(event.target) && !event.target.closest(".workspace-generated-button")) {
      closeGeneratedFilesMenu();
    }

    const slashCommandMenu = document.getElementById("slash-command-menu");
    if (
      slashCommandMenu
      && !slashCommandMenu.contains(event.target)
      && !event.target.closest("#chat-input")
    ) {
      closeSlashCommandMenu();
    }

    if (!projectAddMenu.contains(event.target) && !event.target.closest("#project-add-button")) {
      closeProjectAddMenu();
    }

    if (!gitMenu.contains(event.target) && !event.target.closest("#git-menu-button")) {
      closeGitMenu();
    }

    const runSettingsPanel = document.getElementById("run-settings-panel");
    if (!runSettingsPanel.contains(event.target) && !event.target.closest("#run-settings-button")) {
      closeRunSettingsPanel();
    }

    if (!event.target.closest("#model-picker")) {
      closeModelPicker();
    }

    if (!event.target.closest("#mode-picker")) {
      closeModePicker();
    }
  });

  document.getElementById("workspace-menu").addEventListener("click", async (event) => {
    const action = event.target.dataset.action;
    if (!action || !state.menuWorkspaceId) {
      return;
    }

    if (action === "rename") {
      const workspaceId = state.menuWorkspaceId;
      closeWorkspaceMenu();
      openRenameDialog(workspaceId);
      return;
    }

    if (action === "reset-session") {
      try {
        await resetWorkspaceSession(state.menuWorkspaceId);
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    if (action === "delete") {
      try {
        await deleteWorkspace(state.menuWorkspaceId);
      } catch (error) {
        showToast(error.message);
      }
    }
  });

  document.getElementById("project-add-menu").addEventListener("click", async (event) => {
    const action = event.target.dataset.projectAddAction;
    if (!action) {
      return;
    }

    closeProjectAddMenu();
    try {
      if (action === "import") {
        await chooseProjectFolder();
        return;
      }
      if (action === "create") {
        await chooseCreateProjectLocation();
      }
    } catch (error) {
      showToast(error.message);
    }
  });

  document.getElementById("git-panel").addEventListener("click", async (event) => {
    const actionTarget = event.target.closest("[data-git-action]");
    const action = actionTarget?.dataset.gitAction;
    if (!action) {
      if (event.target.id !== "git-commit-button") {
        return;
      }
      try {
        await commitGitChanges();
      } catch (error) {
        showToast(error.message);
      }
      return;
    }

    try {
      if (action === "stage" || action === "unstage") {
        if (!state.selectedGitPaths.length) {
          showToast("Select at least one file.");
          return;
        }
        await runGitAction(action, { paths: state.selectedGitPaths });
        return;
      }

      await runGitAction(action);
    } catch (error) {
      showToast(error.message);
    }
  });

  document.getElementById("git-panel").addEventListener("change", (event) => {
    const path = event.target.dataset.gitPath;
    if (!path) {
      return;
    }

    toggleGitPathSelection(path, event.target.checked);
  });

  document.getElementById("attachment-list").addEventListener("click", (event) => {
    const index = Number(event.target.dataset.attachmentIndex);
    if (Number.isNaN(index)) {
      return;
    }

    state.attachments = state.attachments.filter((_, itemIndex) => itemIndex !== index);
    renderAttachmentList();
  });

  document.getElementById("messages").addEventListener("click", (event) => {
    if (event.target.id === "load-older-messages") {
      loadOlderMessages().catch((error) => showToast(error.message));
      return;
    }

    // Retry button on failed turns
    const retryBtn = event.target.closest(".message-retry-btn");
    if (retryBtn) {
      const text = retryBtn.dataset.retryText || "";
      const attachments = (() => { try { return JSON.parse(retryBtn.dataset.retryAttachments || "[]"); } catch { return []; } })();
      retryBtn.closest(".message")?.remove();
      submitChatTurn(text, attachments, false).catch((e) => showToast(e.message));
      return;
    }

    const recommendationButton = event.target.closest(".message-recommendation-button, .message-quick-reply-btn");
    if (recommendationButton) {
      if (recommendationButton.dataset.recommendationOther != null) {
        // "Other…" — just focus the composer so the user can type freely
        const input = document.getElementById("chat-input");
        input?.focus();
      } else {
        sendRecommendedPrompt(recommendationButton.dataset.recommendation || "").catch((error) => showToast(error.message));
      }
      return;
    }

    const artifactTab = event.target.closest("[data-artifact-key]");
    if (artifactTab) {
      const section = artifactTab.closest(".message-artifact-section");
      if (!section) {
        return;
      }
      appendMessageArtifactPanel(
        section,
        section._artifacts || [],
        String(artifactTab.dataset.artifactKey || ""),
      );
      return;
    }

    const changeTab = event.target.closest("[data-change-tab-index]");
    if (changeTab) {
      const section = changeTab.closest(".message-change-section");
      const diff = section?.querySelector(".message-diff");
      const toggleButton = section?.querySelector(".message-change-toggle");
      if (!section || !diff) {
        return;
      }

      const activeIndex = Number(changeTab.dataset.changeTabIndex || 0);
      appendChangeDiff(section, section._changeLog || [], activeIndex);
      if (diff.classList.contains("hidden")) {
        diff.classList.remove("hidden");
        if (toggleButton) {
          toggleButton.setAttribute("aria-expanded", "true");
          const label = toggleButton.querySelector(".message-toggle-label");
          if (label) {
            label.textContent = localizeRuntimeLine("Hide Diff");
          }
          const caret = toggleButton.querySelector(".message-toggle-caret");
          if (caret) {
            caret.textContent = "▴";
          }
        }
      }
      return;
    }

    const toggle = event.target.closest(".message-toggle");
    const changeToggle = event.target.closest(".message-change-toggle");
    if (changeToggle) {
      const section = changeToggle.closest(".message-change-section");
      const diff = section?.querySelector(".message-diff");
      if (!section || !diff) {
        return;
      }

      const expanded = changeToggle.getAttribute("aria-expanded") === "true";
      changeToggle.setAttribute("aria-expanded", expanded ? "false" : "true");
      const label = changeToggle.querySelector(".message-toggle-label");
      if (label) {
        label.textContent = localizeRuntimeLine(expanded ? "Show Diff" : "Hide Diff");
      }
      const caret = changeToggle.querySelector(".message-toggle-caret");
      if (caret) {
        caret.textContent = expanded ? "▾" : "▴";
      }
      if (!expanded) {
        appendChangeDiff(
          section,
          section._changeLog || [],
          Number(section.dataset.activeChangeIndex || 0),
        );
      }
      diff.classList.toggle("hidden", expanded);
      return;
    }
    if (!toggle) {
      return;
    }

    const message = toggle.closest(".message");
    const details = message?.querySelector(".message-details");
    if (!details) {
      return;
    }

    const expanded = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", expanded ? "false" : "true");
    const caret = toggle.querySelector(".message-toggle-caret");
    if (caret) {
      caret.textContent = expanded ? "▾" : "▴";
    }
    if (!expanded && details.dataset.loaded !== "true") {
      appendMessageDetails(
        message,
        message?._detailActivityLog || [],
        message?._detailHistoryLog || [],
        message?._detailTerminalLog || "",
      );
      message._detailActivityLog = null;
      message._detailHistoryLog = null;
      message._detailTerminalLog = null;
    }
    details.classList.toggle("hidden", expanded);
  });

  document.getElementById("messages").addEventListener("pointerdown", (event) => {
    const container = document.getElementById("messages");
    if (!container) {
      return;
    }
    clearNestedScrollActivation(container);
    const panel = closestNestedScrollPanel(event.target);
    if (panel) {
      panel.classList.add("scroll-active");
    }
  });

  document.getElementById("messages").addEventListener("wheel", (event) => {
    if (event.ctrlKey || event.metaKey) {
      return;
    }
    if (event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
      return;
    }

    const panel = closestNestedScrollPanel(event.target);
    const container = document.getElementById("messages");
    if (!panel || !container) {
      return;
    }

    if (!panel.classList.contains("scroll-active")) {
      event.preventDefault();
      container.scrollTop += event.deltaY;
      return;
    }

    const atTop = panel.scrollTop <= 0;
    const atBottom = panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 1;
    if ((event.deltaY < 0 && atTop) || (event.deltaY > 0 && atBottom)) {
      event.preventDefault();
      container.scrollTop += event.deltaY;
    }
  }, { passive: false });

  document.getElementById("git-menu").addEventListener("click", async (event) => {
    const action = event.target.dataset.gitMenuAction;
    if (!action) {
      return;
    }

    try {
      await runGitAction(action);
    } catch (error) {
      showToast(error.message);
    }
  });

  document.getElementById("generated-files-menu").addEventListener("click", (event) => {
    const openButton = event.target.closest("[data-generated-file-open]");
    if (!openButton) {
      return;
    }
    openGeneratedFile(state.generatedFilesMenuWorkspaceId, openButton.dataset.generatedFileOpen)
      .catch((error) => showToast(error.message));
  });

  document.getElementById("git-collapse-button").addEventListener("click", () => {
    const section = document.querySelector(".git-section");
    setGitCollapsed(!section || !section.classList.contains("collapsed"));
  });

  document.getElementById("review-open-button").addEventListener("click", () => {
    openReviewView().catch((error) => showToast(error.message));
  });

  document.getElementById("review-open-chat-button").addEventListener("click", () => {
    runCodeReview();
  });

  document.getElementById("full-review-cancel").addEventListener("click", () => {
    closeFullReviewModal();
  });

  document.getElementById("full-review-confirm").addEventListener("click", () => {
    runFullCodebaseReview().catch((err) => showToast(err.message));
  });

  document.getElementById("full-review-modal").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeFullReviewModal();
  });

  document.getElementById("full-review-modal").addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeFullReviewModal();
  });

  document.getElementById("review-view-body").addEventListener("click", async (event) => {
    // Main tab switching (New Review / Results / History)
    const tabTarget = event.target.closest("[data-review-tab]");
    if (tabTarget) {
      state.reviewTab = tabTarget.dataset.reviewTab;
      if (state.reviewTab === "history") {
        const ws = reviewWorkspace();
        if (ws && !state.savedReviews.length) loadReviewHistory(ws.id);
      }
      renderReviewView();
      return;
    }

    // File source tab switching (Changed / Recent / All Files)
    const fileTabTarget = event.target.closest("[data-review-filetab]");
    if (fileTabTarget) {
      const newTab = fileTabTarget.dataset.reviewFiletab;
      state.reviewFileTab = newTab;
      if (newTab === "all" && !state.reviewAllFiles.length && !state.reviewAllFilesLoading) {
        loadAllReviewFiles();
        return; // loadAllReviewFiles calls renderReviewView
      }
      renderReviewView();
      return;
    }

    const depthTarget = event.target.closest("[data-review-depth]");
    if (depthTarget) {
      state.review.depth = depthTarget.dataset.reviewDepth || "standard";
      renderReviewView();
      return;
    }

    const action = event.target.closest("[data-review-action]")?.dataset.reviewAction;
    if (!action) {
      return;
    }

    if (action === "load-all-files") {
      loadAllReviewFiles();
      return;
    }
    if (action === "select-view") {
      const paths = getReviewFilesForTab().map((f) => f.path);
      setReviewSelection([...new Set([...state.selectedReviewPaths, ...paths])]);
      return;
    }
    if (action === "download-report") {
      const ws = reviewWorkspace();
      await generateReviewReport(state.reviewRun, ws?.name || "project");
      return;
    }
    if (action === "download-saved-current") {
      const saved = state.reviewViewingSaved;
      if (saved) {
        const ws = reviewWorkspace();
        const fakeRr = {
          findings: (saved.findings || []).map((f, i) => ({ ...f, _id: `sv-${saved.id}-${i}` })),
          dismissedIds: [],
          summaryPrimary: saved.summary_primary || "",
          summarySecondary: saved.summary_secondary || "",
          primaryModelLabel: saved.primary_model_label || "",
          secondaryModelLabel: saved.secondary_model_label || "",
          primaryModel: saved.primary_model || "",
          depth: saved.depth || "standard",
        };
        await generateReviewReport(fakeRr, ws?.name || "project");
      }
      return;
    }
    if (action === "download-saved") {
      const reviewId = Number(event.target.closest("[data-review-id]")?.dataset.reviewId);
      const review = state.savedReviews.find(r => r.id === reviewId);
      if (review) {
        const ws = reviewWorkspace();
        const fakeRr = {
          findings: (review.findings || []).map((f, i) => ({ ...f, _id: `s-${i}` })),
          dismissedIds: [],
          summaryPrimary: review.summary_primary || "",
          summarySecondary: review.summary_secondary || "",
          primaryModelLabel: review.primary_model_label || "",
          secondaryModelLabel: review.secondary_model_label || "",
          primaryModel: review.primary_model || "",
          depth: review.depth || "standard",
        };
        await generateReviewReport(fakeRr, ws?.name || "project");
      }
      return;
    }
    if (action === "view-saved") {
      const reviewId = Number(event.target.closest("[data-review-id]")?.dataset.reviewId);
      const review = state.savedReviews.find(r => r.id === reviewId);
      if (review) {
        state.reviewViewingSaved = review;
        state.reviewTab = "results";
        renderReviewView();
      }
      return;
    }
    if (action === "close-saved-view") {
      state.reviewViewingSaved = null;
      state.reviewTab = "history";
      renderReviewView();
      return;
    }
    if (action === "select-changed") {
      setReviewSelection((state.reviewData?.changed_files || []).map((entry) => entry.path));
      return;
    }
    if (action === "select-recent") {
      setReviewSelection((state.reviewData?.recent_files || []).map((entry) => entry.path));
      return;
    }
    if (action === "clear-selection") {
      setReviewSelection([]);
      return;
    }
    if (action === "run") {
      runCodeReview();
      return;
    }
    if (action === "full-codebase") {
      openFullReviewModal().catch((err) => showToast(err.message));
      return;
    }
    if (action === "implement-finding") {
      const id = event.target.closest("[data-finding-id]")?.dataset.findingId;
      if (id) implementFinding(id);
      return;
    }
    if (action === "dismiss-finding") {
      const id = event.target.closest("[data-finding-id]")?.dataset.findingId;
      if (id) dismissFinding(id);
      return;
    }
    if (action === "refresh") {
      loadReviewData(true, true).catch((error) => showToast(error.message));
    }
  });

  document.getElementById("review-view-body").addEventListener("change", (event) => {
    const modelRole = event.target.dataset.reviewModel;
    if (modelRole === "primary") {
      state.reviewRun.primaryModel = event.target.value;
      return;
    }
    if (modelRole === "secondary") {
      state.reviewRun.secondaryModel = event.target.value;
      return;
    }
    const depthBtn = event.target.dataset.reviewDepth;
    if (depthBtn) {
      state.review.depth = depthBtn;
      renderReviewView();
      return;
    }
    const path = event.target.dataset.reviewPath;
    if (!path) return;
    toggleReviewPathSelection(path, event.target.checked);
  });

  document.getElementById("review-view-body").addEventListener("input", (event) => {
    if (!event.target.dataset.reviewSearch) return;
    state.reviewSearch = event.target.value;
    // Auto-load all files if searching while on the "all" tab and not yet loaded
    if (state.reviewFileTab === "all" && !state.reviewAllFiles.length && !state.reviewAllFilesLoading && event.target.value) {
      loadAllReviewFiles();
      return;
    }
    renderReviewView();
  });

  document.getElementById("run-button").addEventListener("click", () => {
    const btn = document.getElementById("run-button");
    if (btn?.dataset.mode === "stop") stopRun(); else openRunDialog();
  });
  document.getElementById("run-settings-button").addEventListener("click", (e) => {
    e.stopPropagation();
    if (_runSettingsOpen) closeRunSettingsPanel(); else openRunSettingsPanel();
  });
  document.getElementById("run-settings-close").addEventListener("click", closeRunSettingsPanel);
  document.getElementById("run-settings-cancel").addEventListener("click", closeRunSettingsPanel);
  document.getElementById("run-settings-save").addEventListener("click", saveRunSettings);
  document.getElementById("run-settings-add").addEventListener("click", _addRunSettingsRow);
  document.getElementById("run-minimize-button").addEventListener("click", minimizeRunDialog);
  document.getElementById("run-dialog-close").addEventListener("click", () => {
    if (runIsActiveForWorkspace()) minimizeRunDialog(); else closeRunDialog();
  });
  document.getElementById("run-cancel-button").addEventListener("click", closeRunDialog);
  document.getElementById("run-start-button").addEventListener("click", startRun);
  document.getElementById("run-done-button").addEventListener("click", closeRunDialog);
  document.getElementById("run-dialog").addEventListener("click", (e) => {
    if (e.target === document.getElementById("run-dialog")) {
      if (runIsActiveForWorkspace()) minimizeRunDialog(); else closeRunDialog();
    }
  });
  document.getElementById("run-pill-open").addEventListener("click", openRunDialog);
  document.getElementById("run-pill-dismiss").addEventListener("click", () => {
    runState.status = null;
    runState.workspaceId = null;
    runState.minimized = false;
    setRunPhase("idle");
    updateRunPill();
  });
}

async function bootstrap() {
  bindEvents();
  ensureDesktopBridge();
  initWindowChrome();
  activateSettingsTab("settings-appearance");
  renderComposerState();
  renderRunButton();
  setGitCollapsed(true);
  localStorage.removeItem("bettercode-git-collapsed");

  try {
    const savedWorkspaceId = Number(localStorage.getItem("bettercode-workspace-id")) || null;
    await Promise.all([loadAppInfo(), loadWorkspaces(savedWorkspaceId)]);
    // App updates are temporarily disabled for this release.
    // loadUpdateInfo().catch(() => {});
    for (const runtimeName of ["codex", "cursor", "claude", "gemini"]) {
      const jobId = state.appInfo?.runtimes?.[runtimeName]?.job?.id;
      if (jobId) {
        pollRuntimeJob(jobId);
      }
    }
  } catch (error) {
    document.getElementById("messages").innerHTML = `
      <div class="empty-state">
        <h3>${escapeHtml(t("startup.failed"))}</h3>
        <p>${error.message}</p>
      </div>
    `;
    showToast(error.message);
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible" || state.liveChats.size === 0) {
    return;
  }
  renderMessages(state.messages, currentWorkspace(), state.messagePaging);
});

window.addEventListener("focus", () => {
  if (state.liveChats.size === 0) {
    return;
  }
  renderMessages(state.messages, currentWorkspace(), state.messagePaging);
});

bootstrap();
