from supabase import create_client, Client
import os

# Leggi URL e chiave dal tuo environment o da variabili segrete Streamlit
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@st.cache_data(ttl=60)  # TTL opzionale, in secondi
def load_data():
    # Esegui la query
    data = supabase.table("qry_run_progetti").select("*").execute()
    
    # Trasforma in DataFrame
    df = pd.DataFrame(data.data)

    # parsing e pulizia come prima
    df['Data_svolgimento'] = pd.to_datetime(df['Data_svolgimento'], errors='coerce')
    df['Scenario'] = df['Scenario'].astype(str).str.strip()
    df['Macro_scenario'] = df['Macro_scenario'].astype(str).str.strip()
    df['Stato'] = df['Stato'].astype(str).str.strip()
    df['ID_Progetto'] = df['ID_Progetto'].astype(str).str.strip()
    df['Pista'] = df['Pista'].astype(str).str.strip()
    return df

df = load_data()

# --- Pulsante Aggiorna dati ---
if st.button("Aggiorna dati"):
    st.cache_data.clear()  # svuota la cache dei dati
    df = load_data()        # ricarica dati aggiornati
    st.rerun() # ricarica tutta la pagina

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

def format_solo_scenario(gruppo):
    scenari = set()
    piste = set()
    piattaforme = set()

    for _, row in gruppo.iterrows():
        ms = str(row['Scenario']).strip() if pd.notna(row['Scenario']) else ""
        pista = str(row['Pista']).strip() if pd.notna(row['Pista']) else ""
        piattaforma = str(row['Piattaforma']).strip() if pd.notna(row['Piattaforma']) else ""

        if ms:
            scenari.add(ms)
        if pista:
            piste.add(pista)
        if pista:
            piattaforme.add(piattaforma)

    if not scenari and not piste and not piattaforme:
        return ""

    scenari_str = ", ".join(sorted(scenari))
    piste_str = ", ".join(sorted(piste))
    piattaforme_str = ", ".join(sorted(piattaforme))

    colore_testo = "#ff0000" if ((gruppo['Stato'].fillna('') == 'Da svolgere')).any() else "#000000"

    html_parts = []
    if scenari:
        html_parts.append(
            f"<div><small style='color:{colore_testo}; font-weight:bold'>{scenari_str}</small></div>"
        )
    if piste:
        html_parts.append(
            f"<div><small style='color:blue'>{piste_str}</small></div>"
        )
    if piattaforme:
        html_parts.append(
            f"<div><small style='color:green'>{piattaforme_str}</small></div>"
        )

    return "".join(html_parts)






def build_pivot(df, index_col, solo_id=False, split_comma=False):
    df_to_group = df.copy()
    
    if split_comma:
        df_to_group = df_to_group.assign(**{
            index_col: df_to_group[index_col].str.split(',')
        }).explode(index_col)
        df_to_group[index_col] = df_to_group[index_col].str.strip()
    
    df_grouped = df_to_group.groupby([index_col, 'Data_svolgimento']).apply(
        lambda g: format_progetti(g, mostra_progetto=True, solo_id=solo_id)
    ).reset_index(name='Progetti')

    all_dates = pd.date_range('2025-01-01', '2026-05-10', freq='D')
    pivot = df_grouped.pivot(index=index_col, columns='Data_svolgimento', values='Progetti').reindex(
        columns=all_dates, fill_value=''  # qui riempi i NaN con stringa vuota
    )
    return pivot

def build_pivot_progetti_solo_scenario(df):
    df_grouped = df.groupby(['ID_Progetto', 'Data_svolgimento']).apply(
        lambda g: format_solo_scenario(g)
    ).reset_index(name='Progetti')

    all_dates = pd.date_range('2025-01-01', '2026-05-10', freq='D')
    pivot = df_grouped.pivot(index='ID_Progetto', columns='Data_svolgimento', values='Progetti').reindex(
        columns=all_dates, fill_value=''
    )
    return pivot



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
        is_weekend = col.weekday() >= 5
        is_holiday = col in giorni_festivi
        classes = []
        if col == oggi: classes.append("today-col")
        if is_weekend:  classes.append("weekend-col")
        if is_holiday:  classes.append("holiday-col")
        class_attr = " ".join(classes)
        html_code += f'<th class="{class_attr}">{col.strftime("%d/%m/%y")}</th>'
    html_code += '</tr>'

    for idx, row in pivot_df.iterrows():
        html_code += f'<tr><td>{idx}</td>'
        for col in pivot_df.columns:
            is_weekend = col.weekday() >= 5
            is_holiday = col in giorni_festivi
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
                day_ts=col,
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
      const table = document.getElementById("{table_id}").querySelector("table");
      const rows = Array.from(table.rows).slice(1);
      rows.sort((a, b) => {{
        const valA = a.cells[colIndex].innerText.trim() ? 1 : 0;
        const valB = b.cells[colIndex].innerText.trim() ? 1 : 0;
        if (valA !== valB) return valB - valA;
        if (ordine_first_col) {{
          const idxA = ordine_first_col.indexOf(a.cells[0].innerText.trim());
          const idxB = ordine_first_col.indexOf(b.cells[0].innerText.trim());
          if (idxA !== -1 && idxB !== -1) return idxA - idxB;
        }}
        return 0;
      }});
      rows.forEach(r => table.appendChild(r));
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



# --- Costruzione e visualizzazione tabelle ---

# --- Costruzione pivot ---
pivot_progetti = build_pivot_progetti_solo_scenario(df)
pivot_piste = build_pivot(df, 'Pista', solo_id=True)
pivot_te = build_pivot(df, 'TE', solo_id=True, split_comma=True)

# --- Selezione scheda ---
scheda = st.selectbox("Seleziona scheda", ["Gantt Progetti", "Gantt Piste", "Gantt TE", "Statistiche giornaliere"])

if scheda == "Gantt Progetti":
    from streamlit.components.v1 import html as components_html
    components_html(
        render_html_table(pivot_progetti, "Progetto", "tableProgetti",
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





