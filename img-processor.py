import streamlit as st
from PIL import Image
import io
import zipfile
import py7zr
import os

# --- Logic Functions ---

def resize_and_compress_to_buffer(img, target_size_kb, image_format):
    target_bytes = target_size_kb * 1024
    quality = 95
    fmt = image_format.upper()
    if fmt == 'JPG': fmt = 'JPEG'
    
    if fmt == 'JPEG' and img.mode == 'RGBA':
        img = img.convert('RGB')

    while True:
        output_buffer = io.BytesIO()
        img.save(output_buffer, format=fmt, quality=quality)
        if output_buffer.tell() <= target_bytes or quality <= 10:
            output_buffer.seek(0)
            return output_buffer
        quality -= 5

def apply_logo(base_img, logo_bytes, opacity):
    if not logo_bytes: return base_img
    try:
        logo_img = Image.open(logo_bytes).convert("RGBA")
        base_area = base_img.size[0] * base_img.size[1]
        target_area = base_area * 0.6
        logo_aspect = logo_img.size[0] / logo_img.size[1]
        logo_width = int((target_area * logo_aspect) ** 0.5)
        logo_height = int(logo_width / logo_aspect)
        logo_img = logo_img.resize((logo_width, logo_height), Image.LANCZOS)
        
        opacity_val = min(max(float(opacity) / 100, 0), 1)
        alpha = logo_img.split()[3].point(lambda x: x * opacity_val)
        logo_img.putalpha(alpha)
        
        x = (base_img.size[0] - logo_width) // 2
        y = (base_img.size[1] - logo_height) // 2
        base_img.paste(logo_img, (x, y), logo_img)
        return base_img
    except Exception:
        return base_img

def process_single_image(file_bytes, width, height, logo_bytes, opacity, target_size_kb, image_format):
    img = Image.open(file_bytes)
    img = img.convert("RGBA")
    img = img.resize((width, height), Image.LANCZOS)
    
    if logo_bytes:
        logo_bytes.seek(0)
        img = apply_logo(img, logo_bytes, opacity)
    
    final_fmt = image_format.lower()
    processed_buffer = resize_and_compress_to_buffer(img, target_size_kb, final_fmt)
    return processed_buffer, final_fmt

# --- Universal Extractor Helper (No RAR) ---
def extract_files_from_archive(uploaded_archive):
    """
    Generator that yields (filename, file_bytes) from Zip or 7z.
    """
    filename = uploaded_archive.name.lower()
    uploaded_archive.seek(0)
    
    # 1. Handle ZIP
    if filename.endswith(".zip"):
        with zipfile.ZipFile(uploaded_archive, 'r') as z:
            for name in z.namelist():
                if name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    with z.open(name) as f:
                        yield name, io.BytesIO(f.read())

    # 2. Handle 7Z
    elif filename.endswith(".7z"):
        with py7zr.SevenZipFile(uploaded_archive, 'r') as z:
            all_files = z.readall()
            if all_files:
                for name, data in all_files.items():
                    if name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        yield name, data

# --- UI Setup ---
st.set_page_config(page_title="Image Processor - Baka Digital", page_icon="🎨")
st.title("🎨 Image Processor Tool")
st.caption("Developed by Baka Digital")

with st.sidebar:
    st.header("⚙️ Configuration")
    mode = st.radio("Processing Mode", ["Single File", "Batch (Zip/7z)"])
    st.markdown("---")
    width = st.number_input("Width (pixels)", min_value=1, value=800)
    height = st.number_input("Height (pixels)", min_value=1, value=600)
    image_format = st.selectbox("Output Format", ["webp", "png", "jpg"])
    target_size_kb = st.number_input("Max File Size (KB)", min_value=10, value=100)
    st.markdown("---")
    st.subheader("Logo Overlay")
    logo_file = st.file_uploader("Upload Logo (Optional)", type=['png', 'jpg', 'webp'])
    opacity = st.slider("Logo Opacity %", 0, 100, 50)
    logo_bytes = io.BytesIO(logo_file.getvalue()) if logo_file else None

# --- Main Execution ---

if mode == "Single File":
    st.subheader("Single File Mode")
    uploaded_file = st.file_uploader("Upload Image", type=['png', 'jpg', 'jpeg', 'webp'])
    
    if st.button("Process Image", type="primary"):
        if uploaded_file:
            try:
                processed_buffer, final_fmt = process_single_image(
                    uploaded_file, width, height, logo_bytes, opacity, target_size_kb, image_format
                )
                new_filename = f"processed_{uploaded_file.name.rsplit('.', 1)[0]}.{final_fmt}"
                mime_type = f"image/{final_fmt}" if final_fmt != 'jpg' else "image/jpeg"
                
                st.success("Processing Complete!")
                st.download_button("Download Processed Image", processed_buffer.getvalue(), new_filename, mime_type)
                st.image(processed_buffer, caption="Result", width=300)
            except Exception as e:
                st.error(f"Error: {e}")

else: # Batch Mode
    st.subheader("Batch Archive Mode")
    st.info("Supported formats: **.ZIP, .7Z**")
    
    uploaded_archive = st.file_uploader("Upload Archive", type=["zip", "7z"])
    
    if st.button("Process Batch", type="primary"):
        if uploaded_archive:
            output_zip_buffer = io.BytesIO()
            status_text = st.empty()
            progress_bar = st.progress(0)
            
            try:
                # We always output a ZIP file for compatibility
                with zipfile.ZipFile(output_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as z_out:
                    
                    files_generator = extract_files_from_archive(uploaded_archive)
                    files_to_process = list(files_generator)
                    total_files = len(files_to_process)
                    
                    if total_files == 0:
                        st.warning("No images found in the archive.")
                    else:
                        for i, (filename, file_bytes) in enumerate(files_to_process):
                            status_text.text(f"Processing: {filename}")
                            
                            try:
                                processed_buffer, final_fmt = process_single_image(
                                    file_bytes, width, height, logo_bytes, opacity, target_size_kb, image_format
                                )
                                
                                original_path, original_name = os.path.split(filename)
                                name_no_ext = original_name.rsplit('.', 1)[0]
                                new_filename = f"{name_no_ext}.{final_fmt}"
                                full_new_path = os.path.join(original_path, new_filename)
                                
                                z_out.writestr(full_new_path, processed_buffer.getvalue())
                                
                            except Exception as e:
                                print(f"Skipped {filename}: {e}")
                            
                            progress_bar.progress((i + 1) / total_files)
                
                status_text.text("Processing complete!")
                progress_bar.progress(100)
                st.success("Batch processing complete.")
                
                st.download_button(
                    label="Download Processed ZIP",
                    data=output_zip_buffer.getvalue(),
                    file_name="processed_batch.zip",
                    mime="application/zip"
                )
                
            except Exception as e:
                st.error(f"Error reading archive: {e}")
        else:
            st.warning("Please upload an archive file.")
