import os
import time
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Variáveis injetadas pelo GitHub
OAB = os.getenv("NUMERO_OAB")
UF = os.getenv("UF_OAB")
EMAIL_REMETENTE = os.getenv("EMAIL_REMETENTE")
SENHA_APP = os.getenv("SENHA_APP_GMAIL")
EMAIL_DESTINO = os.getenv("EMAIL_DESTINO")

hoje = datetime.now().strftime("%Y-%m-%d")

# 1. Consultar a API do DJEN (com retry para lidar com instabilidade)
url = f"https://comunica.pje.jus.br/api/v1/comunicacao?numeroOab={OAB}&ufOab={UF}&dataDisponibilizacaoInicio={hoje}"

response = None
for tentativa in range(3):
    try:
        print(f"Tentativa {tentativa + 1}/3 de consulta à API...")
        response = requests.get(url, timeout=30)
        break
    except requests.exceptions.RequestException as e:
        print(f"Erro na tentativa {tentativa + 1}: {e}")
        if tentativa < 2:
            time.sleep(2 ** tentativa)  # espera 1s, 2s, 4s

if response is None:
    print("API do DJEN não respondeu após 3 tentativas. Tente novamente mais tarde.")
    exit(1)

if response.status_code == 200:
    dados = response.json()

    if dados.get("count", 0) > 0:
        # 2. Montar o texto do E-mail
        mensagens = []
        for item in dados["items"]:
            proc = item.get("numeroprocessocommascara", "N/A")
            orgao = item.get("nomeOrgao", "N/A")
            texto = item.get("texto", "")[:200] + "..."  # Resumo do texto
            link = item.get("link", "#")
            mensagens.append(
                f"Processo: {proc}\nÓrgão: {orgao}\nResumo: {texto}\nLink: {link}\n{'-'*40}"
            )

        corpo_email = (
            f"Você tem {dados['count']} nova(s) intimação(ões) no DJEN hoje:\n\n"
            + "\n".join(mensagens)
        )

        # 3. Enviar o E-mail via SMTP do Gmail
        msg = MIMEMultipart()
        msg["From"] = EMAIL_REMETENTE
        msg["To"] = EMAIL_DESTINO
        msg["Subject"] = f"Intimações DJEN - {hoje}"
        msg.attach(MIMEText(corpo_email, "plain"))

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(EMAIL_REMETENTE, SENHA_APP)
            server.send_message(msg)
            server.quit()
            print("E-mail enviado com sucesso.")
        except Exception as e:
            print(f"Erro ao enviar e-mail: {e}")
    else:
        print("Nenhuma intimação encontrada hoje.")
else:
    print(f"Erro na API: Status {response.status_code}")
