"""
Puente Streamlit <-> ElevenLabs
--------------------------------
Genera audios TTS con la API de ElevenLabs y los descarga con el nombre
que vos elijas (por defecto, numerados: 1.mp3, 2.mp3, 3.mp3, ...).

Cómo correrlo:
    pip install streamlit requests
    streamlit run app_elevenlabs.py

Necesitás tu API Key de ElevenLabs (la sacás en elevenlabs.io -> Profile -> API Keys).
"""

import io
import re
import zipfile

import requests
import streamlit as st

st.set_page_config(page_title="Generador de Voz", page_icon="🔊", layout="centered")

ELEVEN_BASE_URL = "https://api.elevenlabs.io/v1"


# ---------------------------------------------------------------------------
# Utilidades ElevenLabs
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=300)
def get_voices(api_key: str):
    """Trae la lista de voces disponibles en la cuenta."""
    resp = requests.get(
        f"{ELEVEN_BASE_URL}/voices",
        headers={"xi-api-key": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return {v["name"]: v["voice_id"] for v in data.get("voices", [])}


def generate_audio(api_key: str, voice_id: str, text: str, model_id: str,
                    stability: float, similarity_boost: float, style: float,
                    speaker_boost: bool) -> bytes:
    """Llama a la API de ElevenLabs y devuelve los bytes del mp3 generado."""
    url = f"{ELEVEN_BASE_URL}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": speaker_boost,
        },
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Error {resp.status_code}: {resp.text}")
    return resp.content


def sanitize_filename(name: str) -> str:
    """Deja el nombre de archivo limpio (sin caracteres raros)."""
    name = name.strip()
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name or "audio"


# ---------------------------------------------------------------------------
# Sidebar: configuración
# ---------------------------------------------------------------------------

st.sidebar.header("⚙️ Configuración")

api_key = st.sidebar.text_input("Clave de acceso", type="password")

model_id = st.sidebar.selectbox(
    "Modelo",
    ["eleven_multilingual_v2", "eleven_turbo_v2_5", "eleven_flash_v2_5", "eleven_monolingual_v1"],
    index=0,
)

with st.sidebar.expander("Ajustes de voz avanzados"):
    stability = st.slider("Stability", 0.0, 1.0, 0.5, 0.05)
    similarity_boost = st.slider("Similarity boost", 0.0, 1.0, 0.75, 0.05)
    style = st.slider("Style", 0.0, 1.0, 0.0, 0.05)
    speaker_boost = st.checkbox("Speaker boost", value=True)

st.sidebar.markdown("---")
naming_mode = st.sidebar.radio(
    "Cómo nombrar los archivos",
    ["Numérico (1, 2, 3...)", "Prefijo + número", "Nombre manual por línea"],
)
prefix = ""
if naming_mode == "Prefijo + número":
    prefix = st.sidebar.text_input("Prefijo", value="audio_")

# ---------------------------------------------------------------------------
# Cuerpo principal
# ---------------------------------------------------------------------------

st.title("🔊 Generador de audios")
st.caption("Escribí un texto por línea. Cada línea genera un audio separado.")

if not api_key:
    st.info("Ingresá tu clave de acceso en el panel lateral para empezar.")
    st.stop()

try:
    voices = get_voices(api_key)
except Exception as e:
    st.error(f"No se pudo conectar con el servicio: {e}")
    st.stop()

if not voices:
    st.warning("No se encontraron voces en tu cuenta.")
    st.stop()

PREFERRED_VOICE = "Ana Sofía-Conversational"
voice_names = list(voices.keys())

if PREFERRED_VOICE in voices:
    default_index = voice_names.index(PREFERRED_VOICE)
else:
    default_index = 0
    st.warning(
        f"No encontré la voz '{PREFERRED_VOICE}' en tu cuenta. "
        "Agregala primero a tu biblioteca de voces, o pegá su ID manualmente abajo."
    )

voice_name = st.selectbox("Voz", voice_names, index=default_index)
voice_id = voices[voice_name]

manual_voice_id = st.text_input(
    "Voice ID manual (opcional, sobreescribe la selección de arriba)",
    value="",
    help="Usalo si 'Ana Sofía-Conversational' todavía no está en tu cuenta pero ya tenés su ID.",
)
if manual_voice_id.strip():
    voice_id = manual_voice_id.strip()

default_text = "Primer audio de prueba\nSegundo audio de prueba"
raw_text = st.text_area("Textos (uno por línea)", value=default_text, height=200)

# Si el usuario eligió nombre manual, dejamos un campo por línea
manual_names = []
lines = [l for l in raw_text.split("\n") if l.strip()]

if naming_mode == "Nombre manual por línea":
    st.markdown("**Nombre de archivo para cada línea:**")
    for i, line in enumerate(lines, start=1):
        col1, col2 = st.columns([3, 2])
        with col1:
            st.text(line[:60] + ("..." if len(line) > 60 else ""))
        with col2:
            manual_names.append(st.text_input(f"Nombre {i}", value=str(i), key=f"name_{i}", label_visibility="collapsed"))

generate_btn = st.button("🎙️ Generar audios", type="primary", use_container_width=True)

if generate_btn:
    if not lines:
        st.warning("Escribí al menos un texto.")
        st.stop()

    results = []  # (filename, bytes)
    progress = st.progress(0.0)

    for i, line in enumerate(lines, start=1):
        if naming_mode == "Numérico (1, 2, 3...)":
            fname = f"{i}.mp3"
        elif naming_mode == "Prefijo + número":
            fname = f"{sanitize_filename(prefix)}{i}.mp3"
        else:
            fname = f"{sanitize_filename(manual_names[i - 1])}.mp3"

        try:
            audio_bytes = generate_audio(
                api_key, voice_id, line, model_id,
                stability, similarity_boost, style, speaker_boost,
            )
            results.append((fname, audio_bytes))
        except Exception as e:
            st.error(f"Error generando '{line[:40]}...': {e}")

        progress.progress(i / len(lines))

    st.session_state["results"] = results

# ---------------------------------------------------------------------------
# Resultados y descargas
# ---------------------------------------------------------------------------

if st.session_state.get("results"):
    st.success(f"{len(st.session_state['results'])} audio(s) generado(s).")
    st.markdown("---")

    for fname, audio_bytes in st.session_state["results"]:
        st.audio(audio_bytes, format="audio/mp3")
        st.download_button(
            label=f"⬇️ Descargar {fname}",
            data=audio_bytes,
            file_name=fname,
            mime="audio/mpeg",
            key=f"dl_{fname}",
        )
        st.markdown("---")

    # Descarga todo junto en un zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for fname, audio_bytes in st.session_state["results"]:
            zf.writestr(fname, audio_bytes)
    zip_buffer.seek(0)

    st.download_button(
        label="📦 Descargar todo (.zip)",
        data=zip_buffer,
        file_name="audios.zip",
        mime="application/zip",
        use_container_width=True,
    )
