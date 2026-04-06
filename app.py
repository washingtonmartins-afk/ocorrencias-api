from flask import Flask, request, jsonify
import os
import smtplib
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

app = Flask(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)

DB_PATH = os.getenv("DB_PATH", "ocorrencias.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ocorrencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disciplina TEXT NOT NULL,
            discente TEXT NOT NULL,
            turma TEXT NOT NULL,
            data_ocorrencia TEXT NOT NULL,
            servidor_responsavel TEXT NOT NULL,
            reincidencia TEXT,
            artigo TEXT,
            inciso TEXT,
            enquadramento_resumo TEXT,
            descricao TEXT NOT NULL,
            mensagem_coord TEXT NOT NULL,
            destinatarios TEXT NOT NULL,
            enviado_em TEXT,
            status_envio TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def validar_payload(data: dict) -> list:
    obrigatorios = [
        "disciplina",
        "discente",
        "turma",
        "data_ocorrencia",
        "servidor_responsavel",
        "descricao",
        "mensagem_coord",
        "destinatarios"
    ]
    return [campo for campo in obrigatorios if not data.get(campo)]


def enviar_email(destinatarios: list[str], assunto: str, corpo: str) -> None:
    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, destinatarios, msg.as_string())


def salvar_ocorrencia(data: dict, status_envio: str, enviado_em: str | None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ocorrencias (
            disciplina, discente, turma, data_ocorrencia, servidor_responsavel,
            reincidencia, artigo, inciso, enquadramento_resumo, descricao,
            mensagem_coord, destinatarios, enviado_em, status_envio
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("disciplina"),
        data.get("discente"),
        data.get("turma"),
        data.get("data_ocorrencia"),
        data.get("servidor_responsavel"),
        data.get("reincidencia"),
        data.get("artigo"),
        data.get("inciso"),
        data.get("enquadramento_resumo"),
        data.get("descricao"),
        data.get("mensagem_coord"),
        ",".join(data.get("destinatarios", [])),
        enviado_em,
        status_envio
    ))
    conn.commit()
    conn.close()


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

        assunto = f"Registro de ocorrência disciplinar – {data['discente']} – {data['turma']}"
        destinatarios = data["destinatarios"]
        corpo = data["mensagem_coord"]

        enviar_email(destinatarios, assunto, corpo)

        enviado_em = datetime.utcnow().isoformat() + "Z"
        salvar_ocorrencia(data, "enviado", enviado_em)

        return jsonify({
            "ok": True,
            "mensagem": "Ocorrência enviada com sucesso.",
            "enviado_em": enviado_em
        }), 200

    except Exception as e:
        try:
            data = request.get_json(force=True)
            salvar_ocorrencia(data, "erro", None)
        except Exception:
            pass

        return jsonify({
            "ok": False,
            "erro": str(e)
        }), 500


@app.get("/health")
def health():
    return jsonify({"ok": True, "status": "online"}), 200


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)