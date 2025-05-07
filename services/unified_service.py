import time
from pathlib import Path
import uuid
import os
from typing import Dict, Any

from services.whisper_service import get_whisper_model
from services.translation_service import get_translation_model
from services.tts_service import get_tts

class WhisperRequest:
    """Clase auxiliar para adaptar la solicitud al formato que espera el servicio Whisper"""
    def __init__(self, audio_path: str):
        self.audio_path = audio_path

def process_unified_translation(request) -> Dict[str, Any]:
    """
    Procesa un flujo completo: transcripción (Whisper) → traducción (M2M100) → síntesis de voz (F5TTS)
    
    Args:
        request: La solicitud unificada con todos los parámetros necesarios
        
    Returns:
        Un diccionario con todos los resultados del proceso
    """
    # Iniciar temporizador total
    total_start_time = time.time()
    result = {}
    
    # Verificar existencia de los archivos de audio
    audio_path = Path(request.audio_path)
    if not audio_path.exists():
        return {
            "error": f"El archivo de audio {request.audio_path} no existe"
        }
    
    voice_reference_path = Path(request.voice_reference_path)
    if not voice_reference_path.exists():
        return {
            "error": f"El archivo de referencia de voz {request.voice_reference_path} no existe"
        }
    
    # Preparar la respuesta con la ruta del audio original
    result["original_audio_path"] = str(audio_path)
    result["source_lang"] = request.source_lang
    result["target_lang"] = request.target_lang
    
    # 1. PASO UNO: TRANSCRIPCIÓN con Whisper
    print(f"🎙️ Transcribiendo audio: {audio_path}")
    transcription_start = time.time()
    
    # Crear objeto de solicitud para el servicio Whisper
    whisper_request = WhisperRequest(str(audio_path))
    
    # Obtener modelo cargado (usar la función que evita recargar)
    whisper_model = get_whisper_model()
    
    # Realizar transcripción
    transcription_result = whisper_model.transcribe(str(audio_path), fp16=False)
    transcribed_text = transcription_result["text"]
    
    # Calcular tiempo de transcripción
    transcription_time = time.time() - transcription_start
    print(f"✅ Transcripción completada en {transcription_time:.2f}s: {transcribed_text[:50]}...")
    
    # Almacenar resultados de la transcripción
    result["transcribed_text"] = transcribed_text
    result["transcription_time"] = round(transcription_time, 2)
    
    # 2. PASO DOS: TRADUCCIÓN con M2M100
    print(f"🌐 Traduciendo de {request.source_lang} a {request.target_lang}")
    translation_start = time.time()
    
    # Obtener modelo, tokenizador y dispositivo
    model, tokenizer, device = get_translation_model()
    
    # Configurar idioma de origen
    tokenizer.src_lang = request.source_lang
    
    # Codificar texto transcrito
    encoded_text = tokenizer(transcribed_text, return_tensors="pt").to(device)
    
    # Generar traducción
    generated_tokens = model.generate(
        **encoded_text, 
        forced_bos_token_id=tokenizer.get_lang_id(request.target_lang)
    )
    
    # Decodificar traducción
    translated_text = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    
    # Calcular tiempo de traducción
    translation_time = time.time() - translation_start
    print(f"✅ Traducción completada en {translation_time:.2f}s: {translated_text[:50]}...")
    
    # Almacenar resultados de la traducción
    result["translated_text"] = translated_text
    formatted_text = translated_text.strip()
    result["translation_time"] = round(translation_time, 2)
    
    # 3. PASO TRES: SÍNTESIS DE VOZ con F5TTS
    print(f"🔊 Generando audio con la traducción")
    tts_start = time.time()
    
    # Obtener instancia TTS
    tts = get_tts()
    
    # Crear directorio único para la salida
    output_dir = Path("unified_outputs") / uuid.uuid4().hex
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "translated_audio.wav"
    
    # Generar síntesis de voz:
    # - Usa el texto transcrito como referencia (ref_text)
    # - Usa el texto traducido como texto a generar (gen_text)
    try:
        print(translated_text)
        tts.infer(
            ref_file=str(voice_reference_path),
            ref_text=transcribed_text,  # Texto transcrito como referencia
            gen_text=formatted_text,   # Texto traducido para generar
            speed=0.8,
            file_wave=str(output_file)
        )
    except Exception as e:
        return {
            "error": f"Error al generar audio: {str(e)}",
            "transcribed_text": transcribed_text,
            "translated_text": translated_text,
            "transcription_time": round(transcription_time, 2),
            "translation_time": round(translation_time, 2)
        }
    
    # Calcular tiempo de síntesis
    tts_time = time.time() - tts_start
    print(f"✅ Síntesis de voz completada en {tts_time:.2f}s: {output_file}")
    
    # Almacenar resultados de la síntesis
    result["output_audio_path"] = str(output_file)
    result["tts_time"] = round(tts_time, 2)
    
    # Calcular tiempo total
    total_time = time.time() - total_start_time
    result["total_time"] = round(total_time, 2)
    
    print(f"✅ Proceso unificado completado en {total_time:.2f}s")
    
    return result