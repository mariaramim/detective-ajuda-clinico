import base64
import json
import os
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st
from PIL import Image

# ✅ PRECISA ser o primeiro comando do Streamlit
st.set_page_config(page_title="Detective da Ajuda — Clínico", layout="wide")

# =========================
# Dev mode (oculta ferramentas)
# =========================
DEV_MODE = os.getenv("DEV_MODE", "0").strip() == "1"

# =========================
# Branding (logo na sidebar)
# =========================
LOGO_PATH = os.path.join("assets", "branding", "logo.png")
LOGO_WIDTH = 260  # ajuste aqui (ex.: 240, 260, 280)

def render_sidebar_logo():
    # 🔒 botão dev escondido (só aparece se DEV_MODE=1)
    if DEV_MODE:
        if st.sidebar.button("🔄 Recarregar cartas"):
            st.cache_data.clear()
            st.rerun()

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
    for k in ["title", "titulo", "name", "nome", "scenario", "cenario", "heading"]:
        v = card.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return f"Carta {card.get('id','?')}"

# =========================
# ✅ Overrides (1–50): pistas + ação-alvo + frase-alvo
# =========================
# Observação: usei:
# - Pistas: texto após "Pistas:"
# - Ação-alvo: texto após "🎯"
# - Frase-alvo: frase 👶 (infantil), por ser a mais direta p/ treino
CARD_SUPPORT = {
    1:  {"clues": ["poça no chão", "expressão preocupada", "pano faltando"],
         "action": "Oferecer pano/papel e sinalizar o chão para evitar escorregões",
         "phrase": "Caiu água. Quer ajuda pra limpar?"},
    2:  {"clues": ["choro", "procura com olhos/mãos", "fala repetida"],
         "action": "Acolher, perguntar o que houve e ajudar a buscar",
         "phrase": "Você perdeu? Vamos procurar juntos?"},
    3:  {"clues": ["sacolas grandes", "postura curvada", "passos lentos"],
         "action": "Oferecer carregar uma sacola e abrir a porta",
         "phrase": "Posso pegar essa sacola?"},
    4:  {"clues": ["revira bolsos", "tensão", "fala “cadê?”"],
         "action": "Organizar a busca (lugares prováveis) e ajudar a procurar",
         "phrase": "Quer que eu procure também?"},
    5:  {"clues": ["“ai”", "mão no local", "careta"],
         "action": "Colocar em água corrente fria e chamar um adulto",
         "phrase": "Vamos pôr na água. Vou chamar um adulto."},
    6:  {"clues": ["estica braço", "sobe em cadeira", "risco de cair"],
         "action": "Ajudar de forma segura para prevenir queda",
         "phrase": "Quer que eu pegue pra você?"},
    7:  {"clues": ["olhar baixo", "silêncio", "ombros caídos"],
         "action": "Checar como está e oferecer presença/apoio",
         "phrase": "Você tá triste? Quer um abraço ou ficar junto?"},
    8:  {"clues": ["espirros", "desconforto", "procura lenço"],
         "action": "Oferecer lenço/ajuda prática e avisar responsável se necessário",
         "phrase": "Quer um lenço? Vou buscar."},
    9:  {"clues": ["olhos fechados", "luz incomoda", "irritação"],
         "action": "Reduzir estímulos e oferecer água/pausa",
         "phrase": "Quer água e silêncio?"},
    10: {"clues": ["coleira presa/enroscada", "animal agitado/assustado"],
         "action": "Chamar um adulto/dono e soltar com cuidado, sem assustar",
         "phrase": "Vou chamar um adulto pra ajudar o bichinho."},

    11: {"clues": ["itens no chão", "pressa", "constrangimento"],
         "action": "Ajudar a recolher e aliviar a vergonha (sinalizar se corredor cheio)",
         "phrase": "Eu pego esses!"},
    12: {"clues": ["olha mapa", "hesita", "pergunta"],
         "action": "Orientar e acompanhar até a sala/local correto",
         "phrase": "Você procura qual sala? Eu te mostro."},
    13: {"clues": ["olhar confuso", "apaga muito", "trava"],
         "action": "Ajudar por etapas (mostrar o primeiro passo) e/ou chamar professor",
         "phrase": "Quer que eu mostre o primeiro passo?"},
    14: {"clues": ["sozinho", "olhando grupo", "sem atividade"],
         "action": "Convidar para algo simples com opção (sem pressionar)",
         "phrase": "Quer brincar com a gente?"},
    15: {"clues": ["pilha alta", "dificuldade de ver", "passos lentos"],
         "action": "Segurar porta e levar parte dos livros",
         "phrase": "Quer que eu segure a porta?"},
    16: {"clues": ["cadarço arrastando"],
         "action": "Avisar rapidamente para evitar queda (sem tocar)",
         "phrase": "Seu cadarço soltou."},
    17: {"clues": ["vítima recua", "cara triste", "grupo rindo"],
         "action": "Proteger a vítima e chamar um adulto/professora com segurança",
         "phrase": "Vem comigo. Vou chamar a professora."},
    18: {"clues": ["olha comida", "vergonha", "fala baixa"],
         "action": "Ajudar sem humilhar (compartilhar se possível e acionar adulto)",
         "phrase": "Quer um pouco do meu? Vamos falar com a tia."},
    19: {"clues": ["poça grande", "risco de escorregar"],
         "action": "Sinalizar/avisar e buscar pano/limpeza (segurança primeiro)",
         "phrase": "Cuidado! Vou chamar um adulto."},
    20: {"clues": ["tensão", "respiração rápida", "mãos nos ouvidos"],
         "action": "Co-regular e levar para ambiente mais calmo, chamando suporte se necessário",
         "phrase": "Vamos pra um lugar quietinho?"},

    21: {"clues": ["objeto no chão", "pessoa procura"],
         "action": "Pegar e devolver imediatamente",
         "phrase": "Caiu isso aqui!"},
    22: {"clues": ["passos lentos", "bengala", "insegurança"],
         "action": "Pedir consentimento e ajudar a atravessar com segurança",
         "phrase": "Quer ajuda pra atravessar?"},
    23: {"clues": ["obstáculo na rampa", "hesitação"],
         "action": "Remover obstáculo/liberar rota acessível",
         "phrase": "Tem coisa na rampa. Quer que eu tire?"},
    24: {"clues": ["esforço", "degrau alto", "porta pesada"],
         "action": "Oferecer ajuda seguindo instruções da pessoa responsável",
         "phrase": "Quer que eu segure a porta?"},
    25: {"clues": ["lágrimas", "encolhida", "isolada"],
         "action": "Oferecer ajuda com cuidado e checar segurança",
         "phrase": "Você quer ajuda? Quer que eu chame alguém?"},
    26: {"clues": ["assustada", "procura adulto"],
         "action": "Acionar segurança/funcionário e ficar junto (não levar sozinho)",
         "phrase": "Vamos achar um adulto que trabalha aqui."},
    27: {"clues": ["sem dono por perto", "perto da rua", "agitado"],
         "action": "Evitar susto e buscar o dono/ajuda para afastar do perigo",
         "phrase": "De quem é o cachorro? Cuidado!"},
    28: {"clues": ["caixa tampa visão", "passos incertos"],
         "action": "Abrir porta e orientar caminho removendo obstáculos",
         "phrase": "Quer que eu abra a porta?"},
    29: {"clues": ["sacola rasga", "itens rolam", "vergonha"],
         "action": "Checar se machucou e ajudar a recolher",
         "phrase": "Você tá bem? Eu ajudo a pegar."},
    30: {"clues": ["franze testa", "aproxima o rosto"],
         "action": "Ajudar a ler/interpretar com calma e apontar informação",
         "phrase": "Quer que eu leia pra você?"},

    31: {"clues": ["balança em pé", "idoso/gestante", "olhar cansado"],
         "action": "Ceder lugar e facilitar segurança",
         "phrase": "Quer sentar aqui?"},
    32: {"clues": ["esforço", "paradas", "degraus"],
         "action": "Ajudar com a mala de forma segura (um lado) ou chamar funcionário",
         "phrase": "Quer ajuda com a mala?"},
    33: {"clues": ["desequilíbrio", "bengala no chão"],
         "action": "Pegar e devolver rapidamente, checando se está bem",
         "phrase": "Sua bengala caiu!"},
    34: {"clues": ["tenta repetidas vezes", "fila cresce"],
         "action": "Chamar funcionário/suporte oficial para evitar constrangimento",
         "phrase": "Quer que eu chame um moço?"},
    35: {"clues": ["objeto no chão atrás", "pessoa não percebe"],
         "action": "Avisar e devolver discretamente",
         "phrase": "Caiu sua carteira!"},
    36: {"clues": ["olha ao redor", "pausa", "vergonha"],
         "action": "Resolver com discrição (chamar garçom/pegar outro)",
         "phrase": "Quer outro talher?"},
    37: {"clues": ["puxa repetido", "ansiedade"],
         "action": "Orientar com calma e indicar outra cabine",
         "phrase": "Tá ocupado. Tem outro ali."},
    38: {"clues": ["bilhete na mão", "hesita", "atrapalha passagem"],
         "action": "Ajudar com discrição a localizar fileira/assento",
         "phrase": "Qual número? Eu ajudo."},
    39: {"clues": ["estica braço", "risco de queda"],
         "action": "Pegar o produto com segurança ou chamar funcionário",
         "phrase": "Quer que eu pegue?"},
    40: {"clues": ["papel tremendo", "preocupação"],
         "action": "Encaminhar para farmacêutico (evitar “interpretar” sozinho)",
         "phrase": "Vamos chamar o farmacêutico."},

    41: {"clues": ["folhas voando", "tensão"],
         "action": "Ajudar a recolher e organizar com discrição",
         "phrase": "Eu ajudo a juntar."},
    42: {"clues": ["silêncio", "olhar confuso", "notas vazias"],
         "action": "Dar suporte sem expor (explicar depois / mandar resumo)",
         "phrase": "Quer que eu explique depois?"},
    43: {"clues": ["força", "frustração", "tenta repetidas"],
         "action": "Oferecer ajuda para abrir (respeitando se não quiser)",
         "phrase": "Quer que eu abra?"},
    44: {"clues": ["tom alto", "desorientação", "pressa"],
         "action": "Acolher e direcionar com calma, evitando escalada",
         "phrase": "Eu te mostro onde é."},
    45: {"clues": ["bocejos", "lentidão", "irritabilidade"],
         "action": "Oferecer pausa e apoio, ajustando demanda",
         "phrase": "Quer uma pausa?"},
    46: {"clues": ["tremor", "olhar fixo", "hiperventila"],
         "action": "Co-regular (respiração/água) e levar para lugar calmo, acionar suporte se necessário",
         "phrase": "Quer água? Vamos pra um lugar calmo."},
    47: {"clues": ["comida no chão", "vergonha", "pessoas olhando"],
         "action": "Checar se está bem e acionar limpeza/guardanapo com discrição",
         "phrase": "Você tá bem? Eu chamo alguém."},
    48: {"clues": ["inclina cabeça", "“como?”", "leitura labial"],
         "action": "Falar de frente, mais devagar, com apoio visual",
         "phrase": "Eu falo de frente e devagar."},
    49: {"clues": ["dor forte", "suor", "senta/colapsa"],
         "action": "Acionar emergência e ficar junto (ação rápida e segura)",
         "phrase": "Vou chamar ajuda agora. Fica comigo."},
    50: {"clues": ["joelho ralado", "vergonha", "objeto no chão"],
         "action": "Checar ferimento e oferecer cuidado/curativo, chamar responsável se menor",
         "phrase": "Você tá bem? Quer curativo?"},
}

# =========================
# Leitura robusta (JSON pode variar)
# =========================
def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        # tenta separar por •, |, ; ou quebra de linha
        parts = []
        for sep in ["•", "|", ";", "\n", ","]:
            if sep in v:
                parts = [p.strip() for p in v.split(sep)]
                break
        if not parts:
            parts = [v.strip()]
        return [p for p in parts if p]
    return []

def get_card_clues(card: dict) -> list[str]:
    # prioridade: override
    cid = card.get("id")
    if isinstance(cid, int) and cid in CARD_SUPPORT:
        return CARD_SUPPORT[cid]["clues"]

    for k in ["keyClues", "clues", "pistas", "hints", "keys", "key_clues"]:
        if k in card and card.get(k) not in (None, ""):
            return _as_list(card.get(k))
    return []

def get_card_action(card: dict) -> str:
    cid = card.get("id")
    if isinstance(cid, int) and cid in CARD_SUPPORT:
        return CARD_SUPPORT[cid]["action"]

    for k in ["targetAction", "acaoAlvo", "acao_alvo", "action", "target_action"]:
        v = card.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def get_card_phrase(card: dict) -> str:
    cid = card.get("id")
    if isinstance(cid, int) and cid in CARD_SUPPORT:
        return CARD_SUPPORT[cid]["phrase"]

    for k in ["targetPhrase", "fraseAlvo", "frase_alvo", "phrase", "target_phrase"]:
        v = card.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

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

    options_ids = [c.get("id") for c in cards if c.get("id") is not None]

    selected_ids = st.multiselect(
        "Cartas (IDs)",
        options=options_ids,
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

    left, right = st.columns([3, 1])

    with left:
        title = get_card_title(card)
        st.subheader(f"Carta {current_id} — {title}")

        img = card_image(card.get("image", ""))
        if img:
            st.image(img, use_column_width=True)
        else:
            st.warning(f"Imagem não encontrada: {card.get('image','')}")

        # ✅ agora robusto + garante preenchimento via override 1–50
        with st.expander("Pistas e resposta-alvo (terapeuta)"):
            clues = get_card_clues(card)
            action_text = get_card_action(card)
            phrase_text = get_card_phrase(card)

            st.write("Pistas:", " • ".join(clues) if clues else "—")
            st.write("Ação-alvo:", action_text if action_text else "—")
            st.write("Frase-alvo:", phrase_text if phrase_text else "—")

            if card.get("needsAdult"):
                st.write("Encaminhar:", card.get("adultType", "adulto responsável"))

    with right:
        st.subheader("Pontuação")
        detection = st.slider("Detecção (0–2)", 0, 2, 0)
        clues_score = st.slider("Pistas (0–2)", 0, 2, 0)
        cog = st.slider("Empatia cognitiva (0–2)", 0, 2, 0)
        action = st.slider("Ação (0–3)", 0, 3, 0)
        comm = st.slider("Comunicação (0–1)", 0, 1, 0)
        safety = st.slider("Segurança/Encaminhamento (0–2)", 0, 2, 0)

        total = total_score(detection, clues_score, cog, action, comm, safety)
        st.metric("Total", total)

        note = st.text_area("Observação clínica (opcional)", height=80)

        if st.button("Salvar tentativa desta carta"):
            st.session_state.session_attempts[current_id] = dict(
                card_id=current_id,
                hint_level=int(hint_level),
                detection=int(detection),
                clues=int(clues_score),
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
# Página: Manual
# =========================
elif page == "Manual":
    st.title("Manual do Terapeuta — Detective da Ajuda (Clínico)")
    st.caption("Versão clínica (consulta rápida).")

    manual_md = """
## 1) Objetivo do aplicativo
Ferramenta de **treino e avaliação clínica** de habilidades socioemocionais e comunicação com cartas (cenas).

## 2) Papéis na sessão
**Terapeuta:** seleciona cartas, conduz com dicas graduais, observa e pontua.  
**Paciente:** descreve, identifica pistas/emoções, propõe ação/frase.

## 3) Fluxo
Pacientes → Sessão → Relatórios.  
**A/B/C** = quadros da carta.

## 4) Nível de dicas (0–3)
0 sem dicas; 1 dica leve; 2 dica moderada; 3 modelagem.

## 5) Pontuação
Detecção, Pistas, Empatia, Ação, Comunicação, Segurança.
"""
    st.markdown(manual_md)

    st.download_button(
        "Baixar manual (arquivo .md)",
        data=manual_md.encode("utf-8"),
        file_name="manual_terapeuta_detective_ajuda.md",
        mime="text/markdown",
    )
