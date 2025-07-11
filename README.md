# Podify My Paper: The AI Audio Storyteller

---
## Overview

---

Turn your research paper, academic PDF, or technical document into an engaging AI-generated podcast—fully voiced and ready to share!

## App Screenshot

---

Here's what the app looks like:

![App UI Screenshot](screenshot.png)

## 🚀 Features

---

- **Podcast from PDF:** Upload any research paper or technical PDF and generate a podcast script in a realistic dialogue format.
- **Two Speaker Roles:** Realistic back-and-forth between "Nishant" (host) and "Megha" (expert guest).
- **Detailed or Highlight Mode:** Choose between a full deep-dive or a concise highlights-only summary podcast.
- **AI Summarization & Scripting:** Uses Google Gemini (Generative AI) for natural, context-aware podcast scripts.
- **Text-to-Speech:** Audio generated with realistic voices (best with Mac; cross-platform option included).
- **Easy Web UI:** Built with Gradio for one-click use—no code required for users.

## 🖥️ Requirements

---

- Python 3.8 or higher
- [Google Generative AI API Key](https://ai.google.dev/)
- macOS (for most realistic voices via `say` command) OR Windows/Linux (using gTTS, see below)
- See [requirements.txt](requirements.txt) for Python packages.

## ⚙️ Installation

---

```bash
git clone https://github.com/nishanttomar21/podify-my-paper.git
cd podify-my-paper
pip install -r requirements.txt
