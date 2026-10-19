import customtkinter as ctk
from db import VERSION, get_setting
from pages import (Dashboard, EggsPage, SalePage, InvoicesPage, CustomersPage,
                   PricesPage, StatementPage, SettingsPage, GREEN, DARK)

ctk.set_appearance_mode("light")
app = ctk.CTk()
app.title(f"{get_setting('farm_name')} Manager  v{VERSION}")
app.geometry("1200x740")
app.minsize(1000, 640)
app.grid_columnconfigure(1, weight=1)
app.grid_rowconfigure(0, weight=1)

side = ctk.CTkFrame(app, width=230, fg_color=DARK, corner_radius=0)
side.grid(row=0, column=0, sticky="nsew")
side.grid_propagate(False)
ctk.CTkLabel(side, text=get_setting("farm_name"), font=("Segoe UI", 22, "bold"),
             text_color="white").pack(padx=20, pady=(28, 2), anchor="w")
ctk.CTkLabel(side, text=get_setting("phone"), text_color="#A5D6A7").pack(padx=20, pady=(0, 24), anchor="w")

host = ctk.CTkFrame(app, fg_color="transparent")
host.grid(row=0, column=1, sticky="nsew")
host.grid_columnconfigure(0, weight=1)
host.grid_rowconfigure(0, weight=1)

PAGES = [("Dashboard", Dashboard), ("Daily Eggs", EggsPage), ("New Sale", SalePage),
         ("Invoices", InvoicesPage), ("Customers", CustomersPage), ("Prices", PricesPage),
         ("Monthly Statement", StatementPage), ("Settings", SettingsPage)]
pages, buttons = {}, {}


def show(name):
    for n, b in buttons.items():
        b.configure(fg_color=GREEN if n == name else "transparent")
    pages[name].refresh()
    pages[name].tkraise()


for name, cls in PAGES:
    pg = cls(host)
    pg.grid(row=0, column=0, sticky="nsew")
    pages[name] = pg
    b = ctk.CTkButton(side, text=name, anchor="w", height=42, fg_color="transparent", hover_color=GREEN,
                      font=("Segoe UI", 15), command=lambda n=name: show(n))
    b.pack(fill="x", padx=12, pady=3)
    buttons[name] = b

show("Dashboard")
app.mainloop()