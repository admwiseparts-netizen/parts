import json
import re
import html
import streamlit as st
from openai import OpenAI

MAX_TITLE = 60

st.set_page_config(
    page_title="Wise Part Number",
    page_icon="🏍️",
    layout="centered",
)

st.markdown("""
<style>
.stApp { background: #090909; color: #f6f6f6; }
h1, h2, h3 { color: #ffd400 !important; }
.block-container { max-width: 760px; padding-top: 2rem; }

.stTextInput input {
    font-size: 22px !important;
    font-weight: 700 !important;
    text-transform: uppercase;
}

.stButton > button {
    width: 100%;
    min-height: 52px;
    border-radius: 10px;
    font-weight: 800;
    font-size: 18px;
}

.wise-card {
    border: 1px solid #2d2d2d;
    background: #141414;
    border-radius: 14px;
    padding: 18px;
    margin: 12px 0;
}

.title-result {
    font-size: 25px;
    line-height: 1.25;
    font-weight: 900;
}

.small-muted {
    color: #aaa;
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)


def get_api_key():
    try:
        return st.secrets["OPENAI_API_KEY"]
    except Exception:
        return None


def canonical_partnumber(value: str) -> str:
    """
    Forma canônica para comparação:
    - maiúsculas
    - remove espaços
    - remove hífens
    - remove pontos, barras e outros separadores
    - mantém apenas letras e números

    Ex:
    59c-27488-00 -> 59C2748800
    59C 27488 00 -> 59C2748800
    """
    value = (value or "").strip().upper()
    return re.sub(r"[^A-Z0-9]", "", value)


def display_partnumber(value: str) -> str:
    """
    Mantém uma apresentação limpa daquilo que o usuário digitou,
    sem obrigar um padrão de hífen específico.
    """
    value = (value or "").strip().upper()
    value = re.sub(r"\s+", "", value)
    return value


def generate_partnumber_variants(value: str):
    """
    Gera variações úteis para busca sem assumir que todas as marcas
    usam a mesma estrutura de part number.
    """
    original = display_partnumber(value)
    canonical = canonical_partnumber(value)

    variants = []

    def add(v):
        v = (v or "").strip()
        if v and v not in variants:
            variants.append(v)

    add(original)
    add(canonical)

    # Variações de caixa
    add(original.lower())
    add(canonical.lower())

    # Troca separadores comuns por hífen / espaço
    cleaned = re.sub(r"[._/\s]+", "-", original)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    add(cleaned)
    add(cleaned.replace("-", " "))
    add(cleaned.replace("-", ""))

    # Se o usuário já forneceu blocos, reaproveita esses blocos.
    blocks = [b for b in re.split(r"[^A-Za-z0-9]+", value.strip()) if b]
    if len(blocks) >= 2:
        blocks_upper = [b.upper() for b in blocks]
        add("-".join(blocks_upper))
        add(" ".join(blocks_upper))
        add("".join(blocks_upper))

    # Alguns formatos OEM comuns. Só gera variantes de busca;
    # não afirma que sejam a formatação "correta".
    n = len(canonical)

    patterns = {
        9: [(3, 3, 3)],
        10: [(3, 5, 2), (5, 3, 2)],
        11: [(5, 3, 3), (3, 5, 3)],
        12: [(5, 3, 4), (4, 4, 4)],
    }

    for pattern in patterns.get(n, []):
        pos = 0
        parts = []
        valid = True
        for size in pattern:
            chunk = canonical[pos:pos+size]
            if not chunk:
                valid = False
                break
            parts.append(chunk)
            pos += size
        if valid and pos == n:
            add("-".join(parts))
            add(" ".join(parts))

    return variants


def clean(text: str) -> str:
    text = (text or "").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def fit_title(title: str, limit: int = MAX_TITLE) -> str:
    title = clean(title)

    if len(title) <= limit:
        return title

    replacements = [
        (r"\bLado Direito\b", "Direito"),
        (r"\bLado Esquerdo\b", "Esquerdo"),
        (r"\bTraseiro\b", "Tras"),
        (r"\bDianteiro\b", "Diant"),
        (r"\bOriginal Genu[ií]no\b", "Original"),
        (r"\bGenu[ií]no\b", "Original"),
        (r"\b(\d{4}) a (\d{4})\b", r"\1-\2"),
    ]

    for pattern, repl in replacements:
        title = re.sub(pattern, repl, title, flags=re.I)
        title = clean(title)
        if len(title) <= limit:
            return title

    words = title.split()
    removable = {
        "PARA", "COMPATÍVEL", "COMPATIVEL",
        "PEÇA", "PECA", "MOTOCICLETA", "MOTO"
    }

    words = [w for w in words if w.upper() not in removable]
    title = " ".join(words)

    if len(title) <= limit:
        return title

    out = []
    for word in title.split():
        candidate = " ".join(out + [word])
        if len(candidate) > limit:
            break
        out.append(word)

    return " ".join(out).rstrip(" -")


def extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("A resposta não retornou JSON válido.")
        return json.loads(match.group(0))


def lookup_part(client: OpenAI, user_input: str):
    canonical = canonical_partnumber(user_input)
    variants = generate_partnumber_variants(user_input)

    variants_text = "\n".join(f"- {v}" for v in variants)

    prompt = f"""
Você é um catalogador técnico especializado em peças de motocicletas para e-commerce brasileiro.

O colaborador digitou este part number:
{user_input}

Forma canônica sem separadores:
{canonical}

Variações equivalentes que DEVEM ser consideradas na pesquisa:
{variants_text}

IMPORTANTE:
- Maiúsculas e minúsculas NÃO diferenciam um part number.
- Hífens, espaços, pontos e barras podem variar entre catálogos.
- Considere códigos equivalentes quando, removendo separadores e ignorando maiúsculas/minúsculas, o código alfanumérico for o mesmo.
- Pesquise tanto o código formatado quanto a forma sem separadores.
- Não descarte um resultado apenas porque o site usa hífen e o usuário não usou, ou vice-versa.
- Não invente compatibilidade.

Sua tarefa:
1. Identificar corretamente o nome da peça.
2. Identificar a marca.
3. Identificar o modelo ou modelos.
4. Identificar anos de aplicação.
5. Criar um título para Mercado Livre com no máximo 60 caracteres.

Regras do título:
- Prioridade: PEÇA + MARCA + MODELO + ANOS.
- Marca antes do modelo.
- Linguagem natural de busca no Brasil.
- Use "Original" somente quando houver evidência de OEM/genuíno.
- Não use palavras promocionais.
- Não coloque o part number no título, salvo se não houver identificação melhor.
- Se houver várias aplicações, use a principal no título e liste todas abaixo.
- Limite absoluto: 60 caracteres.

Retorne SOMENTE JSON válido:
{{
  "partnumber_digitado": "{display_partnumber(user_input)}",
  "partnumber_canonico": "{canonical}",
  "partnumber_identificado": "",
  "peca": "",
  "marca": "",
  "modelos": [""],
  "anos": "",
  "titulo": "",
  "confianca": "alta|media|baixa",
  "observacao": "",
  "fontes": [
    {{"nome": "", "url": ""}}
  ]
}}
"""

    response = client.responses.create(
        model=st.secrets.get("OPENAI_MODEL", "gpt-5"),
        tools=[{"type": "web_search"}],
        input=prompt,
    )

    return extract_json(response.output_text)


st.title("🏍️ Wise Part Number")
st.caption("Identificação de peça + título de Mercado Livre em até 60 caracteres.")

if not get_api_key():
    st.error("O aplicativo ainda não foi configurado pelo administrador.")
    st.stop()

pn_input = st.text_input(
    "Digite o Part Number",
    placeholder="Ex.: 59C-27488-00 ou 59c2748800",
)

st.caption("Pode digitar com ou sem hífen, com espaços, maiúsculas ou minúsculas.")

search = st.button("🔎 PESQUISAR PEÇA", type="primary")

if search:
    if not pn_input.strip():
        st.warning("Digite um part number.")
        st.stop()

    canonical = canonical_partnumber(pn_input)

    if not canonical:
        st.warning("Digite um part number válido.")
        st.stop()

    client = OpenAI(api_key=get_api_key())

    with st.spinner("Pesquisando código, variações e aplicações..."):
        try:
            data = lookup_part(client, pn_input)
        except Exception as e:
            st.error(f"Erro na pesquisa: {e}")
            st.stop()

    raw_title = clean(data.get("titulo", ""))
    title = fit_title(raw_title)

    if not title:
        st.error("Não foi possível gerar um título seguro para esse código.")
        st.stop()

    title_safe = html.escape(title)

    st.markdown(
        f"""
        <div class="wise-card">
            <div class="small-muted">TÍTULO MERCADO LIVRE</div>
            <div class="title-result">{title_safe}</div>
            <div class="small-muted">{len(title)}/60 caracteres</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    safe_js = (
        title
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
    )

    st.components.v1.html(
        f"""
        <button onclick="navigator.clipboard.writeText(`{safe_js}`); this.innerText='✓ COPIADO';"
            style="
                width:100%;
                height:48px;
                border:0;
                border-radius:9px;
                background:#ffd400;
                color:#111;
                font-weight:900;
                font-size:17px;
                cursor:pointer;">
            📋 COPIAR TÍTULO
        </button>
        """,
        height=58,
    )

    st.subheader("Identificação")

    entered = display_partnumber(pn_input)
    identified = data.get("partnumber_identificado") or entered

    st.write(f"**Código digitado:** {entered}")
    st.write(f"**Código identificado:** {identified}")
    st.write(f"**Peça:** {data.get('peca') or 'Não identificada'}")
    st.write(f"**Marca:** {data.get('marca') or 'Não identificada'}")

    modelos = data.get("modelos", [])
    if isinstance(modelos, list):
        modelos = ", ".join(str(x) for x in modelos if x)

    st.write(f"**Modelos:** {modelos or 'Não identificados'}")
    st.write(f"**Anos de aplicação:** {data.get('anos') or 'Não encontrados'}")

    conf = str(data.get("confianca", "")).lower()

    if conf == "alta":
        st.success("Confiança da identificação: ALTA")
    elif conf == "media":
        st.warning("Confiança da identificação: MÉDIA — confira as fontes.")
    else:
        st.error("Confiança da identificação: BAIXA — não cadastre sem conferência.")

    if data.get("observacao"):
        st.info(data["observacao"])

    fontes = data.get("fontes") or []

    if fontes:
        with st.expander("Ver fontes da pesquisa"):
            for source in fontes:
                if isinstance(source, dict):
                    name = source.get("nome") or "Fonte"
                    url = source.get("url") or ""

                    if url:
                        st.markdown(f"- [{name}]({url})")
                    else:
                        st.write(f"- {name}")
                else:
                    st.write(f"- {source}")

    with st.expander("Variações consideradas na pesquisa"):
        for variant in generate_partnumber_variants(pn_input):
            st.code(variant, language=None)

st.divider()
st.caption("Wise Moto Parts • Ferramenta interna de catalogação")
