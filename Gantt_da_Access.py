# python -m streamlit run "C:/Users/francesca.pittoni/OneDrive - IMQ GROUP/Documenti/CSI-Gantt/Gantt_da_Access.py"

# Gantt_da_Supabase.py

import streamlit as st
import html
import pandas as pd
import random
import streamlit.components.v1 as components
import altair as alt
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
from supabase import create_client
import os


# Carica le variabili da secrets di streamlite
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Configurazione pagina ---
st.set_page_config(layout="wide")
oggi = pd.Timestamp.today().normalize()

# --- Giorni festivi ---
giorni_festivi = {
    pd.Timestamp("2025-01-01"),
    pd.Timestamp("2025-04-21"),
    pd.Timestamp("2025-04-25"),
    pd.Timestamp("2025-05-01"),
    pd.Timestamp("2025-06-02"),
    pd.Timestamp("2025-08-15"),
    pd.Timestamp("2025-11-01"),
    pd.Timestamp("2025-12-25"),
    pd.Timestamp("2025-12-26"),
}

# --- Caricamento dati da Supabase ---

@st.cache_data
def load_data():
    limit = 1000
    offset = 0
    rows = []

    while True:
        result = supabase.table("tbl_run_progetti").select("*").range(offset, offset + limit - 1).execute()
        if not result.data:
            break
        rows.extend(result.data)
        offset += limit

    df = pd.DataFrame(rows)

    # parsing e pulizia come prima
    df['Data_svolgimento'] = pd.to_datetime(df['Data_svolgimento'], errors='coerce')
    df['Scenario'] = df['Scenario'].astype(str).str.strip()
    df['Stato'] = df['Stato'].astype(str).str.strip()
    df['ID_Progetto'] = df['ID_Progetto'].astype(str).str.strip()
    df['Pista'] = df['Pista'].astype(str).str.strip()
    return df

df = load_data()


# ordino le piste
ordine_piste = ['PB1', 'PB2', 'PS', 'Biella']
def ordina_pista(pista):
    if pd.isna(pista) or pista == 'nan':
        return len(ordine_piste) + 1
    if pista in ordine_piste:
        return ordine_piste.index(pista)
    else:
        return len(ordine_piste)

df['ordine_pista'] = df['Pista'].apply(ordina_pista)
df = df.sort_values(by=['ordine_pista']).drop(columns=['ordine_pista'])

# Calcolo data inizio per progetto (usiamo la prima Data_svolgimento per ID_Progetto)
df_inizio = (
    df.dropna(subset=['Data_svolgimento'])
      .groupby("ID_Progetto", as_index=False)["Data_svolgimento"]
      .min()
      .rename(columns={"Data_svolgimento": "Data_inizio_proj"})
      .sort_values(by="Data_inizio_proj")
)
# dizionario con data inizio per ordinare i progetti
inizio_progetto = dict(zip(df_inizio["ID_Progetto"].astype(str), df_inizio["Data_inizio_proj"]))

# --- Funzioni di supporto ---
def get_color(progetto_id):
    # colore stabile per ID_Progetto
    random.seed(str(progetto_id))
    colors = ['#f28b82','#fbbc04','#fff475','#ccff90','#a7ffeb','#cbf0f8','#aecbfa','#d7aefb','#fdcfe8']
    return colors[random.randint(0, len(colors)-1)]

def get_color_by_stato(gruppo, progetto_id=None):
    """
    Restituisce il colore della cella in base allo stato delle run.
    Rosso se almeno una run è 'Da svolgere', altrimenti colore standard per il progetto.
    """
    if 'Stato' not in gruppo.columns:
        return '#cccccc'  # fallback grigio
    if (gruppo['Stato'] == 'Da svolgere').any():
        return '#ff6b6b'  # rosso chiaro
    # altrimenti colore standard
    if progetto_id is not None:
        return get_color(progetto_id)
    return '#aecbfa'  # colore default

def format_progetti(gruppo, mostra_progetto=True, solo_id=False):
    progetti_dict = {}
    for _, row in gruppo.iterrows():
        p = str(row['ID_Progetto']).strip() if pd.notna(row['ID_Progetto']) else ""
        ms = str(row['Scenario']).strip() if pd.notna(row['Scenario']) else ""
        if not p:
            continue
        if p not in progetti_dict:
            progetti_dict[p] = set()
        if ms:
            progetti_dict[p].add(ms)

    if not progetti_dict:
        return ""  

    progetti_ordinati = sorted(
        progetti_dict.keys(),
        key=lambda x: inizio_progetto.get(str(x), pd.Timestamp.max)
    )

    progetti_formattati = []
    for p in progetti_ordinati:
        scenari = progetti_dict[p]
        scenari_str = ", ".join(sorted(scenari)) if scenari else ""
        contenuto = f"<b>{p}</b> ({scenari_str})" if scenari_str else f"<b>{p}</b>"
        
        colore = get_color_by_stato(gruppo[gruppo['ID_Progetto'] == p], progetto_id=p)

        progetti_formattati.append(
            f"<div class='cell-content' style='background-color:{colore}; padding:2px 6px; border-radius:5px; margin-bottom:2px;max-height:38px; overflow:hidden;'>"
            f"<small>{contenuto}</small></div>"
        )

    return "".join(progetti_formattati)

def get_project_start_dates(df):
    setup_mask = df['Scenario'].str.contains("Setup\(OR\)|Setup\(Pretest\)", regex=True, case=False)
    start_dates = df[setup_mask].groupby("ID_Progetto")["Data_svolgimento"].min()

    if start_dates.empty:
        # fallback: prendo comunque la prima data di quel progetto
        start_dates = df.groupby("ID_Progetto")["Data_svolgimento"].min()

    return start_dates


def extract_text(html_content):
    if not html_content:
        return ""
    soup = BeautifulSoup(str(html_content), "html.parser")
    texts = [t.strip().replace(",", "\n") for t in soup.stripped_strings]  # virgola → a capo
    return "\n".join(dict.fromkeys(texts))  # rimuove duplicati e unisce con newline

def build_rich_tooltip_from_df(df_source, index_col, idx_value, day_ts, split_comma=False):
    """
    Costruisce il tooltip HTML leggibile a partire dai dati grezzi:
    - Raggruppa per ID_Progetto
    - Deduplica (Scenario, Pista, TE, AL, Piattaforma)
    - Ritorna un HTML con <b>ID</b> e righe "Scenario | Pista | TE | AL | Piattaforma"
      con colonne allineate.
    """
    if pd.isna(day_ts) or idx_value is None or str(idx_value).strip() == "":
        return ""

    # Filtro per giorno
    sub = df_source[df_source["Data_svolgimento"] == day_ts].copy()
    if sub.empty:
        return ""

    key = str(idx_value).strip()

    if index_col == "TE" and split_comma:
        def te_has(te):
            if pd.isna(te):
                return False
            return any(t.strip() == key for t in str(te).split(","))
        sub = sub[sub["TE"].apply(te_has)]
    else:
        sub = sub[sub[index_col].astype(str).str.strip() == key]

    if sub.empty:
        return ""

    # Colonne opzionali
    for col in ["AL", "Piattaforma"]:
        if col not in sub.columns:
            sub[col] = ""

    # Normalizza stringhe
    for c in ["ID_Progetto", "Scenario", "Pista", "TE", "AL", "Piattaforma"]:
        if c in sub.columns:
            sub[c] = sub[c].fillna("").astype(str).str.strip()
        else:
            sub[c] = ""

    # Deduplica righe scenario/risorse per progetto
    cols_keep = ["ID_Progetto", "Scenario", "Pista", "TE", "AL", "Piattaforma"]
    dedup = (
        sub[cols_keep]
        .drop_duplicates()
        .sort_values(["ID_Progetto", "Scenario", "Pista", "TE", "AL", "Piattaforma"])
    )

    # Trova larghezza massima di ogni colonna per l’allineamento
    max_len = [0]*5
    for _, r in dedup.iterrows():
        for i, col in enumerate(["Scenario", "Pista", "TE", "AL", "Piattaforma"]):
            max_len[i] = max(max_len[i], len(r[col]))

    # Costruisci HTML
    parts = []
    for proj, blocco in dedup.groupby("ID_Progetto"):
        parts.append(f"<div class='tt-proj'><b>{html.escape(proj)}</b></div>")
        for _, r in blocco.iterrows():
            line = " | ".join([
                r["Scenario"].ljust(max_len[0]),
                r["Pista"].ljust(max_len[1]),
                r["TE"].ljust(max_len[2]),
                r["AL"].ljust(max_len[3]),
                r["Piattaforma"].ljust(max_len[4])
            ])
            parts.append(f"<div class='tt-row' style='font-family:monospace;'>{html.escape(line)}</div>")

    return "<div class='tt-wrap'>" + "".join(parts) + "</div>"

# TABELLA PER GANTT PISTE
def build_pivot(df, index_col, solo_id=False, split_comma=False):
    df_to_group = df.copy()
    
    if split_comma:
        df_to_group = df_to_group.assign(**{
            index_col: df_to_group[index_col].str.split(',')
        }).explode(index_col)
        df_to_group[index_col] = df_to_group[index_col].str.strip()
    
    df_grouped = df_to_group.groupby([index_col, 'Data_svolgimento', 'Turno']).apply(
        lambda g: format_progetti(g, mostra_progetto=True, solo_id=solo_id)
    ).reset_index(name='Progetti')



    all_dates = pd.date_range('2025-01-01', '2026-05-10', freq='D')

    pivot = df_grouped.pivot_table(
        index=index_col, 
        columns=['Data_svolgimento', 'Turno'], 
        values='Progetti', 
        aggfunc='first',  # o unisci più progetti se necessario
        fill_value=''
    )

        # Gestione Turno nullo: duplico in M e P
    df_to_group['Turno'] = df_to_group['Turno'].fillna('M|P')
    df_to_group = df_to_group.assign(
        Turno=df_to_group['Turno'].str.split('|')
    ).explode('Turno')
    
    # Riordina le colonne per data e turno
    all_dates = pd.date_range('2025-01-01', '2026-05-10', freq='D')
    turni = ['M','P','N']
    multi_cols = pd.MultiIndex.from_product([all_dates, turni], names=['Data_svolgimento','Turno'])
    pivot = pivot.reindex(columns=multi_cols, fill_value='')

    return pivot

def render_html_table(pivot_df, index_name, table_id, df_source, index_col, split_comma=False, ordine_first_col=None):
    html_code = f'''
    <style>
      .table-wrapper {{
        overflow-x: auto;
        max-height: 700px;
        border: 1px solid #ddd;
        position: relative;
        width: 100%;
      }}
      table {{
        border-collapse: collapse;
        width: auto;
        min-width: 5000px;
      }}
      table tr:first-child th {{
        position: sticky;
        top: 0;
        background: #f9f9f9;
        z-index: 5;
      }}
      th, td {{
        width: 100px;
        max-width: 100px;
        min-width: 100px;
        border:1px solid #ddd;
        padding:2px;
        font-size: 10px;
        font-family: "Segoe UI", Arial, sans-serif;
        vertical-align: top;
      }}
      th.weekend-col, td.weekend-col, th.holiday-col, td.holiday-col {{
        width: 20px !important;
        max-width: 20px !important;
        min-width: 20px !important;
      }}
      td.day-separator {{
        border-left: 4px solid #333; /* bordo verticale evidente */
      }}

      .cell-content {{
        overflow: hidden;
        white-space: normal;
        word-break: break-word;
        overflow-wrap: break-word;
        line-height: 1.2em;
      }}
      th:first-child, td:first-child {{
        position: sticky;
        left: 0;
        background: #f9f9f9;
        z-index: 2;
        font-size: 12px;
        width: 100px;
        min-width: 100px;
        max-width: 100px;
        white-space: normal;
        overflow: hidden;
        height: auto;
        font-weight: bold;
      }}
      th:first-child {{ z-index: 3; }}
      .today-col {{ background-color: #fff3cd !important; }}
      .weekend-col {{ background-color: #e0e0e0 !important; }}
      .holiday-col {{ background-color: #ffcccc !important; }}

      /* Tooltip HTML */
      td.has-tip {{ position: relative; }}
      td.has-tip .tip-box {{
        display: none;
        position: absolute;
        bottom: 50%;
        left: 50%;
        background: #333;
        color: #fff;
        padding: 8px 10px;
        border-radius: 6px;
        min-width: 50px;     /* larghezza minima */
        max-width: 800px;     /* larghezza massima */
        font-size: 12px;
        z-index: 50;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        white-space: nowrap;
      }}
      td.has-tip:hover .tip-box {{ 
          display: block;
       }}

      .tt-proj {{ font-weight: 700; margin: 4px 0 2px; }}
      .tt-row  {{ margin: 0 0 2px; }}
      .btn-today {{
        background: #007bff;
        color: white;
        padding: 6px 12px;
        border: none;
        margin-bottom: 8px;
        cursor: pointer;
        border-radius: 4px;
      }}
    </style>

    <button class="btn-today" onclick="vaiAdOggi()">Vai ad oggi</button>
    <div class="table-wrapper" id="{table_id}" tabindex="0">
    <table>
      <tr>
        <th>{index_name}</th>'''

    for col in pivot_df.columns:
        # Se le colonne sono MultiIndex (data, turno)
        if isinstance(col, tuple):
            data = col[0]
            turno = col[1]
        else:
            data = col
            turno = ""

        is_weekend = data.weekday() >= 5
        is_holiday = data in giorni_festivi
        classes = []
        if data == oggi: classes.append("today-col")
        if is_weekend:  classes.append("weekend-col")
        if is_holiday:  classes.append("holiday-col")
        class_attr = " ".join(classes)

        html_code += f'<th class="{class_attr}">{data.strftime("%d/%m/%y")}<br>{turno}</th>'


    for idx, row in pivot_df.iterrows():
        html_code += f'<tr><td>{idx}</td>'
        for col in pivot_df.columns:
                    # Se le colonne sono MultiIndex (data, turno)
            if isinstance(col, tuple):
                data = col[0]
                turno = col[1]
            else:
                data = col
                turno = ""

            is_weekend = data.weekday() >= 5
            is_holiday = data in giorni_festivi
            classes = []
            if col == oggi: classes.append("today-col")
            if is_weekend:  classes.append("weekend-col")
            if is_holiday:  classes.append("holiday-col")
            class_attr = " ".join(classes)

            cell_value = row[col] if pd.notna(row[col]) else ""
            # Tooltip ricco calcolato dai dati
            tip_html = build_rich_tooltip_from_df(
                df_source=df,
                index_col=index_col,
                idx_value=idx,
                day_ts=data,
                split_comma=split_comma
            )
            # Inserisco il tooltip come HTML reale (niente title/data-attr)
            html_code += f'<td class="{class_attr} has-tip"><div class="tip-box">{tip_html}</div>{cell_value}</td>'
        html_code += '</tr>'

    ordine_first_col_js = f'const ordine_first_col = {ordine_first_col};' if ordine_first_col else 'const ordine_first_col = null;'

    html_code += f'''
    </table>
    </div>

    <script>
    {ordine_first_col_js}

    function vaiAdOggi() {{
      document.querySelectorAll(".table-wrapper").forEach(wrapper => {{
        const todayCell = wrapper.querySelector(".today-col");
        if (todayCell) {{
          const colLeft = todayCell.offsetLeft;
          const colWidth = todayCell.offsetWidth;
          const wrapperWidth = wrapper.offsetWidth;
          wrapper.scrollLeft = colLeft - (wrapperWidth / 2) + (colWidth / 2);
        }}
      }});
    }}

    window.onload = function() {{
        setTimeout(() => {{
            vaiAdOggi();
            const table = document.getElementById("{table_id}").querySelector("table");
            const todayCell = table.querySelector(".today-col");
            if (todayCell) {{
            const todayIndex = todayCell.cellIndex;   // indice della colonna "oggi"
            ordinaColonna(todayIndex);
            }}
        }}, 200);  // leggermente più alto per dare tempo al rendering
    }};

    document.addEventListener("keydown", function(e) {{
      const wrapper = document.getElementById("{table_id}");
      if (!wrapper) return;
      const step = 80;
      if (e.key === "ArrowRight") {{
        wrapper.scrollLeft += step;
      }} else if (e.key === "ArrowLeft") {{
        wrapper.scrollLeft -= step;
      }}
    }});

    function ordinaColonna(colIndex) {{
        var table = document.querySelector("table");
        var rows = Array.from(table.rows).slice(1); // esclude intestazione
        var asc = table.getAttribute("data-sort-col") != colIndex || table.getAttribute("data-sort-order") == "desc";

        rows.sort((a, b) => {{
            let A = a.cells[colIndex].innerText.trim().toLowerCase();
            let B = b.cells[colIndex].innerText.trim().toLowerCase();

            // Celle vuote in fondo
            if (A === "" && B !== "") return 1;
            if (A !== "" && B === "") return -1;
            if (A === "" && B === "") return 0;

            // Ordinamento alfabetico
            return asc ? A.localeCompare(B) : B.localeCompare(A);
        }});

        rows.forEach(row => table.appendChild(row));
        table.setAttribute("data-sort-col", colIndex);
        table.setAttribute("data-sort-order", asc ? "asc" : "desc");
    }}


    document.querySelectorAll("#{table_id} table tr:first-child th").forEach((th, index) => {{
      if(index > 0) {{
        th.style.cursor = "pointer";
        th.onclick = () => ordinaColonna(index);
      }}
    }});
    </script>
    '''
    return html_code

#TABELLA PER GANTT PROGETTI
def format_solo_scenario(gruppo):
    if gruppo.empty:
        return ""

    gruppo = gruppo.fillna('')  # sostituisci NaN con stringa vuota

    progetto_id = str(gruppo['ID_Progetto'].iloc[0]) if 'ID_Progetto' in gruppo.columns else "Sconosciuto"

    # creiamo chiave unica per combinazione pista + piattaforma
    gruppo['key'] = gruppo['Pista'].astype(str) + '||' + gruppo['Piattaforma'].astype(str)

    html_parts = []

    # riga iniziale con ID progetto
    html_parts.append(f"<div><strong style='color:blue'>{progetto_id}</strong></div>")

    # raggruppiamo per combinazione pista-piattaforma
    for key, sub in gruppo.groupby('key'):
        # determinare lo stato complessivo per ogni scenario
        scenari_html = []
        for scen, sgroup in sub.groupby('Scenario'):
            if not scen:
                continue
            colore_testo = "#ff0000" if (sgroup['Stato'] == 'Da svolgere').any() else "#000000"
            scenari_html.append(f"<span style='color:{colore_testo}; font-weight:bold'>{scen}</span>")

        pista, piattaforma = key.split('||')

        gruppo_html = ""
        if scenari_html:
            gruppo_html += f"<div>{', '.join(sorted(scenari_html))}</div>"
        if pista or piattaforma:
            gruppo_html += f"<div><small style='color:blue'>{pista}</small> - <small style='color:green'>{piattaforma}</small></div>"

        if gruppo_html:
            html_parts.append(gruppo_html)

    return "<div style='margin-bottom:4px'>" + "<div style='height:4px'></div>".join(html_parts) + "</div>"

def build_pivot_progetti_solo_scenario(df, index_col='ID_Progetto', solo_id=False):
    # 1️⃣ Gestione Turno nullo: duplico in M e P
    df['Turno'] = df['Turno'].fillna('M|P')
    df = df.assign(Turno=df['Turno'].str.split('|')).explode('Turno')

    # 2️⃣ Groupby dopo aver sistemato i Turni
    df_grouped = df.groupby(['ID_Progetto', 'Data_svolgimento', 'Turno']).apply(
        lambda g: format_solo_scenario(g)
    ).reset_index(name='Progetti')

    # 3️⃣ Pivot
    all_dates = pd.date_range('2025-01-01', '2026-05-10', freq='D')
    turni = ['M','P','N']
    multi_cols = pd.MultiIndex.from_product([all_dates, turni], names=['Data_svolgimento','Turno'])
    pivot = df_grouped.pivot_table(
        index=index_col, 
        columns=['Data_svolgimento', 'Turno'], 
        values='Progetti', 
        aggfunc='first',  
        fill_value=''
    )
    pivot = pivot.reindex(columns=multi_cols, fill_value='')

    return pivot

def render_html_table_grouped(pivot_df, index_name, table_id, df_source, index_col, split_comma=False, ordine_first_col=None):
    oggi = pd.Timestamp.today().normalize()

    # --- FILTRO INIZIALE 10-30 GIORNI ---
    all_dates = pivot_df.columns.get_level_values(0) if isinstance(pivot_df.columns, pd.MultiIndex) else pivot_df.columns
    filtro_iniziale = (all_dates >= oggi - pd.Timedelta(days=10)) & (all_dates <= oggi + pd.Timedelta(days=30))
    pivot_filtrato = pivot_df.loc[:, filtro_iniziale]

    html_code = f'''
    <style>
      .table-wrapper {{
        overflow-x: auto;
        max-height: 700px;
        border: 1px solid #ddd;
        position: relative;
        width: 100%;
      }}
      table {{
        border-collapse: collapse;
        width: auto;
        min-width: 5000px;
      }}
      table tr:first-child th {{
        position: sticky;
        top: 0;
        background: #f9f9f9;
        z-index: 5;
      }}
      th, td {{
        width: 140px;
        max-width: 140px;
        min-width: 140px;
        border:1px solid #ddd;
        padding:2px;
        font-size: 9px;
        font-family: "Segoe UI", Arial, sans-serif;
        vertical-align: top;
      }}
      th.weekend-col, td.weekend-col, th.holiday-col, td.holiday-col {{
        width: 15px !important;
        max-width: 15px !important;
        min-width: 15px !important;
      }}

      .cell-content {{
        overflow: hidden;
        white-space: normal;
        word-break: break-word;
        overflow-wrap: break-word;
        line-height: 1.2em;
      }}
      th:first-child, td:first-child {{
        position: sticky;
        left: 0;
        background: #f9f9f9;
        z-index: 2;
        font-size: 12px;
        width: 100px;
        min-width: 100px;
        max-width: 100px;
        white-space: normal;
        overflow: hidden;
        height: auto;
        font-weight: bold;
      }}
      th:first-child {{ z-index: 3; }}
      .today-col {{ background-color: #fff3cd !important; }}
      .weekend-col {{ background-color: #e0e0e0 !important; }}
      .holiday-col {{ background-color: #ffcccc !important; }}

      td.day-separator {{
        border-right: 8px solid #333; /* bordo verticale evidente */
      }}

      /* Tooltip HTML */
      td.has-tip {{ position: relative; }}
      td.has-tip .tip-box {{
        display: none;
        position: absolute;
        bottom: 50%;
        left: 50%;
        background: #333;
        color: #fff;
        padding: 8px 10px;
        border-radius: 6px;
        min-width: 50px;
        max-width: 800px;
        font-size: 12px;
        z-index: 50;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        white-space: nowrap;
      }}
      td.has-tip:hover .tip-box {{ 
          display: block;
       }}

      .tt-proj {{ font-weight: 700; margin: 4px 0 2px; }}
      .tt-row  {{ margin: 0 0 2px; }}
      .btn-today {{
        background: #007bff;
        color: white;
        padding: 6px 12px;
        border: none;
        margin-bottom: 8px;
        cursor: pointer;
        border-radius: 4px;
      }}
    </style>

    <button class="btn-today" onclick="vaiAdOggi()">Vai ad oggi</button>
    <button class="btn-today" onclick="mostraTutto()">Mostra tutto</button>

    <div id="pivotCompleto" style="display:none">
        {pivot_df.to_html(escape=False, index=False)}
    </div>

    <div class="table-wrapper" id="{table_id}" tabindex="0">
    <table>
      <tr>
        <th>{index_name}</th>'''

    for col in pivot_filtrato.columns:
        # Se le colonne sono MultiIndex (data, turno)
        if isinstance(col, tuple):
            data = col[0]
            turno = col[1]
        else:
            data = col
            turno = ""

        is_weekend = data.weekday() >= 5
        is_holiday = data in giorni_festivi
        classes = []
        if data == oggi: 
            classes.append("today-col")
        if is_weekend:  
            classes.append("weekend-col")
        if is_holiday:  
            classes.append("holiday-col")
        # aggiungi bordo se è l'ultimo turno del giorno
        if turno == "N":
            classes.append("day-separator")
        class_attr = " ".join(classes)

        html_code += f'<th class="{class_attr}">{data.strftime("%d/%m/%y")}<br>{turno}</th>'


    last_group = None
    for idx, row in pivot_filtrato.iterrows():
        # Prefisso progetto: primi 7 caratteri
        prefix = str(idx)[:7]
        if last_group is not None and prefix != last_group:
            # riga separatore tra gruppi
            html_code += f'<tr style="height:5px; background:#aaa"><td colspan="{len(pivot_filtrato.columns)+1}"></td></tr>'
        last_group = prefix

        html_code += f'<tr><td>{idx}</td>'
        for col in pivot_filtrato.columns:
                    # Se le colonne sono MultiIndex (data, turno)
            if isinstance(col, tuple):
                data = col[0]
                turno = col[1]
            else:
                data = col
                turno = ""

            is_weekend = data.weekday() >= 5
            is_holiday = data in giorni_festivi
            classes = []
            if data == oggi: classes.append("today-col")
            if is_weekend:  classes.append("weekend-col")
            if is_holiday:  classes.append("holiday-col")
            class_attr = " ".join(classes)

            cell_value = row[col] if pd.notna(row[col]) else ""
            # Tooltip ricco calcolato dai dati
            tip_html = build_rich_tooltip_from_df(
                df_source=df,
                index_col=index_col,
                idx_value=idx,
                day_ts=data,
                split_comma=split_comma
            )
            html_code += f'<td class="{class_attr} has-tip"><div class="tip-box">{tip_html}</div>{cell_value}</td>'
        html_code += '</tr>'

    ordine_first_col_js = f'const ordine_first_col = {ordine_first_col};' if ordine_first_col else 'const ordine_first_col = null;'

    html_code += f'''
    </table>
    </div>

    <script>
    {ordine_first_col_js}

    const pivotCompleto = `{pivot_df.to_html(escape=False, index=False)}`;  // pivot completo in HTML

    function mostraTutto(){{
        document.getElementById("{table_id}").innerHTML = pivotCompleto;
    }}

    function vaiAdOggi() {{
      document.querySelectorAll(".table-wrapper").forEach(wrapper => {{
        const todayCell = wrapper.querySelector(".today-col");
        if (todayCell) {{
          const colLeft = todayCell.offsetLeft;
          const colWidth = todayCell.offsetWidth;
          const wrapperWidth = wrapper.offsetWidth;
          wrapper.scrollLeft = colLeft - (wrapperWidth / 2) + (colWidth / 2);
        }}
      }});
    }}

    

    window.onload = function() {{
        setTimeout(() => {{
            vaiAdOggi();
            const table = document.getElementById("{table_id}").querySelector("table");
            const todayCell = table.querySelector(".today-col");
            if (todayCell) {{
            const todayIndex = todayCell.cellIndex;
            ordinaColonna(todayIndex);
            }}
        }}, 200);
    }};

    document.addEventListener("keydown", function(e) {{
      const wrapper = document.getElementById("{table_id}");
      if (!wrapper) return;
      const step = 80;
      if (e.key === "ArrowRight") {{
        wrapper.scrollLeft += step;
      }} else if (e.key === "ArrowLeft") {{
        wrapper.scrollLeft -= step;
      }}
    }});

    function ordinaColonna(colIndex) {{
        var wrapper = document.getElementById("{table_id}");
        var table = wrapper.querySelector("table");

        // prendo solo le righe con dati (salto l'intestazione)
        var rows = Array.from(table.rows).slice(1);

        // toggle asc/desc
        var asc = table.getAttribute("data-sort-col") != colIndex ||
                table.getAttribute("data-sort-order") == "desc";

        rows.sort((a, b) => {{
            // se una riga non ha abbastanza celle, la mando in fondo
            if (!a.cells[colIndex] || !b.cells[colIndex]) return 0;

            let A = a.cells[colIndex].innerText.trim().toLowerCase();
            let B = b.cells[colIndex].innerText.trim().toLowerCase();

            // Celle vuote in fondo
            if (A === "" && B !== "") return 1;
            if (A !== "" && B === "") return -1;
            if (A === "" && B === "") return 0;

            // Ordinamento alfabetico asc/desc
            return asc ? A.localeCompare(B) : B.localeCompare(A);
        }});

        // riattacco le righe ordinate
        rows.forEach(row => table.appendChild(row));

        // salvo stato ordinamento
        table.setAttribute("data-sort-col", colIndex);
        table.setAttribute("data-sort-order", asc ? "asc" : "desc");
    }}


    document.querySelectorAll("#{table_id} table tr:first-child th").forEach((th, index) => {{
      if(index > 0) {{
        th.style.cursor = "pointer";
        th.onclick = () => ordinaColonna(index);
      }}
    }});
    </script>
    '''
    return html_code

# TABELLA PER RIASSUNTO PROGETTI
def build_pivot_progetti_colorati(df):
    df_grouped = df.groupby(['ID_Progetto', 'Data_svolgimento']).apply(
        lambda g: get_color_by_stato(g, progetto_id=g['ID_Progetto'].iloc[0])
    ).reset_index(name='Colore')

    all_dates = pd.date_range('2025-01-01', '2026-05-10', freq='D')
    pivot = df_grouped.pivot(
        index='ID_Progetto', columns='Data_svolgimento', values='Colore'
    ).reindex(columns=all_dates, fill_value='')

    # 🔽 ottengo la data di inizio progetto
    start_dates = get_project_start_dates(df)

    # 🔽 calcolo il gruppo dei progetti (es primi 7 caratteri dell'ID)
    groups = pivot.index.to_series().apply(lambda x: str(x)[:7])

    # 🔽 costruisco DataFrame per ordinamento
    sort_df = pd.DataFrame({
        'group': groups,
        'start_date': start_dates
    })

    # 🔽 ordino prima per gruppo, poi per data
    sort_df = sort_df.sort_values(['group', 'start_date'])
    
    pivot = pivot.reindex(sort_df.index)
    return pivot

def render_html_table_colored(pivot_df, index_name, table_id): # Per RIASSUNTO PROGETTI con gruppi
    html_code = '''
    <style>
      .table-wrapper {
        overflow-x: auto;
        max-height: 1000px;
        border: 1px solid #ddd;
        position: relative;
        width: 100%;
    }
    table {
        border-collapse: collapse;
        width: auto;
        min-width: 5000px;
    }
    table tr:first-child th {
        position: sticky;
        top: 0;
        background: #f9f9f9;
        z-index: 5;
    }
    th, td {
        width: 20px;
        max-width: 20px;
        min-width: 20px;
        border:1px solid #ddd;
        padding:0;
        font-size: 12px;
        font-family: "Segoe UI", Arial, sans-serif;
    }
    /* Intestazioni colonne tranne la prima */
    th:not(:first-child) {
        font-size: 9px;
        writing-mode: vertical-rl;   /* scrittura verticale */
        white-space: nowrap;
        height: 60px; /* regola l'altezza per il testo inclinato */
        padding: 0 2px;

        transform: rotate(-40deg); 
        transform-origin: bottom left; /* sposta il punto di rotazione in basso a sinistra */
        text-align: left;  /* evita che resti centrato */
    }

    th:first-child, td:first-child {
        position: sticky;
        left: 0;
        background: #f9f9f9;
        z-index: 2;
        font-size: 10px;
        width: 250px;
        min-width: 250px;
        max-width: 250px;
        font-weight: bold;
      }
    th:first-child { 
        z-index: 3; 
    }

      .today-col { background-color: #fff3cd !important; }
      .weekend-col { background-color: #e0e0e0 !important; }
      .holiday-col { background-color: #ffcccc !important; }
      .button-container {
        margin: 10px 0;
        text-align: right;
    }
    .goto-today {
        padding: 6px 12px;
        font-size: 12px;
        cursor: pointer;
        background-color: #007bff;
        color: white;
        border: none;
        border-radius: 4px;
    }
      .goto-today:hover { background-color: #0056b3; }
    </style>

    <div class="button-container">
      <button class="goto-today" onclick="goToToday()">Vai ad oggi</button>
    </div>

    <div class="table-wrapper" id="''' + table_id + '''" tabindex="0">
    <table>
      <tr>
        <th>''' + index_name + '''</th>'''

    for col in pivot_df.columns:
        classes = []
        if col == oggi: classes.append("today-col")
        if col.weekday() >= 5: classes.append("weekend-col")
        if col in giorni_festivi: classes.append("holiday-col")
        class_attr = " ".join(classes)
        html_code += f'<th class="{class_attr}">{col.strftime("%d/%m/%y")}</th>'
    html_code += '</tr>'

    last_group = None
    for idx, row in pivot_df.iterrows():
        # Prefisso progetto: primi 7 caratteri
        prefix = str(idx)[:7]
        if last_group is not None and prefix != last_group:
            # riga separatore tra gruppi con attributo per escluderla dallo sorting
            html_code += f'<tr style="height:5px; background:#aaa" data-separator="1"><td colspan="{len(pivot_df.columns)+1}"></td></tr>'
        last_group = prefix

        html_code += f'<tr><td>{idx}</td>'
        for col in pivot_df.columns:
            classes = []
            if col == oggi: classes.append("today-col")
            if col.weekday() >= 5: classes.append("weekend-col")
            if col in giorni_festivi: classes.append("holiday-col")
            class_attr = " ".join(classes)

            colore = row[col] if row[col] else ""
            style = f' style="background-color:{colore}"' if colore else ""
            html_code += f'<td class="{class_attr}"{style}></td>'
        html_code += '</tr>'

    html_code += '''
    </table></div>

    <script>
    function goToToday() {
      var tableWrapper = document.getElementById("''' + table_id + '''");
      var todayCol = tableWrapper.querySelector(".today-col");
      if(todayCol){
        tableWrapper.scrollLeft = todayCol.offsetLeft - tableWrapper.offsetWidth/2 + todayCol.offsetWidth/2;
      }
    }
    </script>
    '''
    return html_code

# --- Costruzione e visualizzazione tabelle ---

# --- Costruzione pivot ---
pivot_progetti = build_pivot_progetti_solo_scenario(df)
pivot_piste = build_pivot(df, 'Pista', solo_id=True)
pivot_te = build_pivot(df, 'TE', solo_id=True, split_comma=True)

# --- Riga comandi in alto: Aggiorna dati, seleziona scheda, Vai ad oggi ---
col1, col2 = st.columns([1, 3])

with col1:
    if st.button("Aggiorna dati", key="aggiorna_dati"):
        st.cache_data.clear()
        df = load_data()
        st.rerun() # ricarica tutta la pagina
with col2:
    st.markdown("""
        <style>
        div[data-testid="stSelectbox"] > label {display:none;}
        div[data-testid="stSelectbox"] {margin-top: -24px;}
        </style>
        """, unsafe_allow_html=True)
    
    scheda = st.selectbox(
        "", 
        ["Gantt Progetti", "Riassunto Progetti", "Gantt Piste", "Gantt TE", "Statistiche giornaliere"],
        key="scheda_selezione"
    )

# SCHEDE
    
if scheda == "Gantt Progetti":
    from streamlit.components.v1 import html as components_html
    components_html(
        render_html_table_grouped(pivot_progetti, "Progetto", "tableProgetti",
                          df_source=df, index_col="ID_Progetto", split_comma=False),
        height=900, scrolling=True
    )

elif scheda == "Gantt Piste":
    from streamlit.components.v1 import html as components_html
    components_html(
        render_html_table(pivot_piste, "Pista", "tablePiste",
                          df_source=df, index_col="Pista", split_comma=False),
        height=900, scrolling=True
    )

elif scheda == "Gantt TE":
    from streamlit.components.v1 import html as components_html
    components_html(
        render_html_table(pivot_te, "Test Engineer", "tableTE",
                          df_source=df, index_col="TE", split_comma=True),
        height=900, scrolling=True
    )

elif scheda == "Riassunto Progetti":
    pivot_progetti_colorati = build_pivot_progetti_colorati(df)
    from streamlit.components.v1 import html as components_html
    components_html(
        render_html_table_colored(pivot_progetti_colorati, "Progetto", "tableProgettiColorati"),
        height=900, scrolling=True
    )



elif scheda == "Statistiche giornaliere":
    import altair as alt

    # --- Tabella aggregata per grafico ---
    df_count = df.dropna(subset=['Data_svolgimento']).groupby('Data_svolgimento').agg({'ID_Progetto':'nunique'}).reset_index()
    df_count.rename(columns={'ID_Progetto':'Progetti'}, inplace=True)

    # --- Selettore giorno ---
    date_selected = st.date_input(
        "Seleziona una data per vedere i progetti",
        value=pd.Timestamp.today().normalize(),
        min_value=df_count['Data_svolgimento'].min(),
        max_value=df_count['Data_svolgimento'].max()
    )

    # --- Grafico Altair ---
    line_chart = alt.Chart(df_count).mark_line(point=True).encode(
        x='Data_svolgimento:T',
        y='Progetti:Q'
    )

    # --- Punto rosso sul giorno selezionato ---
    highlight_df = df_count[df_count['Data_svolgimento'] == pd.Timestamp(date_selected)]
    highlight_point = alt.Chart(highlight_df).mark_point(color='red', size=100).encode(
        x='Data_svolgimento:T',
        y='Progetti:Q'
    )

    chart = (line_chart + highlight_point).properties(width=900, height=400, title="Progetti giornalieri")
    st.altair_chart(chart, use_container_width=True)

    # --- Mostra elenco progetti del giorno ---
    progetti_giorno = df[df['Data_svolgimento'] == pd.Timestamp(date_selected)]['ID_Progetto'].dropna().unique()
    if len(progetti_giorno) > 0:
        st.write("Progetti del giorno selezionato:")
        for p in progetti_giorno:
            st.write(f"- {p}")
    else:
        st.write("Nessun progetto per questa data.")












