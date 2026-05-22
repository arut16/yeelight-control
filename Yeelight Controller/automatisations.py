#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import json
import os
import sys
import pygame # Pour le son
import copy

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, 'Config')
SOUNDS_DIR = os.path.join(BASE_DIR, 'sounds')
LAMP_IPS_FILE = os.path.join(CONFIG_DIR, 'lamp_ips.json')
AUTOMATIONS_FILE = os.path.join(CONFIG_DIR, 'automations.json')
CLICK_SOUND_PATH = os.path.join(SOUNDS_DIR, "click.wav")
BG_COLOR = "#323232"
BTN_COLOR = "#404040"
TEXT_COLOR = "white"
ACCENT_COLOR = "gold"
SCREEN_W = 640
SCREEN_H = 480

class AutomationApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Automatisations")
        self.geometry(f"{SCREEN_W}x{SCREEN_H}+0+0")
        self.configure(bg=BG_COLOR, cursor="none") # CURSEUR CACHÉ
        self.overrideredirect(True) 
        self.attributes("-topmost", True)
        
        # --- INIT SON ---
        try:
            pygame.mixer.init()
            self.click_sound = pygame.mixer.Sound(CLICK_SOUND_PATH)
            self.click_sound.set_volume(0.9)
        except Exception as e:
            print(f"Erreur son: {e}")
            self.click_sound = None

        # --- ECOUTE GLOBALE ---
        self.bind_all("<Button-1>", self.play_sound_event)
        self.bind_all("<<ComboboxSelected>>", self.play_sound_event)
        
        # Styles
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", 
                        background=BTN_COLOR, 
                        foreground=TEXT_COLOR, 
                        fieldbackground=BTN_COLOR, 
                        font=("Arial", 11), 
                        rowheight=35)
        style.configure("Treeview.Heading", 
                        background="#202020", 
                        foreground=TEXT_COLOR, 
                        font=("Arial", 12, "bold"))
        style.map("Treeview", background=[('selected', 'gold')], foreground=[('selected', 'black')])

        self.lamps = self.load_lamps()
        self.rules = self.load_rules()
        self.selected_rule_index = None
        
        # Temp vars
        self.temp_condition_start = None 
        self.temp_condition_end = None   
        self.temp_condition_text_start = "Non défini"
        self.temp_condition_text_end = "Non défini"

        # ==========================================
        # INTERFACE
        # ==========================================

        # HEADER
        header_frame = tk.Frame(self, bg=BG_COLOR, height=60)
        header_frame.pack(side=tk.TOP, fill="x", padx=15, pady=15)
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="Mes Automatisations", bg=BG_COLOR, fg=ACCENT_COLOR, font=("Arial", 20, "bold")).pack(side="left")

        self.btns_right = tk.Frame(header_frame, bg=BG_COLOR)
        self.btns_right.pack(side="right")

        # Edit
        self.btn_edit = tk.Canvas(self.btns_right, width=90, height=40, bg=BG_COLOR, highlightthickness=0)
        self.btn_edit.create_line(20, 20, 70, 20, fill="#606060", width=36, capstyle=tk.ROUND)
        self.btn_edit.create_text(45, 20, text="Éditer", fill="white", font=("Arial", 11, "bold"))
        self.btn_edit.bind("<Button-1>", self.edit_selected_rule)

        # Duplicate (x2)
        self.btn_dup = tk.Canvas(self.btns_right, width=46, height=46, bg=BG_COLOR, highlightthickness=0)
        self.btn_dup.create_oval(3, 3, 43, 43, fill="#606060", outline="")
        self.btn_dup.create_text(23, 23, text="x2", fill="white", font=("Arial", 16, "bold"))
        self.btn_dup.bind("<Button-1>", self.duplicate_selected_rule)

        # Add (+)
        self.btn_add = tk.Canvas(self.btns_right, width=46, height=46, bg=BG_COLOR, highlightthickness=0)
        self.btn_add.pack(side="left", padx=5)
        self.btn_add.create_oval(3, 3, 43, 43, fill="#606060", outline="")
        self.btn_add.create_text(23, 23, text="+", fill="white", font=("Arial", 26, "bold"))
        self.btn_add.bind("<Button-1>", lambda e: self.open_add_modal())

        # Close (X)
        self.btn_close = tk.Canvas(self.btns_right, width=46, height=46, bg=BG_COLOR, highlightthickness=0)
        self.btn_close.pack(side="left", padx=5)
        self.btn_close.create_oval(3, 3, 43, 43, fill="#D32F2F", outline="")
        self.btn_close.create_line(15, 15, 31, 31, fill="white", width=3)
        self.btn_close.create_line(31, 15, 15, 31, fill="white", width=3)
        self.btn_close.bind("<Button-1>", lambda e: self.quit_app())

        # DELETE BTN
        self.btn_delete = tk.Button(self, text="Supprimer la règle sélectionnée", bg="#F44336", fg="white", 
                  font=("Arial", 13, "bold"), borderwidth=0, padx=20, pady=12,
                  command=self.delete_rule)
        self.btn_delete.pack(side=tk.BOTTOM, pady=20)

        # LIST
        tree_frame = tk.Frame(self, bg=BG_COLOR)
        tree_frame.pack(side=tk.TOP, fill="both", expand=True, padx=15, pady=5)
        
        columns = ("desc", "cond")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.tree.heading("desc", text="Règle")
        self.tree.heading("cond", text="Condition")
        
        self.tree.column("desc", width=300)
        self.tree.column("cond", width=200)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.refresh_list()

    def play_sound_event(self, event):
        if self.click_sound: self.click_sound.play()

    def quit_app(self):
        self.destroy()

    def load_lamps(self):
        try:
            with open(LAMP_IPS_FILE, 'r') as f: return json.load(f)
        except: return {}

    def load_rules(self):
        try:
            if os.path.exists(AUTOMATIONS_FILE):
                with open(AUTOMATIONS_FILE, 'r') as f: return json.load(f)
        except: pass
        return []

    def save_rules(self):
        try:
            with open(AUTOMATIONS_FILE, 'w') as f: json.dump(self.rules, f, indent=4)
        except Exception as e: self.show_custom_alert("Erreur", f"Sauvegarde impossible: {e}")

    # --- ALERTES MAISON (Pour éviter le freeze) ---
    def show_custom_alert(self, title, message):
        """Affiche une popup qui ne freeze pas l'interface"""
        popup = tk.Toplevel(self)
        popup.geometry(f"400x200+{SCREEN_W//2 - 200}+{SCREEN_H//2 - 100}")
        popup.configure(bg="#202020", cursor="none")
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        
        # Bordure Rouge
        tk.Frame(popup, bg="#F44336", height=4).pack(fill="x")
        
        tk.Label(popup, text=title, bg="#202020", fg="white", font=("Arial", 16, "bold")).pack(pady=20)
        tk.Label(popup, text=message, bg="#202020", fg="lightgray", font=("Arial", 12), wraplength=350).pack(pady=10)
        
        tk.Button(popup, text="OK", bg="#F44336", fg="white", font=("Arial", 12, "bold"), width=15,
                  command=popup.destroy).pack(side="bottom", pady=20)
        
        # Force le focus sur cette popup
        popup.focus_force()
        popup.grab_set()
        self.wait_window(popup)

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if selected:
            self.selected_rule_index = self.tree.index(selected[0])
            self.btn_edit.pack(side="left", padx=5, before=self.btn_add)
            self.btn_dup.pack(side="left", padx=5, before=self.btn_add)
        else:
            self.selected_rule_index = None
            self.btn_edit.pack_forget()
            self.btn_dup.pack_forget()

    def edit_selected_rule(self, event):
        if self.selected_rule_index is not None:
            self.open_add_modal(edit_index=self.selected_rule_index)

    # --- DUPLICATION V12 (CORRIGÉE) ---
    def duplicate_selected_rule(self, event):
        if self.selected_rule_index is not None:
            # On récupère les données de la règle à copier
            original_rule = self.rules[self.selected_rule_index]
            # On ouvre la fenêtre d'ajout (mode CREATION) mais avec les données pré-remplies
            # On ne l'ajoute pas encore à la liste self.rules !
            self.open_add_modal(duplicate_data=copy.deepcopy(original_rule))

    def autofit_columns(self):
        font = tkfont.Font(font=("Arial", 11)) 
        max_w_desc = tkfont.Font(font=("Arial", 12, "bold")).measure("Règle") + 20
        for r in self.rules:
            text = f"SI {r['trigger']} est {r['trigger_state'].upper()} ➔ {r['target']} devient {r['action'].upper()}"
            width = font.measure(text) + 20
            if width > max_w_desc: max_w_desc = width
        max_w_cond = tkfont.Font(font=("Arial", 12, "bold")).measure("Condition") + 20
        for r in self.rules:
            text = r.get("condition", {}).get("text", "") if r.get("condition") else ""
            width = font.measure(text) + 20
            if width > max_w_cond: max_w_cond = width
        total_w = self.tree.winfo_width()
        if total_w <= 1: total_w = 600
        if max_w_desc + max_w_cond > total_w:
            ratio = max_w_desc / (max_w_desc + max_w_cond)
            self.tree.column("desc", width=int(total_w * ratio))
            self.tree.column("cond", width=int(total_w * (1 - ratio)))
        else:
            self.tree.column("desc", width=max_w_desc)
            self.tree.column("cond", width=total_w - max_w_desc)

    def reset_temp_condition(self):
        self.temp_condition_start = None
        self.temp_condition_end = None
        self.temp_condition_text_start = "Non défini"
        self.temp_condition_text_end = "Non défini"

    def open_condition_dashboard(self, parent_modal, label_to_update):
        dash = tk.Toplevel(self)
        dash.geometry(f"{SCREEN_W}x{SCREEN_H}+0+0")
        dash.configure(bg=BTN_COLOR, cursor="none")
        dash.overrideredirect(True)
        dash.attributes("-topmost", True)
        
        main_frame = tk.Frame(dash, bg=BTN_COLOR)
        main_frame.pack(expand=True, fill="both", padx=20, pady=20)

        tk.Label(main_frame, text="Définir une Condition Solaire", bg=BTN_COLOR, fg="white", font=("Arial", 18, "bold")).pack(pady=(10, 20))

        # START
        frame_start = tk.Frame(main_frame, bg="#303030", bd=2, relief="groove")
        frame_start.pack(fill="x", pady=10, padx=20)
        tk.Label(frame_start, text="1. Démarrer la condition", bg="#303030", fg=ACCENT_COLOR, font=("Arial", 14, "bold")).pack(pady=5)
        lbl_start_status = tk.Label(frame_start, text=self.temp_condition_text_start, bg="#303030", fg="lightgray", font=("Arial", 12, "italic"))
        lbl_start_status.pack(pady=5)
        frame_start_btns = tk.Frame(frame_start, bg="#303030")
        frame_start_btns.pack(pady=10)
        tk.Button(frame_start_btns, text="Lever du soleil", bg="#606060", fg="white", width=18, height=2, font=("Arial", 11),
                  command=lambda: self.open_sun_choice(dash, "start", "sunrise", lbl_start_status)).pack(side="left", padx=10)
        tk.Button(frame_start_btns, text="Coucher du soleil", bg="#606060", fg="white", width=18, height=2, font=("Arial", 11),
                  command=lambda: self.open_sun_choice(dash, "start", "sunset", lbl_start_status)).pack(side="left", padx=10)

        # END
        frame_end = tk.Frame(main_frame, bg="#303030", bd=2, relief="groove")
        frame_end.pack(fill="x", pady=10, padx=20)
        tk.Label(frame_end, text="2. Terminer la condition", bg="#303030", fg=ACCENT_COLOR, font=("Arial", 14, "bold")).pack(pady=5)
        lbl_end_status = tk.Label(frame_end, text=self.temp_condition_text_end, bg="#303030", fg="lightgray", font=("Arial", 12, "italic"))
        lbl_end_status.pack(pady=5)
        frame_end_btns = tk.Frame(frame_end, bg="#303030")
        frame_end_btns.pack(pady=10)
        tk.Button(frame_end_btns, text="Lever du soleil", bg="#606060", fg="white", width=18, height=2, font=("Arial", 11),
                  command=lambda: self.open_sun_choice(dash, "end", "sunrise", lbl_end_status)).pack(side="left", padx=10)
        tk.Button(frame_end_btns, text="Coucher du soleil", bg="#606060", fg="white", width=18, height=2, font=("Arial", 11),
                  command=lambda: self.open_sun_choice(dash, "end", "sunset", lbl_end_status)).pack(side="left", padx=10)

        btn_frame = tk.Frame(main_frame, bg=BTN_COLOR)
        btn_frame.pack(side="bottom", fill="x", pady=10)

        def validate_condition():
            if self.temp_condition_start and self.temp_condition_end:
                final_text = f"Début: {self.temp_condition_text_start}\nFin: {self.temp_condition_text_end}"
                label_to_update.config(text=final_text, fg="cyan")
                dash.destroy()
            else:
                self.show_custom_alert("Attention", "Veuillez définir le début ET la fin.")

        tk.Button(btn_frame, text="Annuler", bg="#F44336", fg="white", font=("Arial", 12), width=15, height=2,
                  command=dash.destroy).pack(side="left", padx=20)
        tk.Button(btn_frame, text="Valider", bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), width=15, height=2,
                  command=validate_condition).pack(side="right", padx=20)

    def open_sun_choice(self, parent, mode, sun_type, label_widget):
        win = tk.Toplevel(self)
        win.geometry(f"{SCREEN_W}x{SCREEN_H}+0+0")
        win.configure(bg="#505050", cursor="none")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        
        main = tk.Frame(win, bg="#505050")
        main.pack(expand=True)

        sun_label = "Lever" if sun_type == "sunrise" else "Coucher"
        tk.Label(main, text=f"Par rapport au {sun_label}...", bg="#505050", fg="white", font=("Arial", 18, "bold")).pack(pady=40)

        def set_at_time():
            self.set_condition_data(mode, f"{sun_type}_offset_0", f"Au {sun_label}")
            label_widget.config(text=f"Au {sun_label}", fg="white")
            win.destroy()

        btn_opts = {"bg": "#606060", "fg": "white", "width": 25, "height": 3, "font": ("Arial", 12)}
        
        tk.Button(main, text=f"Au {sun_label}", command=set_at_time, **btn_opts).pack(pady=10)
        tk.Button(main, text=f"Avant le {sun_label}", **btn_opts,
                  command=lambda: self.open_delay_choice(win, mode, sun_type, "before", label_widget)).pack(pady=10)
        tk.Button(main, text=f"Après le {sun_label}", **btn_opts,
                  command=lambda: self.open_delay_choice(win, mode, sun_type, "after", label_widget)).pack(pady=10)
        
        tk.Button(main, text="Retour", bg="#F44336", fg="white", width=15, font=("Arial", 12), command=win.destroy).pack(pady=30)

    def open_delay_choice(self, parent, mode, sun_type, timing, label_widget):
        win = tk.Toplevel(self)
        win.geometry(f"{SCREEN_W}x{SCREEN_H}+0+0")
        win.configure(bg="#606060", cursor="none")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        
        main = tk.Frame(win, bg="#606060")
        main.pack(expand=True)

        timing_text = "AVANT" if timing == "before" else "APRÈS"
        sun_text = "LE LEVER" if sun_type == "sunrise" else "LE COUCHER"
        tk.Label(main, text=f"Combien de temps {timing_text} {sun_text} ?", bg="#606060", fg="white", font=("Arial", 16, "bold")).pack(pady=30)

        delays = [("15 min", 15), ("30 min", 30), ("1 h", 60), ("2 h", 120)]

        for txt, val in delays:
            def save_delay(v=val, t=txt):
                offset = -v if timing == "before" else v
                s_label = "lever" if sun_type == "sunrise" else "coucher"
                t_label = "avant" if timing == "before" else "après"
                human_text = f"{t} {t_label} {s_label}"
                code = f"{sun_type}_offset_{offset}"
                self.set_condition_data(mode, code, human_text)
                label_widget.config(text=human_text, fg="white")
                win.destroy()
                parent.destroy()

            tk.Button(main, text=txt, bg="#808080", fg="white", width=20, height=2, font=("Arial", 14), command=save_delay).pack(pady=10)

        tk.Button(main, text="Annuler", bg="#F44336", fg="white", width=15, font=("Arial", 12), command=win.destroy).pack(pady=30)

    def set_condition_data(self, mode, code, text):
        if mode == "start":
            self.temp_condition_start = code
            self.temp_condition_text_start = text
        else:
            self.temp_condition_end = code
            self.temp_condition_text_end = text

    def open_add_modal(self, edit_index=None, duplicate_data=None):
        self.reset_temp_condition()
        is_edit = edit_index is not None
        
        # Données de base
        data = {}
        if is_edit:
            data = self.rules[edit_index]
        elif duplicate_data:
            data = duplicate_data # On utilise les données dupliquées mais on est en mode "CREATION" (edit_index=None)
        
        modal = tk.Toplevel(self)
        modal.geometry(f"{SCREEN_W}x{SCREEN_H}+0+0")
        modal.configure(bg="#404040", cursor="none")
        modal.overrideredirect(True)
        modal.attributes("-topmost", True)
        
        title_txt = "Modifier règle" if is_edit else ("Créer (Duplicata)" if duplicate_data else "Nouvelle règle")
        tk.Label(modal, text=title_txt, bg="#404040", fg="gold", font=("Arial", 20, "bold")).pack(pady=20)

        content = tk.Frame(modal, bg="#404040")
        content.pack(expand=True)

        # 1. Quand
        tk.Label(content, text="1. Quand...", bg="#404040", fg="white", font=("Arial", 14, "bold")).pack(anchor="w")
        f1 = tk.Frame(content, bg="#404040"); f1.pack(pady=5)
        cb_trigger = ttk.Combobox(f1, values=list(self.lamps.keys()), state="readonly", width=15, font=("Arial", 12))
        cb_trigger.pack(side="left", padx=5)
        if data: cb_trigger.set(data.get("trigger", ""))
        
        tk.Label(f1, text="passe à", bg="#404040", fg="gray", font=("Arial", 12)).pack(side="left", padx=5)
        cb_trigger_state = ttk.Combobox(f1, values=["ON", "OFF"], state="readonly", width=5, font=("Arial", 12))
        if data: cb_trigger_state.set(data.get("trigger_state", "on").upper())
        else: cb_trigger_state.current(0)
        cb_trigger_state.pack(side="left", padx=5)

        # 2. Condition
        tk.Label(content, text="⬇", bg="#404040", fg="gray", font=("Arial", 16)).pack(pady=5)
        f_cond = tk.Frame(content, bg="#303030", bd=1, relief="sunken", padx=10, pady=10)
        f_cond.pack(fill="x", pady=5)
        
        cond_text = "Aucune condition (Toujours actif)"
        if data.get("condition"):
            cond = data["condition"]
            self.temp_condition_start = cond["start"]
            self.temp_condition_end = cond["end"]
            self.temp_condition_text_start = cond["text"].split(", ")[0].replace("Début: ", "")
            self.temp_condition_text_end = cond["text"].split(", ")[1].replace("Fin: ", "")
            cond_text = cond["text"]

        lbl_cond_result = tk.Label(f_cond, text=cond_text, bg="#303030", fg="cyan" if data.get("condition") else "gray", font=("Arial", 10, "italic"), wraplength=400)
        lbl_cond_result.pack(pady=5)

        tk.Button(f_cond, text="Définir une Condition (Optionnel)", bg="#606060", fg="white", font=("Arial", 10),
                  command=lambda: self.open_condition_dashboard(modal, lbl_cond_result)).pack()

        # 3. Alors
        tk.Label(content, text="⬇", bg="#404040", fg="gray", font=("Arial", 16)).pack(pady=5)
        tk.Label(content, text="2. Alors...", bg="#404040", fg="white", font=("Arial", 14, "bold")).pack(anchor="w")
        f3 = tk.Frame(content, bg="#404040"); f3.pack(pady=5)
        cb_target = ttk.Combobox(f3, values=list(self.lamps.keys()), state="readonly", width=15, font=("Arial", 12))
        cb_target.pack(side="left", padx=5)
        if data: cb_target.set(data.get("target", ""))

        tk.Label(f3, text="devient", bg="#404040", fg="gray", font=("Arial", 12)).pack(side="left", padx=5)
        cb_action = ttk.Combobox(f3, values=["ON", "OFF"], state="readonly", width=5, font=("Arial", 12))
        if data: cb_action.set(data.get("action", "off").upper())
        else: cb_action.current(1)
        cb_action.pack(side="left", padx=5)

        f_btns = tk.Frame(modal, bg="#404040")
        f_btns.pack(side="bottom", fill="x", pady=20, padx=20)

        def validate():
            trigger = cb_trigger.get()
            target = cb_target.get()
            if not trigger or not target:
                self.show_custom_alert("Attention", "Sélectionnez les lampes."); return
            if trigger == target:
                self.show_custom_alert("Erreur", "La lampe cible doit être différente."); return
            
            new_rule = {
                "trigger": trigger,
                "trigger_state": cb_trigger_state.get().lower(),
                "target": target,
                "action": cb_action.get().lower(),
                "condition": None
            }

            if self.temp_condition_start and self.temp_condition_end:
                new_rule["condition"] = {
                    "start": self.temp_condition_start,
                    "end": self.temp_condition_end,
                    "text": lbl_cond_result.cget("text").replace("\n", ", ")
                }

            # VERIFICATION DOUBLONS
            is_duplicate = False
            for i, r in enumerate(self.rules):
                # Si on est en mode EDITION, on ignore la règle qu'on est en train de modifier elle-même
                if is_edit and i == edit_index:
                    continue
                # Si on est en mode CREATION (ou Duplicata), on vérifie tout
                if r == new_rule:
                    is_duplicate = True
                    break
            
            if is_duplicate:
                self.show_custom_alert("Erreur", "Cette règle existe déjà !")
                return

            if is_edit: self.rules[edit_index] = new_rule
            else: self.rules.append(new_rule)
                
            self.save_rules()
            self.refresh_list()
            modal.destroy()

        tk.Button(f_btns, text="Annuler", bg="#F44336", fg="white", font=("Arial", 12), width=12, height=2,
                  command=modal.destroy).pack(side="left")
        
        btn_txt = "Enregistrer" if is_edit else "Créer"
        tk.Button(f_btns, text=btn_txt, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), width=12, height=2,
                  command=validate).pack(side="right")

    def delete_rule(self):
        selected = self.tree.selection()
        if not selected: return
        for item in selected:
            idx = self.tree.index(item)
            del self.rules[idx]
        self.save_rules()
        self.refresh_list()
        self.btn_edit.pack_forget()
        self.btn_dup.pack_forget()

    def refresh_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for r in self.rules:
            text_rule = f"SI {r['trigger']} est {r['trigger_state'].upper()} ➔ {r['target']} devient {r['action'].upper()}"
            text_cond = r.get("condition", {}).get("text", "") if r.get("condition") else ""
            self.tree.insert("", "end", values=(text_rule, text_cond))
        
        self.update_idletasks()
        self.autofit_columns()

if __name__ == "__main__":
    app = AutomationApp()
    app.mainloop()