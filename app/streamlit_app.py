"""JurisIA: interface de pesquisa na base local do STJ."""

import html
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jurisia.config import DB
from jurisia.rag import ask, generate, metrics
from jurisia.spellcheck import correct_query

st.set_page_config(page_title="JurisIA | Pesquisa no STJ", page_icon="⚖️", layout="wide")

STJ_PORTAL_URL = "https://www.stj.jus.br/sites/portalp/Jurisprudencia/Acordaos-e-Decisoes"
st.markdown("""
<style>
:root {color-scheme:light}
[data-testid="stToolbarActions"], #MainMenu {display:none!important}
/* Mantém o indicador nativo de processamento visível nos dois temas. */
[data-testid="stToolbar"] {visibility:visible!important;opacity:1!important}
[data-testid="stStatusWidget"] {
    background:#003734!important;
    color:#edfffe!important;
    border:1px solid #39716d!important;
    border-radius:6px;
    padding:4px 10px;
    opacity:1!important;
}
[data-testid="stStatusWidget"] p,
[data-testid="stStatusWidget"] span {color:#edfffe!important}
[data-testid="stStatusWidget"] svg {color:#edfffe!important}
[data-testid="stStatusWidget"] svg path {fill:#edfffe!important}
.st-key-clear_cache button {border-radius:4px!important;min-height:40px}
.stApp {background:#f5f6fb;color:#20243b}
[data-testid="stHeader"] {background:transparent}
.block-container {max-width:1180px;padding-top:2rem;padding-bottom:3rem}
[data-testid="stSidebar"] {background:#011d1c;color:#edfffe}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,
[data-testid="stSidebar"] h3 {color:#edfffe!important}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {color:#bbc7c6!important}
[data-testid="stSidebar"] hr {border-color:rgba(255,255,255,.12)}
.brand {font-size:30px;font-weight:500;letter-spacing:-1px;margin:12px 0 0}
.brand span {color:#cbfffc}
.eyebrow {font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#666984}
.hero {background:linear-gradient(115deg,#011d1c,#012624 65%,#003734);border-radius:20px;padding:32px 36px;margin:14px 0 24px;color:white}
.hero h1 {color:white!important;font-size:clamp(27px,3.1vw,40px);line-height:1.2;letter-spacing:-1px;padding:12px 0}
.hero p {color:#ddd9ee;font-size:16px;margin:0;max-width:650px}
.badge {display:inline-block;border-radius:30px;padding:5px 12px;font-size:11px;font-weight:700;letter-spacing:.7px;background:#efedfc;color:#5846a1;margin-right:6px}
.hero .badge {background:#ffffff20;color:#e9e5ff;border:1px solid #ffffff30}
.step {font-size:16px;font-weight:700;margin:4px 0 12px;color:#36345d}
.step b {display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;background:#003734;color:#cbfffc;margin-right:9px;font-size:13px}
[data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"]>div {border-radius:16px}
[data-testid="stForm"] {background:white;border:1px solid #e2e3ee;padding:24px}
[data-testid="stTextArea"] textarea,[data-testid="stTextInput"] input {background:#fafaff;color:#20243b;font-size:16px}
[data-testid="stBaseButton-primary"],button[kind="primary"] {background:linear-gradient(90deg,#00827c,#cbfffc 52%,#fad1ff);color:#012624;border:0;border-radius:6px;font-weight:600;min-height:44px}
[data-testid="stBaseButton-primary"]:hover,button[kind="primary"]:hover {filter:brightness(1.06)}
[data-testid="stMetric"] {background:white;border:1px solid #e2e3ee;border-radius:14px;padding:18px}
.doc-title {font-size:21px;font-weight:500;color:#2c2850;margin:12px 0 8px}
.meta {font-size:13px;color:#62667b;line-height:1.9;margin-bottom:14px}
.snippet {border-left:3px solid #9a8cda;padding:12px 18px;background:#f6f4fc;color:#38364d;line-height:1.75;border-radius:0 10px 10px 0;margin:12px 0 16px}
.empty {text-align:center;padding:36px 20px;color:#6a6d80}
.empty strong {display:block;font-size:19px;color:#37364f;margin-bottom:8px}
.footer {color:#76778a;font-size:12px;margin-top:30px;border-top:1px solid #e0e1ec;padding-top:18px}
mark {background:#fff0b3;color:#292538;padding:0 2px;border-radius:3px}
@media(max-width:640px) {.hero {padding:24px}.block-container {padding-left:1rem;padding-right:1rem}[data-testid="stForm"] {padding:16px}}
</style>
""", unsafe_allow_html=True)


def esc(value):
    return html.escape(str(value or ""))


def date_label(value):
    raw = str(value or "")
    if re.fullmatch(r"\d{8}", raw):
        try:
            return datetime.strptime(raw, "%Y%m%d").strftime("%d/%m/%Y")
        except ValueError:
            pass
    return raw or "Não informada"


def highlight(text, query, enabled):
    terms = sorted(set(re.findall(r"\w{4,}", query)), key=len, reverse=True)
    if not enabled or not terms:
        return esc(text)
    pattern = re.compile("(" + "|".join(re.escape(t) for t in terms) + ")", re.I)
    return "".join("<mark>" + esc(part) + "</mark>" if i % 2 else esc(part)
                   for i, part in enumerate(pattern.split(str(text or ""))))


def readable_citations(answer, hits):
    """Identifica as fontes usando os metadados dos documentos recuperados."""
    def replace(match):
        index = int(match.group(1)) - 1
        if not 0 <= index < len(hits):
            return match.group(0)
        doc = hits[index].get("document", {})
        process_class = str(doc.get("process_class") or "").strip()
        process_number = str(doc.get("process_number") or "").strip()
        if process_number:
            label = f"{process_class} {process_number}".strip()
        else:
            label = f"Documento STJ {doc.get('id') or hits[index].get('id') or index + 1}"
        # Escapa pontuação de Markdown presente nos metadados.
        label = re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", label)
        return f"[{label}]"
    return re.sub(r"\[D(\d+)\]", replace, answer)


@st.cache_data(ttl=60)
def catalog():
    if not DB.exists():
        return [], 1989, datetime.now().year, 0
    with sqlite3.connect(DB) as conn:
        bodies = [row[0] for row in conn.execute(
            "SELECT DISTINCT court_body FROM documents WHERE court_body IS NOT NULL AND court_body != '' ORDER BY court_body")]
        count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        years = [int(row[0]) for row in conn.execute(
            "SELECT DISTINCT SUBSTR(decision_date,1,4) FROM documents WHERE LENGTH(decision_date)=8")
                 if str(row[0]).isdigit() and 1900 <= int(row[0]) <= 2100]
    return bodies, min(years, default=1989), max(years, default=datetime.now().year), count


# Dados pessoais deste aplicativo local, separados da base de acórdãos.

USER_DB = DB.parent / "jurisia_caderno.sqlite3"


def user_db():
    USER_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(USER_DB, timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS saved (id TEXT PRIMARY KEY, document TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', saved_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    return conn


def preference(key, default):
    with user_db() as conn:
        row = conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def save_theme():
    theme = st.session_state.get("ui_theme")
    if theme not in ("Claro", "Escuro"):
        return
    with user_db() as conn:
        conn.execute("INSERT OR REPLACE INTO preferences VALUES ('theme',?)", (theme,))


def saved_documents():
    with user_db() as conn:
        return conn.execute("SELECT id,document,note,saved_at FROM saved ORDER BY saved_at DESC").fetchall()


def save_document(hit):
    with user_db() as conn:
        conn.execute("INSERT OR IGNORE INTO saved(id,document,saved_at) VALUES (?,?,?)",
                     (str(hit['id']), json.dumps(hit['document'], ensure_ascii=False), datetime.now().isoformat()))


def run_search(question, apply_correction=True, **kwargs):
    correction = correct_query(question) if apply_correction else {
        "original": question, "query": question, "suggestion": "", "changes": []
    }
    result = ask(correction["query"], with_gemini=False, **kwargs)
    result.update(query=correction["query"], original_query=question,
                  correction=correction, search_options=kwargs, warning="")
    return result


def make_synthesis(result):
    started = time.monotonic()
    result['warning'] = ''
    result.pop("ai_error_details", None)
    result['synthesis_attempted'] = True
    synthesis_question = (
        f"Pergunta do usuário: {result['query']}\n\n"
        "Orientações para a resposta: responda diretamente à pergunta, em português "
        "claro e acessível. Escreva vários parágrafos curtos, com duas ou três frases "
        "por parágrafo e uma linha em branco entre eles. Comece com a conclusão "
        "principal; depois explique os fundamentos e as condições ou exceções "
        "presentes nos acórdãos recuperados. Cite as fontes usando os identificadores "
        "fornecidos no contexto. Use exclusivamente essas fontes, sem inventar "
        "decisões, fatos, regras ou referências. Não apresente a conclusão como posição "
        "de todo o STJ se as fontes não sustentarem essa abrangência. "
        "Quando houver base suficiente, termine com um exemplo hipotético breve, "
        "claramente identificado como 'Exemplo ilustrativo', em um único parágrafo "
        "curto. O exemplo deve apenas ilustrar uma regra sustentada pelas fontes, "
        "sem afirmar que é um caso real ou garantir um resultado. "
        "Se as fontes forem insuficientes, explique a limitação e omita o exemplo."
    )
    try:
        result['answer'] = generate(synthesis_question, result['hits'])
    except Exception as exc:
        details = str(exc)
        # Oculta a chave caso ela apareça na mensagem da API.
        import os
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            details = details.replace(api_key, "[CHAVE OCULTA]")
        details = re.sub(r"AIza[\w-]+", "[CHAVE OCULTA]", details)
        result["ai_error_details"] = details
        reason = str(exc).lower()
        if '503' in reason or 'high demand' in reason:
            result['warning'] = 'O Gemini está com alta demanda. Tente a síntese mais tarde; seus resultados continuam disponíveis.'
        elif '429' in reason:
            result['warning'] = 'O limite de uso do Gemini foi atingido. Tente a síntese mais tarde.'
        elif 'gemini_api_key' in reason:
            result['warning'] = 'Configure GEMINI_API_KEY no arquivo .env e reinicie a plataforma.'
        elif '404' in reason:
            result['warning'] = 'O modelo configurado não está disponível. Confira GEMINI_MODEL no arquivo .env.'
        else:
            result['warning'] = 'Não foi possível gerar a síntese. Confira a conexão e a configuração do Gemini.'
        result['answer'] = ''
    result['ai_seconds'] = time.monotonic() - started


def task_busy():
    return st.session_state.get("jurisia_future") is not None


def background_executor():
    if "jurisia_executor" not in st.session_state:
        st.session_state["jurisia_executor"] = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="jurisia"
        )
    return st.session_state["jurisia_executor"]


def search_job(question, colored, display_mode, apply_correction, options):
    # O processamento não acessa widgets nem o estado do Streamlit.
    result = run_search(question, apply_correction=apply_correction, **options)
    result.update(colored=colored, display_mode=display_mode)
    return result


def synthesis_job(result):
    # Uma cópia impede alterações concorrentes no resultado exibido.
    result = copy.deepcopy(result)
    make_synthesis(result)
    return result


def start_search(question, colored, display_mode, apply_correction=True, **options):
    if task_busy():
        return False
    st.session_state.pop("jurisia_result", None)
    st.session_state.pop("jurisia_job_error", None)
    st.session_state["jurisia_future"] = background_executor().submit(
        search_job, question, colored, display_mode, apply_correction, options
    )
    st.session_state["jurisia_phase"] = "search"
    return True


def start_synthesis(result):
    if task_busy():
        return False
    result["synthesis_attempted"] = True
    result["warning"] = ""
    result.pop("ai_error_details", None)
    st.session_state.pop("jurisia_job_error", None)
    st.session_state["jurisia_future"] = background_executor().submit(
        synthesis_job, copy.deepcopy(result)
    )
    st.session_state["jurisia_phase"] = "synthesis"
    return True


def finish_job():
    future = st.session_state.get("jurisia_future")
    if future is None or not future.done():
        return False
    phase = st.session_state.pop("jurisia_phase", "search")
    st.session_state.pop("jurisia_future", None)
    try:
        st.session_state["jurisia_result"] = future.result()
    except Exception:
        st.session_state["jurisia_job_error"] = (
            "Não foi possível consultar o índice. Confira a preparação e a indexação."
            if phase == "search" else
            "Não foi possível gerar a síntese. Tente novamente."
        )
    return True


@st.fragment(run_every=0.5 if task_busy() else None)
def research_results():
    if finish_job():
        st.rerun()
    if st.session_state.get("jurisia_job_error"):
        st.error(st.session_state["jurisia_job_error"])
    result = st.session_state.get("jurisia_result")
    if result:
        correction = result.get("correction", {})
        if result.get("original_query", result["query"]) != result["query"]:
            st.info(f"Exibindo resultados para: **{result['query']}**")
            st.caption(f"Você pesquisou: {result['original_query']}")
            if st.button(f"Pesquisar por “{result['original_query']}” mesmo assim", key="original_query", disabled=task_busy()):
                try:
                    if start_search(
                        result["original_query"], result["colored"],
                        result.get("display_mode", "Síntese e acórdãos"),
                        apply_correction=False, **result["search_options"]
                    ):
                        st.rerun()
                except Exception:
                    st.error("Não foi possível pesquisar a consulta original. Tente novamente.")
        if correction.get("suggestion"):
            if st.button(f"Você quis dizer: {correction['suggestion']}?", key="suggested_query", disabled=task_busy()):
                try:
                    if start_search(
                        correction["suggestion"], result["colored"],
                        result.get("display_mode", "Síntese e acórdãos"),
                        apply_correction=False, **result["search_options"]
                    ):
                        st.rerun()
                except Exception:
                    st.error("Não foi possível pesquisar a sugestão. Tente novamente.")
        show_documents = result.get("display_mode", "Síntese e acórdãos") == "Síntese e acórdãos"
        if show_documents:
            st.markdown("### Resultados da pesquisa")
            st.caption(f"Consulta: {result['query']} · {len(result['hits'])} acórdãos · {result['seconds']:.1f} segundos")
        else:
            st.caption(f"Consulta: {result['query']}")
        synthesis_slot = st.container()
        saved_ids = {row[0] for row in saved_documents()}
        if not result["hits"]:
            st.info("Nenhum acórdão encontrado com esses filtros. Tente outro assunto ou amplie o período.")
        visible_hits = (
            result["hits"]
            if result.get("display_mode", "Síntese e acórdãos") == "Síntese e acórdãos"
            else []
        )
        for number, hit in enumerate(visible_hits, 1):
            doc = hit["document"]
            title = f"{doc.get('process_class') or ''} {doc.get('process_number') or ''}".strip()
            with st.container(border=True):
                st.markdown(f'<span class="badge">D{number}</span><span class="badge">STJ · {esc(doc.get("court_body"))}</span><div class="doc-title">{esc(title)}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="meta">Relator: <strong>{esc(doc.get("rapporteur") or "Não informado")}</strong><br>Julgamento: {esc(date_label(doc.get("decision_date")))} &nbsp; · &nbsp; Publicação: {esc(doc.get("publication_date") or "Não informada")}</div>', unsafe_allow_html=True)
                st.markdown('<div class="snippet">' + highlight(hit["snippet"], result["query"], result["colored"]) + '</div>', unsafe_allow_html=True)
                with st.expander("Ler ementa completa"):
                    st.write(doc.get("ementa") or "Sem ementa disponível.")
                    st.caption(f"Identificador: {hit['id']} · Similaridade: {hit['similarity']:.3f}. Não é probabilidade de correção.")
                st.link_button("Consultar no portal do STJ ↗", STJ_PORTAL_URL)
                st.caption("Para consultar a decisão individual, use o número do processo no portal do STJ.")
                ident = str(hit['id'])
                if st.button("Salvo no caderno" if ident in saved_ids else "Salvar no caderno",
                             key=f"save_{ident}", disabled=ident in saved_ids):
                    save_document(hit)
                    st.rerun()
        # Renderiza as decisões antes de chamar um serviço externo.
        with synthesis_slot:
            if result['hits']:
                with st.container(border=True):
                    st.markdown("#### Síntese")
                    st.caption("Síntese automática baseada nos acórdãos encontrados. A pergunta e os trechos são enviados ao Gemini.")
                    request_ai = False
                    if result.get('synthesis_attempted'):
                        request_ai = st.button(
                            "Gerar novamente" if result.get('answer') else "Tentar síntese novamente",
                            key="make_synthesis",
                            disabled=task_busy(),
                        )
                    if (not result.get('synthesis_attempted') or request_ai) and not task_busy():
                        if start_synthesis(result):
                            st.rerun()
                    if task_busy() and st.session_state.get("jurisia_phase") == "synthesis":
                        st.status("Gerando síntese… Você pode alterar a aparência.", state="running", expanded=False)
                    if result.get('warning'):
                        st.warning(result['warning'])
                    if result.get("ai_error_details"):
                        st.error("Detalhes do erro do Gemini:")
                        st.code(result["ai_error_details"], language="text")
                    if result.get('answer'):
                        st.write(readable_citations(result['answer'], result['hits']))
                        st.caption(f"Síntese: {result['ai_seconds']:.1f} segundos · Confira as afirmações nas fontes citadas.")
    elif task_busy():
        st.status("Buscando decisões…", state="running", expanded=False)
    else:
        st.markdown('<div class="empty"><strong>Sua próxima pesquisa começa aqui.</strong>Experimente: erro médico, cobrança indevida ou responsabilidade civil.</div>', unsafe_allow_html=True)


bodies, first_year, last_year, document_count = catalog()

with st.sidebar:
    st.markdown('<div class="brand">Juris<span>IA</span></div>', unsafe_allow_html=True)
    st.caption("PESQUISA JURISPRUDENCIAL")
    st.divider()
    page = st.radio("Navegação", ["Pesquisar jurisprudência", "Meu caderno", "Dados da base"], label_visibility="collapsed")
    st.divider()
    st.markdown("### Superior Tribunal de Justiça")
    st.caption("Acórdãos para consultas de estudo e trabalho.")
    st.caption(f"{document_count:,} acórdãos importados".replace(",", "."))
    if bodies:
        st.caption("Órgãos na base: " + ", ".join(bodies))
    st.divider()
    if 'ui_theme' not in st.session_state:
        saved_theme = preference('theme', 'Escuro')
        st.session_state['ui_theme'] = saved_theme if saved_theme in ("Claro", "Escuro") else "Escuro"
    st.selectbox("Aparência", ["Claro", "Escuro"], key="ui_theme", on_change=save_theme)
    if st.button("Limpar cache", key="clear_cache", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.session_state["cache_cleared_notice"] = True
        st.rerun()
    if st.session_state.pop("cache_cleared_notice", False):
        st.toast("Cache limpo.")
    st.link_button("Consultar jurisprudência no portal do STJ ↗", STJ_PORTAL_URL)


dark = st.session_state.get('ui_theme') == 'Escuro'
bg, panel, field, text, muted, border = (
    ('#012624', '#003734', '#011d1c', '#ffffff', '#bbc7c6', 'rgba(255,255,255,.12)') if dark else
    ('#f5f6fb', '#ffffff', '#fafaff', '#20243b', '#62667b', '#e2e3ee'))


st.markdown(f"""<style>
.stApp {{background:{bg};color:{text};color-scheme:{'dark' if dark else 'light'}}}
[data-testid="stMain"] h1,[data-testid="stMain"] h2,[data-testid="stMain"] h3,
[data-testid="stMain"] h4,[data-testid="stMain"] label,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] {{color:{text}}}
[data-testid="stMain"] [data-testid="stCaptionContainer"] p {{color:{muted}}}
[data-testid="stForm"],[data-testid="stMetric"],
[data-testid="stVerticalBlockBorderWrapper"]>div {{background:{panel};border-color:{border}}}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,[data-baseweb="select"]>div {{background:{field};color:{text}}}
[data-testid="stNumberInput"] button,[data-testid="stExpander"] summary {{background:{panel};color:{text}}}
[data-testid="stMain"] button[kind="secondary"] {{background:{panel};color:{text};border-color:{border}}}
[data-baseweb="popover"] [role="listbox"], [data-baseweb="popover"] li {{background:{panel};color:{text}}}
.doc-title,.step,.empty strong {{color:{text}}}
.meta,.eyebrow,.empty,.footer {{color:{muted}}}
.snippet {{background:{field};color:{text}}}
[data-testid="stMetricValue"],[data-testid="stMetricLabel"] {{color:{text}}}
/* Campos: texto digitado, dicas e campos desativados. */
[data-testid="stMain"] [data-testid="stTextInput"] input,
[data-testid="stMain"] [data-testid="stTextArea"] textarea,
[data-testid="stMain"] [data-testid="stNumberInput"] input {{
    background:{field}!important;
    color:{text}!important;
    -webkit-text-fill-color:{text}!important;
    caret-color:{text}!important;
}}
[data-testid="stMain"] input::placeholder,
[data-testid="stMain"] textarea::placeholder {{
    color:{muted}!important;
    -webkit-text-fill-color:{muted}!important;
    opacity:1!important;
}}
[data-testid="stMain"] input:disabled {{
    color:{muted}!important;
    -webkit-text-fill-color:{muted}!important;
    opacity:1!important;
}}
/* Texto dos botões acompanha a cor de seu próprio fundo. */
[data-testid="stMain"] button[kind="secondary"] p,
[data-testid="stMain"] button[kind="secondary"] span {{color:{text}!important}}
[data-testid="stMain"] button[kind="primary"] {{
    background:linear-gradient(90deg,#00827c,#cbfffc 52%,#fad1ff)!important;
    color:#012624!important;
}}
[data-testid="stMain"] button[kind="primary"] p,
[data-testid="stMain"] button[kind="primary"] span {{color:#012624!important}}
[data-testid="stMain"] [data-testid="stLinkButton"] a {{
    background:{panel}!important;color:{text}!important;border-color:{border}!important;
}}
[data-testid="stMain"] [data-testid="stLinkButton"] a p {{color:{text}!important}}
/* A barra lateral possui fundo escuro nos dois temas. */
[data-testid="stSidebar"] button[kind="secondary"],
[data-testid="stSidebar"] [data-testid="stLinkButton"] a {{
    background:#003734!important;color:#edfffe!important;border:1px solid #39716d!important;
}}
[data-testid="stSidebar"] button[kind="secondary"] p,
[data-testid="stSidebar"] button[kind="secondary"] span,
[data-testid="stSidebar"] [data-testid="stLinkButton"] a p {{color:#edfffe!important}}
[data-testid="stSidebar"] button[kind="secondary"]:hover,
[data-testid="stSidebar"] [data-testid="stLinkButton"] a:hover {{background:#00524d!important}}
[data-testid="stSidebar"] [data-baseweb="select"]>div {{
    background:#003734!important;color:#edfffe!important;
}}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] input {{
    color:#edfffe!important;-webkit-text-fill-color:#edfffe!important;
}}

</style>""", unsafe_allow_html=True)

st.markdown('<div class="eyebrow">JurisIA / Superior Tribunal de Justiça</div>', unsafe_allow_html=True)

if page == "Pesquisar jurisprudência":
    st.markdown('''<div class="hero"><span class="badge">BASE STJ</span><span class="badge">ACÓRDÃOS</span>
    <h1>Encontre a jurisprudência<br>que você precisa.</h1>
    <p>Pesquise por assunto ou faça uma pergunta. Explore as decisões e confira as fontes.</p></div>''', unsafe_allow_html=True)
    if bodies:
        st.caption("Cobertura da base: " + ", ".join(bodies) + " · STJ")
    with st.form("search_form", enter_to_submit=True):
        st.markdown('<div class="step"><b>1</b> O que você quer pesquisar?</div>', unsafe_allow_html=True)
        question = st.text_input("Assunto ou pergunta",
                                placeholder="Ex.: Qual é o entendimento do STJ sobre responsabilidade civil por erro médico?")
        st.caption("Pressione Enter ou clique em Pesquisar no STJ.")
        st.markdown('<div class="step"><b>2</b> Como você quer ver a resposta?</div>', unsafe_allow_html=True)
        display_mode = st.radio(
            "Formato da resposta",
            ["Apenas a síntese", "Síntese e acórdãos"],
            index=1,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.markdown('<div class="step"><b>3</b> Refine sua pesquisa</div>', unsafe_allow_html=True)
        a, b, c, d = st.columns([2, 1, 1, 1])
        a.text_input("Órgão julgador", value="Terceira Turma", disabled=True)
        body = next((name for name in bodies if "TERCEIRA TURMA" in name.upper()), None)
        year_from = b.number_input("Ano inicial", 1900, 2100, first_year)
        year_to = c.number_input("Ano final", 1900, 2100, last_year)
        k = d.selectbox("Número de acórdãos", [5, 15, 30])
        colored = st.checkbox("Destacar palavras da pesquisa", value=True)
        with st.expander("Opções avançadas"):
            rerank = st.checkbox("Combinar significado e palavras na ordenação", value=True)
            threshold = st.slider("Similaridade mínima", 0.0, 0.8, 0.30, 0.01,
                                  help="Parâmetro experimental. Não representa probabilidade de correção.")
        submitted = st.form_submit_button("Pesquisar no STJ", type="primary", use_container_width=True, disabled=task_busy())
    if submitted:
        if not question.strip():
            st.warning("Digite um assunto ou uma pergunta para pesquisar.")
        elif year_from > year_to:
            st.warning("O ano inicial deve ser menor ou igual ao ano final.")
        else:
            if start_search(
                question.strip(), colored, display_mode,
                k=k, body=body, year_from=int(year_from), year_to=int(year_to),
                min_similarity=threshold, use_rerank=rerank,
            ):
                st.rerun()
    research_results()


elif page == "Meu caderno":
    st.title("Meu caderno")
    st.caption("Acórdãos salvos e anotações neste computador. O caderno é compartilhado por quem usa esta instalação.")
    rows = saved_documents()
    if not rows:
        st.info("Faça uma pesquisa e clique em Salvar no caderno para guardar um acórdão.")
    else:
        find = st.text_input("Filtrar acórdãos salvos", placeholder="Processo, relator ou palavra na anotação")
        for ident, document_json, note, saved_at in rows:
            doc = json.loads(document_json)
            if find and find.casefold() not in (document_json + note).casefold():
                continue
            with st.container(border=True):
                st.subheader(f"{doc.get('process_class', '')} {doc.get('process_number', '')}")
                st.caption(f"{doc.get('court_body', '')} · {doc.get('rapporteur', '')} · {date_label(doc.get('decision_date'))}")
                with st.expander("Ementa e fonte"):
                    st.write(doc.get('ementa') or 'Sem ementa disponível.')
                    st.link_button("Consultar no portal do STJ ↗", STJ_PORTAL_URL)
                with st.form(f"note_{ident}"):
                    updated_note = st.text_area("Suas anotações", value=note, max_chars=10000)
                    if st.form_submit_button("Salvar anotação"):
                        with user_db() as conn:
                            conn.execute("UPDATE saved SET note=? WHERE id=?", (updated_note, ident))
                        st.success("Anotação salva.")
                if st.button("Remover do caderno", key=f"remove_{ident}"):
                    st.session_state['confirm_remove'] = ident
                if st.session_state.get('confirm_remove') == ident:
                    st.warning("Remover este acórdão e suas anotações do caderno?")
                    yes, no = st.columns(2)
                    if yes.button("Confirmar remoção", key=f"yes_{ident}"):
                        with user_db() as conn:
                            conn.execute("DELETE FROM saved WHERE id=?", (ident,))
                        st.session_state.pop('confirm_remove', None)
                        st.rerun()
                    if no.button("Cancelar", key=f"no_{ident}"):
                        st.session_state.pop('confirm_remove', None)
                        st.rerun()


else:
    st.title("Dados da base")
    st.caption("Acompanhe a cobertura dos documentos importados e as consultas realizadas.")
    st.link_button("Consultar jurisprudência no portal do STJ ↗", STJ_PORTAL_URL)
    values = metrics()
    a, b, c = st.columns(3)
    a.metric("Acórdãos importados", f"{values['documents']:,}".replace(",", "."))
    b.metric("Consultas realizadas", values["questions"])
    c.metric("Tempo médio registrado", f"{values['avg_seconds']:.1f} s")
    if DB.exists():
        import pandas as pd
        with sqlite3.connect(DB) as conn:
            years = pd.read_sql_query("SELECT SUBSTR(decision_date,1,4) AS ano, COUNT(*) AS acordaos FROM documents WHERE LENGTH(decision_date)=8 GROUP BY ano ORDER BY ano", conn)
        if not years.empty:
            st.subheader("Acórdãos por ano de julgamento")
            st.bar_chart(years.set_index("ano"), color="#7965c4")
    st.caption("Órgãos na base: " + (", ".join(bodies) or "Nenhum documento importado"))


st.markdown('<div class="footer">JurisIA · Pesquisa para estudo e trabalho · Base local de espelhos de acórdãos do STJ. Confira as fontes originais.</div>', unsafe_allow_html=True)
