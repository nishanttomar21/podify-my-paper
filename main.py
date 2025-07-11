import os
import pdfplumber
import gradio as gr
import google.generativeai as genai
from gtts import gTTS
from pydub import AudioSegment
import subprocess

# --- CONFIGURATION ---
GEMINI_API_KEY = "Enter-your-api-key"
OUTPUT_FOLDER = os.path.join(os.getcwd(), "podcast_chunks")
GEMINI_MODEL = "gemini-1.5-flash"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

genai.configure(api_key=GEMINI_API_KEY)

# --- TEXT EXTRACTION & CHUNKING ---
def extract_text_from_pdf(pdf_path):
    """Extracts all text from a PDF file."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def chunk_text(text, max_chars=3500):
    """Splits text into chunks, each no more than max_chars characters."""
    chunks = []
    while len(text) > max_chars:
        split_at = text[:max_chars].rfind('. ')
        if split_at == -1:
            split_at = max_chars
        chunks.append(text[:split_at+1].strip())
        text = text[split_at+1:]
    if text.strip():
        chunks.append(text.strip())
    return chunks

def print_script_lines(script_lines):
    """Nicely prints the list of (speaker, line) podcast dialogue with numbering and clear formatting."""
    print("\n===== Podcast Script for Current Chunk =====\n")
    for i, (speaker, line) in enumerate(script_lines):
        print(f"{i+1:02d}. {speaker}: {line}")
    print("\n============================================\n")

# --- GEMINI SCRIPT GENERATION ---
def generate_conversational_script_gemini(text_chunk, chunk_idx=0, total_chunks=1, prev_script_tail=""):
    """Generates a podcast script for the given text chunk using Gemini."""
    if chunk_idx == 0:
        context = ""
        intro = "Begin with a friendly podcast introduction by Nishant."
    else:
        context = (
            f"Continue the conversation *seamlessly* from the previous lines below.\n"
            f"Do NOT repeat any introduction, greeting, or recap. "
            f"Do NOT mention the podcast title, host, or guest names at the start.\n"
            f"Previous lines:\n{prev_script_tail}\n"
        )
        intro = ""
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
    user_message = (
        "Please create a podcast script based on the input text below.\n"
        "Guidelines:\n"
        "- Use a conversational, accessible tone.\n"
        "- Format the script strictly as a back-and-forth between 'Nishant:' and 'Megha:' for every line.\n"
        "- Include natural speech markers (e.g., 'hmm', 'you know', 'well…') to make it sound authentic.\n"
        "- Keep the conversation concise and focused, summarizing the key points from the input.\n"
        "- Limit the response to the essentials; avoid unnecessary elaboration.\n"
        "- Do not include any music, sound effects, or bracketed placeholders.\n"
        "- Do NOT introduce the speakers or podcast unless explicitly instructed in the system message.\n"
        "- Do NOT add any conclusions, recaps, or sign-off messages unless explicitly instructed in the system message.\n"
        "\n"
        "Input Text:\n"
        f"{text_chunk}\n\n"
        "Podcast Script:"
    )
    # For conversation generation (more creative, varied dialogue)
    generation_config = {
        "temperature": 0.8,  # Higher temperature = more creative, varied outputs
        "top_p": 0.9,  # Consider tokens within top 90% cumulative probability
        "top_k": 40,  # Consider only the top 40 most likely next tokens
        "max_output_tokens": 2000,  # Limit podcast script output to ~2000 tokens
    }
    try:
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
            f"Nishant: Sorry, there was an error generating this section.\n"
            f"Megha: Let's move on to the next part!"
        )

def summarize_with_gemini(text, max_words=1000):
    """Summarizes the given text using Gemini."""
    system_message = (
        "You are an expert summarizer. Summarize the following academic/research/technical text in clear, plain English, "
        "highlighting only the most important insights, facts, and findings. Focus on brevity, clarity, and capturing the main points. "
        f"Limit your summary to about {max_words} words. Do NOT include conclusions, recaps, or personal opinions."
    )
    user_message = "Summarize this text:\n\n" + text
    # For summarization (more factual, less creative)
    generation_config = {
        "temperature": 0.3,         # Low temperature = more deterministic, less creative
        "top_p": 0.85,              # Consider tokens within top 85% cumulative probability
        "top_k": 40,                # Consider only the top 40 most likely next tokens
        "max_output_tokens": 2048,  # Limit summary output to ~2048 tokens
    }
    try:
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

# --- SCRIPT POSTPROCESSING ---
def split_script_by_speaker(script):
    """Splits the Gemini script into lines by speaker."""
    lines = []
    for line in script.split('\n'):
        line = line.strip()
        if line.startswith("Nishant:") or line.lower().startswith("speaker nishant:"):
            lines.append(("Nishant", line.split(":", 1)[1].strip()))
        elif line.startswith("Megha:") or line.lower().startswith("speaker megha:"):
            lines.append(("Megha", line.split(":", 1)[1].strip()))
        elif line:
            lines.append(("A", line))
    return lines


# --- AUDIO GENERATION ---

# --------------------- Mac ONLY (best for two realistic voices) ----------------------
def save_tts(text, speaker, path):
    """Converts text to speech using Mac's built-in 'say' command with different voices for each speaker (macOS only)."""
    voice = "Alex" if speaker == "Nishant" else "Samantha"
    temp_aiff = path.replace('.wav', '.aiff')
    subprocess.run(["say", "-v", voice, text, "-o", temp_aiff])
    audio = AudioSegment.from_file(temp_aiff)
    audio.export(path, format="wav")
    os.remove(temp_aiff)

# --------------------- Cross-platform (works on Windows, Mac, Linux) ----------------------
# def save_tts(text, speaker, path):
#     """Converts text to speech using gTTS for cross-platform compatibility (works on Windows, Linux, and macOS)."""
#     tts = gTTS(text=text, lang='en', slow=False)
#     tts.save(path)

# --- MAIN LOGIC ---
def pdf_to_podcast(pdf_file, podcast_mode):
    if pdf_file is None:
        return None
    pdf_path = pdf_file.name

    if podcast_mode == "Highlights Podcast (Summary Only)":
        all_text = extract_text_from_pdf(pdf_path)
        summary = summarize_with_gemini(all_text)
        chunks = [summary]
    else:
        all_text = extract_text_from_pdf(pdf_path)
        chunks = chunk_text(all_text, max_chars=3500)
        if not chunks:
            raise ValueError("No extractable text found in PDF.")

    podcast = AudioSegment.silent(duration=500)
    prev_script_tail = ""

    for idx, chunk in enumerate(chunks):
        script = generate_conversational_script_gemini(
            chunk, chunk_idx=idx, total_chunks=len(chunks), prev_script_tail=prev_script_tail
        )
        script_lines = split_script_by_speaker(script)
        print_script_lines(script_lines)

        # Save last 4 lines for continuity (handles short and long chunks)
        if len(script_lines) >= 4:
            prev_script_tail = "\n".join(
                f"{speaker}: {line}" for speaker, line in script_lines[-4:]
            )
        else:
            prev_script_tail = "\n".join(
                f"{speaker}: {line}" for speaker, line in script_lines
            )
        for i, (speaker, text) in enumerate(script_lines):
            tts_path = os.path.join(OUTPUT_FOLDER, f"chunk_{idx}_line_{i}_{speaker}.wav")
            save_tts(text, speaker=speaker, path=tts_path)
            podcast += AudioSegment.from_file(tts_path)
            podcast += AudioSegment.silent(duration=400)
        podcast += AudioSegment.silent(duration=1200)

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    final_path = os.path.join(os.getcwd(), f"{base}_podcast.mp3")
    podcast.export(final_path, format="mp3")
    return final_path

# --- GRADIO UI DEFINITION ---
def build_ui():
    with gr.Blocks(theme=gr.themes.Default()) as demo:
        gr.Markdown("## Podify My Paper: The AI Audio Storyteller")
        pdf_file = gr.File(label="Upload PDF", file_types=[".pdf"])
        podcast_mode = gr.Radio(
            ["Full Podcast (All Details)", "Highlights Podcast (Summary Only)"],
            value="Full Podcast (All Details)",
            label="Podcast Style"
        )
        with gr.Row():
            submit_btn = gr.Button("Generate Podcast", variant="primary")
            clear_btn = gr.Button("Reset")
        audio_output = gr.Audio(label="Generated Podcast", interactive=False, type="filepath")

        clear_btn.click(lambda: (None, None, None), outputs=[pdf_file, audio_output])
        submit_btn.click(
            pdf_to_podcast,
            inputs=[pdf_file, podcast_mode],
            outputs=audio_output
        )
    return demo

if __name__ == "__main__":
    demo = build_ui()
    demo.launch(share=True)