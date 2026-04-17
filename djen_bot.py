import os
import re
import time
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ── Variáveis injetadas pelo GitHub Secrets ────────────────────────────────
OAB              = os.getenv("NUMERO_OAB")          # ex: 227892
UF               = os.getenv("UF_OAB", "mg")        # ex: MG → convertido p/ minúsculo
EMAIL_REMETENTE  = os.getenv("EMAIL_REMETENTE")
SENHA_APP        = os.getenv("SENHA_APP_GMAIL")
EMAIL_DESTINO    = os.getenv("EMAIL_DESTINO")

# A API exige UF em minúsculo
UF = UF.lower() if UF else "mg"

# URL correta da API pública do DJEN (versão publicada em 04-03-2026)
API_BASE = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"

hoje = datetime.now().strftime("%Y-%m-%d")

# ── Helpers ────────────────────────────────────────────────────────────────

def strip_html(texto: str) -> str:
    """Remove tags HTML e decodifica entidades básicas."""
    if not texto:
        return ""
    text = re.sub(r"<[^>]+>", " ", texto)
    entities = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&Ccedil;": "Ç", "&ccedil;": "ç",
        "&atilde;": "ã", "&Atilde;": "Ã", "&otilde;": "õ", "&Otilde;": "Õ",
        "&eacute;": "é", "&Eacute;": "É", "&ecirc;": "ê", "&Ecirc;": "Ê",
        "&oacute;": "ó", "&Oacute;": "Ó", "&aacute;": "á", "&Aacute;": "Á",
        "&iacute;": "í", "&Iacute;": "Í", "&uacute;": "ú", "&Uacute;": "Ú",
        "&ndash;": "–", "&mdash;": "—", "&ordm;": "º", "&ordf;": "ª",
    }
    for ent, char in entities.items():
        text = text.replace(ent, char)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_comunicacoes(meio: str = None) -> list:
    """
    Busca TODAS as comunicações do dia para a OAB informada,
    percorrendo todas as páginas (itensPorPagina=100).
    meio='D' → Diário  |  meio='E' → Edital  |  None → ambos
    """
    todos = []
    pagina = 1
    params_base = {
        "numeroOab": OAB,
        "ufOab": UF,
        "dataDisponibilizacaoInicio": hoje,
        "itensPorPagina": 100,
    }
    if meio:
        params_base["meio"] = meio

    while True:
        params = {**params_base, "pagina": pagina}
        for tentativa in range(3):
            try:
                print(f"[{meio or 'ALL'}] Página {pagina}, tentativa {tentativa+1}/3...")
                resp = requests.get(API_BASE, params=params, timeout=30)
                if resp.status_code == 429:
                    print("Rate limit atingido — aguardando 60s...")
                    time.sleep(60)
                    continue
                resp.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                print(f"Erro: {e}")
                if tentativa < 2:
                    time.sleep(2 ** tentativa)
        else:
            print(f"Falha ao buscar página {pagina}. Abortando paginação.")
            break

        dados = resp.json()
        items = dados.get("items", [])
        todos.extend(items)

        total = dados.get("count", 0)
        print(f"  → {len(todos)}/{total} registros obtidos.")

        if len(todos) >= total or not items:
            break
        pagina += 1
        time.sleep(1)  # Respeita rate limit entre páginas

    return todos


def is_priority(item: dict) -> bool:
    """Verifica se a comunicação é uma decisão, acórdão, despacho ou ato judicial."""
    tipo = str(item.get("tipoComunicacao", "")).upper()
    doc = str(item.get("tipoDocumento", "")).upper()
    
    keywords = ["DECISÃO", "ACÓRDÃO", "DESPACHO", "ATO JUDICIAL", "SENTENÇA"]
    
    for kw in keywords:
        if kw in tipo or kw in doc:
            return True
    
    # Intimação é prioridade na maioria dos casos de atos judiciais
    if "INTIMAÇÃO" in tipo:
        return True
        
    return False


def formatar_item(item: dict, idx: int, prioridade: bool = False) -> str:
    """Formata um item de comunicação para o corpo do e-mail."""
    prefixo = "🚨 [PRIORIDADE] " if prioridade else f"#{idx} "
    sep = "═" * 55 if prioridade else "─" * 55
    
    proc    = item.get("numeroprocessocommascara", "N/A")
    orgao   = item.get("nomeOrgao", "N/A")
    tipo    = item.get("tipoComunicacao", "N/A")
    tipo_doc = item.get("tipoDocumento", "N/A")
    classe  = item.get("nomeClasse", "N/A")
    tribunal = item.get("siglaTribunal", "N/A")
    data    = item.get("datadisponibilizacao", hoje)
    meio_c  = item.get("meiocompleto", item.get("meio", "N/A"))
    link    = item.get("link") or "Sem link"

    # Destinatários (partes)
    destinatarios = item.get("destinatarios", [])
    partes_txt = ""
    for d in destinatarios:
        polo_map = {"A": "AUTOR/REQUERENTE", "P": "RÉU/REQUERIDO", "T": "TERCEIRO"}
        polo = polo_map.get(d.get("polo", ""), d.get("polo", ""))
        nome = d.get("nome", "N/A")
        partes_txt += f"    • {polo}: {nome}\n"

    # Texto com limpeza de HTML (resumo de 500 chars para prioridade)
    limite = 600 if prioridade else 350
    texto_raw = strip_html(item.get("texto", ""))
    texto = (texto_raw[:limite] + "…") if len(texto_raw) > limite else texto_raw

    return (
        f"\n{sep}\n"
        f"{prefixo} {tipo.upper()} — {proc}\n"
        f"{sep}\n"
        f"  Tribunal  : {tribunal}\n"
        f"  Órgão     : {orgao}\n"
        f"  Classe    : {classe}\n"
        f"  Doc       : {tipo_doc}\n"
        f"  Meio      : {meio_c}\n"
        f"  Data      : {data}\n"
        f"\nPartes envolvidas:\n{partes_txt}"
        f"\nResumo:\n  {texto}\n"
        f"\nLink: {link}\n"
    )


# ── Coleta de comunicações ──────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"Robô DJEN — {hoje}")
print(f"OAB: {OAB}/{UF.upper()}")
print(f"{'='*55}\n")

# Busca Diário (meio=D) + Edital (meio=E) separadamente para clareza
comunicacoes_diario = fetch_comunicacoes(meio="D")
comunicacoes_edital = fetch_comunicacoes(meio="E")
todas = comunicacoes_diario + comunicacoes_edital

# Deduplica por ID
vistas = set()
unicas = []
for c in todas:
    if c["id"] not in vistas:
        vistas.add(c["id"])
        unicas.append(c)

print(f"\nTotal de comunicações únicas hoje: {len(unicas)}")

if not unicas:
    print("Nenhuma comunicação encontrada hoje. Nada a enviar.")
    exit(0)

# ── Separa por Prioridade ──────────────────────────────────────────────────
prioritarios = []
comuns = []

for item in unicas:
    if is_priority(item):
        prioritarios.append(item)
    else:
        comuns.append(item)

# ── Monta o e-mail ─────────────────────────────────────────────────────────
linhas = [
    f"RELATÓRIO DE COMUNICAÇÕES DJEN — {datetime.now().strftime('%d/%m/%Y')}",
    f"Advogado: STEVEN ADRIAN DOS SANTOS — OAB {OAB}/{UF.upper()}",
    f"Total de comunicações hoje: {len(unicas)} ({len(prioritarios)} PRIORITÁRIAS)\n",
]

idx_global = 1

# Seção de PRIORIDADES
if prioritarios:
    linhas.append(f"\n{'🔥'*20}")
    linhas.append(f"  🚨 PRIORIDADES (DECISÕES/DESPACHOS/INTIMAÇÕES) ")
    linhas.append(f"{'🔥'*20}")
    for item in prioritarios:
        linhas.append(formatar_item(item, idx_global, prioridade=True))
        idx_global += 1

# Seção de OUTRAS COMUNICAÇÕES
if comuns:
    linhas.append(f"\n{'─'*55}")
    linhas.append(f"  📋 OUTRAS COMUNICAÇÕES ")
    linhas.append(f"{'─'*55}")
    for item in comuns:
        linhas.append(formatar_item(item, idx_global, prioridade=False))
        idx_global += 1

corpo_email = "\n".join(linhas)

# ── Envia o e-mail ─────────────────────────────────────────────────────────
qtd_prio = len(prioritarios)
assunto = (
    f"DJEN {datetime.now().strftime('%d/%m/%Y')} — "
    f"URGENTE: {qtd_prio} PRIORIDADE(S)" if qtd_prio > 0 else f"DJEN {datetime.now().strftime('%d/%m/%Y')} — {len(comuns)} itens"
)

msg = MIMEMultipart()
msg["From"]    = EMAIL_REMETENTE
msg["To"]      = EMAIL_DESTINO
msg["Subject"] = assunto
msg.attach(MIMEText(corpo_email, "plain", "utf-8"))

try:
    print("\nConectando ao Gmail SMTP...")
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(EMAIL_REMETENTE, SENHA_APP)
    server.send_message(msg)
    server.quit()
    print(f"✅ E-mail enviado com sucesso! ({len(unicas)} comunicações)")
except Exception as e:
    print(f"❌ Erro ao enviar e-mail: {e}")
    exit(1)
