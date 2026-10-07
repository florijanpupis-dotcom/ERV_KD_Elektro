import datetime
import os
import sys
import tempfile
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

import flet as ft
from fpdf import FPDF
from google.cloud import firestore

# Uvoz vaše klase/modula za Firestore bazu
from db import FirestoreDB

# --- INICIJALIZACIJA BAZA I PUTANJA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(BASE_DIR, "serviceAccountKey.json")

# Inicijalizacija Firestore baze
db_instance = FirestoreDB()
db = db_instance.db  # Povezivanje na instancu baze

# --- PALETA BOJA ---
COLOR_BLACK = "#121212"
COLOR_ORANGE = "#FF6600"
COLOR_WHITE = "#FFFFFF"
COLOR_GRAY = "#222222"

def main(page: ft.Page):
    page.title = "ERV KD Elektro"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = COLOR_BLACK
    page.padding = 10

    radnici_list = []
    gradilista_list = []
    edit_evidencija_id = [None]

    def ucitaj_sifranike():
        nonlocal radnici_list, gradilista_list
        radnici_list = [doc.to_dict()["ime_prezime"] for doc in db.collection("radnici").stream() if "ime_prezime" in doc.to_dict()]
        gradilista_list = [doc.to_dict()["naziv"] for doc in db.collection("gradilista").stream() if "naziv" in doc.to_dict()]
        radnici_list.sort()
        gradilista_list.sort()

    # --- TAB 1: UNOS RADNIH SATI ---
    txt_datum = ft.TextField(
        label="Datum", 
        value=datetime.date.today().strftime("%Y-%m-%d"), 
        read_only=True,
        expand=True
    )
    
    def promeni_datum(e):
        if date_picker.value:
            txt_datum.value = date_picker.value.strftime("%Y-%m-%d")
            page.update()

    date_picker = ft.DatePicker(on_change=promeni_datum)
    page.overlay.append(date_picker)

    dd_radnik = ft.Dropdown(
        label="Odaberi Radnika", 
        options=[],
        width=400
    )
    
    dd_gradiliste = ft.Dropdown(
        label="Odaberi Gradilište", 
        options=[],
        width=400
    )

    txt_pocetak = ft.TextField(label="Početak radnog vremena", value="07:00", read_only=True, expand=True)
    txt_kraj = ft.TextField(label="Kraj radnog vremena", value="15:00", read_only=True, expand=True)

    def set_pocetak(e):
        if time_picker_p.value:
            txt_pocetak.value = time_picker_p.value.strftime("%H:%M")
            page.update()

    def set_kraj(e):
        if time_picker_k.value:
            txt_kraj.value = time_picker_k.value.strftime("%H:%M")
            page.update()

    time_picker_p = ft.TimePicker(on_change=set_pocetak)
    time_picker_k = ft.TimePicker(on_change=set_kraj)
    page.overlay.extend([time_picker_p, time_picker_k])

    dd_pauza = ft.Dropdown(
        label="Pauza (minuta)",
        value="30",
        options=[
            ft.dropdown.Option("0", "0 min"),
            ft.dropdown.Option("30", "30 min"),
            ft.dropdown.Option("45", "45 min"),
            ft.dropdown.Option("60", "60 min"),
        ],
        width=400
    )

    lista_posljednjih_unosa = ft.Column(spacing=10)

    def izracunaj_sate(poc, kr, pauza_min):
        t1 = datetime.datetime.strptime(poc, "%H:%M")
        t2 = datetime.datetime.strptime(kr, "%H:%M")
        diff = (t2 - t1).total_seconds() / 3600.0
        efektivno = diff - (int(pauza_min) / 60.0)
        return max(0.0, round(efektivno, 2))

    def osvezi_zadnjih_10():
        lista_posljednjih_unosa.controls.clear()
        docs = db.collection("evidencija").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).stream()
        for doc in docs:
            d = doc.to_dict()
            doc_id = doc.id
            
            def uredi_zapis(e, id=doc_id, data=d):
                edit_evidencija_id[0] = id
                txt_datum.value = data.get("datum", "")
                dd_radnik.value = data.get("radnik", "")
                dd_gradiliste.value = data.get("gradiliste", "")
                txt_pocetak.value = data.get("pocetak", "07:00")
                txt_kraj.value = data.get("kraj", "15:00")
                dd_pauza.value = str(data.get("pauza", 30))
                lbl_btn_spremi.value = "AŽURIRAJ UNOS"
                page.update()

            def obrisi_zapis(e, id=doc_id):
                db.collection("evidencija").document(id).delete()
                osvezi_zadnjih_10()

            card = ft.Container(
                content=ft.Column([
                    ft.Text(f"📅 {d.get('datum', '')} | 👷 {d.get('radnik', '')}", weight=ft.FontWeight.BOLD, color=COLOR_WHITE, size=15),
                    ft.Text(f"🏗️ {d.get('gradiliste', '')}", color=COLOR_ORANGE, size=14),
                    ft.Text(f"⏰ {d.get('pocetak', '')} - {d.get('kraj', '')} (Pauza: {d.get('pauza', 0)}m) = {d.get('sati', 0)}h", color=COLOR_WHITE, size=13),
                    ft.Row([
                        ft.OutlinedButton("AŽURIRAJ", icon=ft.Icons.EDIT, icon_color=COLOR_ORANGE, on_click=uredi_zapis),
                        ft.OutlinedButton("OBRIŠI", icon=ft.Icons.DELETE, icon_color="red", on_click=obrisi_zapis)
                    ], alignment=ft.MainAxisAlignment.END)
                ]),
                bgcolor=COLOR_GRAY,
                padding=10,
                border_radius=8
            )
            lista_posljednjih_unosa.controls.append(card)
        page.update()

    def spremi_unos(e):
        if not dd_radnik.value or not dd_gradiliste.value:
            page.snack_bar = ft.SnackBar(ft.Text("Odaberite radnika i gradilište!"))
            page.snack_bar.open = True
            page.update()
            return

        sati = izracunaj_sate(txt_pocetak.value, txt_kraj.value, dd_pauza.value)
        data = {
            "datum": txt_datum.value,
            "radnik": dd_radnik.value,
            "gradiliste": dd_gradiliste.value,
            "pocetak": txt_pocetak.value,
            "kraj": txt_kraj.value,
            "pauza": int(dd_pauza.value),
            "sati": sati,
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        }

        if edit_evidencija_id[0]:
            db.collection("evidencija").document(edit_evidencija_id[0]).update(data)
            edit_evidencija_id[0] = None
            lbl_btn_spremi.value = "SPREMI UNOS"
        else:
            db.collection("evidencija").add(data)

        osvezi_zadnjih_10()
        page.snack_bar = ft.SnackBar(ft.Text("Spremljeno uspješno!"))
        page.snack_bar.open = True
        page.update()

    lbl_btn_spremi = ft.Text("SPREMI UNOS", color=COLOR_WHITE, weight=ft.FontWeight.BOLD, size=16)
    
    btn_spremi = ft.Container(
        content=lbl_btn_spremi,
        alignment=ft.alignment.center,
        bgcolor=COLOR_ORANGE,
        padding=15,
        border_radius=8,
        on_click=spremi_unos,
        width=400
    )

    tab1_content = ft.ListView([
        ft.Row([
            txt_datum, 
            ft.IconButton(ft.Icons.CALENDAR_MONTH, icon_color=COLOR_ORANGE, icon_size=32, on_click=lambda _: date_picker.pick_date())
        ]),
        dd_radnik,
        dd_gradiliste,
        ft.Row([
            txt_pocetak, 
            ft.IconButton(ft.Icons.ACCESS_TIME, icon_color=COLOR_ORANGE, icon_size=32, on_click=lambda _: time_picker_p.pick_time())
        ]),
        ft.Row([
            txt_kraj, 
            ft.IconButton(ft.Icons.ACCESS_TIME, icon_color=COLOR_ORANGE, icon_size=32, on_click=lambda _: time_picker_k.pick_time())
        ]),
        dd_pauza,
        ft.Container(height=10),
        btn_spremi,
        ft.Divider(color=COLOR_ORANGE, height=30),
        ft.Text("Zadnjih 10 unosa (Uredi / Obriši):", weight=ft.FontWeight.BOLD, color=COLOR_ORANGE, size=16),
        lista_posljednjih_unosa
    ], spacing=15, padding=10, expand=True)

    # --- TAB 2: ŠIFRANICI ---
    txt_novi_radnik = ft.TextField(label="Ime i Prezime radnika", expand=True)
    lista_radnika_ui = ft.Column(spacing=5)

    def osvezi_radnike_ui():
        lista_radnika_ui.controls.clear()
        docs = db.collection("radnici").stream()
        for doc in docs:
            d = doc.to_dict()
            doc_id = doc.id
            row = ft.Container(
                content=ft.Row([
                    ft.Text(d.get("ime_prezime", ""), expand=True, color=COLOR_WHITE, size=15),
                    ft.IconButton(ft.Icons.DELETE, icon_color="red", on_click=lambda e, id=doc_id: brisi_radnika(id))
                ]),
                bgcolor=COLOR_GRAY,
                padding=8,
                border_radius=5
            )
            lista_radnika_ui.controls.append(row)
        page.update()

    def sinkroniziraj_opcije():
        ucitaj_sifranike()
        dd_radnik.options = [ft.dropdown.Option(r) for r in radnici_list]
        dd_filter_radnik.options = [ft.dropdown.Option("SVI")] + [ft.dropdown.Option(r) for r in radnici_list]
        dd_gradiliste.options = [ft.dropdown.Option(g) for g in gradilista_list]
        dd_filter_gradiliste.options = [ft.dropdown.Option("SVI")] + [ft.dropdown.Option(g) for g in gradilista_list]

    def dodaj_radnika(e):
        if txt_novi_radnik.value:
            db.collection("radnici").add({"ime_prezime": txt_novi_radnik.value})
            txt_novi_radnik.value = ""
            sinkroniziraj_opcije()
            osvezi_radnike_ui()

    def brisi_radnika(doc_id):
        db.collection("radnici").document(doc_id).delete()
        sinkroniziraj_opcije()
        osvezi_radnike_ui()

    txt_novo_gradiliste = ft.TextField(label="Naziv Gradilišta", expand=True)
    lista_gradilista_ui = ft.Column(spacing=5)

    def osvezi_gradilista_ui():
        lista_gradilista_ui.controls.clear()
        docs = db.collection("gradilista").stream()
        for doc in docs:
            d = doc.to_dict()
            doc_id = doc.id
            row = ft.Container(
                content=ft.Row([
                    ft.Text(d.get("naziv", ""), expand=True, color=COLOR_WHITE, size=15),
                    ft.IconButton(ft.Icons.DELETE, icon_color="red", on_click=lambda e, id=doc_id: brisi_gradiliste(id))
                ]),
                bgcolor=COLOR_GRAY,
                padding=8,
                border_radius=5
            )
            lista_gradilista_ui.controls.append(row)
        page.update()

    def dodaj_gradiliste(e):
        if txt_novo_gradiliste.value:
            db.collection("gradilista").add({"naziv": txt_novo_gradiliste.value})
            txt_novo_gradiliste.value = ""
            sinkroniziraj_opcije()
            osvezi_gradilista_ui()

    def brisi_gradiliste(doc_id):
        db.collection("gradilista").document(doc_id).delete()
        sinkroniziraj_opcije()
        osvezi_gradilista_ui()

    btn_dodaj_r = ft.Container(
        content=ft.Text("DODAJ", color=COLOR_WHITE, weight=ft.FontWeight.BOLD),
        bgcolor=COLOR_ORANGE,
        padding=12,
        border_radius=5,
        on_click=dodaj_radnika
    )

    btn_dodaj_g = ft.Container(
        content=ft.Text("DODAJ", color=COLOR_WHITE, weight=ft.FontWeight.BOLD),
        bgcolor=COLOR_ORANGE,
        padding=12,
        border_radius=5,
        on_click=dodaj_gradiliste
    )

    tab2_content = ft.ListView([
        ft.Text("Upravljanje Radnicima", color=COLOR_ORANGE, weight=ft.FontWeight.BOLD, size=16),
        ft.Row([txt_novi_radnik, btn_dodaj_r]),
        lista_radnika_ui,
        ft.Divider(color=COLOR_ORANGE, height=30),
        ft.Text("Upravljanje Gradilištima", color=COLOR_ORANGE, weight=ft.FontWeight.BOLD, size=16),
        ft.Row([txt_novo_gradiliste, btn_dodaj_g]),
        lista_gradilista_ui,
    ], spacing=15, padding=10, expand=True)

    # --- TAB 3: IZVJEŠĆA I PDF EMAIL ---
    current_year = datetime.date.today().year
    dd_godina = ft.Dropdown(
        label="Godina", 
        value=str(current_year), 
        options=[ft.dropdown.Option(str(g)) for g in range(2024, 2030)], 
        width=180
    )
    dd_mjesec = ft.Dropdown(
        label="Mjesec", 
        value=f"{datetime.date.today().month:02d}",
        options=[ft.dropdown.Option(f"{m:02d}") for m in range(1, 13)],
        width=180
    )
    
    dd_filter_radnik = ft.Dropdown(label="Radnik (Filtriraj)", options=[], value="SVI", width=400)
    dd_filter_gradiliste = ft.Dropdown(label="Gradilište (Filtriraj)", options=[], value="SVI", width=400)
    txt_email = ft.TextField(label="Email adresa za slanje PDF-a", hint_text="primjer@kdelektro.hr", width=400)
    
    tabela_izvjesce = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Datum")),
            ft.DataColumn(ft.Text("Radnik")),
            ft.DataColumn(ft.Text("Gradilište")),