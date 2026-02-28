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

def ensure_columns(conn, table: str, columns: dict):
    """
    columns: {col_name: sql_type}
    Ex.: {"prompts_green": "INTEGER DEFAULT 0"}
    """
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    for col, sql_type in columns.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}")
    conn.commit()

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

    # ✅ Migração: campos para padronização/UX
    ensure_columns(conn, "attempts", {
        "prompts_green": "INTEGER DEFAULT 0",
        "prompts_yellow": "INTEGER DEFAULT 0",
        "prompts_red": "INTEGER DEFAULT 0",
        "reformulations": "INTEGER DEFAULT 0",
        "response_class": "TEXT DEFAULT 'Alvo'",
        "alt_logic": "TEXT DEFAULT ''",
        "alt_diff": "TEXT DEFAULT ''"
    })

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
# ✅ Tags por carta (1–50): ⚠ Segurança / 👀 Atenção conjunta / 💬 Comunicação pragmática
# =========================
# Regra prática (MVP):
# - ⚠ Segurança: risco físico/encaminhamento/alto risco de queda/ferimento/emergência
# - 👀 Atenção conjunta: leitura forte de pista/estado do outro (muito "ver e integrar")
# - 💬 Comunicação pragmática: quando “como falar” pesa mais (constrangimento/filmar/zoação/fila/privacidade)
CARD_TAGS = {
    1:  ["⚠ Segurança", "👀 Atenção conjunta"],
    2:  ["👀 Atenção conjunta"],
    3:  ["👀 Atenção conjunta"],
    4:  ["👀 Atenção conjunta"],
    5:  ["⚠ Segurança", "👀 Atenção conjunta"],
    6:  ["⚠ Segurança", "👀 Atenção conjunta"],
    7:  ["👀 Atenção conjunta", "💬 Comunicação pragmática"],
    8:  ["👀 Atenção conjunta", "💬 Comunicação pragmática"],
    9:  ["⚠ Segurança", "👀 Atenção conjunta", "💬 Comunicação pragmática"],
    10: ["⚠ Segurança", "👀 Atenção conjunta"],

    11: ["💬 Comunicação pragmática", "👀 Atenção conjunta"],
    12: ["💬 Comunicação pragmática"],
    13: ["👀 Atenção conjunta", "💬 Comunicação pragmática"],
    14: ["👀 Atenção conjunta", "💬 Comunicação pragmática"],
    15: ["⚠ Segurança", "👀 Atenção conjunta"],
    16: ["⚠ Segurança", "💬 Comunicação pragmática"],
    17: ["⚠ Segurança", "💬 Comunicação pragmática", "👀 Atenção conjunta"],
    18: ["💬 Comunicação pragmática", "👀 Atenção conjunta"],
    19: ["⚠ Segurança", "👀 Atenção conjunta"],
    20: ["⚠ Segurança", "👀 Atenção conjunta", "💬 Comunicação pragmática"],

    21: ["💬 Comunicação pragmática"],
    22: ["⚠ Segurança", "💬 Comunicação pragmática"],
    23: ["⚠ Segurança", "💬 Comunicação pragmática"],
    24: ["⚠ Segurança", "💬 Comunicação pragmática"],
    25: ["⚠ Segurança", "👀 Atenção conjunta", "💬 Comunicação pragmática"],
    26: ["⚠ Segurança", "💬 Comunicação pragmática"],
    27: ["⚠ Segurança", "👀 Atenção conjunta"],
    28: ["⚠ Segurança", "💬 Comunicação pragmática"],
    29: ["⚠ Segurança", "👀 Atenção conjunta", "💬 Comunicação pragmática"],
    30: ["💬 Comunicação pragmática"],

    31: ["⚠ Segurança", "💬 Comunicação pragmática", "👀 Atenção conjunta"],
    32: ["⚠ Segurança", "💬 Comunicação pragmática"],
    33: ["⚠ Segurança", "💬 Comunicação pragmática"],
    34: ["💬 Comunicação pragmática"],
    35: ["💬 Comunicação pragmática"],
    36: ["💬 Comunicação pragmática"],
    37: ["💬 Comunicação pragmática"],
    38: ["⚠ Segurança", "💬 Comunicação pragmática"],
    39: ["⚠ Segurança", "💬 Comunicação pragmática"],
    40: ["⚠ Segurança", "💬 Comunicação pragmática"],

    41: ["💬 Comunicação pragmática"],
    42: ["💬 Comunicação pragmática"],
    43: ["💬 Comunicação pragmática"],
    44: ["⚠ Segurança", "💬 Comunicação pragmática"],
    45: ["👀 Atenção conjunta", "💬 Comunicação pragmática"],
    46: ["⚠ Segurança", "💬 Comunicação pragmática", "👀 Atenção conjunta"],
    47: ["⚠ Segurança", "💬 Comunicação pragmática", "👀 Atenção conjunta"],
    48: ["💬 Comunicação pragmática"],
    49: ["⚠ Segurança", "👀 Atenção conjunta", "💬 Comunicação pragmática"],
    50: ["⚠ Segurança", "👀 Atenção conjunta", "💬 Comunicação pragmática"],
}

def get_tags_for_card(card_id: int) -> list[str]:
    return CARD_TAGS.get(card_id, [])

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

# =========================
# ✅ Meta por carta (contadores / alternativa válida)
# =========================
def init_attempt_meta(card_id: int):
    key = f"meta_{card_id}"
    if key not in st.session_state:
        st.session_state[key] = {
            "prompts_green": 0,
            "prompts_yellow": 0,
            "prompts_red": 0,
            "reformulations": 0,
            "response_class": "Alvo",
            "alt_logic": "",
            "alt_diff": "",
            "red_unlocked": False
        }
    return st.session_state[key]

def get_default_micro_script():
    return [
        "O que está acontecendo?",
        "O que você faria primeiro?",
        "Por quê? / O que pode acontecer se…?"
    ]

def get_default_prompts():
    return {
        "green": [
            "Olha com calma a cena.",
            "O que está acontecendo aqui?",
            "O que você percebe no rosto/corpo/situação?"
        ],
        "yellow": [
            "Qual seria o primeiro passo?",
            "Tem mais de uma forma de agir?",
            "O que dá para fazer agora, em 1 passo?"
        ]
    }

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

        # ✅ Caixa do terapeuta com semáforo + tags + alternativa válida
        meta = init_attempt_meta(int(current_id))
        is_eval = (mode == "avaliacao")
        if not is_eval:
            meta["red_unlocked"] = True

        with st.expander("Caixa do terapeuta — condução (padronização)"):
            clues = get_card_clues(card)
            action_text = get_card_action(card)
            phrase_text = get_card_phrase(card)

            tags = get_tags_for_card(int(current_id))
            if tags:
                st.caption("Tags: " + " • ".join(tags))

            st.info("**O que observar (processo):** atenção social, iniciativa, empatia cognitiva, ação funcional, comunicação, segurança.")

            st.write("**Micro-roteiro (3 passos):**")
            for i, line in enumerate(get_default_micro_script(), start=1):
                st.write(f"{i}. {line}")

            st.caption("**Regra prática:** 1 pergunta + esperar; se necessário, 1 reformulação; depois prompts graduados.")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🟢 Prompts", meta["prompts_green"])
            c2.metric("🟡 Prompts", meta["prompts_yellow"])
            c3.metric("🔴 Dicas", meta["prompts_red"])
            c4.metric("Reformulação", f"{meta['reformulations']}/1")

            st.divider()

            st.write("### 🟢 Pistas (Avaliação OK)")
            st.write("Pistas:", " • ".join(clues) if clues else "—")

            prompts = get_default_prompts()
            green = prompts["green"]
            yellow = prompts["yellow"]

            colg, coly, colr = st.columns(3)

            with colg:
                st.write("**🟢 Neutro**")
                st.selectbox("Escolher prompt 🟢", green, key=f"sel_g_{current_id}")
                if st.button("Aplicar 🟢", key=f"btn_g_{current_id}"):
                    meta["prompts_green"] += 1
                    st.toast("Prompt 🟢 registrado")

            with coly:
                st.write("**🟡 Direcionamento leve**")
                st.selectbox("Escolher prompt 🟡", yellow, key=f"sel_y_{current_id}")
                if st.button("Aplicar 🟡", key=f"btn_y_{current_id}"):
                    meta["prompts_yellow"] += 1
                    st.toast("Prompt 🟡 registrado")

            with colr:
                st.write("**🔴 Dica/modelo**")
                if is_eval and not meta["red_unlocked"]:
                    st.warning("Modo Avaliação: Ação/Frase-alvo ficam ocultas por padrão.")
                    if st.button("Desbloquear dica 🔴 (registrar)", key=f"unlock_red_{current_id}"):
                        meta["red_unlocked"] = True
                        st.toast("Dica 🔴 desbloqueada (Avaliação)")

                if (not is_eval) or meta["red_unlocked"]:
                    st.write("**Ação-alvo (🔴):**", action_text if action_text else "—")
                    st.write("**Frase-alvo (🔴):**", phrase_text if phrase_text else "—")

                    colra, colrf = st.columns(2)
                    with colra:
                        if st.button("Registrar uso da AÇÃO-alvo 🔴", key=f"btn_red_action_{current_id}"):
                            meta["prompts_red"] += 1
                            st.toast("Uso de ação-alvo 🔴 registrado")
                    with colrf:
                        if st.button("Registrar uso da FRASE-alvo 🔴", key=f"btn_red_phrase_{current_id}"):
                            meta["prompts_red"] += 1
                            st.toast("Uso de frase-alvo 🔴 registrado")

            st.divider()

            st.write("### Reformulação (limite 1)")
            if meta["reformulations"] < 1:
                if st.button("Registrar 1 reformulação", key=f"btn_ref_{current_id}"):
                    meta["reformulations"] += 1
                    st.toast("Reformulação registrada")
            else:
                st.caption("Limite atingido. Use prompts graduados.")

            st.divider()

            st.write("### Classificação da resposta do paciente")
            meta["response_class"] = st.radio(
                "Marcar como:",
                ["Alvo", "Parcial", "Alternativa válida", "Inadequada"],
                index=["Alvo", "Parcial", "Alternativa válida", "Inadequada"].index(meta.get("response_class", "Alvo")),
                key=f"resp_class_{current_id}"
            )

            if meta["response_class"] == "Alternativa válida":
                meta["alt_logic"] = st.text_input(
                    "Qual foi a lógica? (curto)",
                    value=meta.get("alt_logic", ""),
                    key=f"alt_logic_{current_id}"
                )
                meta["alt_diff"] = st.text_input(
                    "Em que difere do alvo? (curto)",
                    value=meta.get("alt_diff", ""),
                    key=f"alt_diff_{current_id}"
                )

            if card.get("needsAdult"):
                st.warning(f"Encaminhar: {card.get('adultType', 'adulto responsável')}")

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
            meta = init_attempt_meta(int(current_id))

            st.session_state.session_attempts[current_id] = dict(
                card_id=int(current_id),
                hint_level=int(hint_level),
                detection=int(detection),
                clues=int(clues_score),
                cog_empathy=int(cog),
                action=int(action),
                communication=int(comm),
                safety=int(safety),
                total=int(total),
                notes=note.strip(),

                # ✅ NOVO (UX padronização)
                prompts_green=int(meta["prompts_green"]),
                prompts_yellow=int(meta["prompts_yellow"]),
                prompts_red=int(meta["prompts_red"]),
                reformulations=int(meta["reformulations"]),
                response_class=meta.get("response_class", "Alvo"),
                alt_logic=meta.get("alt_logic", ""),
                alt_diff=meta.get("alt_diff", "")
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
                (session_id, card_id, hint_level, detection, clues, cog_empathy, action, communication, safety, total, notes,
                 prompts_green, prompts_yellow, prompts_red, reformulations, response_class, alt_logic, alt_diff)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                att["notes"],
                att.get("prompts_green", 0),
                att.get("prompts_yellow", 0),
                att.get("prompts_red", 0),
                att.get("reformulations", 0),
                att.get("response_class", "Alvo"),
                att.get("alt_logic", ""),
                att.get("alt_diff", ""),
            ))
        conn.commit()

        st.success(f"Sessão salva! (ID {session_id})")
        st.session_state.session_attempts = {}
        st.session_state.session_idx = 0

        # ✅ opcional: limpa metas da sessão para não carregar contadores antigos
        for k in list(st.session_state.keys()):
            if str(k).startswith("meta_"):
                del st.session_state[k]

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
               a.action, a.communication, a.safety, a.total, a.notes,
               a.prompts_green, a.prompts_yellow, a.prompts_red, a.reformulations,
               a.response_class, a.alt_logic, a.alt_diff
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
    st.write("Média de dicas (nível selecionado):", round(df_att["hint_level"].mean(), 2))
    if "prompts_red" in df_att.columns:
        st.write("Média de 🔴 (dicas/modelo usadas):", round(df_att["prompts_red"].mean(), 2))
    if "response_class" in df_att.columns:
        st.write("% Alternativa válida:", round((df_att["response_class"] == "Alternativa válida").mean() * 100, 1), "%")

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

    manual_md = """
## 1) Objetivo do aplicativo
O aplicativo é uma ferramenta de treino e avaliação clínica de habilidades socioemocionais e de comunicação a partir de cartas com cenas. Ele ajuda o terapeuta a:
- selecionar estímulos (cartas) de acordo com o paciente e a meta terapêutica;
- conduzir a conversa e observar repertórios;
- registrar pontuação por domínios (detecção, pistas, empatia, ação etc.);
- gerar histórico e relatórios.

## 2) Papéis na sessão
### Papel do terapeuta
Você é o condutor e avaliador:
- seleciona as cartas (planejamento clínico);
- define o nível de ajuda (dicas);
- faz perguntas, oferece pistas graduais e modela linguagem quando necessário;
- observa e pontua o desempenho do paciente;
- registra observações clínicas.

### Papel do paciente
O paciente é o respondente ativo:
- descreve o que está vendo;
- identifica emoções/pistas;
- propõe o que fazer/dizer;
- ajusta respostas conforme recebe dicas;
- prática frases e ações alternativas.

Em geral: o terapeuta regula o “nível de estrutura”; o paciente fornece o material (percepção + interpretação + resposta).

## 3) Fluxo do app (o que cada página faz)
### A) Pacientes
Serve para:
- criar um paciente com nome/código;
- selecionar o “paciente ativo” para que a sessão e os relatórios fiquem vinculados.

Boas práticas:
- em “observações”, registre apenas dados clínicos necessários.

### B) Sessão
Aqui acontece a atividade.

Passo a passo recomendado:
1. Confirme o Paciente ativo (aparece no topo).
2. Escolha o Modo (treino guiado / independente / avaliação).
3. Defina o Nível de dicas usado nesta tentativa.
4. Em Escolher cartas da sessão, selecione os IDs das cartas que você quer trabalhar.
5. Use Anterior / Próxima para navegar nas cartas.
6. Para cada carta:
   - mostre o estímulo ao paciente;
   - conduza a exploração;
   - pontue e escreva observações;
   - clique **Salvar tentativa desta carta**.
7. Ao final, escreva **Notas da sessão** e clique **Salvar sessão**.

Importante: “IDs (1,2,3…)” = cartas selecionadas pelo terapeuta.  
“A, B, C” são as cenas/quadros dentro da carta (a sequência narrativa).

### C) Relatórios
Mostra o histórico do paciente com:
- tentativas por carta;
- médias;
- tabela completa;
- exportação em CSV.

## 4) Roteiro clínico para usar em cada carta
Use sempre do mais simples ao mais complexo:

### Etapa 1 — Detecção (o que aconteceu?)
Perguntas:
- “O que está acontecendo aqui?”
- “O que você vê primeiro?”
- “Qual é o problema principal?”

### Etapa 2 — Pistas (como você sabe?)
Perguntas:
- “O que na imagem te faz pensar isso?”
- “Que sinais mostram isso? (olhos, boca, corpo, situação)”
- “O que mudou do A para o B? e do B para o C?”

### Etapa 3 — Empatia cognitiva (o que cada um pensa/sente?)
Perguntas:
- “Como a pessoa se sente?”
- “O que ela pode estar pensando?”
- “O que a outra pessoa entende da situação?”

### Etapa 4 — Ação (o que fazer agora?)
Perguntas:
- “O que você faria se fosse você?”
- “Qual seria uma ajuda boa aqui?”
- “O que NÃO ajudaria?”

### Etapa 5 — Comunicação (o que dizer?)
Perguntas:
- “O que você diria?”
- “Como pedir ajuda?”
- “Dá pra falar de um jeito mais calmo/mais claro?”

### Etapa 6 — Segurança/Encaminhamento (quando precisa adulto?)
Perguntas:
- “Isso precisa de um adulto?”
- “É perigoso? tem risco?”
- “Qual adulto e por quê?”

## 5) Como usar o “Nível de Dicas” (0–3)
A ideia é padronizar para ficar comparável entre sessões.
- **0 = Sem dicas:** paciente responde espontaneamente.
- **1 = Dica leve:** pergunta orientadora (“olhe o rosto… o que te diz?”).
- **2 = Dica moderada:** você aponta a pista (“veja o copo no chão… isso muda o quê?”).
- **3 = Dica forte/modelagem:** você sugere estrutura de resposta ou oferece opções (“você pode dizer ‘vamos limpar juntos’ ou ‘posso ajudar?’”).

Regra de ouro: anote o menor nível de dica que desbloqueou a resposta.

## 6) Critérios de pontuação (como interpretar)
Você já tem os dados por domínio. Para ficar consistente, use este “guia rápido”:

### Detecção (0–2)
- **0:** não entende o que aconteceu / descrição confusa  
- **1:** entende parcialmente ou precisa de condução  
- **2:** entende claramente e com precisão  

### Pistas (0–2)
- **0:** não usa pistas visuais/situacionais  
- **1:** usa 1 pista ou vaga  
- **2:** usa múltiplas pistas relevantes (detalhes + contexto)  

### Empatia cognitiva (0–2)
- **0:** não atribui estados mentais / respostas rígidas  
- **1:** atribui um estado (“triste”) sem integração  
- **2:** integra emoção + motivo + perspectiva do outro  

### Ação (0–3)
- **0:** não propõe ajuda / propõe ação inadequada  
- **1:** ajuda genérica (“sei lá…”) ou incompleta  
- **2:** ajuda adequada e funcional  
- **3:** ajuda adequada + ajustada ao outro (timing/forma/alternativas)  

### Comunicação (0–1)
- **0:** não consegue formular frase adequada  
- **1:** formula frase adequada e compreensível  

### Segurança/Encaminhamento (0–2)
- **0:** não reconhece risco/necessidade de adulto quando existe  
- **1:** reconhece com ajuda  
- **2:** reconhece sozinho e indica adulto/encaminhamento apropriado  

## 7) O que registrar em “Observação clínica”
Use frases curtas e úteis. Exemplos:
- “Precisou de dica nível 2 para notar a pista X.”
- “Respondeu com ação concreta, mas sem frase.”
- “Empatia melhorou ao comparar A→B.”
- “Rigidez: repetiu mesma resposta em cartas diferentes.”
- “Boa generalização: transferiu estratégia de carta anterior.”

## 8) Estrutura de sessão sugerida (15 a 30 min)
- Aquecimento (2 min): 1 carta simples
- Núcleo (10–20 min): 3–6 cartas (dependendo da tolerância)
- Generalização (2–5 min): “isso acontece na vida real quando?”
- Fechamento (1–2 min): reforço + resumo de estratégia (“hoje você… percebeu pistas e pediu ajuda assim…”)

## 9) Mini “script” pronto para você falar (opcional)
Você pode usar literalmente:

“Vamos olhar essa cena. Primeiro você me diz o que aconteceu. Depois me mostra as pistas que te fizeram pensar isso. Em seguida, vamos pensar como cada pessoa está se sentindo e o que seria uma ajuda boa. No final, você treina uma frase que você diria.”

## 10) Solucionando problemas clínicos (o que fazer quando trava)
- Se o paciente só descreve objetos: peça mudança A→B→C (“o que mudou?”).
- Se ele não fala emoções: ofereça duas opções (“parece triste ou com raiva?”).
- Se dá resposta “certa” mas mecânica: pergunte “por quê?” e peça pistas.
- Se acelera e erra: volte ao básico — “me mostra onde você viu isso”.
"""
    st.markdown(manual_md)
