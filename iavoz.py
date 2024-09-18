import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import requests
from pydub import AudioSegment
import io
import re
import tempfile

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()  # Usar una carpeta temporal para almacenar archivos
app.config['ALLOWED_EXTENSIONS'] = {'txt'}

YOUR_XI_API_KEY = "sk_1c7266f6dd0681924de371b9535adce989b87488436dd446"
VOICE_ID = "OYIb9zSloh1QDbhBhVWt"  # Cambiar según tu voz de Eleven Labs

# Función para convertir el tiempo de formato SRT a segundos
def srt_to_seconds(timestamp):
    time_parts = re.split(r'[:,]', timestamp)
    h, m, s, ms = map(int, time_parts)
    total_seconds = h * 3600 + m * 60 + s + ms / 1000
    return total_seconds

# Función para verificar la extensión del archivo
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/', methods=['GET', 'POST'])
def index():
    success_message = None
    error_message = None
    audio_url = None

    if request.method == 'POST':
        if 'file' not in request.files:
            error_message = 'No se encontró ningún archivo en la solicitud.'
        else:
            file = request.files['file']
            if file.filename == '':
                error_message = 'No se seleccionó ningún archivo.'
            elif file and allowed_file(file.filename):
                # Guardar el archivo en una carpeta temporal
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'uploaded.txt')
                file.save(file_path)

                # Leer el contenido del archivo SRT
                with open(file_path, 'r', encoding='utf-8') as f:
                    srt_data = f.read()

                # Parsear el texto SRT
                lines = srt_data.strip().split('\n\n')
                paragraphs = []
                for line in lines:
                    parts = line.split('\n')
                    index = parts[0]
                    times = parts[1].split(' --> ')
                    start_time = srt_to_seconds(times[0])
                    end_time = srt_to_seconds(times[1])
                    text = ' '.join(parts[2:])
                    paragraphs.append((start_time, end_time, text))

                segments = []

                for i, (start_time, end_time, paragraph) in enumerate(paragraphs):
                    is_last_paragraph = i == len(paragraphs) - 1
                    is_first_paragraph = i == 0

                    # Calcular la longitud del texto del párrafo
                    text_length = len(paragraph)

                    # Calcular stability dinámicamente basado en la longitud del texto
                    if text_length <= 100:
                        stability_value = 0.7
                    elif text_length > 100 and text_length <= 200:
                        stability_value = 0.75
                    else:
                        stability_value = 0.8

                    # Hacer la solicitud a la API de Eleven Labs con stability ajustado
                    response = requests.post(
                        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream",
                        json={
                            "text": paragraph,
                            "model_id": "eleven_multilingual_v2",
                            "accent_strength": 2.0,
                            "voice_settings": {
                                "stability": stability_value,
                                "similarity_boost": 0.5,
                                "style": 0.0,
                                "use_speaker_boost": True,
                                "accent_strength": 1.8
                            },
                            "previous_text": None if is_first_paragraph else paragraphs[i - 1][2],
                            "next_text": None if is_last_paragraph else paragraphs[i + 1][2]
                        },
                        headers={"xi-api-key": YOUR_XI_API_KEY},
                    )

                    if response.status_code != 200:
                        error_message = f"Error en la solicitud: {response.status_code}"
                        break

                    segments.append(AudioSegment.from_mp3(io.BytesIO(response.content)))

                    # Insertar silencio de 3 segundos (3000 milisegundos) después de cada párrafo
                    if not is_last_paragraph:
                        silence_segment = AudioSegment.silent(duration=3000)
                        segments.append(silence_segment)

                if not error_message:
                    # Concatenar todos los segmentos de audio
                    audio_segment = segments[0]
                    for new_segment in segments[1:]:
                        audio_segment = audio_segment + new_segment

                    # Exportar el audio final a un archivo temporal
                    audio_out_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output.wav')
                    audio_segment.export(audio_out_path, format="wav")

                    # Obtener la URL para reproducir el audio
                    audio_url = url_for('play_audio', filename='output.wav')

                    success_message = 'Audio generado correctamente.'

    return render_template('index.html', success_message=success_message, error_message=error_message, audio_url=audio_url)

@app.route('/play_audio/<filename>')
def play_audio(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)
