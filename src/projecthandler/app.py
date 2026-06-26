from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .models import EntityInstance, Project
from .parser import PdfProjectParser


APP_TITLE = "ProjectHandler: Gerenciador de Projetos de Rede de Distribuição"
APP_FOOTER = "Desenvolvido por: Caio Cezar Dias"


COLORS = {
    "app_bg": "#F5F7FA",
    "surface": "#FFFFFF",
    "sidebar": "#EAF0ED",
    "sidebar_line": "#D4DED9",
    "header": "#123C37",
    "header_hover": "#1E5B52",
    "header_text": "#FFFFFF",
    "accent": "#C1842C",
    "accent_dark": "#8A5A18",
    "text": "#17211F",
    "muted": "#63706B",
    "line": "#DCE5E0",
    "soft": "#F0F4F2",
    "soft_hover": "#E6EEE9",
    "chip_bg": "#F4EFE6",
    "disabled": "#AAB7B2",
}


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: object | None = None,
        *,
        width: int = 132,
        height: int = 38,
        radius: int = 10,
        bg: str = COLORS["surface"],
        fill: str = COLORS["soft"],
        hover_fill: str = COLORS["soft_hover"],
        selected_fill: str = COLORS["surface"],
        disabled_fill: str = COLORS["soft"],
        border: str = COLORS["line"],
        selected_border: str = COLORS["header"],
        text_color: str = COLORS["text"],
        selected_text_color: str = COLORS["text"],
        disabled_text_color: str = COLORS["disabled"],
        font: tuple[str, int, str] = ("Segoe UI", 10, "bold"),
        border_width: int = 1,
        selected_border_width: int = 2,
    ) -> None:
        super().__init__(parent, width=width, height=height, bg=bg, bd=0, highlightthickness=0, relief="flat")
        self.text = text
        self.command = command
        self.button_width = width
        self.button_height = height
        self.radius = radius
        self.fill = fill
        self.hover_fill = hover_fill
        self.selected_fill = selected_fill
        self.disabled_fill = disabled_fill
        self.border = border
        self.selected_border = selected_border
        self.text_color = text_color
        self.selected_text_color = selected_text_color
        self.disabled_text_color = disabled_text_color
        self.button_font = font
        self.border_width = border_width
        self.selected_border_width = selected_border_width
        self.selected = False
        self.enabled = True
        self.hovered = False
        self.configure(cursor="hand2")
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.draw()

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.draw()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self.draw()

    def set_text(self, text: str) -> None:
        self.text = text
        self.draw()

    def _on_enter(self, _event: tk.Event) -> None:
        self.hovered = True
        self.draw()

    def _on_leave(self, _event: tk.Event) -> None:
        self.hovered = False
        self.draw()

    def _on_click(self, _event: tk.Event) -> None:
        if self.enabled and callable(self.command):
            self.command()

    def draw(self) -> None:
        self.delete("all")
        fill = self.selected_fill if self.selected else self.fill
        if self.hovered and not self.selected and self.enabled:
            fill = self.hover_fill
        if not self.enabled:
            fill = self.disabled_fill
        border = self.selected_border if self.selected else self.border
        text_color = self.selected_text_color if self.selected else self.text_color
        if not self.enabled:
            text_color = self.disabled_text_color
        border_width = self.selected_border_width if self.selected else self.border_width

        self._rounded_rect(0, 0, self.button_width, self.button_height, self.radius, border)
        inset = max(border_width, 1)
        self._rounded_rect(
            inset,
            inset,
            self.button_width - inset,
            self.button_height - inset,
            max(self.radius - inset, 2),
            fill,
        )
        self.create_text(
            self.button_width / 2,
            self.button_height / 2,
            text=self.text,
            fill=text_color,
            font=self.button_font,
            width=self.button_width - 18,
            justify="center",
        )

    def _rounded_rect(self, x1: int, y1: int, x2: int, y2: int, radius: int, fill: str) -> None:
        radius = min(radius, max((x2 - x1) // 2, 1), max((y2 - y1) // 2, 1))
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        self.create_polygon(points, smooth=True, fill=fill, outline="")


class ProjectHandlerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.parser = PdfProjectParser()
        self.projects: list[Project] = []
        self.selected_project: Project | None = None
        self.active_tab = "summary"
        self.active_entity_type = ""
        self.tab_buttons: dict[str, RoundedButton] = {}
        self.entity_type_buttons: dict[str, RoundedButton] = {}
        self.tab_pages: dict[str, tk.Frame | ttk.Frame] = {}

        self.root.title(APP_TITLE)
        self.root.geometry("1220x780")
        self.root.minsize(980, 640)
        self.root.configure(bg=COLORS["app_bg"])
        self._configure_style()
        self._build_layout()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Segoe UI", 10), background=COLORS["app_bg"], foreground=COLORS["text"])
        style.configure("App.TFrame", background=COLORS["app_bg"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Header.TLabel", background=COLORS["header"], foreground=COLORS["header_text"], font=("Segoe UI", 16, "bold"), padding=(18, 16))
        style.configure("Footer.TLabel", background=COLORS["surface"], foreground=COLORS["text"], font=("Segoe UI", 9, "bold"), padding=(16, 8))
        style.configure("Sidebar.TFrame", background=COLORS["sidebar"])
        style.configure("SidebarTitle.TLabel", background=COLORS["sidebar"], foreground=COLORS["text"], font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", background=COLORS["app_bg"], foreground=COLORS["text"], font=("Segoe UI", 15, "bold"))
        style.configure("Count.TLabel", background=COLORS["app_bg"], foreground=COLORS["accent_dark"], font=("Segoe UI", 10, "bold"))

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        ttk.Label(self.root, text=APP_TITLE, style="Header.TLabel", anchor="center").grid(row=0, column=0, sticky="ew")

        body = ttk.Frame(self.root, style="App.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(body, style="Sidebar.TFrame", padding=(16, 16))
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.rowconfigure(3, weight=1)

        ttk.Label(sidebar, text="Projetos carregados", style="SidebarTitle.TLabel").grid(row=0, column=0, sticky="ew")
        ttk.Label(sidebar, text="PDFs disponíveis na sessão", style="SidebarTitle.TLabel", foreground=COLORS["muted"]).grid(row=1, column=0, sticky="ew", pady=(2, 12))
        self.load_button = RoundedButton(
            sidebar,
            "Carregar projetos",
            self.load_projects,
            width=252,
            bg=COLORS["sidebar"],
            fill=COLORS["header"],
            hover_fill=COLORS["header_hover"],
            border=COLORS["header"],
            text_color=COLORS["header_text"],
        )
        self.load_button.grid(row=2, column=0, sticky="ew", pady=(0, 14))

        list_frame = tk.Frame(sidebar, bg=COLORS["sidebar"], highlightbackground=COLORS["sidebar_line"], highlightthickness=1)
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.project_list = tk.Listbox(
            list_frame,
            width=34,
            activestyle="none",
            exportselection=False,
            bd=0,
            highlightthickness=0,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            selectbackground=COLORS["header"],
            selectforeground=COLORS["header_text"],
            font=("Segoe UI", 10),
            relief="flat",
        )
        self.project_list.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        self.project_list.bind("<<ListboxSelect>>", self._on_project_select)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.project_list.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.project_list.configure(yscrollcommand=list_scroll.set)

        self.main_area = ttk.Frame(body, style="App.TFrame", padding=22)
        self.main_area.grid(row=0, column=1, sticky="nsew")
        self.main_area.columnconfigure(0, weight=1)
        self.main_area.rowconfigure(2, weight=1)

        topbar = ttk.Frame(self.main_area, style="App.TFrame")
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.columnconfigure(0, weight=1)

        self.title_label = ttk.Label(topbar, text="Nenhum projeto carregado", style="Title.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.open_pdf_button = RoundedButton(
            topbar,
            "Abrir PDF original",
            self.open_selected_pdf,
            width=160,
            height=36,
            bg=COLORS["app_bg"],
            fill=COLORS["surface"],
            hover_fill=COLORS["soft"],
            border=COLORS["line"],
            selected_border=COLORS["line"],
            selected_fill=COLORS["surface"],
            font=("Segoe UI", 9, "bold"),
        )
        self.open_pdf_button.set_enabled(False)
        self.open_pdf_button.grid(row=0, column=1, sticky="e")

        self.count_label = ttk.Label(self.main_area, text="Carregue um PDF para visualizar as entidades encontradas.", style="Count.TLabel")
        self.count_label.grid(row=1, column=0, sticky="w", pady=(8, 16))

        self.content_area = tk.Frame(self.main_area, bg=COLORS["surface"], highlightbackground=COLORS["line"], highlightthickness=1)
        self.content_area.grid(row=2, column=0, sticky="nsew")
        self.content_area.columnconfigure(0, weight=1)
        self.content_area.rowconfigure(1, weight=1)

        self.tab_bar = tk.Frame(self.content_area, bg=COLORS["surface"])
        self.tab_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 2))
        self._build_tab_button("summary", "Resumo", 0)
        self._build_tab_button("entities", "Entidades", 1)

        self.tab_content = tk.Frame(self.content_area, bg=COLORS["surface"])
        self.tab_content.grid(row=1, column=0, sticky="nsew")
        self.tab_content.columnconfigure(0, weight=1)
        self.tab_content.rowconfigure(0, weight=1)

        self._build_summary_tab()
        self._build_entities_tab()
        self._show_tab("summary")
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

        ttk.Label(self.root, text=APP_FOOTER, style="Footer.TLabel", anchor="w").grid(row=2, column=0, sticky="ew")

    def _build_tab_button(self, tab_name: str, text: str, column: int) -> None:
        button = RoundedButton(
            self.tab_bar,
            text,
            lambda name=tab_name: self._show_tab(name),
            width=120,
            height=42,
            radius=10,
            selected_border_width=3,
            bg=COLORS["surface"],
            selected_fill=COLORS["surface"],
            selected_border=COLORS["header"],
        )
        button.grid(row=0, column=column, sticky="w", padx=(0, 10))
        self.tab_buttons[tab_name] = button

    def _show_tab(self, tab_name: str) -> None:
        self.active_tab = tab_name
        if tab_name in self.tab_pages:
            self.tab_pages[tab_name].tkraise()
        for name, button in self.tab_buttons.items():
            button.set_selected(name == tab_name)

    def _build_summary_tab(self) -> None:
        self.summary_tab = tk.Frame(self.tab_content, bg=COLORS["surface"])
        self.summary_tab.grid(row=0, column=0, sticky="nsew")
        self.summary_tab.columnconfigure(0, weight=1)
        self.summary_tab.rowconfigure(0, weight=1)
        self.tab_pages["summary"] = self.summary_tab

        self.summary_canvas = tk.Canvas(self.summary_tab, bg=COLORS["surface"], bd=0, highlightthickness=0)
        self.summary_scrollbar = ttk.Scrollbar(self.summary_tab, orient="vertical", command=self.summary_canvas.yview)
        self.summary_canvas.configure(yscrollcommand=self.summary_scrollbar.set)
        self.summary_canvas.grid(row=0, column=0, sticky="nsew")
        self.summary_scrollbar.grid(row=0, column=1, sticky="ns")

        self.summary_cards = tk.Frame(self.summary_canvas, bg=COLORS["surface"])
        self.summary_window = self.summary_canvas.create_window((0, 0), window=self.summary_cards, anchor="nw")
        self.summary_cards.bind("<Configure>", self._sync_summary_scroll_region)
        self.summary_canvas.bind("<Configure>", self._sync_summary_width)

    def _sync_summary_scroll_region(self, _event: tk.Event | None = None) -> None:
        self.summary_canvas.configure(scrollregion=self.summary_canvas.bbox("all"))

    def _sync_summary_width(self, event: tk.Event) -> None:
        self.summary_canvas.itemconfigure(self.summary_window, width=event.width)

    def _build_entities_tab(self) -> None:
        self.entities_tab = tk.Frame(self.tab_content, bg=COLORS["surface"])
        self.entities_tab.grid(row=0, column=0, sticky="nsew")
        self.entities_tab.columnconfigure(0, weight=1)
        self.entities_tab.rowconfigure(1, weight=1)
        self.tab_pages["entities"] = self.entities_tab

        self.entity_type_bar = tk.Frame(self.entities_tab, bg=COLORS["surface"])
        self.entity_type_bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))

        self.entities_canvas = tk.Canvas(self.entities_tab, bg=COLORS["surface"], bd=0, highlightthickness=0, relief="flat")
        self.entities_scrollbar = ttk.Scrollbar(self.entities_tab, orient="vertical", command=self.entities_canvas.yview)
        self.entities_canvas.configure(yscrollcommand=self.entities_scrollbar.set)
        self.entities_canvas.grid(row=1, column=0, sticky="nsew")
        self.entities_scrollbar.grid(row=1, column=1, sticky="ns")

        self.entities_cards = tk.Frame(self.entities_canvas, bg=COLORS["surface"])
        self.entities_window = self.entities_canvas.create_window((0, 0), window=self.entities_cards, anchor="nw")
        self.entities_cards.bind("<Configure>", self._sync_entities_scroll_region)
        self.entities_canvas.bind("<Configure>", self._sync_entities_width)

    def _sync_entities_scroll_region(self, _event: tk.Event | None = None) -> None:
        self.entities_canvas.configure(scrollregion=self.entities_canvas.bbox("all"))

    def _sync_entities_width(self, event: tk.Event) -> None:
        self.entities_canvas.itemconfigure(self.entities_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self.active_tab == "summary":
            self.summary_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif self.active_tab == "entities":
            self.entities_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def load_projects(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Carregar projetos de rede",
            filetypes=(("Arquivos PDF", "*.pdf"), ("Todos os arquivos", "*.*")),
        )
        if not paths:
            return

        failures: list[str] = []
        for raw_path in paths:
            path = Path(raw_path)
            try:
                project = self.parser.parse_file(path)
            except Exception as exc:  # pragma: no cover - UI safeguard
                failures.append(f"{path.name}: {exc}")
                continue
            self.projects.append(project)

        self._refresh_project_list()
        if self.projects:
            self.project_list.selection_clear(0, tk.END)
            self.project_list.selection_set(len(self.projects) - 1)
            self.project_list.see(len(self.projects) - 1)
            self._select_project(len(self.projects) - 1)

        if failures:
            messagebox.showwarning("Falha ao carregar", "\n".join(failures))

    def _refresh_project_list(self) -> None:
        self.project_list.delete(0, tk.END)
        for project in self.projects:
            self.project_list.insert(tk.END, project.display_name)

    def _on_project_select(self, _event: tk.Event) -> None:
        selection = self.project_list.curselection()
        if not selection:
            return
        self._select_project(selection[0])

    def _select_project(self, index: int) -> None:
        self.selected_project = self.projects[index]
        self._render_project(self.selected_project)

    def _render_project(self, project: Project) -> None:
        self.title_label.configure(text=project.display_name)
        self.open_pdf_button.set_enabled(project.source_path is not None)
        total_entities = sum(max(entity.quantity, 1) for entity in project.entities)
        self.count_label.configure(text=f"{total_entities} entidades encontradas")
        self._render_summary(project)
        self._render_entities(project)

    def _render_summary(self, project: Project) -> None:
        for child in self.summary_cards.winfo_children():
            child.destroy()

        ordered_keys = [
            "ns",
            "cidade",
            "bairro",
            "cliente",
            "telefone",
            "servico",
            "data",
            "circuito",
            "dispositivo",
            "levantamento",
            "projeto",
            "aprovacao",
            "impacto_ambiental",
            "escala",
            "formato",
            "folha",
        ]

        self._build_section_title(self.summary_cards, "Informações do Projeto", 0)
        field_index = 0
        for key in ordered_keys:
            value = project.metadata.get(key)
            if not value:
                continue
            row = 1 + field_index // 2
            col = field_index % 2
            card = self._build_summary_card(self.summary_cards, self._labelize(key), value)
            card.grid(row=row, column=col, sticky="ew", padx=(18, 9 if col == 0 else 18), pady=(0, 12))
            field_index += 1

        if field_index == 0:
            empty = self._build_summary_card(self.summary_cards, "Metadados", "Nenhum campo do quadro do projeto foi encontrado.")
            empty.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 12))

        totals_row = 2 + max((field_index - 1) // 2, 0)
        self._build_section_title(self.summary_cards, "Entidades Encontradas", totals_row)
        counts = sorted(project.entity_counts().items())
        if counts:
            for index, (display_type, count) in enumerate(counts):
                row = totals_row + 1 + index // 2
                col = index % 2
                card = self._build_summary_card(self.summary_cards, display_type, f"{count} instâncias")
                card.grid(row=row, column=col, sticky="ew", padx=(18, 9 if col == 0 else 18), pady=(0, 12))
        else:
            empty = self._build_summary_card(self.summary_cards, "Entidades", "Nenhuma entidade compatível com o vocabulário atual.")
            empty.grid(row=totals_row + 1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 12))

        self.summary_cards.columnconfigure(0, weight=1)
        self.summary_cards.columnconfigure(1, weight=1)
        self._sync_summary_scroll_region()
        self.summary_canvas.yview_moveto(0)

    def _build_section_title(self, parent: tk.Frame, text: str, row: int) -> None:
        label = tk.Label(parent, text=text, bg=COLORS["surface"], fg=COLORS["text"], font=("Segoe UI", 13, "bold"), anchor="w")
        label.grid(row=row, column=0, columnspan=2, sticky="ew", padx=18, pady=(18 if row else 14, 10))

    def _build_summary_card(self, parent: tk.Frame, label: str, value: object) -> tk.Frame:
        card = tk.Frame(parent, bg=COLORS["surface"], highlightbackground=COLORS["line"], highlightthickness=1)
        card.columnconfigure(0, weight=1)
        tk.Label(card, text=label, bg=COLORS["surface"], fg=COLORS["muted"], font=("Segoe UI", 8, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))
        tk.Label(card, text=str(value), bg=COLORS["surface"], fg=COLORS["text"], font=("Segoe UI", 10), anchor="w", justify="left", wraplength=380).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 11))
        return card

    def _render_entities(self, project: Project) -> None:
        for child in self.entity_type_bar.winfo_children():
            child.destroy()
        self.entity_type_buttons.clear()

        grouped = project.grouped_entities()
        if not grouped:
            self.active_entity_type = ""
            self._clear_entity_cards()
            self._build_empty_entities_state()
            return

        preferred = self.active_entity_type if self.active_entity_type in grouped else sorted(grouped)[0]
        for index, (display_type, entities) in enumerate(sorted(grouped.items())):
            count = sum(max(entity.quantity, 1) for entity in entities)
            width = min(max(142, len(display_type) * 7 + 46), 230)
            button = RoundedButton(
                self.entity_type_bar,
                f"{display_type} ({count})",
                lambda entity_type=display_type: self._show_entity_type(entity_type),
                width=width,
                height=38,
                radius=9,
                bg=COLORS["surface"],
                selected_border=COLORS["accent_dark"],
                selected_border_width=2,
                selected_fill=COLORS["chip_bg"],
                font=("Segoe UI", 9, "bold"),
            )
            button.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 8), pady=(0, 8))
            self.entity_type_buttons[display_type] = button

        self._show_entity_type(preferred)

    def _show_entity_type(self, display_type: str) -> None:
        if not self.selected_project:
            return
        grouped = self.selected_project.grouped_entities()
        self.active_entity_type = display_type
        for name, button in self.entity_type_buttons.items():
            button.set_selected(name == display_type)

        self._clear_entity_cards()
        entities = grouped.get(display_type, [])
        if not entities:
            self._build_empty_entities_state()
            return

        title = tk.Label(
            self.entities_cards,
            text=f"{display_type} - {sum(max(entity.quantity, 1) for entity in entities)} instâncias",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="ew", padx=18, pady=(10, 10))

        for index, entity in enumerate(entities, start=1):
            card = self._build_entity_card(self.entities_cards, entity)
            card.grid(row=index, column=0, sticky="ew", padx=18, pady=(0, 12))

        self.entities_cards.columnconfigure(0, weight=1)
        self._sync_entities_scroll_region()
        self.entities_canvas.yview_moveto(0)

    def _clear_entity_cards(self) -> None:
        for child in self.entities_cards.winfo_children():
            child.destroy()

    def _build_empty_entities_state(self) -> None:
        empty = tk.Frame(self.entities_cards, bg=COLORS["surface"])
        empty.grid(row=0, column=0, sticky="nsew", padx=22, pady=22)
        tk.Label(empty, text="Nenhuma entidade encontrada", bg=COLORS["surface"], fg=COLORS["text"], font=("Segoe UI", 13, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(
            empty,
            text="O PDF foi carregado, mas o texto extraído não contém entidades compatíveis com o vocabulário atual.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
            anchor="w",
            wraplength=760,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self._sync_entities_scroll_region()
        self.entities_canvas.yview_moveto(0)

    def _build_entity_card(self, parent: tk.Frame, entity: EntityInstance) -> tk.Frame:
        card = tk.Frame(parent, bg=COLORS["surface"], highlightbackground=COLORS["line"], highlightthickness=1)
        card.columnconfigure(0, weight=1)

        header = tk.Frame(card, bg=COLORS["surface"])
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        header.columnconfigure(1, weight=1)

        badge = tk.Label(header, text=entity.display_type, bg=COLORS["chip_bg"], fg=COLORS["accent_dark"], font=("Segoe UI", 9, "bold"), padx=8, pady=3)
        badge.grid(row=0, column=0, sticky="w", padx=(0, 10))

        tk.Label(header, text=entity.label, bg=COLORS["surface"], fg=COLORS["text"], font=("Segoe UI", 12, "bold"), anchor="w").grid(row=0, column=1, sticky="ew")

        meta_text = f"Qtd. {entity.quantity}"
        if entity.page:
            meta_text += f" - Pág. {entity.page}"
        tk.Label(header, text=meta_text, bg=COLORS["surface"], fg=COLORS["muted"], font=("Segoe UI", 9), anchor="e").grid(row=0, column=2, sticky="e")

        attributes = self._format_attributes(entity)
        if attributes:
            attr_frame = tk.Frame(card, bg=COLORS["surface"])
            attr_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(6, 2))
            for index, (name, value) in enumerate(attributes):
                row = index // 3
                col = index % 3
                item = tk.Frame(attr_frame, bg=COLORS["soft"], padx=8, pady=6)
                item.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0), pady=(0, 8))
                item.columnconfigure(0, weight=1)
                tk.Label(item, text=name, bg=COLORS["soft"], fg=COLORS["muted"], font=("Segoe UI", 8, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
                tk.Label(item, text=str(value), bg=COLORS["soft"], fg=COLORS["text"], font=("Segoe UI", 9), anchor="w", wraplength=220, justify="left").grid(row=1, column=0, sticky="ew")
            for col in range(3):
                attr_frame.columnconfigure(col, weight=1)

        if entity.source_text:
            tk.Label(
                card,
                text=entity.source_text,
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=("Segoe UI", 9),
                anchor="w",
                justify="left",
                wraplength=920,
            ).grid(row=2, column=0, sticky="ew", padx=14, pady=(4, 12))

        return card

    def _format_attributes(self, entity: EntityInstance) -> list[tuple[str, object]]:
        attributes = [(self._labelize(key), value) for key, value in entity.attributes.items() if value not in (None, "")]
        if entity.confidence < 1:
            attributes.append(("Confiança", f"{entity.confidence:.0%}"))
        return attributes

    def open_selected_pdf(self) -> None:
        if not self.selected_project or not self.selected_project.source_path:
            return
        open_path(self.selected_project.source_path)

    def _labelize(self, key: str) -> str:
        labels = {
            "ns": "NS",
            "servico": "Serviço",
            "aprovacao": "Aprovação",
            "impacto_ambiental": "Impacto Ambiental",
            "altura_m": "Altura",
            "resistencia_dan": "Resistência",
            "tipo_rede": "Tipo de Rede",
            "estilo_rede": "Estilo de Rede",
            "tensao_rede": "Tensão",
            "fator_condenar": "Fator de Condenar",
            "tipos_possiveis": "Tipos Possíveis",
        }
        return labels.get(key, key.replace("_", " ").title())


def open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


def main() -> None:
    root = tk.Tk()
    ProjectHandlerApp(root)
    root.mainloop()

