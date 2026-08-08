
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



def generate_catalog_content(client: OpenAI, confirmed_data: dict):
    peca = confirmed_data.get("peca", "")
    marca = confirmed_data.get("marca", "")
    modelos = confirmed_data.get("modelos", [])
    anos = confirmed_data.get("anos", "")
    pn = confirmed_data.get("partnumber_identificado") or confirmed_data.get("partnumber_digitado", "")
    titulo = fit_title(clean(confirmed_data.get("titulo", "")))

    prompt = f"""
Você é especialista em SEO e cadastro de peças de motocicletas no Brasil.

A identificação abaixo JÁ FOI CONFIRMADA pelo colaborador. Não altere a aplicação.

Peça: {peca}
Marca: {marca}
Modelos: {modelos}
Anos: {anos}
Part number: {pn}
Título confirmado: {titulo}

Crie conteúdo comercial para cadastro da peça.

PALAVRAS-CHAVE:
- gere termos de busca realmente úteis;
- inclua peça, marca, modelos, anos, part number e variações naturais;
- evite repetição artificial;
- entregue em uma única linha separada por vírgulas.

DESCRIÇÃO COMPLETA:
- português do Brasil;
- comece com "Esse anúncio contém:";
- informe claramente peça, marca, modelos e anos;
- inclua o código da peça;
- não invente estado físico, garantia, procedência ou características não informadas;
- peça ao comprador para conferir fotos e código antes da compra;
- linguagem profissional e objetiva;
- pronta para copiar e colar em marketplace.

META DESCRIPTION:
- texto comercial natural;
- aproximadamente 140 a 160 caracteres;
- inclua peça + marca/modelo quando possível;
- não invente informações.

Retorne SOMENTE JSON válido:
{{
  "palavras_chave": "",
  "descricao": "",
  "meta_description": ""
}}
"""
    response = client.responses.create(
        model=st.secrets.get("OPENAI_MODEL", "gpt-5"),
        input=prompt,
    )
    return extract_json(response.output_text)


def perform_research(client, user_input, retry=0, rejected=None):
    canonical = canonical_partnumber(user_input)
    variants = generate_partnumber_variants(user_input)
    variants_text = "\n".join(f"- {v}" for v in variants)
    rejected_text = json.dumps(rejected, ensure_ascii=False) if rejected else "Nenhuma"

    prompt = f"""
Você é um catalogador técnico especializado em peças de motocicletas.

Part number digitado: {user_input}
Forma canônica: {canonical}

Variações equivalentes:
{variants_text}

Esta é a tentativa de pesquisa número {retry + 1}.

IDENTIFICAÇÃO REJEITADA ANTERIORMENTE:
{rejected_text}

Regras fundamentais:
- ignore diferenças de maiúsculas/minúsculas e separadores;
- pesquise código formatado e sem separadores;
- se houver uma identificação rejeitada anteriormente, NÃO repita a mesma conclusão sem encontrar evidência nova;
- procure outras aplicações, catálogos OEM, distribuidores, fichas de peças e referências cruzadas;
- não invente compatibilidade;
- identifique peça, marca, modelos e anos;
- crie título Mercado Livre de no máximo 60 caracteres;
- prioridade do título: PEÇA + MARCA + MODELO + ANOS;
- marca antes do modelo;
- se houver várias aplicações, escolha a principal no título.

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


# Estado da sessão
defaults = {
    "result": None,
    "confirmed": False,
    "content": None,
    "retry": 0,
    "last_input": "",
    "rejected": [],
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


st.title("🏍️ Wise Part Number")
st.caption("Part number → identificação → confirmação → conteúdo completo para cadastro.")

if not get_api_key():
    st.error("O aplicativo ainda não foi configurado pelo administrador.")
    st.stop()

pn_input = st.text_input(
    "Digite o Part Number",
    value=st.session_state.last_input,
    placeholder="Ex.: 59C-27488-00 ou 59c2748800",
)
st.caption("Pode digitar com ou sem hífen, espaços, maiúsculas ou minúsculas.")

if st.button("🔎 PESQUISAR PEÇA", type="primary"):
    if not pn_input.strip():
        st.warning("Digite um part number.")
        st.stop()

    st.session_state.last_input = pn_input
    st.session_state.retry = 0
    st.session_state.rejected = []
    st.session_state.confirmed = False
    st.session_state.content = None

    client = OpenAI(api_key=get_api_key())
    with st.spinner("Pesquisando código, variações e aplicações..."):
        try:
            st.session_state.result = perform_research(client, pn_input)
        except Exception as e:
            st.error(f"Erro na pesquisa: {e}")
            st.stop()


data = st.session_state.result

if data:
    title = fit_title(clean(data.get("titulo", "")))
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

    st.subheader("Identificação encontrada")
    st.write(f"**Código:** {data.get('partnumber_identificado') or display_partnumber(st.session_state.last_input)}")
    st.write(f"**Peça:** {data.get('peca') or 'Não identificada'}")
    st.write(f"**Marca:** {data.get('marca') or 'Não identificada'}")

    modelos = data.get("modelos", [])
    modelos_txt = ", ".join(str(x) for x in modelos if x) if isinstance(modelos, list) else str(modelos)
    st.write(f"**Modelos:** {modelos_txt or 'Não identificados'}")
    st.write(f"**Anos:** {data.get('anos') or 'Não encontrados'}")

    conf = str(data.get("confianca", "")).lower()
    if conf == "alta":
        st.success("Confiança da pesquisa: ALTA")
    elif conf == "media":
        st.warning("Confiança da pesquisa: MÉDIA")
    else:
        st.error("Confiança da pesquisa: BAIXA")

    if data.get("observacao"):
        st.info(data["observacao"])

    if not st.session_state.confirmed:
        st.markdown("### A peça identificada está correta?")
        col_yes, col_no = st.columns(2)

        with col_yes:
            if st.button("✅ SIM, ESTÁ CORRETA", type="primary", use_container_width=True):
                st.session_state.confirmed = True
                client = OpenAI(api_key=get_api_key())
                with st.spinner("Criando palavras-chave, descrição e meta description..."):
                    try:
                        st.session_state.content = generate_catalog_content(client, data)
                    except Exception as e:
                        st.error(f"Erro ao gerar conteúdo: {e}")
                st.rerun()

        with col_no:
            if st.button("❌ NÃO, PESQUISAR NOVAMENTE", use_container_width=True):
                st.session_state.rejected.append(data)
                st.session_state.retry += 1
                st.session_state.confirmed = False
                st.session_state.content = None

                client = OpenAI(api_key=get_api_key())
                with st.spinner("Procurando outra identificação para esse código..."):
                    try:
                        st.session_state.result = perform_research(
                            client,
                            st.session_state.last_input,
                            retry=st.session_state.retry,
                            rejected=st.session_state.rejected[-3:],
                        )
                    except Exception as e:
                        st.error(f"Erro na nova pesquisa: {e}")
                st.rerun()

    else:
        st.success("✓ Peça confirmada pelo colaborador")

        content = st.session_state.content
        if content:
            st.markdown("## Conteúdo para cadastro")

            st.markdown("### Título")
            st.code(title, language=None)
            st.caption(f"{len(title)}/60 caracteres")

            st.markdown("### Palavras-chave")
            st.text_area(
                "Palavras-chave",
                value=content.get("palavras_chave", ""),
                height=110,
                label_visibility="collapsed",
            )

            st.markdown("### Descrição completa")
            st.text_area(
                "Descrição completa",
                value=content.get("descricao", ""),
                height=300,
                label_visibility="collapsed",
            )

            meta = clean(content.get("meta_description", ""))
            st.markdown("### Meta description")
            st.text_area(
                "Meta description",
                value=meta,
                height=100,
                label_visibility="collapsed",
            )
            st.caption(f"{len(meta)} caracteres")

            st.download_button(
                "⬇️ BAIXAR CONTEÚDO .TXT",
                data=(
                    f"TÍTULO\n{title}\n\n"
                    f"PALAVRAS-CHAVE\n{content.get('palavras_chave','')}\n\n"
                    f"DESCRIÇÃO\n{content.get('descricao','')}\n\n"
                    f"META DESCRIPTION\n{meta}\n"
                ),
                file_name=f"{canonical_partnumber(st.session_state.last_input)}_cadastro.txt",
                mime="text/plain",
                use_container_width=True,
            )

        if st.button("↩️ CORRIGIR IDENTIFICAÇÃO / PESQUISAR NOVAMENTE", use_container_width=True):
            st.session_state.rejected.append(data)
            st.session_state.retry += 1
            st.session_state.confirmed = False
            st.session_state.content = None
            client = OpenAI(api_key=get_api_key())
            with st.spinner("Procurando outra identificação..."):
                try:
                    st.session_state.result = perform_research(
                        client,
                        st.session_state.last_input,
                        retry=st.session_state.retry,
                        rejected=st.session_state.rejected[-3:],
                    )
                except Exception as e:
                    st.error(f"Erro: {e}")
            st.rerun()

    fontes = data.get("fontes") or []
    if fontes:
        with st.expander("Ver fontes da identificação"):
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

st.divider()
st.caption("Wise Moto Parts • Ferramenta interna de catalogação")
