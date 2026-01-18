import json
import os
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st
from PIL import Image

# ✅ Logo na sidebar (maior, centralizada e no topo)
LOGO_PATH = os.path.join("assets", "branding", "logo.png")

st.markdown("""
<style>
/* centraliza imagem dentro da sidebar */
[data-testid="stSidebar"] img {
    display: block;
    margin-left: auto;
    margin-right: auto;
}
/* sobe o conteúdo da sidebar */
section[data-testid="stSidebar"] > div {
    padding-top: 0.2rem;
}
</style>
""", unsafe_allow_html=True)

if os.path.exists(LOGO_PATH):
    st.sidebar.image(LOGO_PATH, width=200)
    st.sidebar.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)

st.sidebar.markdown("---")

DB_PATH = os.path.join("db", "clinic.db")
CARDS_PATH = os.path.join("data", "cards.json")

def get_conn():
    os.makedirs("db", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            age_group TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            mode TEXT NOT NULL,
            session_notes TEXT,
            FOREIGN KEY(client_id) REFERENCES clients(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            card_id INTEGER NOT NULL,
            hint_level INTEGER NOT NULL,
            detection INTEGER NOT NULL,
            clues INTEGER NOT NULL,
            cog_empathy INTEGER NOT NULL,
            action INTEGER NOT NULL,
            communication INTEGER NOT NULL,
            safety INTEGER NOT NULL,
            total INTEGER NOT NULL,
            notes TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    """)
    conn.commit()
    return conn

@st.cache_data
def load_cards():
    with open(CARDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def card_image(path):
    return Image.open(path) if os.path.exists(path) else None

def total_score(detection, clues, cog_empathy, action, communication, safety):
    return int(detection + clues + cog_empathy + action + communication + safety)

cards = load_cards()
cards_by_id = {c["id"]: c for c in cards}
conn = get_conn()

st.sidebar.title("Navegação")
page = st.sidebar.radio("Ir para:", ["Pacientes", "Sessão", "Relatórios"])

if page == "Pacientes":
    st.title("Pacientes")

    st.subheader("Criar novo paciente")
    col1, col2 = st.columns(2)
    with col1:
        nickname = st.text_input("Apelido/código (evite dados sensíveis)")
        age_group = st.selectbox("Faixa", ["crianca", "adolescente", "adulto"])
    with col2:
        notes = st.text_area("Observações (opcional)", height=100)

    if st.button("Criar paciente"):
        if nickname.strip():
            conn.execute(
                "INSERT INTO clients (nickname, age_group, notes, created_at) VALUES (?,?,?,?)",
                (nickname.strip(), age_group, notes.strip(), datetime.now().isoformat())
            )
            conn.commit()
            st.success("Paciente criado!")
        else:
            st.warning("Digite um apelido/código.")

    st.divider()
    st.subheader("Selecionar paciente ativo")

    df = pd.read_sql_query("SELECT * FROM clients ORDER BY id DESC", conn)
    if df.empty:
        st.info("Nenhum paciente cadastrado ainda.")
    else:
        if "active_client_id" not in st.session_state:
            st.session_state.active_client_id = int(df.iloc[0]["id"])

        st.session_state.active_client_id = st.selectbox(
            "Paciente ativo:",
            df["id"].tolist(),
            format_func=lambda x: f'#{x} — {df[df["id"]==x].iloc[0]["nickname"]} ({df[df["id"]==x].iloc[0]["age_group"]})'
        )
        st.write("Paciente ativo:", st.session_state.active_client_id)

elif page == "Sessão":
    st.title("Sessão")

    if "active_client_id" not in st.session_state:
        st.warning("Selecione um paciente em 'Pacientes'.")
        st.stop()

    client_id = st.session_state.active_client_id
    client_row = pd.read_sql_query("SELECT * FROM clients WHERE id = ?", conn, params=(client_id,))
    if client_row.empty:
        st.warning("Paciente não encontrado.")
        st.stop()

    client_name = client_row.iloc[0]["nickname"]
    st.caption(f"Paciente ativo: #{client_id} — {client_name}")

    mode = st.selectbox("Modo", ["treino_guiado", "treino_independente", "avaliacao"])
    hint_level = st.selectbox("Nível de dicas usado nesta tentativa", [0, 1, 2, 3], index=0)

    st.subheader("Escolher cartas da sessão")
    default_ids = [c["id"] for c in cards[:10]]
    selected_ids = st.multiselect(
        "Cartas (IDs)",
        options=[c["id"] for c in cards],
        default=default_ids
    )
    if not selected_ids:
        st.info("Selecione pelo menos uma carta.")
        st.stop()

    if "session_idx" not in st.session_state:
        st.session_state.session_idx = 0
    if "session_attempts" not in st.session_state:
        st.session_state.session_attempts = {}

    max_idx = len(selected_ids) - 1
    colA, colB, colC = st.columns([1,1,2])
    with colA:
        if st.button("⬅️ Anterior") and st.session_state.session_idx > 0:
            st.session_state.session_idx -= 1
    with colB:
        if st.button("➡️ Próxima") and st.session_state.session_idx < max_idx:
            st.session_state.session_idx += 1
    with colC:
        st.write(f"Carta {st.session_state.session_idx + 1} de {len(selected_ids)}")

    current_id = selected_ids[st.session_state.session_idx]
    card = cards_by_id[current_id]

    st.divider()
    left, right = st.columns([2, 1])

    with left:
        st.subheader(f"Carta {card['id']} — {card['title']}")
        img = card_image(card["image"])
        if img:
            st.image(img, use_column_width=True)
        else:
            st.warning(f"Imagem não encontrada: {card['image']}")

        with st.expander("Pistas e resposta-alvo (terapeuta)"):
            st.write("Pistas:", " • ".join(card.get("keyClues", [])))
            st.write("Ação-alvo:", card.get("targetAction", ""))
            st.write("Frase-alvo:", card.get("targetPhrase", ""))
            if card.get("needsAdult"):
                st.write("Encaminhar:", card.get("adultType", "adulto responsável"))

    with right:
        st.subheader("Pontuação")
        detection = st.slider("Detecção (0–2)", 0, 2, 0)
        clues = st.slider("Pistas (0–2)", 0, 2, 0)
        cog = st.slider("Empatia cognitiva (0–2)", 0, 2, 0)
        action = st.slider("Ação (0–3)", 0, 3, 0)
        comm = st.slider("Comunicação (0–1)", 0, 1, 0)
        safety = st.slider("Segurança/Encaminhamento (0–2)", 0, 2, 0)

        total = total_score(detection, clues, cog, action, comm, safety)
        st.metric("Total", total)

        note = st.text_area("Observação clínica (opcional)", height=80)

        if st.button("Salvar tentativa desta carta"):
            st.session_state.session_attempts[current_id] = dict(
                card_id=current_id,
                hint_level=int(hint_level),
                detection=int(detection),
                clues=int(clues),
                cog_empathy=int(cog),
                action=int(action),
                communication=int(comm),
                safety=int(safety),
                total=int(total),
                notes=note.strip()
            )
            st.success("Tentativa salva (nesta sessão).")

    st.divider()
    st.subheader("Finalizar sessão")
    session_notes = st.text_area("Notas da sessão (opcional)", height=100)

    if st.button("✅ Salvar sessão"):
        if len(st.session_state.session_attempts) == 0:
            st.warning("Você ainda não salvou nenhuma tentativa.")
            st.stop()

        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sessions (client_id, created_at, mode, session_notes) VALUES (?,?,?,?)",
            (client_id, datetime.now().isoformat(), mode, session_notes.strip())
        )
        session_id = cur.lastrowid

        for att in st.session_state.session_attempts.values():
            conn.execute("""
                INSERT INTO attempts
                (session_id, card_id, hint_level, detection, clues, cog_empathy, action, communication, safety, total, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                session_id,
                att["card_id"],
                att["hint_level"],
                att["detection"],
                att["clues"],
                att["cog_empathy"],
                att["action"],
                att["communication"],
                att["safety"],
                att["total"],
                att["notes"]
            ))
        conn.commit()

        st.success(f"Sessão salva! (ID {session_id})")
        st.session_state.session_attempts = {}
        st.session_state.session_idx = 0

elif page == "Relatórios":
    st.title("Relatórios")

    df_clients = pd.read_sql_query("SELECT * FROM clients ORDER BY id DESC", conn)
    if df_clients.empty:
        st.info("Sem pacientes ainda.")
        st.stop()

    client_id = st.selectbox(
        "Escolha o paciente",
        df_clients["id"].tolist(),
        format_func=lambda x: f'#{x} — {df_clients[df_clients["id"]==x].iloc[0]["nickname"]}'
    )

    df_att = pd.read_sql_query("""
        SELECT s.id as session_id, s.created_at, s.mode,
               a.card_id, a.hint_level, a.detection, a.clues, a.cog_empathy,
               a.action, a.communication, a.safety, a.total, a.notes
        FROM attempts a
        JOIN sessions s ON s.id = a.session_id
        WHERE s.client_id = ?
        ORDER BY s.id DESC, a.id DESC
    """, conn, params=(client_id,))

    if df_att.empty:
        st.info("Sem tentativas ainda para este paciente.")
        st.stop()

    st.subheader("Resumo")
    st.write("Tentativas:", df_att.shape[0])
    st.write("Média total:", round(df_att["total"].mean(), 2))
    st.write("Média de dicas:", round(df_att["hint_level"].mean(), 2))

    st.subheader("Tabela")
    st.dataframe(df_att, use_container_width=True)

    st.subheader("Exportar CSV")
    csv = df_att.to_csv(index=False).encode("utf-8")
    st.download_button("Baixar CSV", csv, file_name="relatorio_tentativas.csv", mime="text/csv")
