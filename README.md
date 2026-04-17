# 🤖 Robô de Intimações DJEN

Consulta diária automática da API do DJEN (PJe) e envio de e-mail com as intimações do dia.

## Como funciona

Roda automaticamente de segunda a sexta às **06:00 (Brasília)** via GitHub Actions.
Se houver intimações no dia, envia um e-mail resume para o destinatário configurado.

## Secrets necessários

No repositório GitHub: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Valor |
|---|---|
| `NUMERO_OAB` | `227892` |
| `UF_OAB` | `MG` |
| `EMAIL_REMETENTE` | `intimacoescnj2026sadv@gmail.com` |
| `SENHA_APP_GMAIL` | *(Senha de Aplicativo gerada no Google)* |
| `EMAIL_DESTINO` | `stevenadriandossantos@gmail.com` |

> ⚠️ Use uma **Senha de Aplicativo** do Google, não sua senha pessoal.
> Gere em: myaccount.google.com → Segurança → Verificação em duas etapas → Senhas de app

## Execução manual

Na aba **Actions** do repositório, clique em **"Robô de Intimações DJEN"** → **Run workflow**.
