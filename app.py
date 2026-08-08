import re
import html
from collections import Counter
import streamlit as st
from ddgs import DDGS

MAX_TITLE = 60

st.set_page_config(page_title="Wise Part Number", page_icon="🏍️", layout="centered")

st.markdown("""
<style>
.stApp {background:#090909;color:#f6f6f6}
h1,h2,h3 {color:#ffd400!important}
.block-container {max-width:800px;padding-top:2rem}
.stTextInput input {font-size:22px!important;font-weight:700!important;text-transform:uppercase}
.stButton>button {width:100%;min-height:50px;border-radius:10px;font-weight:800}
.card {border:1px solid #333;background:#141414;border-radius:14px;padding:18px;margin:12px 0}
.title {font-size:24px;font-weight:900}
.muted {color:#aaa;font-size:13px}
</style>
""", unsafe_allow_html=True)

def canonical(v):
    return re.sub(r"[^A-Z0-9]", "", (v or "").upper())

def variants(v):
    raw = (v or "").strip().upper()
    can = canonical(raw)
    out = []
    def add(x):
        if x and x not in out: out.append(x)
    add(raw); add(can)
    blocks = [x for x in re.split(r"[^A-Z0-9]+", raw) if x]
    if len(blocks) > 1:
        add("-".join(blocks)); add(" ".join(blocks))
    n=len(can)
    for pat in {9:[(3,3,3)],10:[(3,5,2),(5,3,2)],11:[(5,3,3),(3,5,3)],12:[(5,3,4)]}.get(n,[]):
        p=0; b=[]
        for size in pat:
            b.append(can[p:p+size]); p+=size
        add("-".join(b)); add(" ".join(b))
    return out

def fit_title(s):
    s=re.sub(r"\s+"," ",s).strip(" -|")
    for a,b in [
        (" Peça Original"," Original"),(" Genuíno"," Original"),
        (" Genuino"," Original"),(" Lado Direito"," Direito"),
        (" Lado Esquerdo"," Esquerdo")]:
        s=s.replace(a,b)
    s=re.sub(r"(\d{4})\s+a\s+(\d{4})",r"\1-\2",s,flags=re.I)
    if len(s)<=60:return s
    words=s.split(); out=[]
    for w in words:
        if len(" ".join(out+[w]))>60:break
        out.append(w)
    return " ".join(out)

def search_web(pn):
    qs=[]
    vs=variants(pn)
    # Search multiple exact variants plus motorcycle context.
    for v in vs[:5]:
        qs.append(f'"{v}" moto peça')
    results=[]; seen=set()
    with DDGS() as d:
        for q in qs:
            try:
                for r in d.text(q, max_results=8):
                    url=r.get("href","")
                    if url and url not in seen:
                        seen.add(url)
                        results.append({
                            "title":r.get("title",""),
                            "body":r.get("body",""),
                            "url":url
                        })
            except Exception:
                pass
    return results

PART_TERMS = [
    "CAPA DO SILENCIADOR", "PROTETOR DO SILENCIADOR", "PROTETOR DO TUBO DE ESCAPE",
    "CAPA PROTEÇÃO DO ESCAPAMENTO", "CAPA PROTECAO DO ESCAPAMENTO",
    "CARENAGEM", "RABETA", "PARALAMA", "FAROL", "LANTERNA", "PISCA",
    "SUPORTE", "PEDALEIRA", "MANOPLA", "MANETE", "RADIADOR", "PAINEL",
    "BENGALA", "MESA SUPERIOR", "MESA INFERIOR", "BALANÇA", "BALANCA",
    "BOMBA DE COMBUSTÍVEL", "BOMBA DE COMBUSTIVEL", "ESTATOR", "RETIFICADOR",
    "VENTOINHA", "CHICOTE", "SENSOR", "TAMPA", "EMBREAGEM", "CABEÇOTE",
    "CABECOTE", "MOTOR DE PARTIDA", "CDI", "ECM", "ESPELHO", "ESCAPAMENTO",
    "SILENCIADOR", "PARAFUSO", "ARRUELA", "GAXETA", "VEDAÇÃO", "VEDACAO",
    "COXIM", "BUCHA", "ROLAMENTO", "GUIDÃO", "GUIDAO"
]

BRANDS = [
    "YAMAHA","HONDA","SUZUKI","KAWASAKI","BMW","DUCATI","BUELL",
    "HARLEY-DAVIDSON","HARLEY DAVIDSON","TRIUMPH","DAFRA","SHINERAY",
    "ROYAL ENFIELD","KTM","KYMCO","KASINSKI","HAOJUE"
]

def extract_identity(results, pn):
    """Extrai evidências dos snippets sem IA e privilegia descrições OEM explícitas."""
    can = canonical(pn)
    texts = []
    for r in results:
        blob = html.unescape((r.get("title","") + " " + r.get("body","")).upper())
        compact = re.sub(r"[^A-Z0-9]", "", blob)
        # Prioriza páginas onde o PN realmente aparece.
        if can in compact:
            texts.append(blob)

    if not texts:
        texts = [html.unescape((r.get("title","")+" "+r.get("body","")).upper()) for r in results]

    joined = " ".join(texts)

    # Nome da peça: procura vocabulário técnico próximo ao código e também termos conhecidos.
    found_parts = []
    for term in PART_TERMS:
        count = joined.count(term)
        if count:
            found_parts.append((count, len(term), term))
    found_parts.sort(reverse=True)

    peca = found_parts[0][2].title() if found_parts else ""

    # Corrige capitalização técnica comum.
    fixes = {
        "Capa Do Silenciador":"Capa do Silenciador",
        "Protetor Do Silenciador":"Protetor do Silenciador",
        "Protetor Do Tubo De Escape":"Protetor do Tubo de Escape",
        "Capa Proteção Do Escapamento":"Capa Proteção do Escapamento",
        "Capa Protecao Do Escapamento":"Capa Proteção do Escapamento",
        "Bomba De Combustível":"Bomba de Combustível",
        "Bomba De Combustivel":"Bomba de Combustível",
        "Motor De Partida":"Motor de Partida",
    }
    peca = fixes.get(peca, peca)

    marca = ""
    for b in BRANDS:
        if b in joined:
            marca = b.title().replace("Bmw","BMW").replace("Ktm","KTM")
            break

    # Modelos: extrai expressões recorrentes em resultados.
    model_patterns = [
        r"\bYS\s*250\b", r"\bFAZER\s*250\b", r"\bFZ25\b", r"\bMT[- ]?03\b",
        r"\bYZF[- ]?R3\b", r"\bNMAX\s*160\b", r"\bLANDER\s*250\b",
        r"\bCROSSER\s*150\b", r"\bFACTOR\s*(?:125|150)\b",
        r"\bCG\s*(?:125|150|160)\b", r"\bCBX\s*250\b", r"\bCB\s*300R?\b",
        r"\bXRE\s*300\b", r"\bBROS\s*160\b", r"\bPCX\s*(?:150|160)\b",
        r"\bCBR\s*\d+\w*\b", r"\bNINJA\s*\d+\b"
    ]
    mods=[]
    for pat in model_patterns:
        for m in re.findall(pat, joined, flags=re.I):
            val=re.sub(r"\s+"," ",m.upper()).strip()
            if val not in mods: mods.append(val)
    modelos = " / ".join(mods[:3])

    # Anos: encontra faixas explícitas como 2011 a 2017, 11-17.
    ranges=[]
    for a,b in re.findall(r"\b(20\d{2})\s*(?:A|ATÉ|ATE|-)\s*(20\d{2})\b", joined):
        pair=(int(a),int(b))
        if 1990 <= pair[0] <= pair[1] <= 2035: ranges.append(pair)
    for a,b in re.findall(r"\b(\d{2})\s*[-/]\s*(\d{2})\b", joined):
        aa,bb=2000+int(a),2000+int(b)
        if 2000 <= aa <= bb <= 2035: ranges.append((aa,bb))
    anos=""
    if ranges:
        counts=Counter(ranges)
        best=counts.most_common(1)[0][0]
        anos=f"{best[0]} a {best[1]}"

    # Evidências mais úteis.
    evidence=[]
    for r in results:
        blob=(r.get("title","")+" "+r.get("body",""))
        if can in canonical(blob):
            evidence.append(r)
    if not evidence: evidence=results

    return {
        "peca": peca,
        "marca": marca,
        "modelos": modelos,
        "anos": anos,
        "evidence": evidence[:12]
    }

def keyword_text(data, pn):
    bits=[data.get("peca",""),data.get("marca",""),data.get("modelos",""),data.get("anos",""),pn,canonical(pn)]
    vals=[]
    for x in bits:
        x=str(x).strip()
        if x and x not in vals: vals.append(x)
    return ", ".join(vals)

def description(data,pn):
    p=data.get("peca","Peça"); m=data.get("marca",""); mod=data.get("modelos",""); anos=data.get("anos","")
    ident=" ".join(x for x in [p,m,mod,anos] if x).strip()
    return f"""Esse anúncio contém: {ident}.

Código da peça: {pn}

Produto para aplicação informada acima. Antes da compra, favor conferir atentamente o código da peça, modelo, ano e as fotos do anúncio para confirmar a compatibilidade com sua motocicleta."""

def meta(data):
    txt=" ".join(x for x in [data.get("peca",""),data.get("marca",""),data.get("modelos",""),data.get("anos","")] if x).strip()
    base=f"{txt}. Consulte código, aplicação e fotos antes da compra."
    return base[:160].rstrip()

for k,v in {"results":None,"candidate":{},"confirmed":False}.items():
    if k not in st.session_state: st.session_state[k]=v

st.title("🏍️ Wise Part Number")
st.caption("Versão 3.2 • pesquisa → título → confirmação → cadastro")
st.caption("Pesquisa gratuita na web • sem OpenAI API e sem créditos.")

pn=st.text_input("Digite o Part Number",placeholder="Ex.: B97-F3121-00 ou b97f312100")
st.caption("Maiúsculas, minúsculas, hífens e espaços são tratados automaticamente.")

if st.button("🔎 PESQUISAR PEÇA",type="primary"):
    if not canonical(pn):
        st.warning("Digite um part number válido."); st.stop()
    with st.spinner("Pesquisando o código na web..."):
        res=search_web(pn)
    st.session_state.results=res
    st.session_state.candidate={}
    st.session_state.confirmed=False

if st.session_state.results is not None:
    res = st.session_state.results

    if not res:
        st.error("Não encontrei resultados suficientes para esse código.")
    else:
        ident = extract_identity(res, pn)

        # Monta um único título completo.
        titulo_encontrado = fit_title(
            " ".join(
                x for x in [
                    ident.get("peca", ""),
                    ident.get("marca", ""),
                    ident.get("modelos", ""),
                    ident.get("anos", "")
                ] if x
            )
        )

        st.subheader("Título encontrado")

        if titulo_encontrado:
            titulo_editado = st.text_input(
                "Título do item",
                value=titulo_encontrado,
                max_chars=60,
                label_visibility="collapsed"
            )
            titulo_editado = fit_title(titulo_editado)
            st.caption(f"{len(titulo_editado)}/60 caracteres")
        else:
            titulo_editado = st.text_input(
                "Título do item",
                placeholder="Não foi possível montar um título automaticamente",
                max_chars=60,
                label_visibility="collapsed"
            )

        # Guarda internamente os dados estruturados, mas não polui a tela.
        st.session_state.candidate = {
            "titulo": titulo_editado,
            "peca": ident.get("peca", ""),
            "marca": ident.get("marca", ""),
            "modelos": ident.get("modelos", ""),
            "anos": ident.get("anos", "")
        }

        st.markdown("### Esse título está correto?")
        col_sim, col_nao = st.columns(2)

        if col_sim.button("✅ SIM, ESTÁ CORRETO", type="primary", use_container_width=True):
            st.session_state.confirmed = True
            st.rerun()

        if col_nao.button("❌ NÃO, PESQUISAR NOVAMENTE", use_container_width=True):
            with st.spinner("Refazendo a pesquisa com outras variações do código..."):
                st.session_state.results = search_web(canonical(pn))
            st.session_state.confirmed = False
            st.rerun()

        with st.expander("Ver fontes da pesquisa"):
            for r in ident["evidence"]:
                st.markdown(f"**{r['title']}**")
                st.write(r["body"])
                st.markdown(f"[Abrir fonte]({r['url']})")
                st.divider()

if st.session_state.confirmed:
    ident = st.session_state.candidate
    titulo = fit_title(ident.get("titulo", ""))

    st.success("✓ Título confirmado")

    st.markdown("### Título")
    st.text_input(
        "Título confirmado",
        value=titulo,
        max_chars=60,
        disabled=True,
        label_visibility="collapsed"
    )
    st.caption(f"{len(titulo)}/60 caracteres")

    # Os dados extraídos ficam disponíveis para enriquecer o conteúdo,
    # mas o colaborador não precisa preencher campos separados.
    data = {
        "peca": ident.get("peca", ""),
        "marca": ident.get("marca", ""),
        "modelos": ident.get("modelos", ""),
        "anos": ident.get("anos", "")
    }

    kws = keyword_text(data, pn)
    desc = description(data, pn)
    md = meta(data)

    st.markdown("## Conteúdo para cadastro")

    st.markdown("### Palavras-chave")
    st.text_area(
        "Palavras-chave",
        value=kws,
        height=110,
        label_visibility="collapsed"
    )

    st.markdown("### Descrição completa")
    st.text_area(
        "Descrição completa",
        value=desc,
        height=240,
        label_visibility="collapsed"
    )

    st.markdown("### Meta description")
    st.text_area(
        "Meta description",
        value=md,
        height=100,
        label_visibility="collapsed"
    )
    st.caption(f"{len(md)}/160 caracteres")

    arquivo_txt = (
        f"TÍTULO\n{titulo}\n\n"
        f"PALAVRAS-CHAVE\n{kws}\n\n"
        f"DESCRIÇÃO COMPLETA\n{desc}\n\n"
        f"META DESCRIPTION\n{md}\n"
    )

    st.download_button(
        "⬇️ BAIXAR CONTEÚDO .TXT",
        data=arquivo_txt,
        file_name=f"{canonical(pn)}_cadastro.txt",
        mime="text/plain",
        use_container_width=True
    )

    if st.button("↩️ TÍTULO INCORRETO — PESQUISAR NOVAMENTE", use_container_width=True):
        with st.spinner("Procurando outra identificação..."):
            st.session_state.results = search_web(canonical(pn))
        st.session_state.confirmed = False
        st.rerun()


st.divider()
st.caption("Wise Moto Parts • Ferramenta interna de catalogação")
