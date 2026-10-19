# Naz Poultry Manager

Offline desktop software for poultry farms: daily egg records, sales, invoicing and customer balances.
Built with Python, CustomTkinter, SQLite and ReportLab.

## Features
- Daily egg entry with trays, dozens and production % calculation
- Sales with editable per-egg and per-dozen prices (PKR)
- Thermal 80mm receipts for daily sales and A4 invoices for monthly billing
- Discounts, partial payments and customer balances
- Monthly customer statements with previous balance
- Invoice history with reprint and one-click database backup
- Automatic database upgrades between versions

## Run from source
    pip install -r requirements.txt
    python main.py

## Build the .exe (Windows)
    pyinstaller --onefile --windowed --collect-all customtkinter --name "Naz Poultry Manager" main.py

## Roadmap
Expenses and profit, mortality tracking, production forecasting and alerts, charts and reports.

## Author
Nazim Hussain - github.com/nazim-hussain1