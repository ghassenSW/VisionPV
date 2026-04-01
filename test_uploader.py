import os, time
from dotenv import load_dotenv
from mistralai import Mistral

load_dotenv("C:\\Users\\ghass\\OneDrive\\Desktop\\PFE\\VisionPV\\.env")
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

with open('example.pdf', 'wb') as f:
    f.write(b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n188\n%%EOF\n')
with open('example.pdf', 'rb') as f:
    fc = f.read()

up = client.files.upload(file={'file_name': 'example.pdf', 'content': fc}, purpose='ocr')
print('Status after upload:', getattr(up, 'status', 'no-attr'), 'type:', type(up))
for _ in range(2):
    try:
        info = client.files.retrieve(file_id=up.id)
        print('Info dict:', info)
        print('Dir info:', dir(info))
        from pprint import pprint
        pprint(info)
    except Exception as e:
        print("Err", e)
    time.sleep(2)
