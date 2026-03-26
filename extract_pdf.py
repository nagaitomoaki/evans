import pdfplumber
import os
import sys

EVANS_DIR = r"C:\Users\nttom\OneDrive\ドキュメント\evans"

def extract_pdf(pdf_path, output_path):
    print(f"Processing: {os.path.basename(pdf_path)}")
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"  Total pages: {total_pages}")
        for i, page in enumerate(pdf.pages):
            if i % 10 == 0:
                print(f"  Page {i+1}/{total_pages}...")
            text = page.extract_text()
            if text:
                text_parts.append(text)

    full_text = "\n".join(text_parts)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"  Saved to: {output_path} ({len(full_text)} chars)")

def main():
    for year in [2022, 2023, 2024, 2025, 2026]:
        # Find PDF for this year
        pdf_name = None
        for f in os.listdir(EVANS_DIR):
            if f.endswith(f"_{year}.pdf"):
                pdf_name = f
                break

        if not pdf_name:
            print(f"No PDF found for {year}")
            continue

        pdf_path = os.path.join(EVANS_DIR, pdf_name)
        output_path = os.path.join(EVANS_DIR, f"evans_{year}.txt")

        if os.path.exists(output_path):
            print(f"evans_{year}.txt already exists, skipping...")
            continue

        try:
            extract_pdf(pdf_path, output_path)
        except Exception as e:
            print(f"Error processing {year}: {e}")

if __name__ == "__main__":
    main()
