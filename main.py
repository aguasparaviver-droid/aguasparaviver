import os
from datetime import datetime
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from supabase import Client, create_client

load_dotenv()

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v22.0")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "nascente-fotos")

GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

user_states: dict[str, dict[str, Any]] = {}


def build_public_image_url(foto_path: str | None) -> str | None:
    if not foto_path or not SUPABASE_URL:
        return None
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{foto_path}"


def get_media_url(image_id: str) -> tuple[str, str | None]:
    if not WHATSAPP_TOKEN:
        raise RuntimeError("WHATSAPP_TOKEN não configurado.")

    url = f"{GRAPH_URL}/{image_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()
    media_url = data["url"]
    mime_type = data.get("mime_type")

    print("=== META MEDIA INFO ===")
    print(data)

    return media_url, mime_type


def download_media_bytes(media_url: str) -> bytes:
    if not WHATSAPP_TOKEN:
        raise RuntimeError("WHATSAPP_TOKEN não configurado.")

    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    response = requests.get(media_url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.content


def guess_extension(mime_type: str | None) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    return mapping.get((mime_type or "").lower(), ".jpg")


def upload_image_to_supabase(phone: str, image_id: str) -> str | None:
    if not supabase:
        print("SUPABASE NÃO CONFIGURADO. IMAGEM NÃO SERÁ ENVIADA.")
        return None

    media_url, mime_type = get_media_url(image_id)
    image_bytes = download_media_bytes(media_url)
    extension = guess_extension(mime_type)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    file_path = f"{phone}/{timestamp}_{image_id}{extension}"

    print("=== ENVIANDO IMAGEM PARA O SUPABASE STORAGE ===")
    print({"bucket": SUPABASE_BUCKET, "path": file_path, "mime_type": mime_type})

    supabase.storage.from_(SUPABASE_BUCKET).upload(
        path=file_path,
        file=image_bytes,
        file_options={
            "content-type": mime_type or "image/jpeg",
            "upsert": "false",
        },
    )

    print("=== IMAGEM ENVIADA PARA O STORAGE ===")
    return file_path


def save_registration(state: dict[str, Any], phone: str) -> None:
    if not supabase:
        raise RuntimeError("Supabase não configurado.")

    foto_path = None
    image_id = state.get("image_id")

    if image_id:
        foto_path = upload_image_to_supabase(phone, image_id)

    payload = {
        "telefone": phone,
        "esta_no_local": state.get("esta_no_local"),
        "tempo_existencia": state.get("tempo_existencia"),
        "periodo_aparece": state.get("periodo_aparece"),
        "estado_local": state.get("estado_local"),
        "ponto_referencia": state.get("ponto_referencia"),
        "latitude": state.get("latitude"),
        "longitude": state.get("longitude"),
        "image_id": image_id,
        "foto_path": foto_path,
        "status_envio": "confirmado",
    }

    print("=== PAYLOAD ENVIADO AO SUPABASE ===")
    print(payload)

    response = supabase.table("registros_nascentes").insert(payload).execute()

    print("=== REGISTRO SALVO NO SUPABASE ===")
    print(response)


def send_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not WHATSAPP_TOKEN:
        raise RuntimeError("WHATSAPP_TOKEN não configurado.")

    if not PHONE_NUMBER_ID:
        raise RuntimeError("PHONE_NUMBER_ID não configurado.")

    url = f"{GRAPH_URL}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    print("=== ENVIANDO PARA WHATSAPP ===")
    print(payload)

    response = requests.post(url, json=payload, headers=headers, timeout=30)

    print("=== STATUS DA RESPOSTA ===")
    print(response.status_code)
    print(response.text)

    response.raise_for_status()
    return response.json()


def send_text_message(to: str, text: str) -> dict[str, Any]:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    return send_request(payload)


def send_reply_buttons(
    to: str,
    body_text: str,
    buttons: list[dict[str, Any]],
    footer_text: str | None = None,
) -> dict[str, Any]:
    interactive = {
        "type": "button",
        "body": {"text": body_text},
        "action": {"buttons": buttons},
    }

    if footer_text:
        interactive["footer"] = {"text": footer_text}

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    }
    return send_request(payload)


def send_list_message(
    to: str,
    body_text: str,
    button_text: str,
    sections: list[dict[str, Any]],
    header_text: str | None = None,
    footer_text: str | None = None,
) -> dict[str, Any]:
    interactive = {
        "type": "list",
        "body": {"text": body_text},
        "action": {
            "button": button_text,
            "sections": sections,
        },
    }

    if header_text:
        interactive["header"] = {
            "type": "text",
            "text": header_text,
        }

    if footer_text:
        interactive["footer"] = {"text": footer_text}

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    }
    return send_request(payload)


def show_main_menu(to: str) -> dict[str, Any]:
    buttons = [
        {
            "type": "reply",
            "reply": {
                "id": "menu_registrar",
                "title": "Registrar",
            },
        },
        {
            "type": "reply",
            "reply": {
                "id": "menu_saber_mais",
                "title": "Saber mais",
            },
        },
    ]

    return send_reply_buttons(
        to=to,
        body_text="🌱 Olá! Este é o Águas para Viver.\nO que deseja fazer?",
        buttons=buttons,
        footer_text="Projeto de monitoramento de nascentes",
    )


def ask_onde_esta(to: str) -> dict[str, Any]:
    buttons = [
        {"type": "reply", "reply": {"id": "onde_esta_sim", "title": "Sim, estou"}},
        {"type": "reply", "reply": {"id": "onde_esta_nao", "title": "Não estou"}},
    ]

    return send_reply_buttons(
        to=to,
        body_text=(
            "📍 Você está no local da nascente neste momento?\n\n"
            "Se estiver no local, vamos pedir a localização e uma foto."
        ),
        buttons=buttons,
        footer_text="Escolha uma opção",
    )


def ask_tempo_existencia(to: str) -> dict[str, Any]:
    sections = [
        {
            "title": "Tempo de existência da nascente",
            "rows": [
                {
                    "id": "tempo_0_10",
                    "title": "0 a 10 anos",
                    "description": "A nascente existe entre 0 e 10 anos",
                },
                {
                    "id": "tempo_10_20",
                    "title": "10 a 20 anos",
                    "description": "A nascente existe entre 10 e 20 anos",
                },
                {
                    "id": "tempo_acima_20",
                    "title": "Acima de 20 anos",
                    "description": "A nascente existe há mais de 20 anos",
                },
                {
                    "id": "tempo_nao_sei",
                    "title": "Não sei informar",
                    "description": "Não sei estimar",
                },
            ],
        }
    ]

    return send_list_message(
        to=to,
        header_text="Cadastro de nascente",
        body_text="📅 Há quanto tempo essa nascente existe nesse local?",
        button_text="Ver opções",
        sections=sections,
        footer_text="Selecione uma opção",
    )


def ask_periodo_aparece(to: str) -> dict[str, Any]:
    buttons = [
        {"type": "reply", "reply": {"id": "periodo_ano_todo", "title": "Ano todo"}},
        {"type": "reply", "reply": {"id": "periodo_chuvoso", "title": "Só chuvoso"}},
        {"type": "reply", "reply": {"id": "periodo_nao_sei", "title": "Não sei"}},
    ]

    return send_reply_buttons(
        to=to,
        body_text="🌦️ Em qual período essa nascente aparece?",
        buttons=buttons,
        footer_text="Escolha uma opção",
    )


def ask_estado_local(to: str) -> dict[str, Any]:
    buttons = [
        {"type": "reply", "reply": {"id": "estado_preservado", "title": "Preservado"}},
        {"type": "reply", "reply": {"id": "estado_degradado", "title": "Degradado"}},
    ]

    return send_reply_buttons(
        to=to,
        body_text="🔍 Como está o local da nascente?",
        buttons=buttons,
        footer_text="Escolha uma opção",
    )


def ask_location_required(to: str) -> dict[str, Any]:
    return send_text_message(
        to,
        (
            "📍 Envie agora a localização da nascente.\n\n"
            "Como enviar no WhatsApp:\n"
            "1. Toque no ícone de clipe 📎\n"
            "2. Selecione 'Localização'\n"
            "3. Toque em 'Enviar sua localização atual'\n\n"
            "Nesta etapa, preciso da localização para continuar."
        ),
    )


def ask_photo_required(to: str) -> dict[str, Any]:
    return send_text_message(
        to,
        (
            "📷 Agora envie uma foto da nascente.\n\n"
            "Nesta etapa, aceito apenas foto.\n"
            "Não consigo receber áudio, vídeo, documento ou figurinhas para esse campo."
        ),
    )


def ask_optional_photo_decision(to: str) -> dict[str, Any]:
    buttons = [
        {"type": "reply", "reply": {"id": "foto_opcional_sim", "title": "Tenho foto"}},
        {"type": "reply", "reply": {"id": "foto_opcional_nao", "title": "Não tenho"}},
    ]

    return send_reply_buttons(
        to=to,
        body_text=(
            "📷 Você tem uma foto da nascente para enviar?\n\n"
            "Ela não é obrigatória nessa situação, mas ajuda muito na análise."
        ),
        buttons=buttons,
        footer_text="Escolha uma opção",
    )


def ask_optional_photo_send(to: str) -> dict[str, Any]:
    return send_text_message(
        to,
        (
            "📷 Pode enviar a foto da nascente agora.\n\n"
            "Nesta etapa, aceito apenas imagem.\n"
            "Se mudar de ideia e quiser seguir sem foto, envie 'oi' para reiniciar o fluxo."
        ),
    )


def ask_referencia(to: str) -> dict[str, Any]:
    return send_text_message(
        to,
        "📍 Informe um ponto de referência da nascente.\nEx.: perto da ponte, atrás da escola, ao lado da estrada."
    )


def ask_confirmacao(to: str) -> dict[str, Any]:
    buttons = [
        {"type": "reply", "reply": {"id": "confirmar_envio", "title": "Confirmar"}},
        {"type": "reply", "reply": {"id": "cancelar_envio", "title": "Cancelar"}},
    ]

    return send_reply_buttons(
        to=to,
        body_text="Deseja finalizar o envio desse registro?",
        buttons=buttons,
        footer_text="Confirme para concluir",
    )


def reset_user_state(phone: str) -> None:
    user_states[phone] = {"step": "menu"}


def get_user_state(phone: str) -> dict[str, Any]:
    if phone not in user_states:
        reset_user_state(phone)
    return user_states[phone]


def parse_incoming_message(message: dict[str, Any]) -> dict[str, Any]:
    message_type = message.get("type")

    parsed = {
        "type": message_type,
        "text": None,
        "button_id": None,
        "button_title": None,
        "list_id": None,
        "list_title": None,
        "location": None,
        "image_id": None,
    }

    if message_type == "text":
        parsed["text"] = message.get("text", {}).get("body", "").strip()

    elif message_type == "interactive":
        interactive = message.get("interactive", {})
        interactive_type = interactive.get("type")

        if interactive_type == "button_reply":
            parsed["type"] = "button_reply"
            parsed["button_id"] = interactive.get("button_reply", {}).get("id")
            parsed["button_title"] = interactive.get("button_reply", {}).get("title")

        elif interactive_type == "list_reply":
            parsed["type"] = "list_reply"
            parsed["list_id"] = interactive.get("list_reply", {}).get("id")
            parsed["list_title"] = interactive.get("list_reply", {}).get("title")

    elif message_type == "location":
        location = message.get("location", {})
        parsed["location"] = {
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
        }

    elif message_type == "image":
        parsed["image_id"] = message.get("image", {}).get("id")

    return parsed


def handle_start_or_menu(from_number: str) -> None:
    reset_user_state(from_number)
    show_main_menu(from_number)


def handle_unexpected_message_type(from_number: str, parsed: dict[str, Any]) -> None:
    state = get_user_state(from_number)
    step = state.get("step")
    message_type = parsed.get("type")

    if step == "localizacao":
        send_text_message(
            from_number,
            (
                "Ainda estou aguardando a localização da nascente 📍\n\n"
                "Envie a localização atual pelo WhatsApp para continuar. "
                "Nesta etapa, não consigo avançar com outro tipo de mensagem."
            ),
        )
        return

    if step in {"foto", "foto_opcional_envio"}:
        send_text_message(
            from_number,
            (
                "Ainda estou aguardando uma foto da nascente 📷\n\n"
                "Envie apenas uma imagem. "
                "Não consigo aceitar áudio, vídeo, documento, figurinha ou outro formato nesta etapa."
            ),
        )
        return

    if step == "referencia":
        send_text_message(
            from_number,
            (
                "Ainda preciso do ponto de referência em texto.\n\n"
                "Escreva uma referência do local, como por exemplo: "
                "'perto da ponte', 'atrás da escola' ou 'ao lado da estrada'."
            ),
        )
        return

    if step == "periodo_aparece":
        send_text_message(
            from_number,
            "Escolha uma das opções exibidas para informar em qual período a nascente aparece."
        )
        return

    if step == "estado_local":
        send_text_message(
            from_number,
            "Escolha uma das opções exibidas para informar como está o local da nascente."
        )
        return

    if step == "tempo_existencia":
        send_text_message(
            from_number,
            "Escolha uma das opções exibidas para informar há quanto tempo a nascente existe nesse local."
        )
        return

    if step == "onde_esta":
        send_text_message(
            from_number,
            "Escolha uma das opções exibidas para informar se você está ou não no local da nascente."
        )
        return

    if step == "foto_opcional_decisao":
        send_text_message(
            from_number,
            "Escolha uma das opções exibidas para informar se você tem ou não uma foto da nascente."
        )
        return

    if step == "confirmacao":
        send_text_message(
            from_number,
            "Para concluir, escolha uma das opções de confirmação exibidas na conversa."
        )
        return

    send_text_message(
        from_number,
        f"Recebi uma mensagem do tipo '{message_type}', mas neste momento preciso que você siga o fluxo do formulário. Para recomeçar, envie 'oi'."
    )


def build_summary(state: dict[str, Any]) -> str:
    linhas = [
        "Resumo do registro:",
        f"• Está no local: {state.get('esta_no_local', '-')}",
        f"• Tempo de existência: {state.get('tempo_existencia', '-')}",
        f"• Período em que aparece: {state.get('periodo_aparece', '-')}",
        f"• Estado do local: {state.get('estado_local', '-')}",
        f"• Referência: {state.get('ponto_referencia', '-')}",
    ]

    if state.get("latitude") is not None or state.get("longitude") is not None:
        linhas.append(f"• Latitude: {state.get('latitude', '-')}")
        linhas.append(f"• Longitude: {state.get('longitude', '-')}")
    else:
        linhas.append("• Localização enviada: Não")

    linhas.append(f"• Foto enviada: {'Sim' if state.get('image_id') else 'Não'}")
    linhas.append("")
    linhas.append("Deseja finalizar?")

    return "\n".join(linhas)


def handle_button_reply(from_number: str, parsed: dict[str, Any]) -> None:
    state = get_user_state(from_number)
    button_id = parsed["button_id"]

    if button_id == "menu_registrar":
        state["step"] = "onde_esta"
        ask_onde_esta(from_number)
        return

    if button_id == "menu_saber_mais":
        send_text_message(
            from_number,
            "O projeto Águas para Viver recebe registros de nascentes com informações sobre localização, foto e condições do local para apoiar o monitoramento ambiental."
        )
        return

    if button_id == "onde_esta_sim":
        state["esta_no_local"] = "Sim"
        state["step"] = "localizacao"
        ask_location_required(from_number)
        return

    if button_id == "onde_esta_nao":
        state["esta_no_local"] = "Não"
        state["latitude"] = None
        state["longitude"] = None
        state["step"] = "tempo_existencia"
        ask_tempo_existencia(from_number)
        return

    if button_id in {"periodo_ano_todo", "periodo_chuvoso", "periodo_nao_sei"}:
        mapa_periodo = {
            "periodo_ano_todo": "Ano todo",
            "periodo_chuvoso": "Só em período chuvoso",
            "periodo_nao_sei": "Não sei informar",
        }
        state["periodo_aparece"] = mapa_periodo[button_id]
        state["step"] = "estado_local"
        ask_estado_local(from_number)
        return

    if button_id in {"estado_preservado", "estado_degradado"}:
        mapa_estado = {
            "estado_preservado": "Preservado",
            "estado_degradado": "Degradado",
        }
        state["estado_local"] = mapa_estado[button_id]
        state["step"] = "referencia"
        ask_referencia(from_number)
        return

    if button_id == "foto_opcional_sim":
        state["step"] = "foto_opcional_envio"
        ask_optional_photo_send(from_number)
        return

    if button_id == "foto_opcional_nao":
        state["image_id"] = None
        state["step"] = "confirmacao"
        send_text_message(from_number, build_summary(state))
        ask_confirmacao(from_number)
        return

    if button_id == "confirmar_envio":
        print("=== REGISTRO FINAL ===")
        print(state)

        try:
            save_registration(state, from_number)
            send_text_message(
                from_number,
                "✅ Registro enviado com sucesso. Agradecemos pela contribuição.\n\nQuando quiser iniciar um novo registro, é só enviar 'oi'."
            )
        except Exception as e:
            print("=== ERRO AO SALVAR NO SUPABASE NO FLUXO FINAL ===")
            print(repr(e))
            send_text_message(
                from_number,
                "Recebemos seus dados, mas houve uma falha ao salvar o registro final. Tente novamente em instantes."
            )

        reset_user_state(from_number)
        return

    if button_id == "cancelar_envio":
        send_text_message(
            from_number,
            "Cadastro cancelado.\n\nQuando quiser começar novamente, é só enviar 'oi'."
        )
        reset_user_state(from_number)
        return

    send_text_message(
        from_number,
        "Não foi possível identificar essa ação. Para recomeçar, envie 'oi'."
    )


def handle_list_reply(from_number: str, parsed: dict[str, Any]) -> None:
    state = get_user_state(from_number)
    list_id = parsed["list_id"]

    mapa_tempo = {
        "tempo_0_10": "0 a 10 anos",
        "tempo_10_20": "10 a 20 anos",
        "tempo_acima_20": "Acima de 20 anos",
        "tempo_nao_sei": "Não sei informar",
    }

    if list_id in mapa_tempo:
        state["tempo_existencia"] = mapa_tempo[list_id]
        state["step"] = "periodo_aparece"
        ask_periodo_aparece(from_number)
        return

    send_text_message(
        from_number,
        "Não foi possível identificar a opção escolhida. Vamos tentar novamente."
    )

    if state.get("step") == "tempo_existencia":
        ask_tempo_existencia(from_number)
    else:
        show_main_menu(from_number)


def handle_text(from_number: str, parsed: dict[str, Any]) -> None:
    state = get_user_state(from_number)
    text = (parsed["text"] or "").strip()
    step = state.get("step")

    if text.lower() in {"oi", "olá", "ola", "menu", "iniciar", "start"}:
        handle_start_or_menu(from_number)
        return

    if step == "menu":
        handle_start_or_menu(from_number)
        return

    if step == "referencia":
        state["ponto_referencia"] = text

        if state.get("esta_no_local") == "Sim":
            state["step"] = "confirmacao"
            send_text_message(from_number, build_summary(state))
            ask_confirmacao(from_number)
        else:
            state["step"] = "foto_opcional_decisao"
            ask_optional_photo_decision(from_number)
        return

    if step == "localizacao":
        send_text_message(
            from_number,
            (
                "Ainda preciso da localização da nascente 📍\n\n"
                "Use o recurso de compartilhar localização do WhatsApp para continuar."
            ),
        )
        return

    if step in {"foto", "foto_opcional_envio"}:
        send_text_message(
            from_number,
            (
                "Ainda preciso da foto da nascente 📷\n\n"
                "Envie apenas uma imagem para continuar."
            ),
        )
        return

    if step == "onde_esta":
        send_text_message(
            from_number,
            "Escolha uma das opções exibidas para informar se você está ou não no local da nascente."
        )
        return

    if step == "tempo_existencia":
        send_text_message(
            from_number,
            "Escolha uma das opções exibidas para informar há quanto tempo a nascente existe nesse local."
        )
        return

    if step == "periodo_aparece":
        send_text_message(
            from_number,
            "Escolha uma das opções exibidas para informar em qual período a nascente aparece."
        )
        return

    if step == "estado_local":
        send_text_message(
            from_number,
            "Escolha uma das opções exibidas para informar como está o local da nascente."
        )
        return

    if step == "foto_opcional_decisao":
        send_text_message(
            from_number,
            "Escolha uma das opções exibidas para informar se você tem ou não uma foto da nascente."
        )
        return

    if step == "confirmacao":
        send_text_message(
            from_number,
            "Para concluir, escolha uma das opções de confirmação exibidas na conversa."
        )
        return

    send_text_message(
        from_number,
        "Para começar ou reiniciar o atendimento, envie 'oi'."
    )


def handle_location(from_number: str, parsed: dict[str, Any]) -> None:
    state = get_user_state(from_number)
    step = state.get("step")

    if step != "localizacao":
        send_text_message(
            from_number,
            (
                "Recebi uma localização fora da etapa esperada.\n\n"
                "Por enquanto, siga a pergunta atual do formulário. "
                "Se quiser recomeçar, envie 'oi'."
            ),
        )
        return

    location = parsed.get("location") or {}
    state["latitude"] = location.get("latitude")
    state["longitude"] = location.get("longitude")
    state["step"] = "foto"

    send_text_message(
        from_number,
        "Localização recebida com sucesso ✅\n\nAgora envie uma foto da nascente 📷"
    )


def handle_image(from_number: str, parsed: dict[str, Any]) -> None:
    state = get_user_state(from_number)
    step = state.get("step")

    if step not in {"foto", "foto_opcional_envio"}:
        send_text_message(
            from_number,
            (
                "Recebi uma foto fora da etapa esperada.\n\n"
                "Por enquanto, siga a pergunta atual do formulário. "
                "Se quiser recomeçar, envie 'oi'."
            ),
        )
        return

    state["image_id"] = parsed["image_id"]

    if step == "foto":
        state["step"] = "tempo_existencia"
        send_text_message(from_number, "Foto recebida com sucesso ✅")
        ask_tempo_existencia(from_number)
        return

    state["step"] = "confirmacao"
    send_text_message(from_number, "Foto recebida com sucesso ✅")
    send_text_message(from_number, build_summary(state))
    ask_confirmacao(from_number)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "message": "API do bot está rodando."}


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/registros")
def listar_registros():
    if not supabase:
        return {"error": "Supabase não configurado."}

    response = (
        supabase
        .table("registros_nascentes")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    registros = response.data or []

    saida = []
    for item in registros:
        saida.append({
            "id": item.get("id"),
            "created_at": item.get("created_at"),
            "telefone": item.get("telefone"),
            "esta_no_local": item.get("esta_no_local"),
            "tempo_existencia": item.get("tempo_existencia"),
            "periodo_aparece": item.get("periodo_aparece"),
            "estado_local": item.get("estado_local"),
            "ponto_referencia": item.get("ponto_referencia"),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "image_id": item.get("image_id"),
            "foto_path": item.get("foto_path"),
            "foto_url": build_public_image_url(item.get("foto_path")),
            "status_envio": item.get("status_envio"),
        })

    return {"registros": saida}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Águas para Viver</title>

  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  />

  <style>
    html, body {
      margin: 0;
      width: 100%;
      height: 100%;
      font-family: Inter, Arial, sans-serif;
      background: #0b0f14;
    }

    #map {
      width: 100%;
      height: 100vh;
    }

    .floating-title {
      position: absolute;
      top: 16px;
      left: 16px;
      z-index: 1000;
      background: rgba(18, 24, 32, 0.78);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      color: white;
      padding: 12px 14px;
      border-radius: 14px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
      max-width: 300px;
    }

    .floating-title h1 {
      margin: 0;
      font-size: 16px;
      font-weight: 600;
      letter-spacing: 0.2px;
    }

    .floating-title p {
      margin: 4px 0 0;
      font-size: 12px;
      line-height: 1.4;
      color: rgba(255,255,255,0.82);
    }

    .leaflet-popup-content-wrapper {
      border-radius: 16px;
      padding: 0;
      overflow: hidden;
      box-shadow: 0 14px 34px rgba(0,0,0,0.22);
    }

    .leaflet-popup-content {
      margin: 0;
      width: 220px !important;
    }

    .popup-card {
      background: white;
      color: #111827;
    }

    .popup-img {
      width: 100%;
      height: 120px;
      object-fit: cover;
      display: block;
      background: #eef2f7;
    }

    .popup-body {
      padding: 12px 12px 14px;
    }

    .popup-title {
      margin: 0 0 8px;
      font-size: 15px;
      font-weight: 700;
      color: #111827;
    }

    .popup-line {
      margin: 4px 0;
      font-size: 12px;
      line-height: 1.45;
      color: #374151;
    }

    .popup-label {
      font-weight: 600;
      color: #111827;
    }

    .leaflet-container a.leaflet-popup-close-button {
      color: #6b7280;
      padding: 8px 10px 0 0;
    }

    .leaflet-control-zoom {
      border: none !important;
      box-shadow: 0 10px 24px rgba(0,0,0,0.15) !important;
      border-radius: 14px !important;
      overflow: hidden;
    }

    .leaflet-control-zoom a {
      width: 34px !important;
      height: 34px !important;
      line-height: 34px !important;
      font-size: 18px !important;
    }
  </style>
</head>
<body>
  <div class="floating-title">
    <h1>🌱 Águas para Viver</h1>
    <p>Mapa demonstrativo de nascentes registradas (V.0.0.2) - Desenvolvido por Jade Pereira.</p>
  </div>

  <div id="map"></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const map = L.map('map', {
      zoomControl: true,
      preferCanvas: true
    }).setView([-19.861, -44.608], 13);

    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {
        maxZoom: 24,
        attribution: '&copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community'
      }
    ).addTo(map);

    function escapeHtml(text) {
      if (text === null || text === undefined) return '-';
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function formatDate(value) {
      if (!value) return '-';
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return value;
      return d.toLocaleString('pt-BR');
    }

    function popupHtml(r) {
      const foto = r.foto_url
        ? `<img class="popup-img" src="${r.foto_url}" alt="Foto da nascente"
             onerror="this.style.display='none'">`
        : '';

      return `
        <div class="popup-card">
          ${foto}
          <div class="popup-body">
            <h3 class="popup-title">Registro de nascente</h3>
            <div class="popup-line"><span class="popup-label">Tempo de existência:</span> ${escapeHtml(r.tempo_existencia)}</div>
            <div class="popup-line"><span class="popup-label">Período:</span> ${escapeHtml(r.periodo_aparece)}</div>
            <div class="popup-line"><span class="popup-label">Estado:</span> ${escapeHtml(r.estado_local)}</div>
            <div class="popup-line"><span class="popup-label">Referência:</span> ${escapeHtml(r.ponto_referencia)}</div>
            <div class="popup-line"><span class="popup-label">Data:</span> ${escapeHtml(formatDate(r.created_at))}</div>
          </div>
        </div>
      `;
    }

    async function carregarRegistros() {
      const res = await fetch('/registros');
      const data = await res.json();
      const registros = data.registros || [];

      const bounds = [];

      registros.forEach((r) => {
        const lat = r.latitude;
        const lng = r.longitude;

        if (lat === null || lat === undefined || lng === null || lng === undefined) {
          return;
        }

        const marker = L.circleMarker([lat, lng], {
          radius: 7,
          weight: 2,
          color: '#ffffff',
          fillColor: '#16a34a',
          fillOpacity: 0.95
        }).addTo(map);

        marker.bindPopup(popupHtml(r), {
          maxWidth: 240,
          closeButton: true
        });

        bounds.push([lat, lng]);
      });

      if (bounds.length) {
        map.fitBounds(bounds, { padding: [40, 40] });
      }
    }

    carregarRegistros();
  </script>
</body>
</html>
    """


@app.get("/webhook")
async def verify_webhook(request: Request) -> PlainTextResponse:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge or "", status_code=200)

    return PlainTextResponse(content="Forbidden", status_code=403)


@app.post("/webhook")
async def receive_webhook(request: Request) -> JSONResponse:
    data = await request.json()

    print("=== EVENTO RECEBIDO ===")
    print(data)

    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return JSONResponse(content={"status": "ok", "detail": "sem mensagens"})

        message = messages[0]
        from_number = message.get("from")

        if not from_number:
            return JSONResponse(content={"status": "ok", "detail": "sem remetente"})

        parsed = parse_incoming_message(message)

        print("=== MENSAGEM NORMALIZADA ===")
        print(parsed)

        if parsed["type"] == "text":
            handle_text(from_number, parsed)
        elif parsed["type"] == "button_reply":
            handle_button_reply(from_number, parsed)
        elif parsed["type"] == "list_reply":
            handle_list_reply(from_number, parsed)
        elif parsed["type"] == "location":
            handle_location(from_number, parsed)
        elif parsed["type"] == "image":
            handle_image(from_number, parsed)
        else:
            handle_unexpected_message_type(from_number, parsed)

    except Exception as e:
        print("=== ERRO AO PROCESSAR WEBHOOK ===")
        print(repr(e))

    return JSONResponse(content={"status": "ok"})
