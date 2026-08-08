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

def candidate_from_results(results, pn):
    """Sem IA: usa títulos de resultados como candidatos e remove ruído comercial."""
    can=canonical(pn)
    candidates=[]
    bad = re.compile(r"\b(compre|preço|mercado livre|shopee|amazon|ebay|frete|oferta|r\$)\b",re.I)
    for r in results:
        t=html.unescape(r["title"])
        # Remove site suffixes
        t=re.split(r"\s+[|\-–—]\s+(?=[A-Z][A-Za-z0-9 .]+$)",t)[0]
        # Remove PN in qualquer form
        for v in variants(pn):
            if v: t=re.sub(re.escape(v), "", t, flags=re.I)
        t=re.sub(r"\s+"," ",t).strip(" -|:")
        if len(t)>=8 and not bad.search(t):
            candidates.append(t)
    # Prefer title occurring with informative motorcycle terms and reasonable length
    def score(t):
        s=0
        if 15<=len(t)<=80:s+=3
        if re.search(r"\b(honda|yamaha|suzuki|kawasaki|bmw|ducati|buell|harley|triumph|dafra|shineray|royal enfield)\b",t,re.I):s+=4
        if re.search(r"\b(19|20)\d{2}\b",t):s+=2
        if re.search(r"\b(carenagem|farol|suporte|pedaleira|radiador|manopla|tampa|motor|guidão|guidao|painel|bengala|rabeta|paralama|chicote|sensor|bomba|embreagem|válvula|valvula)\b",t,re.I):s+=3
        return s
    candidates.sort(key=score, reverse=True)
    return candidates[:5]

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

for k,v in {"results":None,"candidate":"","confirmed":False}.items():
    if k not in st.session_state: st.session_state[k]=v

st.title("🏍️ Wise Part Number")
st.caption("Pesquisa gratuita na web • sem OpenAI API e sem créditos.")

pn=st.text_input("Digite o Part Number",placeholder="Ex.: B97-F3121-00 ou b97f312100")
st.caption("Maiúsculas, minúsculas, hífens e espaços são tratados automaticamente.")

if st.button("🔎 PESQUISAR PEÇA",type="primary"):
    if not canonical(pn):
        st.warning("Digite um part number válido."); st.stop()
    with st.spinner("Pesquisando o código na web..."):
        res=search_web(pn)
    st.session_state.results=res
    cand=candidate_from_results(res,pn)
    st.session_state.candidate=cand[0] if cand else ""
    st.session_state.confirmed=False

if st.session_state.results is not None:
    res=st.session_state.results
    if not res:
        st.error("Não encontrei resultados suficientes para esse código.")
    else:
        st.subheader("Resultado encontrado")
        cands=candidate_from_results(res,pn)
        if cands:
            choice=st.selectbox("Qual identificação parece correta?",cands,index=0)
        else:
            choice=st.text_input("Identificação da peça","")
        st.caption("Como esta versão não usa IA, confirme a identificação com as fontes abaixo.")

        st.markdown("### A peça está correta?")
        a,b=st.columns(2)
        if a.button("✅ SIM",type="primary"):
            st.session_state.candidate=choice
            st.session_state.confirmed=True
            st.rerun()
        if b.button("❌ NÃO — NOVA PESQUISA"):
            with st.spinner("Refazendo a pesquisa com outras variações..."):
                st.session_state.results=search_web(canonical(pn))
            st.session_state.confirmed=False
            st.rerun()

        with st.expander("Ver resultados/fontes da pesquisa"):
            for r in res[:15]:
                st.markdown(f"**{r['title']}**")
                st.write(r["body"])
                st.markdown(f"[Abrir fonte]({r['url']})")
                st.divider()

if st.session_state.confirmed:
    st.success("✓ Identificação confirmada")
    ident=st.session_state.candidate
    st.markdown("### Complete os dados para gerar o cadastro")
    peca=st.text_input("Nome da peça",value=ident)
    marca=st.text_input("Marca")
    modelos=st.text_input("Modelo(s)")
    anos=st.text_input("Anos de aplicação")
    if st.button("📝 GERAR CONTEÚDO",type="primary"):
        data={"peca":peca,"marca":marca,"modelos":modelos,"anos":anos}
        title=fit_title(" ".join(x for x in [peca,marca,modelos,anos] if x))
        kws=keyword_text(data,pn)
        desc=description(data,pn)
        md=meta(data)
        st.markdown('<div class="card"><div class="muted">TÍTULO</div><div class="title">'+html.escape(title)+'</div><div class="muted">'+str(len(title))+'/60 caracteres</div></div>',unsafe_allow_html=True)
        st.text_area("Palavras-chave",kws,height=100)
        st.text_area("Descrição completa",desc,height=230)
        st.text_area("Meta description",md,height=100)
        st.caption(f"{len(md)}/160 caracteres")

st.divider()
st.caption("Wise Moto Parts • Ferramenta interna de catalogação")
