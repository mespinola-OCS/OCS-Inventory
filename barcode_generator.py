import base64
import datetime
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont
import qrcode
import streamlit as st
import tempfile
import os


def generate_qr_code(data):
    # High DPI for better quality
    dpi = 300  # Increase the DPI for higher resolution
    
    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white').convert('RGB')

    # Resize QR code to 0.7" x 0.7" at high DPI (e.g., 300 DPI)
    img = img.resize((int(0.7 * dpi), int(0.7 * dpi)), Image.LANCZOS)

    # Create a new image with white background to accommodate the QR code and text
    img_with_number = Image.new('RGB', (int(2.625 * dpi), int(1 * dpi)), 'white')
    img_with_number.paste(img, (int((2.625 * dpi - img.width) / 2), 0))

    # Draw text below the QR code
    draw = ImageDraw.Draw(img_with_number)
    font = ImageFont.truetype("arial.ttf", int(14 * dpi / 72))  # Scale font size based on DPI
    text = data

    # Use textbbox (new method) instead of textsize (deprecated) to get the bounding box of the text
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    # Draw the text in the center below the QR code
    draw.text(
        ((img_with_number.width - text_width) / 2, img.height + 2),
        text,
        fill='black',
        font=font
    )

    return img_with_number


def create_pdf(items):
    # Constants for layout
    page_width = 8.5 * 72  # 72 points per inch
    page_height = 11 * 72
    label_width = 2.625 * 72
    label_height = 1 * 72
    margin_x = (page_width - 3 * label_width) / 4
    margin_y = (page_height - 10 * label_height) / 11

    pdf = FPDF('P', 'pt', (page_width, page_height))
    pdf.add_page()
    
    current_x = margin_x
    current_y = margin_y

    for quantity, qr_string in items:
        
        for _ in range(quantity):
            # Generate QR code with string
            img = generate_qr_code(qr_string)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                img.save(tmpfile.name, format="png", dpi=(300, 300))
                # Add QR code image to PDF
                pdf.image(tmpfile.name, x=current_x, y=current_y, w=label_width, h=label_height)
            os.remove(tmpfile.name)
            
            # Move to the next label position
            current_x += label_width + margin_x
            if current_x + label_width / 2 > page_width:
                current_x = margin_x
                current_y += label_height + margin_y
                if current_y + label_height / 2 > page_height:
                    pdf.add_page()
                    current_y = margin_y
    return pdf


# Main code to generate and download the PDF
def download_qr_code_pdf(items):
    # Generate the QR code PDF
    def create_download_link(val, filename):
        b64 = base64.b64encode(val)  # val looks like b'...'
        return f'<a href="data:application/octet-stream;base64,{b64.decode()}" download="{filename}.pdf">Download file</a>'
    name = datetime.datetime.now()
    name = name.strftime('%Y-%m-%d %H:%M')
    name = f"Exported_Barcodes_{name}.pdf"
    pdf = create_pdf(items)

    html = create_download_link(pdf.output(dest="S").encode("latin-1"), name)
    st.markdown(html, unsafe_allow_html=True)