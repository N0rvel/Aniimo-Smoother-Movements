"""Small bilingual offline interface; no persistence outside the chosen game."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from installer import VERSION, check, install, restore
from platform_windows import discover_games

TEXT = {
 "en": {
    "intro": "Remove the brief slowdown when changing movement direction.",
    "folder": "Aniimo game folder", "browse": "Browse...", "check": "Check compatibility",
    "install": "Install fix", "restore": "Remove movement fix",
    "ready": "Select Aniimo, then check compatibility.",
    "working": "Working... keep Aniimo and its repair tool closed.",
    "scope": "Uses the game's steering-deceleration command for the controlled character.",
    "warning": "Supported resource build: 3551601. Unknown scripts are refused.",
    "confirm": "Close Aniimo first. Install the movement fix with verified backups?",
    "confirm_restore": "Close Aniimo first. Restore the resources saved before this movement mod?",
    "compatible": "The audited movement script was found. Ready to install.",
    "already_equal": "The movement hooks are already present.",
    "installed": "Fix installed and file integrity verified. Restart Aniimo to apply it.",
    "restored": "Movement fix removed; the saved resources were restored exactly.",
    "recovery_required": "An incomplete installation needs restoration before reinstalling.",
    "game_updated_or_modified": "The resources have changed. Restore later-installed mods first; do not overwrite a game update.",
    "error": "Operation stopped", "busy": "Wait for the current operation.",
    "notes": "Install after the camera fix. Uninstall mods in reverse order. Unknown scripts are refused.",
    "build": "Resource build(s): ", "missing": "No game folder selected.",
 },
 "fr": {
    "intro": "Supprime le freinage lors des changements de direction.",
    "folder": "Dossier du jeu Aniimo", "browse": "Parcourir…", "check": "Vérifier la compatibilité",
    "install": "Installer le correctif", "restore": "Retirer ce correctif",
    "ready": "Sélectionne Aniimo, puis vérifie la compatibilité.",
    "working": "Opération en cours… garde Aniimo et son outil de réparation fermés.",
    "scope": "Utilise la commande de freinage en virage du jeu pour le personnage contrôlé.",
    "warning": "Build de ressources supporté : 3551601. Les scripts inconnus sont refusés.",
    "confirm": "Ferme Aniimo. Installer le correctif avec des sauvegardes vérifiées ?",
    "confirm_restore": "Ferme Aniimo. Restaurer les ressources sauvegardées avant ce mod de déplacement ?",
    "compatible": "Le script de déplacement étudié est présent. Le correctif est prêt à installer.",
    "already_equal": "Les modifications de déplacement sont déjà présentes.",
    "installed": "Correctif installé et intégrité des fichiers vérifiée. Relance Aniimo pour l’appliquer.",
    "restored": "Correctif retiré et ressources précédentes restaurées à l'identique.",
    "recovery_required": "Installation incomplète : restaurer avant de réinstaller.",
    "game_updated_or_modified": "Les ressources ont changé. Retire d'abord les mods installés ensuite ; ne remplace pas une mise à jour par une ancienne sauvegarde.",
    "error": "Opération arrêtée", "busy": "Attends la fin de l'opération.",
    "notes": "Installer après le mod caméra. Désinstaller dans l'ordre inverse. Un script inconnu est refusé.",
    "build": "Version(s) de ressources : ", "missing": "Aucun dossier sélectionné.",
 }
}


def launch(initial=None):
    app = tk.Tk()
    app.title("Aniimo Smooth Movement — " + VERSION)
    app.geometry("780x515")
    app.minsize(700, 470)
    app.option_add("*Font", "{Segoe UI} 10")
    style = ttk.Style(app)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    frame = ttk.Frame(app, padding=24)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(6, weight=1)
    top = ttk.Frame(frame)
    top.grid(row=0, column=0, columnspan=2, sticky="ew")
    ttk.Label(top, text="Aniimo Smooth Movement", font=("Segoe UI", 20, "bold")).pack(side="left")
    lang = tk.StringVar(value="English")
    language = ttk.Combobox(top, values=("English", "Français"), textvariable=lang, state="readonly", width=10)
    language.pack(side="right")
    intro = ttk.Label(frame, wraplength=710)
    intro.grid(row=1, column=0, columnspan=2, sticky="w", pady=(12,20))
    label = ttk.Label(frame)
    label.grid(row=2, column=0, sticky="w", pady=(0,5))
    found = discover_games()
    path = tk.StringVar(value=str(initial or (found[0] if len(found) == 1 else "")))
    entry = ttk.Combobox(frame, textvariable=path, values=tuple(map(str, found)))
    entry.grid(row=3, column=0, sticky="ew", padx=(0,8))
    browse = ttk.Button(frame)
    browse.grid(row=3, column=1)
    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=2, sticky="w", pady=18)
    actions = {key: ttk.Button(buttons) for key in ("check", "install", "restore")}
    for button in actions.values():
        button.pack(side="left", padx=(0,10))
    status = tk.StringVar()
    status_label = ttk.Label(frame, textvariable=status, wraplength=705, justify="left")
    status_label.grid(row=5, column=0, columnspan=2, sticky="nw", pady=(0,14))
    notes = ttk.Label(frame, wraplength=705, justify="left")
    notes.grid(row=7, column=0, columnspan=2, sticky="sw", pady=(0,12))
    warning = ttk.Label(frame, wraplength=705, foreground="#7b4d13")
    warning.grid(row=8, column=0, columnspan=2, sticky="sw")
    state = {"busy": False, "result": None}
    messages = queue.Queue()

    def words():
        return TEXT["fr" if lang.get() == "Français" else "en"]

    def display_result(result):
        t = words()
        text = t.get(result.get("state"), str(result))
        builds = sorted({str(d.get("build")) for d in result.get("resources", [])})
        if builds:
            text += "\n\n" + t["build"] + ", ".join(builds)
        status.set(text)

    def translate(*_):
        t = words()
        intro.configure(text=t["intro"])
        label.configure(text=t["folder"])
        browse.configure(text=t["browse"])
        for key, button in actions.items():
            button.configure(text=t[key])
        notes.configure(text=t["scope"]+"\n"+t["notes"])
        warning.configure(text=t["warning"])
        if state["busy"]:
            status.set(t["working"])
        elif state["result"]:
            display_result(state["result"])
        else:
            status.set(t["ready"])

    def select():
        chosen = filedialog.askdirectory(parent=app, title=words()["folder"], initialdir=path.get() or None)
        if chosen:
            path.set(chosen)
            state["result"] = None
            status.set(words()["ready"])

    def action(which):
        if state["busy"]:
            return
        t = words()
        target = path.get().strip().strip('"')
        if not target:
            messagebox.showerror(t["error"], t["missing"], parent=app)
            return
        if which != "check" and not messagebox.askyesno(
                "Aniimo Smooth Movement", t["confirm" if which == "install" else "confirm_restore"], parent=app):
            return
        state["busy"] = True
        status.set(t["working"])
        for widget in (*actions.values(), browse, entry):
            widget.configure(state="disabled")
        def work():
            try:
                result = {"check": check, "install": install, "restore": restore}[which](Path(target))
                messages.put((True, result))
            except Exception as exc:
                messages.put((False, str(exc)))
        threading.Thread(target=work, daemon=False).start()

    def poll():
        try:
            ok, result = messages.get_nowait()
        except queue.Empty:
            pass
        else:
            state["busy"] = False
            for widget in (*actions.values(), browse, entry):
                widget.configure(state="normal")
            if ok:
                state["result"] = result
                display_result(result)
            else:
                state["result"] = None
                status.set(words()["error"]+":\n"+result)
                messagebox.showerror(words()["error"], result, parent=app)
        app.after(150, poll)

    def close():
        if state["busy"]:
            messagebox.showinfo("Aniimo Smooth Movement", words()["busy"], parent=app)
        else:
            app.destroy()

    browse.configure(command=select)
    for key, button in actions.items():
        button.configure(command=lambda k=key: action(k))
    language.bind("<<ComboboxSelected>>", translate)
    app.protocol("WM_DELETE_WINDOW", close)
    translate()
    poll()
    app.mainloop()
