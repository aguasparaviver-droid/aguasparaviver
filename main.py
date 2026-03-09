import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v22.0")

GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"

# Estado em memória para MVP
user_states = {}


def send_request(payload: dict) -> dict:
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


def send_text_message(to: str, text: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    return send_request(payload)


def send_reply_buttons(to: str, body_text: str, buttons: list, footer_text: str | None = None) -> dict:
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
    sections: list,
    header_text: str | None = None,
    footer_text: str | None = None,
) -> dict:
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


def show_main_menu(to: str) -> dict:
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


def ask_tipo_nascente(to: str) -> dict:
    sections = [
        {
            "title": "Tipos de nascente",
            "rows": [
                {
                    "id": "tipo_olho_dagua",
                    "title": "Olho d'água",
                    "description": "Nascente pontual e visível",
                },
                {
                    "id": "tipo_mina",
                    "title": "Mina",
                    "description": "Saída de água do terreno",
                },
                {
                    "id": "tipo_brejo",
                    "title": "Brejo",
                    "description": "Área encharcada",
                },
                {
                    "id": "tipo_corrego",
                    "title": "Córrego",
                    "description": "Curso d'água associado",
                },
                {
                    "id": "tipo_outro",
                    "title": "Outro",
                    "description": "Outro tipo informado",
                },
            ],
        }
    ]

    return send_list_message(
        to=to,
        header_text="Cadastro de nascente",
        body_text="1️⃣ Escolha o tipo de nascente:",
        button_text="Ver opções",
        sections=sections,
        footer_text="Selecione uma opção",
    )


def ask_estado_local(to: str) -> dict:
    buttons = [
        {
            "type": "reply",
            "reply": {"id": "estado_preservado", "title": "Preservado"},
        },
        {
            "type": "reply",
            "reply": {"id": "estado_alterado", "title": "Alterado"},
        },
        {
            "type": "reply",
            "reply": {"id": "estado_degradado", "title": "Degradado"},
        },
    ]

    return send_reply_buttons(
        to=to,
        body_text="2️⃣ Como está o local?",
        buttons=buttons,
        footer_text="Escolha uma opção",
    )


def ask_localizacao_opcoes(to: str) -> dict:
    buttons = [
        {
            "type": "reply",
            "reply": {"id": "localizacao_enviar", "title": "Enviar localização"},
        },
        {
            "type": "reply",
            "reply": {"id": "localizacao_pular", "title": "Pular"},
        },
    ]

    return send_reply_buttons(
        to=to,
        body_text=(
            "4️⃣ Agora precisamos da localização da nascente.\n\n"
            "📍 Importante: a pessoa precisa estar próxima do local no momento do envio, "
            "para que a coordenada fique mais precisa.\n\n"
            "Como enviar a localização no WhatsApp:\n"
            "1. Toque no ícone de clipe ou '+'\n"
            "2. Selecione 'Localização'\n"
            "3. Toque em 'Enviar sua localização atual'\n\n"
            "Se preferir, é possível pular essa etapa."
        ),
        buttons=buttons,
        footer_text="Escolha uma opção",
    )


def ask_confirmacao(to: str) -> dict:
    buttons = [
        {
            "type": "reply",
            "reply": {"id": "confirmar_envio", "title": "Confirmar"},
        },
        {
            "type": "reply",
            "reply": {"id": "cancelar_envio", "title": "Cancelar"},
        },
    ]

    return send_reply_buttons(
        to=to,
        body_text="Deseja finalizar o envio desse registro?",
        buttons=buttons,
        footer_text="Confirme para concluir",
    )


def reset_user_state(phone: str):
    user_states[phone] = {"step": "menu"}


def get_user_state(phone: str) -> dict:
    if phone not in user_states:
        reset_user_state(phone)
    return user_states[phone]


def parse_incoming_message(message: dict) -> dict:
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
        parsed["text"] = message["text"]["body"].strip()

    elif message_type == "interactive":
        interactive = message.get("interactive", {})
        interactive_type = interactive.get("type")

        if interactive_type == "button_reply":
            parsed["type"] = "button_reply"
            parsed["button_id"] = interactive["button_reply"]["id"]
            parsed["button_title"] = interactive["button_reply"]["title"]

        elif interactive_type == "list_reply":
            parsed["type"] = "list_reply"
            parsed["list_id"] = interactive["list_reply"]["id"]
            parsed["list_title"] = interactive["list_reply"]["title"]

    elif message_type == "location":
        parsed["location"] = {
            "latitude": message["location"]["latitude"],
            "longitude": message["location"]["longitude"],
        }

    elif message_type == "image":
        parsed["image_id"] = message["image"]["id"]

    return parsed


def handle_start_or_menu(from_number: str):
    reset_user_state(from_number)
    show_main_menu(from_number)


def handle_button_reply(from_number: str, parsed: dict):
    state = get_user_state(from_number)
    button_id = parsed["button_id"]

    if button_id == "menu_registrar":
        state["step"] = "tipo_nascente"
        ask_tipo_nascente(from_number)
        return

    if button_id == "menu_saber_mais":
        send_text_message(
            from_number,
            "O projeto Águas para Viver recebe registros de nascentes com descrição, localização e foto para apoiar o monitoramento ambiental."
        )
        return

    if button_id in {"estado_preservado", "estado_alterado", "estado_degradado"}:
        mapa_estado = {
            "estado_preservado": "Preservado",
            "estado_alterado": "Alterado",
            "estado_degradado": "Degradado",
        }
        state["estado_local"] = mapa_estado[button_id]
        state["step"] = "referencia"
        send_text_message(
            from_number,
            "3️⃣ Informe um ponto de referência da nascente.\nEx.: perto da ponte, atrás da escola, ao lado da estrada."
        )
        return

    if button_id == "localizacao_enviar":
        state["step"] = "localizacao"
        send_text_message(
            from_number,
            "Perfeito. Pode enviar a localização atual da nascente 📍"
        )
        return

    if button_id == "localizacao_pular":
        state["latitude"] = None
        state["longitude"] = None
        state["step"] = "foto"
        send_text_message(
            from_number,
            "Tudo certo. Vamos seguir sem a localização.\n\n5️⃣ Agora envie uma foto 📷 da nascente."
        )
        return

    if button_id == "confirmar_envio":
        print("=== REGISTRO FINAL ===")
        print(state)

        send_text_message(
            from_number,
            "✅ Registro enviado com sucesso. Agradecemos pela contribuição.\n\nQuando quiser iniciar um novo registro, é só enviar 'oi'."
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

    send_text_message(from_number, "Não foi possível identificar essa ação. Para recomeçar, envie 'oi'.")


def handle_list_reply(from_number: str, parsed: dict):
    state = get_user_state(from_number)
    list_id = parsed["list_id"]

    mapa_tipos = {
        "tipo_olho_dagua": "Olho d'água",
        "tipo_mina": "Mina",
        "tipo_brejo": "Brejo",
        "tipo_corrego": "Córrego",
        "tipo_outro": "Outro",
    }

    if list_id in mapa_tipos:
        state["tipo_nascente"] = mapa_tipos[list_id]
        state["step"] = "estado_local"
        ask_estado_local(from_number)
        return

    send_text_message(from_number, "Não foi possível identificar a opção escolhida. Vamos tentar de novo.")
    ask_tipo_nascente(from_number)


def handle_text(from_number: str, parsed: dict):
    state = get_user_state(from_number)
    text = parsed["text"]
    step = state.get("step")

    if text.lower() in {"oi", "olá", "ola", "menu", "iniciar", "start"}:
        handle_start_or_menu(from_number)
        return

    if step == "menu":
        handle_start_or_menu(from_number)
        return

    if step == "referencia":
        state["ponto_referencia"] = text
        state["step"] = "aguardando_decisao_localizacao"
        ask_localizacao_opcoes(from_number)
        return

    if step == "localizacao":
        send_text_message(
            from_number,
            "Ainda precisamos da localização 📍. Use o recurso de compartilhar localização do WhatsApp."
        )
        return

    if step == "foto":
        send_text_message(
            from_number,
            "Agora precisamos da foto 📷 da nascente para concluir o registro."
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


def handle_location(from_number: str, parsed: dict):
    state = get_user_state(from_number)
    step = state.get("step")

    if step != "localizacao":
        send_text_message(
            from_number,
            "Recebemos uma localização fora da etapa esperada. Para iniciar um novo registro, envie 'oi'."
        )
        return

    state["latitude"] = parsed["location"]["latitude"]
    state["longitude"] = parsed["location"]["longitude"]
    state["step"] = "foto"

    send_text_message(
        from_number,
        "5️⃣ Localização recebida com sucesso. Agora envie uma foto 📷 da nascente."
    )


def handle_image(from_number: str, parsed: dict):
    state = get_user_state(from_number)
    step = state.get("step")

    if step != "foto":
        send_text_message(
            from_number,
            "Recebemos uma foto fora da etapa esperada. Para iniciar um novo registro, envie 'oi'."
        )
        return

    state["image_id"] = parsed["image_id"]
    state["step"] = "confirmacao"

    resumo = (
        "Resumo do registro:\n"
        f"• Tipo: {state.get('tipo_nascente', '-')}\n"
        f"• Estado: {state.get('estado_local', '-')}\n"
        f"• Referência: {state.get('ponto_referencia', '-')}\n"
        f"• Latitude: {state.get('latitude', '-')}\n"
        f"• Longitude: {state.get('longitude', '-')}\n\n"
        "Deseja finalizar?"
    )

    send_text_message(from_number, resumo)
    ask_confirmacao(from_number)


@app.get("/")
def root():
    return {"status": "ok", "message": "API do bot está rodando."}


@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge or "", status_code=200)

    return PlainTextResponse(content="Forbidden", status_code=403)


@app.post("/webhook")
async def receive_webhook(request: Request):
    data = await request.json()

    print("EVENTO RECEBIDO:")
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
        parsed = parse_incoming_message(message)

        print("MENSAGEM NORMALIZADA:")
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
            send_text_message(
                from_number,
                f"Recebemos uma mensagem do tipo '{parsed['type']}', mas esse formato ainda não está configurado."
            )

    except Exception as e:
        print("ERRO AO PROCESSAR WEBHOOK:", str(e))

    return JSONResponse(content={"status": "ok"})
