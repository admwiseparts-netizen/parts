
import json
import re
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
.small-muted { color: #aaa; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

def api_key():
    try:
        return st.secrets["OPENAI_API_KEY"]
    except Exception:
        return None

def normalize_pn(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().upper())

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

    # Retira termos menos importantes antes de sacrificar peça/modelo.
    words = title.split()
    removable = {"PARA", "COMPATÍVEL", "COMPATIVEL", "PEÇA", "PECA", "MOTOCICLETA", "MOTO"}
    words = [w for w in words if w.upper() not in removable]
    title = " ".join(words)
    if len(title) <= limit:
        return title

    # Preserva apenas palavras completas.
    out = []
    for w in title.split():
        candidate = " ".join(out + [w])
        if len(candidate) > limit:
            break
        out.append(w)
    return " ".join(out).rstrip(" -")

def extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            raise ValueError("A resposta não retornou JSON válido.")
        return json.loads(m.group(0))

def lookup_part(client: OpenAI, pn: str):
    prompt = f"""
Você é um catalogador técnico de peças de motocicletas para e-commerce brasileiro.

Pesquise na web o part number: {pn}

Sua tarefa:
- identificar corretamente o nome da peça;
- identificar marca;
- identificar modelo ou modelos;
- identificar anos de aplicação;
- não inventar compatibilidade;
- quando houver conflito entre fontes, deixar isso claro;
- criar um título Mercado Livre de no máximo 60 caracteres.

Regras do título:
- priorize: PEÇA + MARCA + MODELO + ANOS;
- escreva marca antes do modelo;
- use linguagem natural de busca no Brasil;
- use "Original" somente se houver evidência de OEM/genuíno;
- não use palavras promocionais;
- não coloque o part number no título, salvo se não houver identificação melhor;
- se houver várias aplicações, use a principal no título e liste todas abaixo;
- limite absoluto de 60 caracteres.

Retorne SOMENTE JSON válido:
{{
  "partnumber": "{pn}",
  "peca": "",
  "marca": "",
  "modelos": [""],
  "anos": "",
  "titulo": "",
  "confianca": "alta|media|baixa",
  "observacao": "",
  "fontes": [{{"nome":"", "url":""}}]
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

if not api_key():
    st.error("O aplicativo ainda não foi configurado pelo administrador.")
    st.stop()

pn_input = st.text_input(
    "Digite o Part Number",
    placeholder="Ex.: 59C-27488-00",
    label_visibility="visible",
)

search = st.button("🔎 PESQUISAR PEÇA", type="primary")

if search:
    pn = normalize_pn(pn_input)
    if not pn:
        st.warning("Digite um part number.")
        st.stop()

    client = OpenAI(api_key=api_key())

    with st.spinner("Pesquisando peça e aplicação..."):
        try:
            data = lookup_part(client, pn)
        except Exception as e:
            st.error(f"Erro na pesquisa: {e}")
            st.stop()

    raw_title = clean(data.get("titulo", ""))
    title = fit_title(raw_title)

    if not title:
        st.error("Não foi possível gerar um título seguro para esse código.")
        st.stop()

    st.markdown(
        f"""
        <div class="wise-card">
            <div class="small-muted">TÍTULO MERCADO LIVRE</div>
            <div class="title-result">{title}</div>
            <div class="small-muted">{len(title)}/60 caracteres</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Copiar
    safe = title.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    st.components.v1.html(
        f"""
        <button onclick="navigator.clipboard.writeText(`{safe}`); this.innerText='✓ COPIADO';"
            style="
                width:100%;height:48px;border:0;border-radius:9px;
                background:#ffd400;color:#111;font-weight:900;
                font-size:17px;cursor:pointer;">
            📋 COPIAR TÍTULO
        </button>
        """,
        height=58,
    )

    st.subheader("Identificação")
    st.write(f"**Part number:** {pn}")
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
            for f in fontes:
                if isinstance(f, dict):
                    nome = f.get("nome") or "Fonte"
                    url = f.get("url") or ""
                    if url:
                        st.markdown(f"- [{nome}]({url})")
                    else:
                        st.write(f"- {nome}")
                else:
                    st.write(f"- {f}")

st.divider()
st.caption("Wise Moto Parts • Ferramenta interna de catalogação")
