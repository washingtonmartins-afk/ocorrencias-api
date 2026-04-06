from flask import Flask, request, jsonify
import os
import smtplib
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

app = Flask(__name__)

# =========================
# CONFIGURAÇÕES GERAIS
# =========================
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)

DB_PATH = os.getenv("DB_PATH", "ocorrencias.db")
EMAIL_PEDAGOGICO = "pedagogico.vgd@vgd.ifmt.edu.br"

# Coordenações por curso
MAPEAMENTO_EMAILS = {
    "logistica": "teclog.vgd@ifmt.edu.br",
    "edificacoes": "tecedf.vgd@ifmt.edu.br",
    "desenho": "tecdcc.vgd@ifmt.edu.br",
    "sistemas": "tecdcc.vgd@ifmt.edu.br"
}


# =========================
# BANCO DE DADOS
# =========================
def init_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)  # 🔥 apaga o banco antigo
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ocorrencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disciplina TEXT NOT NULL,
            discente TEXT NOT NULL,
            turma TEXT NOT NULL,
            curso TEXT NOT NULL,
            data_ocorrencia TEXT NOT NULL,
            servidor_responsavel TEXT NOT NULL,
            servidor_email TEXT,
            reincidencia TEXT,
            artigo TEXT,
            inciso TEXT,
            enquadramento_resumo TEXT,
            descricao TEXT NOT NULL,
            mensagem_coord TEXT NOT NULL,
            destinatarios_to TEXT NOT NULL,
            destinatarios_cc TEXT NOT NULL,
            enviado_em TEXT,
            status_envio TEXT NOT NULL,
            erro_envio TEXT
        )
    """)
    conn.commit()
    conn.close()


# =========================
# VALIDAÇÃO
# =========================
def validar_payload(data: dict) -> list:
    obrigatorios = [
        "disciplina",
        "discente",
        "turma",
        "curso",
        "data_ocorrencia",
        "servidor_responsavel",
        "descricao",
        "mensagem_coord"
    ]
    return [campo for campo in obrigatorios if not data.get(campo)]


# =========================
# DESTINATÁRIOS
# =========================
def normalizar_curso(curso: str) -> str:
    if not curso:
        return ""

    curso = curso.strip().lower()
    mapa_alias = {
        "logística": "logistica",
        "logistica": "logistica",
        "edificações": "edificacoes",
        "edificacoes": "edificacoes",
        "desenho de construção civil": "desenho",
        "desenho de construcao civil": "desenho",
        "desenho": "desenho",
        "sistema para internet": "sistemas",
        "sistemas para internet": "sistemas",
        "sistemas": "sistemas"
    }
    return mapa_alias.get(curso, curso)


def obter_destinatarios(curso: str):
    curso_key = normalizar_curso(curso)
    email_coord = MAPEAMENTO_EMAILS.get(curso_key)

    if not email_coord:
        return None, None

    to = [email_coord]
    cc = [EMAIL_PEDAGOGICO]

    return to, cc


# =========================
# ENVIO DE E-MAIL
# =========================
def enviar_email(
    to: list[str],
    cc: list[str],
    assunto: str,
    corpo: str,
    reply_to: str | None = None
) -> None:
    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(to)
    msg["Cc"] = ", ".join(cc)
    msg["Subject"] = assunto

    if reply_to:
        msg["Reply-To"] = reply_to

    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    destinatarios_totais = to + cc

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, destinatarios_totais, msg.as_string())


# =========================
# PERSISTÊNCIA
# =========================
def salvar_ocorrencia(
    data: dict,
    to: list[str],
    cc: list[str],
    status_envio: str,
    enviado_em: str | None,
    erro_envio: str | None = None
):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ocorrencias (
            disciplina, discente, turma, curso, data_ocorrencia,
            servidor_responsavel, servidor_email, reincidencia,
            artigo, inciso, enquadramento_resumo, descricao,
            mensagem_coord, destinatarios_to, destinatarios_cc,
            enviado_em, status_envio, erro_envio
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("disciplina"),
        data.get("discente"),
        data.get("turma"),
        normalizar_curso(data.get("curso", "")),
        data.get("data_ocorrencia"),
        data.get("servidor_responsavel"),
        data.get("servidor_email"),
        data.get("reincidencia"),
        data.get("artigo"),
        data.get("inciso"),
        data.get("enquadramento_resumo"),
        data.get("descricao"),
        data.get("mensagem_coord"),
        ",".join(to),
        ",".join(cc),
        enviado_em,
        status_envio,
        erro_envio
    ))
    conn.commit()
    conn.close()


# =========================
# ROTAS
# =========================
@app.post("/ocorrencias/enviar")
def enviar_ocorrencia():
    try:
        data = request.get_json(force=True)

        faltando = validar_payload(data)
        if faltando:
            return jsonify({
                "ok": False,
                "erro": "Campos obrigatórios ausentes.",
                "faltando": faltando
            }), 400

        to, cc = obter_destinatarios(data["curso"])
        if not to:
            return jsonify({
                "ok": False,
                "erro": "Curso inválido ou não mapeado.",
                "curso_recebido": data.get("curso")
            }), 400

        assunto = f"Registro de ocorrência disciplinar – {data['discente']} – {data['turma']}"
        corpo = data["mensagem_coord"]
        reply_to = data.get("servidor_email")

        enviar_email(to, cc, assunto, corpo, reply_to=reply_to)

        enviado_em = datetime.utcnow().isoformat() + "Z"
        salvar_ocorrencia(data, to, cc, "enviado", enviado_em)

        return jsonify({
            "ok": True,
            "mensagem": "Ocorrência enviada com sucesso.",
            "destinatarios_to": to,
            "destinatarios_cc": cc,
            "enviado_em": enviado_em
        }), 200

    except Exception as e:
        import traceback
        erro_completo = traceback.format_exc()
        print("ERRO COMPLETO:\n", erro_completo)

        try:
            data = request.get_json(force=True)
            curso = data.get("curso", "")
            to, cc = obter_destinatarios(curso)

            salvar_ocorrencia(
                data=data,
                to=to or [],
                cc=cc or [],
                status_envio="erro",
                enviado_em=None,
                erro_envio=str(e)
            )
        except Exception as erro_secundario:
            print("ERRO AO SALVAR FALHA:\n", str(erro_secundario))

        return jsonify({
            "ok": False,
            "erro": str(e)
        }), 500


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "status": "online"
    }), 200


@app.get("/")
def home():
    return jsonify({
        "ok": True,
        "servico": "API de Ocorrências Disciplinares",
        "status": "online"
    }), 200


# =========================
# INICIALIZAÇÃO
# =========================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)