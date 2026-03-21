# VisionPV

A robust AI-powered tool for extracting accident data from scanned Tunisian PV (Procès-Verbal) documents. This solution utilizes Mistral and Gemini models for Vision & Text processing, mapping complex OCR and tabular data into standardized JSON formats.

## Setup

1. **Clone this project/repository.**

2. **Set up your environment:**
   Provide your API keys in an `.env` file at the root of the `VisionPV` folder.
   
   Create a `.env` file containing:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   MISTRAL_API_KEY=your_mistral_api_key_here
   ```

3. **Install Dependencies:**
   Install required Python packages and tools (e.g. `Pillow`, `pdf2image`, `mistralai`, `google-genai`, `python-dotenv`, `opencv-python`). Make sure system-level libraries like `poppler` (for pdf2image) and `tesseract` (for OCR if utilized) are installed locally.
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Configure your variables (such as input/output folders) within `main.py`, `LLM_mistral.py`, or `OCR_mistral.py` depending on the script entrypoint you intend to execute.

Run the main process:
```bash
python main.py
```