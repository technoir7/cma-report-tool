
try:
    from weasyprint import HTML
    print("WeasyPrint imported successfully.")
    pdf = HTML(string="<h1>Test</h1>").write_pdf()
    print(f"Generated PDF of size {len(pdf)}")
except Exception as e:
    print(f"WeasyPrint failed: {e}")
