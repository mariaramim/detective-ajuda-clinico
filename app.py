import base64
import json
import os
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st
from PIL import Image

# ✅ PRECISA ser o primeiro comando Streamlit
st.set_page_config(page_title="Detective da Ajuda — Clínico", layout="wide")

# =========================
# Branding (logo na sidebar)
# =========================
LOGO_PATH = os.path.join("assets", "branding", "logo.png")
LOGO_WIDTH = 260  # ajuste aqui (ex.: 240, 260, 280)

def render_sidebar_logo():
    if st.sidebar.button("🔄 Recarregar cartas"):
    st.cache_data.clear()
    st.rerun()
    # um pequeno respiro no topo
    st.sidebar.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)

    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        st.sidebar.markdown(
            f"""
            <div style="text-align:center; padding-top:0px; padding-bottom:8px;">
                <img src="data:image/png;base64,{b64}"
                     style="width:{LOGO_WIDTH}px; max-width:100%; height:auto; display:inline-block;"
                     alt="Tecnoneuro" />
            </div>
            """,
            unsafe_allow_html=True
        )

    st.sidebar.markdown("---")

render_sidebar_logo()

# =========================
# Paths e DB
# =========================
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

def _cards_mtime() -> float:
    try:
        return os.path.getmtime(CARDS_PATH)
    except OSError:
        return 0.0

@st.cache_data(show_spinner=False)
def load_cards(_mtime: float):
    with open(CARDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def card_image(path: str):
    return Image.open(path) if path and os.path.exists(path) else None

def total_score(detection, clues, cog_empathy, action, communication, safety):
    return int(detection + clues + cog_empathy + action + communication + safety)

def get_card_title(card: dict) -> str:
    """
    Deixa o app robusto: se o JSON tiver 'title' ou 'titulo' ou 'name', etc.
    """
    for k in ["title", "titulo", "name", "nome", "scenario", "cenario", "heading"]:
        v = card.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "(sem título)"

cards = load_cards(_cards_mtime())
cards_by_id = {c.get("id"): c for c in cards if c.get("id") is not None}
conn = get_conn()

# =========================
# Navegação
# =========================
st.sidebar.title("Navegação")
page = st.sidebar.radio("Ir para:", ["Pacientes", "Sessão", "Relatórios", "Manual"])

# =========================
# Página: Pacientes
# =========================
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

# =========================
# Página: Sessão
# =========================
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

    default_ids = [c.get("id") for c in cards[:10] if c.get("id") is not None]
    if not default_ids:
        default_ids = [c.get("id") for c in cards if c.get("id") is not None]

    selected_ids = st.multiselect(
        "Cartas (IDs)",
        options=[c.get("id") for c in cards if c.get("id") is not None],
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
    colA, colB, colC = st.columns([1, 1, 2])
    with colA:
        if st.button("⬅️ Anterior") and st.session_state.session_idx > 0:
            st.session_state.session_idx -= 1
    with colB:
        if st.button("➡️ Próxima") and st.session_state.session_idx < max_idx:
            st.session_state.session_idx += 1
    with colC:
        st.write(f"Carta {st.session_state.session_idx + 1} de {len(selected_ids)}")

    current_id = selected_ids[st.session_state.session_idx]
    card = cards_by_id.get(current_id, {})

    st.divider()

    # ✅ Estímulo grande (como antes): esquerda bem larga
    left, right = st.columns([3, 1])

    with left:
        title = get_card_title(card)
        st.subheader(f"Carta {current_id} — {title}")

        img = card_image(card.get("image", ""))
        if img:
            st.image(img, use_column_width=True)
        else:
            st.warning(f"Imagem não encontrada: {card.get('image','')}")

        with st.expander("Pistas e resposta-alvo (terapeuta)"):
            st.write("Pistas:", " • ".join(card.get("keyClues", []) or []))
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

# =========================
# Página: Relatórios
# =========================
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

# =========================
# Página: Manual (Opção 1)
# =========================
elif page == "Manual":
    st.title("Manual do Terapeuta — Detective da Ajuda (Clínico)")
    st.caption("Versão clínica (consulta rápida).")

    manual_md = """
## 1) Objetivo do aplicativo
O aplicativo é uma ferramenta de **treino e avaliação clínica** de habilidades socioemocionais e de comunicação a partir de cartas com cenas. Ele ajuda o terapeuta a:
- selecionar estímulos (cartas) de acordo com o paciente e a meta terapêutica;
- conduzir a conversa e observar repertórios;
- registrar pontuação por domínios (detecção, pistas, empatia, ação etc.);
- gerar histórico e relatórios.

---

## 2) Papéis na sessão

### Papel do terapeuta
Você é o **condutor e avaliador**:
- seleciona as cartas (planejamento clínico);
- define o nível de ajuda (dicas);
- faz perguntas, oferece pistas graduais e modela linguagem quando necessário;
- observa e pontua o desempenho do paciente;
- registra observações clínicas.

### Papel do paciente
O paciente é o **respondente ativo**:
- descreve o que está vendo;
- identifica emoções/pistas;
- propõe o que fazer/dizer;
- ajusta respostas conforme recebe dicas;
- pratica frases e ações alternativas.

**Regra geral:** o terapeuta regula o “nível de estrutura”; o paciente fornece o material (percepção + interpretação + resposta).

---

## 3) Fluxo do app

### A) Pacientes
- cria um paciente com **nome/código** (evitar dados sensíveis);
- seleciona o “paciente ativo” para vincular sessão e relatórios.

### B) Sessão
1. Confirme o *Paciente ativo*.
2. Escolha o **Modo**.
3. Defina o **Nível de dicas** (0–3).
4. Selecione as **Cartas (IDs)**.
5. Use **Anterior/Próxima**.
6. Para cada carta: conduza, pontue, registre e **Salvar tentativa desta carta**.
7. Ao final: **Notas da sessão** → **Salvar sessão**.

**IDs** = cartas escolhidas pelo terapeuta.  
**A/B/C** = quadros dentro da carta (sequência narrativa).

### C) Relatórios
Histórico + médias + tabela + exportação CSV.

---

## 4) Roteiro clínico por carta
**Detecção → Pistas → Empatia cognitiva → Ação → Comunicação → Segurança/Encaminhamento**

---

## 5) Nível de dicas (0–3)
0 sem dicas; 1 dica leve; 2 dica moderada; 3 modelagem.

---

## 6) Pontuação (guia rápido)
- Detecção (0–2)
- Pistas (0–2)
- Empatia cognitiva (0–2)
- Ação (0–3)
- Comunicação (0–1)
- Segurança/Encaminhamento (0–2)

---

## 7) Observação clínica
Use frases curtas (ex.: “Precisou de dica 2 para notar pista X”).
"""

    st.markdown(manual_md)

    # opcional: download (se quiser tirar, eu removo)
    st.download_button(
        "Baixar manual (arquivo .md)",
        data=manual_md.encode("utf-8"),
        file_name="manual_terapeuta_detective_ajuda.md",
        mime="text/markdown",
    )
