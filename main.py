import os
import pdfplumber
import gradio as gr
import google.generativeai as genai
from pydub import AudioSegment
from murf import Murf
import glob
import requests
import base64

# ========== CONFIGURATION ==========
GEMINI_API_KEY = "YOUR_API_KEY"
MURF_API_KEY = "YOUR_API_KEY"
GEMINI_MODEL = "gemini-1.5-flash"
OUTPUT_FOLDER = os.path.join(os.getcwd(), "podcast_chunks")

LANGUAGES = {
    "en-US": "English",
    "hi-IN": "Hindi",
    "de-DE": "German",
    "fr-FR": "French"
}

# ========== INIT ==========
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
genai.configure(api_key=GEMINI_API_KEY)
client = Murf(api_key=MURF_API_KEY)

# ========== PDF PROCESSING ==========
def extract_text_from_pdf(pdf_path):
    """
    Extracts all text from a PDF file. Raises error if no text found.
    """
    text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    if not text.strip():
        raise ValueError("No text could be extracted from the PDF. Please check the document content.")

    return text

def validate_pdf(pdf_path):
    """
    Validates a PDF file for extension, minimum size, and readability.
    """
    if not pdf_path.lower().endswith('.pdf'):
        raise ValueError("File must be a PDF.")
    if os.path.getsize(pdf_path) < 200:
        raise ValueError("File is empty or too small to be a valid PDF.")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                raise ValueError("PDF has no pages or is not readable.")
    except Exception as e:
        raise ValueError(f"Could not open PDF file: {e}")

def chunk_text(text, max_chars=3500):
    """
    Splits text into chunks of max_chars for processing.
    """
    chunks = []

    while len(text) > max_chars:
        split_at = text[:max_chars].rfind('. ')
        split_at = split_at if split_at != -1 else max_chars
        chunks.append(text[:split_at+1].strip())
        text = text[split_at+1:]

    if text.strip():
        chunks.append(text.strip())

    return chunks

def cleanup_temp_audio_files(folder, extension=".wav"):
    """
    Deletes all temporary audio files after processing.
    """
    pattern = os.path.join(folder, f"*{extension}")

    for audio_file in glob.glob(pattern):
        try:
            os.remove(audio_file)
        except Exception as e:
            print(f"Failed to remove {audio_file}: {e}")

# ========== GEMINI AI INTEGRATIONS ==========
def generate_conversational_script(text_chunk, chunk_idx=0, total_chunks=1, prev_script_tail="", output_lang="en-US"):
    """
    Generates a conversational podcast script for a text chunk.
    """
    # System message for Gemini: controls style and rules
    context = ""
    intro = ""
    outro = ""

    if chunk_idx == 0:
        intro = "Begin with a friendly podcast introduction by Nishant."
    else:
        context = (
            f"Continue the conversation *seamlessly* from the previous lines below.\n"
            f"Do NOT repeat any introduction, greeting, or recap. "
            f"Do NOT mention the podcast title, host, or guest names at the start.\n"
            f"Previous lines:\n{prev_script_tail}\n"
        )

    if chunk_idx == total_chunks - 1:
        outro = "End with a natural, friendly sign-off thanking listeners for joining ‘TechTalks with Nishant’."
    else:
        outro = (
            "Do NOT include any summary, thank you, conclusion, or sign-off at the end. "
            "Continue the conversation as if the microphones never turned off."
        )

    system_message = (
        "You are an expert podcast script writer for the show ‘TechTalks with Nishant’. "
        "Transform provided input text into an engaging, informative podcast conversation. "
        "The host should always be named Nishant and the guest should always be named Megha. "
        "Only use 'Nishant:' and 'Megha:' as speaker labels for every line. "
        "Nishant leads the discussion and Megha provides insights and answers. "
        "Do NOT use any Markdown formatting (such as ** or *), nor any other text decorations. "
        "Write in clear, plain text for easy reading and text-to-speech synthesis. "
        "Use a natural, friendly, and conversational tone suitable for a general audience. "
        "Explain complex ideas simply, use analogies or stories when appropriate, and avoid unnecessary jargon. "
        f"{context}{intro} {outro}"
    )

    # Ensure output language if not English
    if output_lang != "en-US":
        system_message += f" All output must be in {LANGUAGES.get(output_lang, 'en-US')}."

    user_message = (
        "Please create a podcast script based on the input text below.\n"
        "Guidelines:\n"
        "- Use a conversational, accessible tone.\n"
        "- Format the script strictly as a back-and-forth between 'Nishant:' and 'Megha:' for every line.\n"
        "- Include natural speech markers (e.g., 'hmm', 'you know', 'well…') to make it sound authentic.\n"
        "- Keep the conversation concise and focused, summarizing the key points from the input.\n"
        "- Do not include any music, sound effects, or bracketed placeholders.\n"
        "- Do NOT introduce the speakers or podcast unless explicitly instructed in the system message.\n"
        "- Do NOT add any conclusions, recaps, or sign-off messages unless explicitly instructed in the system message.\n"
        "\n"
        "Input Text:\n"
        f"{text_chunk}\n\n"
        "Podcast Script:"
    )

    generation_config = {
        "temperature": 0.8,
        "top_p": 0.9,
        "top_k": 40,
        "max_output_tokens": 2048,
    }

    try:
        # noinspection PyTypeChecker
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config=generation_config,
            system_instruction=system_message
        )
        response = model.generate_content(user_message)
        return response.text
    except Exception as e:
        print("Gemini API error:", e)
        return (
            "Nishant: Sorry, there was an error generating this section.\n"
            "Megha: Let's move on to the next part!"
        )

def translate_text(text, target_lang="en-US"):
    """
    Translate text using Gemini if target_lang is not English.
    """
    if target_lang != "en-US":
        system_message = (
            f"You are an expert translator. Translate the following text to {target_lang} in a clear, simple, and modern style. "
            f"Use everyday language and common words, as spoken by regular people today, not old-fashioned or overly formal terms. "
            f"Make the translation sound natural, conversational, and easy to understand. Only output the translated text, no notes, no English."
        )

        user_message = text
        generation_config = {
            "temperature": 0.3,
            "max_output_tokens": 2048,
        }

        try:
            # noinspection PyTypeChecker
            model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                generation_config=generation_config,
                system_instruction=system_message
            )
            response = model.generate_content(user_message)
            return response.text
        except Exception as e:
            print("Gemini translation error:", e)
            return text

    return text

def summarize_text(text, max_words=1000):
    """
    Summarizes the given text using Gemini.
    """
    system_message = (
        "You are an expert summarizer. Summarize the following academic/research/technical text in clear, plain English, "
        "highlighting only the most important insights, facts, and findings. Focus on brevity, clarity, and capturing the main points. "
        f"Limit your summary to about {max_words} words. Do NOT include conclusions, recaps, or personal opinions."
    )

    user_message = "Summarize this text:\n\n" + text
    generation_config = {
        "temperature": 0.3,
        "top_p": 0.85,
        "top_k": 40,
        "max_output_tokens": 2048,
    }

    try:
        # noinspection PyTypeChecker
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config=generation_config,
            system_instruction=system_message
        )
        response = model.generate_content(user_message)
        return response.text
    except Exception as e:
        print("Gemini summary error:", e)
        return "Summary not available."

# ========== AUDIO SCRIPT POST-PROCESSING ==========
def split_script_by_speaker(script):
    """
    Splits script into lines by speaker.
    """
    lines = []

    for line in script.split('\n'):
        line = line.strip()
        if line.startswith("Nishant:") or line.lower().startswith("speaker nishant:"):
            lines.append(("Nishant", line.split(":", 1)[1].strip()))
        elif line.startswith("Megha:") or line.lower().startswith("speaker megha:"):
            lines.append(("Megha", line.split(":", 1)[1].strip()))
        elif line:
            lines.append(("Unknown", line))

    return lines

def print_script_lines(script_lines):
    """
    Prints script lines with clear formatting for debugging.
    """
    print("\n===== Podcast Script for Current Chunk =====\n")
    for i, (speaker, line) in enumerate(script_lines):
        print(f"{i+1:02d}. {speaker}: {line}")
    print("\n============================================\n")

# ========== AUDIO GENERATION ==========
def save_tts(text, speaker, path, lang="en-US"):
    """
    Converts text to speech using Murf AI, saves the audio file at the given path.
    Handles Murf API responses that may be URL, base64-encoded string, or raw bytes.
    """
    voice_id = "en-UK-ruby" if speaker == "Megha" else "en-AU-jimm"
    try:
        response = client.text_to_speech.generate(
            text=text,
            voice_id=voice_id,
            style="Conversational",
            multi_native_locale=lang
        )
        audio_file = response.audio_file

        if audio_file:
            if isinstance(audio_file, str):
                if audio_file.startswith('http'):
                    audio_response = requests.get(audio_file)
                    if audio_response.status_code == 200:
                        with open(path, "wb") as f:
                            f.write(audio_response.content)
                    else:
                        print(f"Failed to download audio from Murf URL: {audio_file}")
                        return
                else:
                    try:
                        audio_data = base64.b64decode(audio_file)
                        with open(path, "wb") as f:
                            f.write(audio_data)
                    except Exception as e:
                        print(f"Base64 decode error: {e}")
                        return
            elif isinstance(audio_file, bytes):
                with open(path, "wb") as f:
                    f.write(audio_file)
            else:
                print(f"Unknown audio_file type from Murf: {type(audio_file)}")
                return
            if os.path.getsize(path) == 0:
                print(f"Error: Audio file {path} is empty.")
        else:
            print(f"No audio data received from Murf for {speaker}.")
    except Exception as e:
        print(f"Error with Murf TTS for {speaker}: {e}")

# --- ALTERNATIVE TTS: gTTS (Uncomment to use on all platforms) ----------
# from gtts import gTTS
# def save_tts(text, speaker, path, lang="en-US"):
#     tts = gTTS(text=text, lang='en', slow=False)
#     tts.save(path)

# --- ALTERNATIVE TTS: Mac 'say' command (Uncomment for macOS) ----------
# import subprocess
# def save_tts(text, speaker, path, lang="en-US"):
#     voice = "Alex" if speaker == "Nishant" else "Samantha"
#     temp_aiff = path.replace('.wav', '.aiff')
#     subprocess.run(["say", "-v", voice, text, "-o", temp_aiff])
#     audio = AudioSegment.from_file(temp_aiff)
#     audio.export(path, format="wav")
#     os.remove(temp_aiff)

# ========== MAIN PIPELINE ==========
def pdf_to_podcast(pdf_file, podcast_mode, lang):
    """
    Main logic: generates podcast MP3 from PDF.
    """
    if pdf_file is None:
        return None

    pdf_path = pdf_file.name
    validate_pdf(pdf_path)

    all_text = extract_text_from_pdf(pdf_path)

    # Decide podcast mode
    if podcast_mode == "Highlights Podcast (Summary Only)":
        chunks = [summarize_text(all_text)]
    else:
        chunks = chunk_text(all_text, max_chars=3500)

    podcast = AudioSegment.silent(duration=500)
    prev_script_tail = ""

    for idx, chunk in enumerate(chunks):
        # Translation based on selected language (default English)
        chunk = translate_text(chunk, lang)
        script = generate_conversational_script(
            chunk,
            chunk_idx=idx,
            total_chunks=len(chunks),
            prev_script_tail=prev_script_tail,
            output_lang=lang
        )
        script_lines = split_script_by_speaker(script)
        print_script_lines(script_lines)

        # Save last few lines for context
        if len(script_lines) >= 4:
            prev_script_tail = "\n".join(f"{speaker}: {line}" for speaker, line in script_lines[-4:])
        else:
            prev_script_tail = "\n".join(f"{speaker}: {line}" for speaker, line in script_lines)

        # Generate and append TTS for each line
        for i, (speaker, text) in enumerate(script_lines):
            tts_path = os.path.join(OUTPUT_FOLDER, f"chunk_{idx}_line_{i}_{speaker}.wav")
            save_tts(text, speaker=speaker, path=tts_path, lang=lang)

            if os.path.exists(tts_path) and os.path.getsize(tts_path) > 0:
                podcast += AudioSegment.from_file(tts_path)
                podcast += AudioSegment.silent(duration=400)
            else:
                print(f"Skipping missing or empty audio file: {tts_path}")

        podcast += AudioSegment.silent(duration=1200)

    # Export the full podcast as MP3
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    final_path = os.path.join(os.getcwd(), f"{base}_podcast.mp3")

    podcast.export(final_path, format="mp3")
    cleanup_temp_audio_files(OUTPUT_FOLDER, ".wav")

    return final_path if os.path.exists(final_path) and os.path.getsize(final_path) > 0 else None

# ========== GRADIO UI ==========
def build_ui():
    with gr.Blocks(theme=gr.themes.Default()) as demo:
        gr.Markdown("## Podify My Paper: The AI Audio Storyteller")
        pdf_file = gr.File(label="Upload PDF", file_types=[".pdf"])
        with gr.Row():
            podcast_mode = gr.Radio(
                ["Full Podcast (All Details)", "Highlights Podcast (Summary Only)"],
                value="Full Podcast (All Details)",
                label="Podcast Style",
                interactive=True,
                show_label=True,
                elem_id="podcast_style"
            )

            language = gr.Dropdown(
                label="Select Language",
                choices=[(v, k) for k, v in LANGUAGES.items()],
                value="en-US",
                interactive=True,
                show_label=True,
                elem_id="select_language"
            )

        with gr.Row():
            submit_btn = gr.Button("Generate Podcast", variant="primary")
            clear_btn = gr.Button("Reset")

        audio_output = gr.Audio(label="Generated Podcast", interactive=False, type="filepath")

        clear_btn.click(
            lambda: (None, "Full Podcast (All Details)", "en-US", None),
            outputs=[pdf_file, podcast_mode, language, audio_output]
        )

        submit_btn.click(
            pdf_to_podcast,
            inputs=[pdf_file, podcast_mode, language],
            outputs=audio_output
        )

    return demo

# ========== MAIN ==========
if __name__ == "__main__":
    demo = build_ui()
    demo.launch(share=True)