import io
import streamlit as st
import time
from PIL import Image
from imgconvrtr import convert_img_format
from videoconvrtr import (
    convert_video_to_webm,
    is_ffmpeg_available,
    get_ffmpeg_diagnostics,
)

# Maximum file size limit: 200MB
MAX_FILE_SIZE_MB = 200
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # 200MB in bytes

# App Title
st.title("Codec & Dagger")
st.markdown("**Powered by libwebp API, AVIF, and advanced optimizers**")

# Check library and tool availability
from imgconvrtr import (is_libwebp_available, get_libwebp_diagnostics,
                        is_libavif_available, get_libavif_diagnostics,
                        get_compression_tools)

libwebp_available = is_libwebp_available()
libavif_available = is_libavif_available()
compression_tools = get_compression_tools()

libwebp_status = "✅ Available" if libwebp_available else "⚠️ Not found (using Pillow fallback)"
libavif_status = "✅ Available" if libavif_available else "⚠️ Not found"

st.caption(f"libwebp status: {libwebp_status} | libavif status: {libavif_status}")

# Show compression tools status
tools_status = []
if compression_tools.get('mozjpeg'):
    tools_status.append("MozJPEG ✅")
if compression_tools.get('oxipng'):
    tools_status.append("OxiPNG ✅")
if compression_tools.get('optipng'):
    tools_status.append("OptiPNG ✅")

if tools_status:
    st.caption(f"Compression tools: {', '.join(tools_status)}")

ffmpeg_available = is_ffmpeg_available()
ffmpeg_status = "✅ Available (managed helper)" if ffmpeg_available else "⚠️ Not available"
st.caption(f"ffmpeg status: {ffmpeg_status}")

# Show diagnostics if libraries are not available
if not libwebp_available or not libavif_available:
    with st.expander("🔍 Library Diagnostic Information"):
        if not libwebp_available:
            st.write("**Why libwebp is not found:**")
            diagnostics = get_libwebp_diagnostics()
            if diagnostics:
                for msg in diagnostics:
                    st.text(msg)
            else:
                st.text("No diagnostic information available.")
        
        if not libavif_available:
            st.write("**Why libavif is not found:**")
            diagnostics = get_libavif_diagnostics()
            if diagnostics:
                for msg in diagnostics:
                    st.text(msg)
            else:
                st.text("No diagnostic information available.")
        
        st.markdown("---")
        st.write("**How to fix:**")
        
        st.markdown("""
        **Option 1: Automatic Setup (Easiest)**
        
        Run one of these scripts in your project folder:
        - **PowerShell:** `.\setup_libwebp.ps1`
        - **Command Prompt:** `setup_libwebp.bat`
        
        These scripts will automatically download and set up libwebp.dll for you!
        """)
        
        st.markdown("""
        **Option 2: Manual Setup**
        
        1. **Download libwebp for Windows:**
           - Visit: https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.2.1-windows-x64.zip
           - Extract the ZIP file
           - Copy `libwebp.dll` from the `bin` folder to the same folder as `app.py`
        
        2. **Install AVIF support:**
           - Run: `pip install pillow-avif-plugin`
        
        3. **Restart the Streamlit app** after copying the DLL file
        """)
        
        st.markdown("""
        **Option 3: Use Pillow's built-in WebP support**
        
        - The app will automatically use Pillow's WebP support as a fallback
        - Pillow includes libwebp internally, so WebP conversion will still work
        - You just won't get the direct libwebp API integration
        """)
        
        st.info("💡 **Tip:** Use Option 1 (automatic setup) for the easiest installation!")

def _format_size(num_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024.0 or unit == "GB":
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} GB"


image_tab, video_tab = st.tabs(["Image Converter", "Video Converter"])

with image_tab:
    uploaded_file = st.file_uploader(
        "Upload an Image",
        type=["png", "jpg", "jpeg", "jfif", "bmp", "webp", "avif", "svg"],
        help=f"Maximum file size: {MAX_FILE_SIZE_MB}MB",
    )

    if uploaded_file is not None:
        file_size = uploaded_file.size
        if file_size > MAX_FILE_SIZE_BYTES:
            st.error(
                f"❌ File size exceeds the maximum limit of {MAX_FILE_SIZE_MB}MB. "
                f"Your file is {_format_size(file_size)}. "
                f"Please upload a smaller file."
            )
            st.stop()
        original_bytes = uploaded_file.getvalue()
        original_size = len(original_bytes) if original_bytes else 0

        file_extension = uploaded_file.name.lower().split('.')[-1] if uploaded_file.name else ''
        is_svg = file_extension == 'svg'
        original_img_for_comparison = None

        if is_svg:
            from imgconvrtr import rasterize_svg
            try:
                img = rasterize_svg(original_bytes)
                original_img_for_comparison = img
                st.image(img, caption="Uploaded SVG Image (rasterized for preview)", width="stretch")
                st.write("**Original format:** SVG")
                st.write(f"**Image dimensions:** {img.size[0]} x {img.size[1]} pixels")
                st.info("ℹ️ SVG files will be rasterized before conversion to the selected format.")
            except Exception as e:
                st.error(f"❌ Could not load SVG: {str(e)}")
                st.stop()
        else:
            img = Image.open(uploaded_file)
            original_img_for_comparison = img.copy()
            st.image(img, caption="Uploaded Image", width="stretch")
            st.write(f"**Original format:** {img.format}")
            st.write(f"**Image dimensions:** {img.size[0]} x {img.size[1]} pixels")

        output_format = st.selectbox("Choose the output format", ["AVIF", "WebP", "PNG", "JPEG", "JFIF", "BMP"])

        profile_presets = {
            "Balanced": {
                "quality": {"jpeg": 88, "jfif": 88, "webp": 82, "avif": 75},
                "jpeg_progressive": True,
                "jpeg_subsampling": "4:2:0",
                "webp_method": 4,
                "webp_alpha_quality": 90,
                "webp_exact": False,
                "avif_speed": 6,
                "avif_subsampling": "4:2:0",
                "lossless_webp": False,
                "lossless_avif": False,
            },
            "High quality": {
                "quality": {"jpeg": 92, "jfif": 92, "webp": 90, "avif": 80},
                "jpeg_progressive": True,
                "jpeg_subsampling": "4:4:4",
                "webp_method": 6,
                "webp_alpha_quality": 100,
                "webp_exact": True,
                "avif_speed": 4,
                "avif_subsampling": "4:4:4",
                "lossless_webp": False,
                "lossless_avif": False,
            },
            "Lossless intent": {
                "quality": {"jpeg": 90, "jfif": 90, "webp": 100, "avif": 100},
                "jpeg_progressive": True,
                "jpeg_subsampling": "4:4:4",
                "webp_method": 6,
                "webp_alpha_quality": 100,
                "webp_exact": True,
                "avif_speed": 4,
                "avif_subsampling": "4:4:4",
                "lossless_webp": True,
                "lossless_avif": True,
            },
        }

        st.markdown("### Encoding profile")
        profile_name = st.selectbox("Choose launch profile", ["Balanced", "High quality", "Lossless intent"], index=0)
        selected_profile = profile_presets[profile_name]
        format_key = output_format.lower()
        default_quality = selected_profile["quality"].get(format_key, 88)

        col1, col2, col3 = st.columns(3)
        with col1:
            quality_help = "Higher values mean better quality but larger file size."
            if format_key == "png":
                quality_help = "PNG is lossless; quality has no visual effect and is kept for consistency."
            elif format_key == "bmp":
                quality_help = "BMP does not use quality settings."
            quality = st.slider(
                "Quality (for lossy formats)",
                min_value=0,
                max_value=100,
                value=default_quality,
                help=quality_help,
                disabled=format_key in ["png", "bmp"],
            )
        with col2:
            lossless = False
            if format_key in ["webp", "avif"]:
                default_lossless = selected_profile["lossless_webp"] if format_key == "webp" else selected_profile["lossless_avif"]
                lossless = st.checkbox("Lossless encoding", value=default_lossless, help=f"Lossless {output_format} encoding")
        with col3:
            optimize = False
            if format_key in ["png", "jpeg", "jpg", "jfif"]:
                optimize = st.checkbox("Advanced optimization", value=False, help="Use MozJPEG/OxiPNG/OptiPNG when available")

        with st.expander("Advanced quality and metadata controls"):
            preserve_icc = st.checkbox("Preserve ICC color profile", value=True)
            preserve_exif = st.checkbox("Preserve EXIF metadata", value=False)
            preserve_xmp = st.checkbox("Preserve XMP metadata", value=False)
            advanced_options = {}
            jpeg_background = (255, 255, 255)

            if format_key in ["jpeg", "jpg", "jfif"]:
                jpeg_progressive = st.checkbox("Progressive JPEG", value=selected_profile["jpeg_progressive"])
                jpeg_subsampling = st.selectbox(
                    "JPEG subsampling",
                    ["4:4:4", "4:2:2", "4:2:0"],
                    index=["4:4:4", "4:2:2", "4:2:0"].index(selected_profile["jpeg_subsampling"]),
                )
                matte_hex = st.color_picker("Transparency background color", value="#FFFFFF").lstrip("#")
                jpeg_background = tuple(int(matte_hex[i:i+2], 16) for i in (0, 2, 4))
                advanced_options.update({"jpeg_progressive": jpeg_progressive, "jpeg_subsampling": jpeg_subsampling})

            if format_key == "webp":
                advanced_options["webp_method"] = st.slider("WebP method", min_value=0, max_value=6, value=selected_profile["webp_method"])
                advanced_options["webp_alpha_quality"] = st.slider("WebP alpha quality", min_value=0, max_value=100, value=selected_profile["webp_alpha_quality"])
                advanced_options["webp_exact"] = st.checkbox("WebP exact", value=selected_profile["webp_exact"])

            if format_key == "avif":
                advanced_options["avif_speed"] = st.slider("AVIF speed", min_value=0, max_value=10, value=selected_profile["avif_speed"])
                advanced_options["avif_subsampling"] = st.selectbox(
                    "AVIF subsampling",
                    ["4:4:4", "4:2:2", "4:2:0"],
                    index=["4:4:4", "4:2:2", "4:2:0"].index(selected_profile["avif_subsampling"]),
                )

            if format_key == "png":
                advanced_options["png_strip_metadata"] = st.selectbox("PNG optimizer metadata stripping", ["none", "safe", "all"], index=1)

        if st.button("Convert 📸", key="convert_image_btn"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            try:
                status_text.text("📖 Reading image file...")
                progress_bar.progress(10)
                status_text.text(f"🔄 Converting to {output_format.upper()} format...")
                progress_bar.progress(30)
                converted_img = convert_img_format(
                    original_bytes,
                    output_format.lower(),
                    quality=quality,
                    lossless=lossless,
                    optimize=optimize,
                    preserve_icc=preserve_icc,
                    preserve_exif=preserve_exif,
                    preserve_xmp=preserve_xmp,
                    advanced_options=advanced_options,
                    jpeg_background=jpeg_background,
                )
                status_text.text("📊 Processing converted image...")
                progress_bar.progress(75)
                converted_bytes = converted_img.getvalue()
                converted_size = len(converted_bytes)
                size_diff = converted_size - original_size
                percent_change = (size_diff / original_size) * 100 if original_size > 0 else 0.0
                mime_types = {
                    "webp": "image/webp",
                    "png": "image/png",
                    "jpeg": "image/jpeg",
                    "jpg": "image/jpeg",
                    "jfif": "image/jpeg",
                    "bmp": "image/bmp",
                    "avif": "image/avif",
                }
                mime_type = mime_types.get(output_format.lower(), "image/webp")
                progress_bar.progress(100)
                status_text.text("✅ Conversion complete!")
                time.sleep(0.3)
                progress_bar.empty()
                status_text.empty()
                st.success("✅ Conversion successful!")

                st.markdown("### 📊 Before/After Comparison")
                col_before, col_after = st.columns(2)
                if original_img_for_comparison is not None:
                    original_img = original_img_for_comparison
                else:
                    from imgconvrtr import rasterize_svg
                    original_img = rasterize_svg(original_bytes) if is_svg else Image.open(io.BytesIO(original_bytes))
                converted_img_display = Image.open(io.BytesIO(converted_bytes))

                with col_before:
                    st.markdown("**📷 Original Image**")
                    st.image(original_img, use_container_width=True)
                    st.caption(f"**Format:** {'SVG' if is_svg else (original_img.format or 'Unknown')}")
                    st.caption(f"**Size:** {_format_size(float(original_size))}")
                    st.caption(f"**Dimensions:** {original_img.size[0]} × {original_img.size[1]} px")
                with col_after:
                    st.markdown("**✨ Converted Image**")
                    st.image(converted_img_display, use_container_width=True)
                    st.caption(f"**Format:** {output_format.upper()}")
                    st.caption(f"**Size:** {_format_size(float(converted_size))}")
                    st.caption(f"**Dimensions:** {converted_img_display.size[0]} × {converted_img_display.size[1]} px")

                st.markdown("---")
                st.markdown("### 📈 Size Comparison")
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                with col_stat1:
                    st.metric(label="Original Size", value=_format_size(float(original_size)))
                with col_stat2:
                    st.metric(label="Converted Size", value=_format_size(float(converted_size)), delta=f"{percent_change:+.2f}%")
                with col_stat3:
                    if size_diff < 0:
                        st.metric(label="Space Saved", value=_format_size(float(abs(size_diff))))
                    else:
                        st.metric(label="Size Change", value=_format_size(float(size_diff)))

                st.download_button(
                    label=f"📥 Download as {output_format}",
                    data=converted_bytes,
                    file_name=f"image.{output_format.lower()}",
                    mime=mime_type,
                    use_container_width=True,
                )
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"❌ Conversion failed: {str(e)}")
                st.exception(e)

with video_tab:
    st.markdown("### Video to WebM")
    st.caption("Convert common video formats to WebM (VP9 + Opus).")
    if not ffmpeg_available:
        st.warning("Managed ffmpeg is unavailable. Install dependencies and restart the app.")
        diagnostics = get_ffmpeg_diagnostics()
        if diagnostics:
            for msg in diagnostics:
                st.text(msg)

    uploaded_video = st.file_uploader(
        "Upload a Video",
        type=["mp4", "mov", "mkv", "avi", "webm", "m4v"],
        help=f"Maximum file size: {MAX_FILE_SIZE_MB}MB",
        key="video_uploader",
    )
    if uploaded_video is not None:
        video_size = uploaded_video.size
        if video_size > MAX_FILE_SIZE_BYTES:
            st.error(
                f"❌ File size exceeds the maximum limit of {MAX_FILE_SIZE_MB}MB. "
                f"Your file is {_format_size(video_size)}. Please upload a smaller video."
            )
            st.stop()

        st.video(uploaded_video)
        st.caption(f"Original size: {_format_size(float(video_size))}")

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            crf = st.slider("CRF (quality)", min_value=0, max_value=63, value=32)
            speed = st.slider("Speed (0=best, 6=fastest)", min_value=0, max_value=6, value=4)
        with col_b:
            audio_bitrate = st.slider("Audio bitrate (kbps)", min_value=32, max_value=320, value=128)
            fps_limit = st.number_input("Optional FPS limit (0 = keep source)", min_value=0.0, max_value=240.0, value=0.0, step=1.0)
        with col_c:
            reverse_output = st.checkbox(
                "Reverse video/audio",
                value=False,
                help="Applies ffmpeg reverse filters (video reverse + audio areverse when audio exists).",
            )
            resize_enabled = st.checkbox("Resize output")
            width = st.number_input("Width", min_value=16, max_value=7680, value=1280, step=2, disabled=not resize_enabled)
            height = st.number_input("Height", min_value=16, max_value=4320, value=720, step=2, disabled=not resize_enabled)

        timeout_seconds = st.slider("Timeout (seconds)", min_value=60, max_value=3600, value=1800)

        if st.button("Convert Video to WebM 🎬", key="convert_video_btn", disabled=not ffmpeg_available):
            progress_bar = st.progress(0)
            status_text = st.empty()
            try:
                status_text.text("📖 Reading video bytes...")
                progress_bar.progress(10)
                video_bytes = uploaded_video.getvalue()
                status_text.text("🔄 Running ffmpeg conversion...")
                progress_bar.progress(40)
                webm_bytes = convert_video_to_webm(
                    video_bytes=video_bytes,
                    input_filename=uploaded_video.name or "input.mp4",
                    crf=crf,
                    speed=speed,
                    audio_bitrate_kbps=audio_bitrate,
                    width=int(width) if resize_enabled else None,
                    height=int(height) if resize_enabled else None,
                    fps=float(fps_limit) if fps_limit > 0 else None,
                    reverse_output=reverse_output,
                    timeout_seconds=timeout_seconds,
                )
                progress_bar.progress(90)
                output_size = len(webm_bytes)
                size_delta_pct = ((output_size - video_size) / video_size) * 100 if video_size > 0 else 0.0
                progress_bar.progress(100)
                status_text.text("✅ Video conversion complete!")
                time.sleep(0.3)
                progress_bar.empty()
                status_text.empty()
                st.success("✅ Video conversion successful!")
                st.video(webm_bytes)
                st.metric("Converted size", _format_size(float(output_size)), delta=f"{size_delta_pct:+.2f}%")
                st.download_button(
                    "📥 Download WebM",
                    data=webm_bytes,
                    file_name="video.webm",
                    mime="video/webm",
                    use_container_width=True,
                )
            except Exception as e:
                progress_bar.empty()
                status_text.empty()
                st.error(f"❌ Video conversion failed: {e}")
                st.exception(e)

# Footer with information
st.markdown("---")
st.markdown("""
### Supported Formats
- **Image Input:** PNG, JPEG, JFIF, BMP, WebP, AVIF, SVG
- **Image Output:** AVIF, WebP, PNG, JPEG, JFIF, BMP
- **Video Input:** MP4, MOV, MKV, AVI, WEBM, M4V
- **Video Output:** WEBM (VP9 video + Opus audio)

### Features
- Image and video conversion in separate dedicated tabs
- Direct integration with libwebp C API for WebP image encoding/decoding
- AVIF image output via Pillow/pillow-avif-plugin
- Video-to-WebM conversion via managed ffmpeg (`imageio-ffmpeg`)
- Optional reverse video conversion (`reverse` + `areverse` when audio exists)
- Advanced image optimization with MozJPEG, OxiPNG, and OptiPNG when available
""")
