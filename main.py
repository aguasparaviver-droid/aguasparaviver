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
        "tipo_nascente": state.get("tipo_nascente"),
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


def ask_tipo_nascente(to: str) -> dict[str, Any]:
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


def ask_estado_local(to: str) -> dict[str, Any]:
    buttons = [
        {"type": "reply", "reply": {"id": "estado_preservado", "title": "Preservado"}},
        {"type": "reply", "reply": {"id": "estado_alterado", "title": "Alterado"}},
        {"type": "reply", "reply": {"id": "estado_degradado", "title": "Degradado"}},
    ]

    return send_reply_buttons(
        to=to,
        body_text="2️⃣ Como está o local?",
        buttons=buttons,
        footer_text="Escolha uma opção",
    )


def ask_localizacao_opcoes(to: str) -> dict[str, Any]:
    buttons = [
        {"type": "reply", "reply": {"id": "localizacao_enviar", "title": "Enviar localização"}},
        {"type": "reply", "reply": {"id": "localizacao_pular", "title": "Pular"}},
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


def handle_button_reply(from_number: str, parsed: dict[str, Any]) -> None:
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
        send_text_message(from_number, "Perfeito. Pode enviar a localização atual da nascente 📍")
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

    send_text_message(from_number, "Não foi possível identificar essa ação. Para recomeçar, envie 'oi'.")


def handle_list_reply(from_number: str, parsed: dict[str, Any]) -> None:
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

    send_text_message(from_number, "Para começar ou reiniciar o atendimento, envie 'oi'.")


def handle_location(from_number: str, parsed: dict[str, Any]) -> None:
    state = get_user_state(from_number)
    step = state.get("step")

    if step != "localizacao":
        send_text_message(
            from_number,
            "Recebemos uma localização fora da etapa esperada. Para iniciar um novo registro, envie 'oi'."
        )
        return

    location = parsed.get("location") or {}
    state["latitude"] = location.get("latitude")
    state["longitude"] = location.get("longitude")
    state["step"] = "foto"

    send_text_message(
        from_number,
        "5️⃣ Localização recebida com sucesso. Agora envie uma foto 📷 da nascente."
    )


def handle_image(from_number: str, parsed: dict[str, Any]) -> None:
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
            "tipo_nascente": item.get("tipo_nascente"),
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
  <title>Águas para Viver - Dashboard</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #f6f8f7;
      color: #1f2937;
    }
    .topbar {
      padding: 16px 20px;
      background: white;
      border-bottom: 1px solid #e5e7eb;
    }
    .topbar h1 {
      margin: 0;
      font-size: 22px;
    }
    .topbar p {
      margin: 6px 0 0;
      color: #6b7280;
    }
    .layout {
      display: grid;
      grid-template-columns: 340px 1fr;
      height: calc(100vh - 78px);
    }
    .sidebar {
      background: white;
      border-right: 1px solid #e5e7eb;
      overflow-y: auto;
      padding: 16px;
    }
    .card {
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 12px;
      background: #fff;
      cursor: pointer;
      transition: 0.2s;
    }
    .card:hover {
      background: #f9fafb;
    }
    .card h3 {
      margin: 0 0 8px;
      font-size: 16px;
    }
    .meta {
      font-size: 13px;
      color: #4b5563;
      line-height: 1.45;
    }
    .badge {
      display: inline-block;
      margin-top: 8px;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 12px;
      background: #ecfdf5;
      color: #065f46;
    }
    #map {
      width: 100%;
      height: 100%;
    }
    .popup-img {
      width: 100%;
      max-width: 240px;
      border-radius: 8px;
      margin-top: 8px;
      display: block;
    }
    .empty {
      color: #6b7280;
      font-size: 14px;
    }
    @media (max-width: 900px) {
      .layout {
        grid-template-columns: 1fr;
        grid-template-rows: 280px 1fr;
      }
      .sidebar {
        order: 2;
        border-right: none;
        border-top: 1px solid #e5e7eb;
      }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <h1>🌱 Águas para Viver</h1>
    <p>Mapa demonstrativo de registros de nascentes</p>
  </div>

  <div class="layout">
    <aside class="sidebar">
      <div id="lista"></div>
    </aside>
    <main id="map"></main>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const map = L.map('map').setView([-19.861, -44.608], 12);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap'
    }).addTo(map);

    function escapeHtml(text) {
      if (text === null || text === undefined) return '-';
      return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    async function carregarRegistros() {
      const res = await fetch('/registros');
      const data = await res.json();
      const registros = data.registros || [];
      const lista = document.getElementById('lista');

      if (!registros.length) {
        lista.innerHTML = '<p class="empty">Nenhum registro encontrado.</p>';
        return;
      }

      const bounds = [];

      registros.forEach((r) => {
        const lat = r.latitude;
        const lng = r.longitude;

        const fotoHtml = r.foto_url
          ? `<img class="popup-img" src="${r.foto_url}" alt="Foto da nascente" />`
          : '<p><em>Sem foto disponível</em></p>';

        const popupHtml = `
          <div style="min-width:220px;">
            <strong>${escapeHtml(r.tipo_nascente || 'Nascente')}</strong><br/>
            <b>Estado:</b> ${escapeHtml(r.estado_local)}<br/>
            <b>Referência:</b> ${escapeHtml(r.ponto_referencia)}<br/>
            <b>Telefone:</b> ${escapeHtml(r.telefone)}<br/>
            <b>Data:</b> ${escapeHtml(r.created_at)}<br/>
            ${fotoHtml}
          </div>
        `;

        let marker = null;

        if (lat !== null && lat !== undefined && lng !== null && lng !== undefined) {
          marker = L.marker([lat, lng]).addTo(map).bindPopup(popupHtml);
          bounds.push([lat, lng]);
        }

        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
          <h3>${escapeHtml(r.tipo_nascente || 'Nascente')}</h3>
          <div class="meta">
            <div><strong>Estado:</strong> ${escapeHtml(r.estado_local)}</div>
            <div><strong>Referência:</strong> ${escapeHtml(r.ponto_referencia)}</div>
            <div><strong>Coord.:</strong> ${escapeHtml(lat)}, ${escapeHtml(lng)}</div>
          </div>
          <span class="badge">Registro #${escapeHtml(r.id)}</span>
        `;

        card.addEventListener('click', () => {
          if (marker) {
            map.setView([lat, lng], 16);
            marker.openPopup();
          }
        });

        lista.appendChild(card);
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
            send_text_message(
                from_number,
                f"Recebemos uma mensagem do tipo '{parsed['type']}', mas esse formato ainda não está configurado."
            )

    except Exception as e:
        print("=== ERRO AO PROCESSAR WEBHOOK ===")
        print(repr(e))

    return JSONResponse(content={"status": "ok"})
