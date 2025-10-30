# services/ui_theme.py
"""
Centralized theme + shared UI helpers for PoseCare.

This file defines:
 - color palette / typography tokens
 - apply_theme() to set root colors
 - apply_ctk_theme() (backwards-compatible alias for old code)
 - GlassCard: two-panel auth card (form left, hero/branding right)
 - pill_entry() and primary_button() for consistent input/button styling
 - card() helper for generic rounded section frames
"""

from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk  # pillow


# ─────────────────────────
# Palette / tokens (tuned to match your screenshot)
# ─────────────────────────
TOP_BG    = "#0f1115"   # overall page background
CARD_BG   = "#1c2430"   # dark card background
FIELD_BG  = "#2a3442"   # pill input background
TEXT      = "#E9EEF5"   # main text
MUTED     = "#9FB3C8"   # helper / subtle text
PRIMARY   = "#2D8CFF"   # bright blue button
PRIMARY_H = "#1976F2"   # hover blue
BORDER    = "#283448"   # divider/border-ish

FONTS = {
    "title":    ("Segoe UI", 24, "bold"),
    "subtitle": ("Segoe UI", 12),
    "label":    ("Segoe UI", 14),
    "button":   ("Segoe UI", 15, "bold"),
}

# some code in other pages may expect PALETTE, so we expose one
PALETTE = {
    "bg": TOP_BG,
    "card": CARD_BG,
    "field": FIELD_BG,
    "text": TEXT,
    "muted": MUTED,
    "border": BORDER,
    "primary": PRIMARY,
    "primary_hover": PRIMARY_H,
}


# ─────────────────────────
# Theme application
# ─────────────────────────
def apply_theme(widget: object) -> None:
    """
    Preferred new function.
    Call once on any top-level/frame to apply global bg + dark appearance.
    """
    try:
        ctk.set_appearance_mode("dark")
        # keep CTk in dark mode; ignore if already set
        ctk.set_default_color_theme("dark-blue")
    except Exception:
        pass

    try:
        widget.configure(fg_color=TOP_BG)
    except Exception:
        # some widgets (like CTk root) might not expose fg_color early
        pass


def apply_ctk_theme(widget: object) -> None:
    """
    Backwards-compatibility wrapper.
    Old code calls apply_ctk_theme(), so we just forward to apply_theme().
    """
    apply_theme(widget)


# ─────────────────────────
# Reusable "card" helper
# Some of your older pages (dashboard, etc.) might call card(parent, ...)
# We'll provide a simple rounded frame so they don't crash.
# ─────────────────────────
def card(parent, **grid_kwargs) -> ctk.CTkFrame:
    """
    Create a rounded, dark section frame for grouping content.
    Returns the frame. If you pass grid_kwargs, we grid() it for you.
    """
    frame = ctk.CTkFrame(
        parent,
        fg_color=CARD_BG,
        corner_radius=16,
    )
    # Let caller decide layout, but if kwargs provided, we do a convenience .grid()
    if grid_kwargs:
        frame.grid(**grid_kwargs)
    return frame


# ─────────────────────────
# GlassCard component
# ─────────────────────────
class GlassCard(ctk.CTkFrame):
    """
    A rounded 2-column auth card:
      • left: form / fields
      • right: hero image or branding with a dark overlay

    Usage:
        card = GlassCard(root, bg_image_path="hero.jpg")
        left_side  = card.left
        right_side = card.right
    """

    def __init__(
        self,
        parent,
        width: int = 900,
        height: int = 480,
        bg_image_path: Optional[str] = None,
    ):
        super().__init__(parent, corner_radius=20, fg_color=TOP_BG)
        self.configure(width=width, height=height)

        # two-column inside
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # LEFT PANEL (form / text)
        self.left = ctk.CTkFrame(
            self,
            fg_color=CARD_BG,
            corner_radius=20,
        )
        self.left.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(24, 12),
            pady=24,
        )
        self.left.grid_columnconfigure(0, weight=1)
        # add a stretchy bottom row so content hugs the top nicely
        self.left.grid_rowconfigure(99, weight=1)

        # RIGHT PANEL (hero / image)
        self.right = ctk.CTkFrame(
            self,
            fg_color=CARD_BG,
            corner_radius=20,
        )
        self.right.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(12, 24),
            pady=24,
        )
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(0, weight=1)

        # optional background image with overlay
        self._bg_label: Optional[ctk.CTkLabel] = None
        self._overlay: Optional[ctk.CTkFrame] = None
        self._bg_photo: Optional[ImageTk.PhotoImage] = None

        if bg_image_path:
            self.set_right_background(bg_image_path)

    def set_right_background(self, img_path: str) -> None:
        """
        Fill the right pane with an image and a translucent dark overlay.
        Safe no-op if the image can't load.
        """
        try:
            pil_img = Image.open(img_path)
            # just resize to roughly fit; can refine if you want dynamic sizing
            pil_img = pil_img.resize((480, 480), Image.LANCZOS)
            self._bg_photo = ImageTk.PhotoImage(pil_img)

            self._bg_label = ctk.CTkLabel(
                self.right,
                text="",
                image=self._bg_photo,
                corner_radius=20,
            )
            self._bg_label.place(relx=0, rely=0, relwidth=1, relheight=1)

            self._overlay = ctk.CTkFrame(
                self.right,
                fg_color="#00000080",  # ~50% black overlay
                corner_radius=20,
            )
            self._overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        except Exception:
            # couldn't load image, so just keep CARD_BG
            pass


# ─────────────────────────
# Input + button builders
# ─────────────────────────
def pill_entry(master, placeholder: str = "") -> ctk.CTkEntry:
    """
    Rounded pill-style text entry, matches the screenshot style.
    """
    return ctk.CTkEntry(
        master,
        placeholder_text=placeholder,
        height=44,
        corner_radius=18,
        fg_color=FIELD_BG,
        text_color=TEXT,
        border_width=0,
    )


def primary_button(
    master,
    text: str,
    command=None,
    width: int = 220,
) -> ctk.CTkButton:
    """
    Bright blue action button ("Submit", "Login").
    """
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        height=48,
        width=width,
        corner_radius=24,
        fg_color=PRIMARY,
        hover_color=PRIMARY_H,
        text_color="white",
        font=FONTS["button"],
    )
